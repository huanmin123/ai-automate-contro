from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.types import Interrupt

from ai_automate_contro.ai.session_compression import (
    MANUAL_COMPRESS_KEEP_MESSAGES,
    archive_messages,
    count_ai_terminal_tokens,
)
from ai_automate_contro.ai.session_store import update_ai_terminal_session_index
from ai_automate_contro.ai.terminal_context import context_update_from_tool_result
from ai_automate_contro.ai.terminal_events import AITerminalEvent
from ai_automate_contro.ai.terminal_message_utils import (
    extract_interrupts,
    interrupt_action_requests,
    message_content_to_text,
)


class AITerminalStateMixin:
    def _last_assistant_message(self, messages: list[BaseMessage]) -> str:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            if message.tool_calls:
                continue
            content = message_content_to_text(message.content).strip()
            if content:
                return content
        return ""

    def _latest_user_approved(self) -> bool:
        return self._approval_resume_active

    def _graph_config(self) -> dict[str, Any]:
        return {
            "recursion_limit": self.graph_recursion_limit,
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
        for key in (
            "current_plan_path",
            "current_debug_workspace",
            "latest_output_dir",
            "latest_compression_archive_dir",
            "latest_compression_messages_path",
            "latest_compression_summary_path",
            "latest_compression_token_count",
            "latest_compression_message_count",
        ):
            value = values.get(key)
            if isinstance(value, str) and value:
                result[key] = value
        return result

    def _update_context_state(self, update: dict[str, Any]) -> None:
        self.graph.update_state(self._graph_config(), update)

    def _before_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self._print_tool_progress("start", tool_name, arguments)

    def _after_tool_call(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        self._print_tool_progress("done", tool_name, arguments, result)
        update = context_update_from_tool_result(tool_name, arguments, result)
        if update:
            self._update_context_state(update)
            self._sync_current_session_index()

    def _print_tool_progress(
        self,
        phase: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> None:
        if phase == "start":
            detail = _tool_argument_summary(tool_name, arguments)
            if self._emit_event(AITerminalEvent("tool_started", title=tool_name, text=detail)):
                return
            self._emit_terminal_output(f"• 调用工具 {tool_name} {detail}".rstrip())
            return
        status = "完成" if not isinstance(result, dict) or result.get("ok", True) else "失败"
        detail = f"{status}{_tool_result_summary(tool_name, result or {})}"
        if self._emit_event(AITerminalEvent("tool_finished", title=tool_name, text=detail)):
            return
        self._emit_terminal_output(f"• 工具 {tool_name} {detail}")

    def _sync_current_session_index(self) -> None:
        update_ai_terminal_session_index(self.project_root, self.checkpointer, self.thread_id)

    def _current_interrupts(self) -> tuple[Interrupt, ...]:
        return self.graph.get_state(self._graph_config()).interrupts

    def _print_pending_interrupt(self, final_state: Any) -> bool:
        interrupts = extract_interrupts(final_state) or self._current_interrupts()
        if not interrupts:
            return False
        self._print_interrupts(interrupts)
        return True

    def _print_interrupts(self, interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> None:
        requests = interrupt_action_requests(interrupts)
        if getattr(self, "_client_event_sink", None) is not None:
            if not requests:
                self._emit_event(
                    AITerminalEvent(
                        "approval_requested",
                        text="AI 正在等待人工输入。\n输入 /approve 继续，或输入 /reject <原因> 停止本次工具调用。",
                    )
                )
                return
            chunks = ["AI 请求执行受保护工具。"]
            for index, request in enumerate(requests, start=1):
                name = request.get("name", "<未知>")
                args = request.get("args", {})
                description = request.get("description", "")
                chunks.append(f"{index}. 工具：{name}")
                if description:
                    chunks.append(str(description))
                chunks.append(json.dumps(args, ensure_ascii=False, indent=2))
            chunks.append("输入 /approve 批准执行，或输入 /reject <原因> 拒绝并继续会话。")
            self._emit_event(AITerminalEvent("approval_requested", text="\n".join(chunks)))
            return
        if not requests:
            self._emit_terminal_output("[等待审批] AI 正在等待人工输入。")
            self._emit_terminal_output("输入 approve 继续，或输入 reject <原因> 停止本次工具调用。")
            return
        self._emit_terminal_output("[等待审批] AI 请求执行受保护工具。")
        for index, request in enumerate(requests, start=1):
            name = request.get("name", "<未知>")
            args = request.get("args", {})
            description = request.get("description", "")
            self._emit_terminal_output(f"{index}. 工具：{name}")
            if description:
                self._emit_terminal_output(str(description))
            self._emit_terminal_output(json.dumps(args, ensure_ascii=False, indent=2))
        self._emit_terminal_output("输入 approve 批准执行，或输入 reject <原因> 拒绝并继续会话。")

    def _checkpoint_count(self) -> int:
        return sum(1 for _ in self.checkpointer.list({"configurable": {"thread_id": self.thread_id}}))

    def _compress_current_thread(self, *, reason: str = "manual") -> dict[str, Any]:
        messages = self._current_messages()
        token_count = count_ai_terminal_tokens(messages)
        if not messages:
            return {
                "ok": True,
                "compressed": False,
                "reason": "no messages in current thread",
                "thread_id": self.thread_id,
            }
        result = self.summary_middleware.compress_messages(
            messages,
            reason=reason,
            keep_messages=MANUAL_COMPRESS_KEEP_MESSAGES,
        )
        if result is None:
            summary = "Manual archive created, but the thread is too small to replace with a compressed summary."
            archive = archive_messages(
                self.project_root,
                self.thread_id,
                messages,
                summary=summary,
                reason=reason,
            )
            self._update_context_state(archive.state_update())
            self._sync_current_session_index()
            return {
                "ok": True,
                "compressed": False,
                "reason": "not enough messages to compress safely",
                "thread_id": self.thread_id,
                "message_count": len(messages),
                "token_count": token_count,
                "archive_dir": str(archive.archive_dir),
                "messages_path": str(archive.messages_path),
                "summary_path": str(archive.summary_path),
            }

        self.graph.update_state(self._graph_config(), result.state_update())
        self._sync_current_session_index()
        return {
            "ok": True,
            "compressed": True,
            "thread_id": self.thread_id,
            "message_count": len(messages),
            "token_count": token_count,
            "summarized_messages": len(result.messages_to_summarize),
            "preserved_messages": len(result.preserved_messages),
            "archive_dir": str(result.archive.archive_dir),
            "messages_path": str(result.archive.messages_path),
            "summary_path": str(result.archive.summary_path),
        }

    def _close_checkpoint_connection(self) -> None:
        connection = getattr(self, "_checkpoint_connection", None)
        if connection is None:
            return
        connection.close()
        self._checkpoint_connection = None


def _tool_argument_summary(tool_name: str, arguments: dict[str, Any]) -> str:
    if not arguments:
        return ""
    fields_by_tool = {
        "inspect_web_page": ("url", "headed"),
        "grep_project_text": ("pattern", "root_path", "file_glob"),
        "read_project_file_slice": ("path", "start_line", "line_count"),
        "read_plan_package": ("plan_path",),
        "create_plan_package": ("package_path", "name"),
        "write_plan_package_file": ("plan_path", "relative_path", "mode"),
        "validate_plan": ("plan_path",),
        "run_plan": ("plan_path", "run_name"),
        "read_latest_run_state": ("plan_path",),
        "read_latest_run_report": ("plan_path",),
        "analyze_latest_run_failure": ("plan_path", "output_dir"),
        "read_run_log": ("plan_path", "output_dir", "lines"),
        "read_run_events": ("plan_path", "output_dir", "lines"),
        "list_output_artifacts": ("plan_path", "filter_text", "limit"),
        "read_output_artifact": ("plan_path", "relative_path", "max_bytes"),
        "create_debug_workspace": ("plan_path", "name"),
        "list_debug_workspaces": ("plan_path",),
        "find_debug_workspace": ("plan_path", "name"),
        "read_debug_workspace": ("workspace",),
        "prepare_failure_debug_workspace": ("plan_path", "output_dir", "name"),
        "inject_debug_steps": ("workspace", "presets", "position", "step"),
        "write_debug_workspace_file": ("workspace", "root", "relative_path", "mode"),
        "patch_debug_workspace_json": ("workspace", "root", "relative_path"),
        "propose_debug_fix": ("workspace", "apply", "run_after_apply"),
        "validate_debug_plan": ("workspace",),
        "run_debug_plan": ("workspace", "run_name"),
        "generate_debug_patch": ("workspace",),
        "apply_debug_patch_after_approval": ("workspace",),
        "read_compression_archive": ("mode", "archive_path", "pattern"),
        "list_plan_packages": ("filter_text",),
    }
    fields = fields_by_tool.get(tool_name, tuple(arguments)[:3])
    parts = []
    for key in fields:
        if key not in arguments:
            continue
        value = arguments.get(key)
        if key.startswith("_") or callable(value):
            continue
        text = _compact_tool_value(value)
        if text:
            parts.append(f"{key}={text}")
    return "(" + ", ".join(parts) + ")" if parts else ""


def _tool_result_summary(tool_name: str, result: dict[str, Any]) -> str:
    if not result:
        return ""
    summary_parts: list[str] = []
    if tool_name == "inspect_web_page":
        page = result.get("page") if isinstance(result.get("page"), dict) else {}
        title = page.get("title") or ""
        final_url = page.get("final_url") or result.get("resolved_url") or ""
        auth = page.get("auth") if isinstance(page.get("auth"), dict) else {}
        signals = []
        if auth.get("login_fields_detected"):
            signals.append("登录字段")
        if auth.get("challenge_detected"):
            signals.append("验证信号")
        if title:
            summary_parts.append(f"title={_compact_tool_value(title)}")
        if final_url:
            summary_parts.append(f"url={_compact_tool_value(final_url)}")
        if signals:
            summary_parts.append("发现" + "/".join(signals))
    elif tool_name == "grep_project_text":
        summary_parts.append(f"matches={result.get('match_count', 0)}")
        if result.get("truncated"):
            summary_parts.append("已截断")
    elif tool_name == "read_project_file_slice":
        summary_parts.append(f"lines={result.get('line_count', 0)}")
        if result.get("relative_path"):
            summary_parts.append(f"path={_compact_tool_value(result.get('relative_path'))}")
    elif tool_name in {"run_plan", "run_debug_plan"}:
        status = result.get("status") or ("passed" if result.get("ok") else "failed")
        summary_parts.append(f"status={status}")
        if result.get("output_dir"):
            summary_parts.append(f"output={_compact_path(result.get('output_dir'))}")
        if result.get("error"):
            summary_parts.append(f"error={_compact_tool_value(result.get('error'), limit=120)}")
    elif tool_name in {"validate_plan", "validate_debug_plan"}:
        summary_parts.append("通过" if result.get("ok") else "未通过")
    elif tool_name == "list_plan_packages":
        plans = result.get("plans") if isinstance(result.get("plans"), list) else []
        summary_parts.append(f"plans={len(plans)}")
    elif tool_name == "list_output_artifacts":
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        summary_parts.append(f"artifacts={len(artifacts)}")
    elif tool_name in {"create_plan_package", "write_plan_package_file", "read_plan_package"}:
        if result.get("plan_path"):
            summary_parts.append(f"plan={_compact_path(result.get('plan_path'))}")
        elif isinstance(result.get("summary"), dict) and result["summary"].get("path"):
            summary_parts.append(f"plan={_compact_path(result['summary'].get('path'))}")
    elif "workspace" in result:
        summary_parts.append(f"workspace={_compact_path(result.get('workspace'))}")
    elif "path" in result:
        summary_parts.append(f"path={_compact_path(result.get('path'))}")
    elif "relative_path" in result:
        summary_parts.append(f"path={_compact_tool_value(result.get('relative_path'))}")
    elif result.get("error"):
        summary_parts.append(f"error={_compact_tool_value(result.get('error'), limit=120)}")
    if not summary_parts and "ok" in result:
        summary_parts.append("ok=true" if result.get("ok") else "ok=false")
    return "：" + "，".join(summary_parts) if summary_parts else ""


def _compact_tool_value(value: Any, *, limit: int = 80) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        text = "[" + ", ".join(_compact_tool_value(item, limit=24) for item in list(value)[:4]) + "]"
        if len(value) > 4:
            text += "..."
    elif isinstance(value, dict):
        text = "{...}"
    else:
        text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _compact_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        parts = path.parts
        if len(parts) >= 3:
            return str(Path(*parts[-3:]))
    except Exception:
        pass
    return _compact_tool_value(text)
