from __future__ import annotations

from typing import Any

from langgraph.types import Command

from ai_automate_contro.ai.terminal_message_utils import (
    approval_decision_for_request,
    interrupt_action_requests,
)


class AITerminalApprovalMixin:
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
        decisions = [approval_decision_for_request(request) for request in interrupt_action_requests(interrupts)]
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
        decisions = [{"type": "reject", "message": message} for _ in interrupt_action_requests(interrupts)]
        self._resume_agent({"decisions": decisions})

    def _resume_agent(self, resume_payload: dict[str, Any]) -> None:
        try:
            final_state = self.graph.invoke(
                Command(resume=resume_payload),
                config=self._graph_config(),
            )
        except Exception as error:
            self.perror(error)
            return
        if self._print_pending_interrupt(final_state):
            return
        messages = list(final_state["messages"])
        last_message = self._last_assistant_message(messages)
        if last_message:
            self.poutput(last_message)
