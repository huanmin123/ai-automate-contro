from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from typing_extensions import NotRequired

from ai_automate_contro.plans.packages import resolve_plan_path
from ai_automate_contro.support.paths import path_from_text
from ai_automate_contro.ai.work_plan import (
    format_work_plan_for_context,
    normalize_work_plan_items,
    normalize_work_plan_summary,
)


class AITerminalState(AgentState):
    current_plan_path: NotRequired[str]
    current_debug_workspace: NotRequired[str]
    latest_output_dir: NotRequired[str]
    latest_compression_archive_dir: NotRequired[str]
    latest_compression_messages_path: NotRequired[str]
    latest_compression_summary_path: NotRequired[str]
    latest_compression_token_count: NotRequired[str]
    latest_compression_message_count: NotRequired[str]
    latest_plan_quality_review_plan_path: NotRequired[str]
    latest_plan_quality_review_signature: NotRequired[str]
    latest_plan_quality_review_ok: NotRequired[str]
    latest_plan_quality_review_severity: NotRequired[str]
    latest_plan_quality_review_next_action: NotRequired[str]
    work_plan_items: NotRequired[list[dict[str, str]]]
    work_plan_summary: NotRequired[str]


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


def build_ai_terminal_context_middleware(
    context_state_provider: Callable[[], dict[str, Any]],
) -> Any:
    @wrap_model_call(state_schema=AITerminalState, name="AITerminalContextMiddleware")
    def _inject_runtime_ai_terminal_context(
        request: ModelRequest[Any],
        handler: Any,
    ) -> ModelResponse[Any]:
        state = dict(request.state)
        try:
            state.update(context_state_provider())
        except Exception:
            pass
        context_text = format_ai_terminal_context(state)
        if not context_text:
            return handler(request)
        base_content = request.system_message.content if request.system_message is not None else ""
        if isinstance(base_content, list):
            base_content = "\n".join(str(item) for item in base_content)
        system_message = SystemMessage(content=f"{base_content}\n\n{context_text}".strip())
        return handler(request.override(system_message=system_message))

    return _inject_runtime_ai_terminal_context


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
    latest_compression_summary_path = state.get("latest_compression_summary_path")
    latest_compression_messages_path = state.get("latest_compression_messages_path")
    latest_compression_archive_dir = state.get("latest_compression_archive_dir")
    if isinstance(latest_compression_summary_path, str) and latest_compression_summary_path:
        lines.append(f"- latest_compression_summary_path: {latest_compression_summary_path}")
        added = True
    if isinstance(latest_compression_messages_path, str) and latest_compression_messages_path:
        lines.append(f"- latest_compression_messages_path: {latest_compression_messages_path}")
        added = True
    if isinstance(latest_compression_archive_dir, str) and latest_compression_archive_dir:
        lines.append(f"- latest_compression_archive_dir: {latest_compression_archive_dir}")
        added = True
    quality_review_plan_path = state.get("latest_plan_quality_review_plan_path")
    quality_review_ok = state.get("latest_plan_quality_review_ok")
    quality_review_severity = state.get("latest_plan_quality_review_severity")
    quality_review_next_action = state.get("latest_plan_quality_review_next_action")
    quality_review_signature = state.get("latest_plan_quality_review_signature")
    if isinstance(quality_review_plan_path, str) and quality_review_plan_path:
        lines.append(f"- latest_plan_quality_review_plan_path: {quality_review_plan_path}")
        added = True
    if isinstance(quality_review_ok, str) and quality_review_ok:
        lines.append(f"- latest_plan_quality_review_ok: {quality_review_ok}")
        added = True
    if isinstance(quality_review_severity, str) and quality_review_severity:
        lines.append(f"- latest_plan_quality_review_severity: {quality_review_severity}")
        added = True
    if isinstance(quality_review_next_action, str) and quality_review_next_action:
        lines.append(f"- latest_plan_quality_review_next_action: {quality_review_next_action}")
        added = True
    if isinstance(quality_review_signature, str) and quality_review_signature:
        lines.append("- latest_plan_quality_review_signature: <recorded>")
        added = True
    if not added:
        plan_context = format_work_plan_for_context(
            state.get("work_plan_items"),
            summary=state.get("work_plan_summary", ""),
        )
        if not plan_context:
            return ""
        return plan_context
    plan_context = format_work_plan_for_context(
        state.get("work_plan_items"),
        summary=state.get("work_plan_summary", ""),
    )
    if plan_context:
        lines.extend(["", plan_context])
    lines.append("如果用户没有指定路径，优先使用这些上下文；如果上下文不足，再询问或调用工具确认。需要历史细节时，先读取压缩摘要，再按需读取归档消息文件的相关行段。")
    return "\n".join(lines)


def context_update_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str]:
    update: dict[str, str] = {}
    if tool_name == "update_work_plan":
        return {}
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
    if tool_name == "review_plan_quality":
        _capture_context_value(update, "plan_path", result.get("plan_path"))
        _capture_context_value(update, "plan_path", arguments.get("plan_path"))
        _capture_context_value(update, "latest_plan_quality_review_plan_path", result.get("plan_path"))
        _capture_context_value(update, "latest_plan_quality_review_signature", result.get("plan_signature"))
        _capture_context_value(update, "latest_plan_quality_review_severity", result.get("severity"))
        _capture_context_value(update, "latest_plan_quality_review_next_action", result.get("next_action"))
        if "ok" in result:
            update["latest_plan_quality_review_ok"] = "true" if bool(result.get("ok")) else "false"
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


def work_plan_update_from_tool_result(
    tool_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if tool_name != "update_work_plan" or not isinstance(result, dict) or result.get("ok") is False:
        return {}
    return {
        "work_plan_items": normalize_work_plan_items(result.get("items")),
        "work_plan_summary": normalize_work_plan_summary(result.get("summary", "")),
    }


def _capture_context_value(update: dict[str, str], key: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if key == "plan_path":
        update["current_plan_path"] = str(resolve_plan_path(value))
        return
    if key == "workspace":
        update["current_debug_workspace"] = str(path_from_text(value).resolve())
        return
    if key == "output_dir":
        update["latest_output_dir"] = str(path_from_text(value).resolve())
        return
    if key.startswith("latest_plan_quality_review_"):
        update[key] = str(value)
