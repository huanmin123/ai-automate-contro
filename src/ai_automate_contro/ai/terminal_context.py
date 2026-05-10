from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.types import Interrupt
from typing_extensions import NotRequired

from ai_automate_contro.plans.packages import resolve_plan_path


SYSTEM_PROMPT = """你是 keygen automation 的 plan 级 AI 终端。

你的职责：
- 帮用户创建、理解、校验、运行、调试、修复和总结 plan 包。
- 通过工具读取 plan、运行 plan、查看日志、查看产物、创建 debug workspace、注入调试步骤、生成 patch。
- 分析失败时优先调用 analyze_latest_run_failure 汇总证据，再决定是否创建 debug workspace。
- 需要修改 plan 时，只能先写入 debug workspace 的 injected-plan/，再生成 patch。
- 修改 JSON plan/config 时优先使用 patch_debug_workspace_json 做最小路径修改，避免整文件重写造成补丁噪声。
- 原始 plan 的修改必须先生成 patch，并获得用户明确批准后才能调用 apply_debug_patch_after_approval。

边界：
- 不要把自己当作 plan action 写入 steps。
- 不要绕过验证码、二次验证、登录安全策略或人工确认。
- 不要把运行产物写到 output/ 之外。
- 不要让主 plan.json 引用另一个主 plan.json。
- 用户需要登录、输入账号密码、验证码或人工确认时，提前说明要用户做什么，并使用 manual_confirm/debug 注入流程。
- 不要直接修改原始 plan；write_debug_workspace_file 只能用于 injected-plan、notes 或 report。

项目约定：
- plan.json 是最小执行单元。
- test-plans/ 下面直接放分类和 plan 包。
- 每个 plan 包结构为 plan.json、config.json、sub-plans/、resources/、output/、docs/。
- 输出动作路径是相对于当前 plan 包 output/ 的路径，不能以 output/ 开头。

工具使用：
- 需要读取、校验、运行、调试、修复或生成补丁时，直接使用系统提供的原生工具调用。
- 不要输出伪造的 JSON 工具调用对象，也不要把工具调用写成普通文本让用户手动执行。
- 工具失败时，读取工具返回的错误并给出下一步，而不是绕过工具边界。
- 应用补丁前必须让用户明确批准；没有明确批准时不要调用 apply_debug_patch_after_approval。

回答要求：
- 简洁、具体、可执行。
- 先说明结论和关键证据，再给下一步。
- 不要复述大段工具输出；只总结和任务有关的信息。
"""


class AITerminalState(AgentState):
    current_plan_path: NotRequired[str]
    current_debug_workspace: NotRequired[str]
    latest_output_dir: NotRequired[str]


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


@wrap_model_call(state_schema=AITerminalState, name="AITerminalContextMiddleware")
def inject_ai_terminal_context(
    request: ModelRequest[Any],
    handler: Any,
) -> ModelResponse[Any]:
    context_text = format_ai_terminal_context(request.state)
    if not context_text:
        return handler(request)
    base_content = request.system_message.content if request.system_message is not None else ""
    if isinstance(base_content, list):
        base_content = "\n".join(str(item) for item in base_content)
    system_message = SystemMessage(content=f"{base_content}\n\n{context_text}".strip())
    return handler(request.override(system_message=system_message))


def format_ai_terminal_context(state: dict[str, Any]) -> str:
    lines = ["当前 AI 终端上下文："]
    added = False
    current_plan_path = state.get("current_plan_path")
    if isinstance(current_plan_path, str) and current_plan_path:
        lines.append(f"- current_plan_path: {current_plan_path}")
        added = True
    current_debug_workspace = state.get("current_debug_workspace")
    if isinstance(current_debug_workspace, str) and current_debug_workspace:
        lines.append(f"- current_debug_workspace: {current_debug_workspace}")
        added = True
    latest_output_dir = state.get("latest_output_dir")
    if isinstance(latest_output_dir, str) and latest_output_dir:
        lines.append(f"- latest_output_dir: {latest_output_dir}")
        added = True
    if not added:
        return ""
    lines.append("如果用户没有指定路径，优先使用这些上下文；如果上下文不足，再询问或调用工具确认。")
    return "\n".join(lines)


