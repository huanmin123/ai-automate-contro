from __future__ import annotations

import json
import os
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cmd2

warnings.filterwarnings("ignore", message=r"The default value of `allowed_objects`.*")
warnings.filterwarnings("ignore", message=r".*allowed_objects.*")
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.agents.middleware import wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, Interrupt
from typing_extensions import NotRequired

from keygen_automation.ai import service_config_for_artifact
from keygen_automation.ai_terminal_langgraph import build_langchain_tools
from keygen_automation.ai_terminal_tools import describe_ai_terminal_tool, list_ai_terminal_tools
from keygen_automation.config import load_plan_config
from keygen_automation.plan_packages import find_latest_run_output, resolve_plan_path


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


@dataclass
class AITerminalConfig:
    service_name: str
    service_config: dict[str, Any]


class AITerminalState(AgentState):
    current_plan_path: NotRequired[str]
    current_debug_workspace: NotRequired[str]
    latest_output_dir: NotRequired[str]


class AITerminal(cmd2.Cmd):
    intro = "Keygen Automation AI Terminal. Type help or ? to list commands."

    def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
        super().__init__(allow_cli_args=False)
        self.project_root = project_root.resolve()
        self.config = load_ai_terminal_config(self.project_root, service_name=service)
        self.model_name = str(self.config.service_config["model"])
        self.thread_id = thread_id
        self._current_turn_text: str | None = None
        self._approval_resume_active = False
        self.checkpoint_path = self.project_root / ".keygen" / "ai-terminal-checkpoints.sqlite"
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_connection = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.tools = build_langchain_tools(
            self.project_root,
            latest_user_approved=self._latest_user_approved,
            after_tool_call=self._after_tool_call,
        )
        self.model = _build_chat_model(self.config.service_config)
        self.graph = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=_build_system_prompt(),
            state_schema=AITerminalState,
            middleware=[
                _inject_ai_terminal_context,
                HumanInTheLoopMiddleware(
                    interrupt_on={
                        "apply_debug_patch_after_approval": {
                            "allowed_decisions": ["approve", "edit", "reject"],
                            "description": _format_patch_approval_request,
                        }
                    }
                )
            ],
            checkpointer=self.checkpointer,
        )
        self.prompt = "ai> "

    def default(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        if self._current_interrupts():
            if _text_has_approval(text):
                self.do_approve("")
                return
            if _text_has_rejection(text):
                self.do_reject(text)
                return
            self.perror("pending approval; use approve or reject <reason> before sending a new request")
            return
        self._run_agent_turn(text)

    def do_context(self, _: str) -> None:
        """Show current AI terminal context."""
        service_config = service_config_for_artifact(self.config.service_config)
        messages = self._current_messages()
        self.poutput(
            json.dumps(
                {
                    "project_root": str(self.project_root),
                    "service": self.config.service_name,
                    "service_config": service_config,
                    "model": self.model_name,
                    "agent": "langchain.agents.create_agent",
                    "checkpointer": "langgraph.checkpoint.sqlite.SqliteSaver",
                    "checkpoint_path": str(self.checkpoint_path),
                    "thread_id": self.thread_id,
                    "native_tools": len(self.tools),
                    "messages": len(messages),
                    "checkpoints": self._checkpoint_count(),
                    "state": self._context_state(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def do_tools(self, arg: str) -> None:
        """List tools available to the AI terminal, or show one schema: tools [name]"""
        tool_name = arg.strip()
        if tool_name:
            try:
                payload = describe_ai_terminal_tool(tool_name)
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        payload = list_ai_terminal_tools()
        payload["native_langchain_tools"] = [
            {
                "name": tool.name,
                "description": tool.description,
                "args": list(tool.args),
            }
            for tool in self.tools
        ]
        self.poutput(json.dumps(payload, ensure_ascii=False, indent=2))

    def do_reset(self, _: str) -> None:
        """Delete the current AI terminal thread checkpoint."""
        self.checkpointer.delete_thread(self.thread_id)
        self.poutput(f"AI terminal thread reset: {self.thread_id}")

    def do_use(self, arg: str) -> None:
        """Set or show current plan context: use [plan.json-or-package-dir]"""
        raw_path = arg.strip()
        if not raw_path:
            plan_path = self._context_state().get("current_plan_path") or "<none>"
            self.poutput(f"current plan: {plan_path}")
            return
        try:
            plan_path = resolve_plan_path(raw_path)
            latest_output = find_latest_run_output(plan_path.parent)
        except Exception as error:
            self.perror(str(error))
            return
        update: dict[str, Any] = {"current_plan_path": str(plan_path)}
        if latest_output is not None:
            update["latest_output_dir"] = str(latest_output)
        self._update_context_state(update)
        self.poutput(f"current plan: {plan_path}")
        if latest_output is not None:
            self.poutput(f"latest output: {latest_output}")

    def do_workspace(self, arg: str) -> None:
        """Set or show current debug workspace: workspace [output/debug/<run>]"""
        raw_path = arg.strip()
        if not raw_path:
            workspace = self._context_state().get("current_debug_workspace") or "<none>"
            self.poutput(f"current debug workspace: {workspace}")
            return
        workspace = Path(raw_path).resolve()
        if not workspace.exists():
            self.perror(f"debug workspace does not exist: {workspace}")
            return
        self._update_context_state({"current_debug_workspace": str(workspace)})
        self.poutput(f"current debug workspace: {workspace}")

    def do_run_context(self, arg: str) -> None:
        """Set or show latest run output context: run_context [output-dir]"""
        raw_path = arg.strip()
        if not raw_path:
            output_dir = self._context_state().get("latest_output_dir") or "<none>"
            self.poutput(f"latest output: {output_dir}")
            return
        output_dir = Path(raw_path).resolve()
        if not output_dir.exists():
            self.perror(f"run output does not exist: {output_dir}")
            return
        self._update_context_state({"latest_output_dir": str(output_dir)})
        self.poutput(f"latest output: {output_dir}")

    def do_ask(self, arg: str) -> None:
        """Send one user message to the AI terminal: ask <message>"""
        self.default(arg)

    def do_thread(self, arg: str) -> None:
        """Show or switch thread: thread [thread-id]"""
        next_thread_id = arg.strip()
        if not next_thread_id:
            self.poutput(self.thread_id)
            return
        self.thread_id = next_thread_id
        self.poutput(f"AI terminal thread: {self.thread_id}")

    def do_history(self, arg: str) -> None:
        """Show recent conversation messages: history [limit]"""
        try:
            limit = int(arg.strip()) if arg.strip() else 12
        except ValueError:
            self.perror("usage: history [limit]")
            return
        if limit <= 0:
            self.perror("limit must be greater than 0")
            return
        messages = self._current_messages()[-limit:]
        if not messages:
            self.poutput("history: <empty>")
            return
        for index, message in enumerate(messages, start=1):
            role = type(message).__name__
            content = _message_content_to_text(message.content).strip()
            if isinstance(message, AIMessage) and message.tool_calls:
                calls = ", ".join(str(call.get("name")) for call in message.tool_calls)
                content = f"tool_calls={calls}"
            if len(content) > 500:
                content = content[:497] + "..."
            self.poutput(f"{index:02d}. {role}: {content}")

    def _run_agent_turn(self, text: str) -> None:
        self._current_turn_text = text
        try:
            final_state = self.graph.invoke(
                {"messages": [HumanMessage(content=text)]},
                config=self._graph_config(),
            )
        except Exception as error:
            self.perror(str(error))
            return
        finally:
            self._current_turn_text = None
        if self._print_pending_interrupt(final_state):
            return
        messages = list(final_state["messages"])
        last_message = self._last_assistant_message(messages)
        if last_message:
            self.poutput(last_message)

    def _last_assistant_message(self, messages: list[BaseMessage]) -> str:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            if message.tool_calls:
                continue
            content = _message_content_to_text(message.content).strip()
            if content:
                return content
        return ""

    def _latest_user_approved(self) -> bool:
        return self._approval_resume_active

    def do_pending(self, _: str) -> None:
        """Show pending human approval requests."""
        interrupts = self._current_interrupts()
        if not interrupts:
            self.poutput("pending: <none>")
            return
        self._print_interrupts(interrupts)

    def do_approve(self, _: str) -> None:
        """Approve pending patch application and resume the AI terminal graph."""
        interrupts = self._current_interrupts()
        if not interrupts:
            self.perror("no pending approval")
            return
        decisions = [_approval_decision_for_request(request) for request in _interrupt_action_requests(interrupts)]
        self._approval_resume_active = True
        try:
            self._resume_agent({"decisions": decisions})
        finally:
            self._approval_resume_active = False

    def do_reject(self, arg: str) -> None:
        """Reject pending patch application and resume the AI terminal graph: reject [reason]"""
        interrupts = self._current_interrupts()
        if not interrupts:
            self.perror("no pending approval")
            return
        message = arg.strip() or "用户拒绝应用补丁。"
        decisions = [{"type": "reject", "message": message} for _ in _interrupt_action_requests(interrupts)]
        self._resume_agent({"decisions": decisions})

    def _resume_agent(self, resume_payload: dict[str, Any]) -> None:
        try:
            final_state = self.graph.invoke(
                Command(resume=resume_payload),
                config=self._graph_config(),
            )
        except Exception as error:
            self.perror(str(error))
            return
        if self._print_pending_interrupt(final_state):
            return
        messages = list(final_state["messages"])
        last_message = self._last_assistant_message(messages)
        if last_message:
            self.poutput(last_message)

    def _graph_config(self) -> dict[str, Any]:
        return {
            "recursion_limit": 32,
            "configurable": {
                "thread_id": self.thread_id,
            },
        }

    def _current_messages(self) -> list[BaseMessage]:
        state = self.graph.get_state(self._graph_config())
        messages = state.values.get("messages", [])
        if isinstance(messages, list):
            return messages
        return []

    def _context_state(self) -> dict[str, str]:
        values = self.graph.get_state(self._graph_config()).values
        result: dict[str, str] = {}
        for key in ("current_plan_path", "current_debug_workspace", "latest_output_dir"):
            value = values.get(key)
            if isinstance(value, str) and value:
                result[key] = value
        return result

    def _update_context_state(self, update: dict[str, Any]) -> None:
        self.graph.update_state(self._graph_config(), update)

    def _after_tool_call(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        update = _context_update_from_tool_result(tool_name, arguments, result)
        if update:
            self._update_context_state(update)

    def _current_interrupts(self) -> tuple[Interrupt, ...]:
        return self.graph.get_state(self._graph_config()).interrupts

    def _print_pending_interrupt(self, final_state: Any) -> bool:
        interrupts = _extract_interrupts(final_state) or self._current_interrupts()
        if not interrupts:
            return False
        self._print_interrupts(interrupts)
        return True

    def _print_interrupts(self, interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> None:
        requests = _interrupt_action_requests(interrupts)
        if not requests:
            self.poutput("[WAIT_APPROVAL] pending human input.")
            self.poutput("Use 'approve' to continue or 'reject <reason>' to stop the tool call.")
            return
        self.poutput("[WAIT_APPROVAL] The AI requested a protected tool call.")
        for index, request in enumerate(requests, start=1):
            name = request.get("name", "<unknown>")
            args = request.get("args", {})
            description = request.get("description", "")
            self.poutput(f"{index}. tool: {name}")
            if description:
                self.poutput(str(description))
            self.poutput(json.dumps(args, ensure_ascii=False, indent=2))
        self.poutput("Use 'approve' to apply, or 'reject <reason>' to deny and resume.")

    def _checkpoint_count(self) -> int:
        return sum(1 for _ in self.checkpointer.list({"configurable": {"thread_id": self.thread_id}}))

    def do_exit(self, arg: str) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        self.last_result = True
        return True

    def do_quit(self, arg: Any) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        return super().do_quit(arg)

    def _close_checkpoint_connection(self) -> None:
        connection = getattr(self, "_checkpoint_connection", None)
        if connection is None:
            return
        connection.close()
        self._checkpoint_connection = None


def load_ai_terminal_config(project_root: Path, *, service_name: str = "default") -> AITerminalConfig:
    plan_config = load_plan_config(project_root, project_root / "test-plans")
    ai_services = plan_config.get("ai_services", {})
    if not isinstance(ai_services, dict):
        raise ValueError("config.ai_services must be a JSON object.")
    service_config = ai_services.get(service_name)
    if not isinstance(service_config, dict):
        raise KeyError(f"AI terminal service is not configured: {service_name}")
    if not service_config.get("model"):
        raise ValueError(f"AI terminal service '{service_name}' requires model.")
    _resolve_ai_terminal_api_key(service_name, service_config)
    return AITerminalConfig(service_name=service_name, service_config=service_config)


def _build_chat_model(service_config: dict[str, Any]) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "model": str(service_config["model"]),
        "api_key": _resolve_ai_terminal_api_key("default", service_config),
        "timeout": float(service_config.get("timeout_seconds", 90)),
        "temperature": float(service_config.get("temperature", 0.2)),
    }
    if service_config.get("base_url"):
        kwargs["base_url"] = str(service_config["base_url"])
    if service_config.get("max_retries") is not None:
        kwargs["max_retries"] = int(service_config["max_retries"])
    return ChatOpenAI(**kwargs)


def _resolve_ai_terminal_api_key(service_name: str, service_config: dict[str, Any]) -> str:
    if service_config.get("api_key"):
        return str(service_config["api_key"])
    api_key_env = service_config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            return api_key
    raise ValueError(f"AI terminal service '{service_name}' requires api_key or api_key_env.")


def _build_system_prompt() -> str:
    return SYSTEM_PROMPT


@wrap_model_call(state_schema=AITerminalState, name="AITerminalContextMiddleware")
def _inject_ai_terminal_context(
    request: ModelRequest[Any],
    handler: Any,
) -> ModelResponse[Any]:
    context_text = _format_ai_terminal_context(request.state)
    if not context_text:
        return handler(request)
    base_content = request.system_message.content if request.system_message is not None else ""
    if isinstance(base_content, list):
        base_content = "\n".join(str(item) for item in base_content)
    system_message = SystemMessage(content=f"{base_content}\n\n{context_text}".strip())
    return handler(request.override(system_message=system_message))


def _format_ai_terminal_context(state: dict[str, Any]) -> str:
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


def _context_update_from_tool_result(
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


def _format_patch_approval_request(tool_call: dict[str, Any], *_: Any) -> str:
    args = tool_call.get("args", {})
    workspace = args.get("workspace", "<unknown>")
    return (
        "即将把 debug workspace 里的 patch 应用回原始 plan 包。\n"
        "请先确认 patch.diff 已检查过，且这次修改只包含你要应用的最小修复。\n"
        f"workspace: {workspace}"
    )


def _extract_interrupts(value: Any) -> tuple[Interrupt, ...]:
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


def _interrupt_action_requests(interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> list[dict[str, Any]]:
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


def _approval_decision_for_request(request: dict[str, Any]) -> dict[str, Any]:
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


def _latest_human_message_approved(messages: list[BaseMessage]) -> bool:
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        normalized = _message_content_to_text(message.content).lower()
        return _text_has_approval(normalized)
    return False


def _text_has_approval(text: str) -> bool:
    approval_tokens = ("同意", "确认", "批准", "可以应用", "应用补丁", "yes", "approve", "approved", "--yes")
    normalized = text.lower()
    return any(token in normalized for token in approval_tokens)


def _text_has_rejection(text: str) -> bool:
    rejection_tokens = ("拒绝", "不同意", "不要应用", "不应用", "取消", "reject", "deny", "no")
    normalized = text.lower()
    return any(token in normalized for token in rejection_tokens)


def _message_content_to_text(content: Any) -> str:
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
