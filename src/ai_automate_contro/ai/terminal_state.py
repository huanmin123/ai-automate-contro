from __future__ import annotations

import json
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

    def _after_tool_call(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        update = context_update_from_tool_result(tool_name, arguments, result)
        if update:
            self._update_context_state(update)
            self._sync_current_session_index()

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
        if not requests:
            self.poutput("[等待审批] AI 正在等待人工输入。")
            self.poutput("输入 approve 继续，或输入 reject <原因> 停止本次工具调用。")
            return
        self.poutput("[等待审批] AI 请求执行受保护工具。")
        for index, request in enumerate(requests, start=1):
            name = request.get("name", "<未知>")
            args = request.get("args", {})
            description = request.get("description", "")
            self.poutput(f"{index}. 工具：{name}")
            if description:
                self.poutput(str(description))
            self.poutput(json.dumps(args, ensure_ascii=False, indent=2))
        self.poutput("输入 approve 批准执行，或输入 reject <原因> 拒绝并继续会话。")

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