def context_update_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str]:
    update: dict[str, str] = {}
    for key in ("plan_path", "output_dir", "workspace"):
        _capture_context_value(update, key, arguments.get(key))
        _capture_context_value(update, key, result.get(key))

    summary = result.get("summary")
    if isinstance(summary, dict):
        _capture_context_value(update, "plan_path", summary.get("path"))
        _capture_context_value(update, "output_dir", summary.get("latest_output"))

    plan = result.get("plan")
    if isinstance(plan, dict):
        _capture_context_value(update, "plan_path", plan.get("path"))

    workspace = result.get("workspace")
    if isinstance(workspace, dict):
        _capture_context_value(update, "workspace", workspace.get("root"))
        _capture_context_value(update, "plan_path", workspace.get("plan_path"))
    elif isinstance(workspace, str):
        _capture_context_value(update, "workspace", workspace)

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        _capture_context_value(update, "output_dir", nested_result.get("output_dir"))
        _capture_context_value(update, "workspace", nested_result.get("workspace"))

    latest_state = result.get("latest_state")
    if isinstance(latest_state, dict):
        _capture_context_value(update, "output_dir", latest_state.get("output_dir"))

    manifest = result.get("manifest")
    if isinstance(manifest, dict):
        _capture_context_value(update, "workspace", manifest.get("root"))
        _capture_context_value(update, "plan_path", manifest.get("plan_path"))

    if tool_name in {"read_plan_package", "validate_plan", "run_plan"}:
        _capture_context_value(update, "plan_path", arguments.get("plan_path"))
    if tool_name in {
        "read_debug_workspace",
        "inject_debug_steps",
        "patch_debug_workspace_json",
        "propose_debug_fix",
        "validate_debug_plan",
        "run_debug_plan",
        "generate_debug_patch",
        "apply_debug_patch_after_approval",
    }:
        _capture_context_value(update, "workspace", arguments.get("workspace"))
    return update


def format_patch_approval_request(tool_call: dict[str, Any], *_: Any) -> str:
    args = tool_call.get("args", {})
    workspace = args.get("workspace", "<unknown>")
    return (
        "即将把 debug workspace 里的 patch 应用回原始 plan 包。\n"
        "请先确认 patch.diff 已检查过，且这次修改只包含你要应用的最小修复。\n"
        f"workspace: {workspace}"
    )


def extract_interrupts(value: Any) -> tuple[Interrupt, ...]:
    if isinstance(value, dict):
        raw_interrupts = value.get("__interrupt__") or ()
        if isinstance(raw_interrupts, tuple):
            return raw_interrupts
        if isinstance(raw_interrupts, list):
            return tuple(raw_interrupts)
    interrupts = getattr(value, "interrupts", None)
    if isinstance(interrupts, tuple):
        return interrupts
    if isinstance(interrupts, list):
        return tuple(interrupts)
    return ()


def interrupt_action_requests(interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", None)
        if not isinstance(value, dict):
            continue
        action_requests = value.get("action_requests")
        if not isinstance(action_requests, list):
            continue
        for request in action_requests:
            if isinstance(request, dict):
                requests.append(request)
    return requests


def approval_decision_for_request(request: dict[str, Any]) -> dict[str, Any]:
    action_name = str(request.get("name", ""))
    args = request.get("args", {})
    if not isinstance(args, dict):
        args = {}
    edited_args = dict(args)
    if action_name == "apply_debug_patch_after_approval":
        edited_args["approved"] = True
        return {
            "type": "edit",
            "edited_action": {
                "name": action_name,
                "args": edited_args,
            },
        }
    return {"type": "approve"}


def latest_human_message_approved(messages: list[BaseMessage]) -> bool:
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        normalized = message_content_to_text(message.content).lower()
        return text_has_approval(normalized)
    return False


def text_has_approval(text: str) -> bool:
    approval_tokens = ("同意", "确认", "批准", "可以应用", "应用补丁", "yes", "approve", "approved", "--yes")
    normalized = text.lower()
    return any(token in normalized for token in approval_tokens)


def text_has_rejection(text: str) -> bool:
    rejection_tokens = ("拒绝", "不同意", "不要应用", "不应用", "取消", "reject", "deny", "no")
    normalized = text.lower()
    return any(token in normalized for token in rejection_tokens)


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                if item.get("text"):
                    chunks.append(str(item["text"]))
                elif item.get("content"):
                    chunks.append(str(item["content"]))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content)


def _capture_context_value(update: dict[str, str], key: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if key == "plan_path":
        update["current_plan_path"] = str(resolve_plan_path(value))
        return
    if key == "workspace":
        update["current_debug_workspace"] = str(Path(value).resolve())
        return
    if key == "output_dir":
        update["latest_output_dir"] = str(Path(value).resolve())
