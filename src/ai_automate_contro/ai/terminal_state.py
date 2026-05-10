from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.types import Interrupt

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
        update = context_update_from_tool_result(tool_name, arguments, result)
        if update:
            self._update_context_state(update)

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

    def _close_checkpoint_connection(self) -> None:
        connection = getattr(self, "_checkpoint_connection", None)
        if connection is None:
            return
        connection.close()
        self._checkpoint_connection = None
