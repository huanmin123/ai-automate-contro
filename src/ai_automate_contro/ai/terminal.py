from __future__ import annotations

import sqlite3
import threading
import warnings
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.session_compression import install_langgraph_warning_filter

install_langgraph_warning_filter()

import cmd2
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

from langgraph.checkpoint.sqlite import SqliteSaver

from ai_automate_contro.ai.image_attachments import (
    ImageAttachment,
    build_human_message_additional_kwargs,
    build_human_message_content,
    expand_messages_image_attachments_for_model,
)
from ai_automate_contro.ai.langgraph_tools import build_langchain_tools
from ai_automate_contro.ai.file_search import assert_ripgrep_available
from ai_automate_contro.ai.terminal_approval import AITerminalApprovalMixin
from ai_automate_contro.ai.terminal_commands import AITerminalCommandsMixin
from ai_automate_contro.ai.terminal_config import build_chat_model, load_ai_terminal_config
from ai_automate_contro.ai.session_compression import build_summarization_middleware
from ai_automate_contro.ai.terminal_context import (
    AITerminalState,
    inject_ai_terminal_context,
)
from ai_automate_contro.ai.terminal_message_utils import (
    format_patch_approval_request,
    text_has_approval,
    text_has_rejection,
)
from ai_automate_contro.ai.terminal_prompts import build_system_prompt
from ai_automate_contro.ai.terminal_state import AITerminalStateMixin


BUSY_ALLOWED_COMMANDS = {"?", "cancel", "help", "status"}


class AITerminal(
    AITerminalApprovalMixin,
    AITerminalCommandsMixin,
    AITerminalStateMixin,
    cmd2.Cmd,
):
    intro = "Keygen Automation AI Terminal. Type help or ? to list commands."

    def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
        super().__init__(allow_cli_args=False)
        self.project_root = project_root.resolve()
        assert_ripgrep_available()
        self.config = load_ai_terminal_config(self.project_root, service_name=service)
        self.model_name = str(self.config.service_config["model"])
        self.thread_id = thread_id
        self._current_turn_text: str | None = None
        self._current_turn_id: int = 0
        self._cancelled_turn_ids: set[int] = set()
        self._turn_lock = threading.Lock()
        self._approval_resume_active = False
        self._last_error: str = ""
        self._pending_attachments: list[ImageAttachment] = []
        self.checkpoint_path = self.project_root / ".keygen" / "ai-terminal-checkpoints.sqlite"
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_connection = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.tools = build_langchain_tools(
            self.project_root,
            latest_user_approved=self._latest_user_approved,
            after_tool_call=self._after_tool_call,
        )
        self.model = build_chat_model(self.config.service_config)
        self.summary_middleware = build_summarization_middleware(
            self.model,
            project_root=self.project_root,
            thread_id_provider=lambda: self.thread_id,
        )
        self.graph = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=build_system_prompt(),
            state_schema=AITerminalState,
            middleware=[
                inject_ai_terminal_context,
                inject_image_attachments_for_model,
                self.summary_middleware,
                HumanInTheLoopMiddleware(
                    interrupt_on={
                        "apply_debug_patch_after_approval": {
                            "allowed_decisions": ["approve", "edit", "reject"],
                            "description": format_patch_approval_request,
                        }
                    }
                ),
            ],
            checkpointer=self.checkpointer,
        )
        self.prompt = "ai> "

    def onecmd_plus_hooks(
        self,
        line: str,
        *,
        add_to_history: bool = True,
        raise_keyboard_interrupt: bool = False,
        py_bridge_call: bool = False,
        orig_rl_history_length: int | None = None,
    ) -> bool:
        if self._is_agent_busy() and not self._command_allowed_while_busy(line):
            self.perror("AI terminal is busy; only status, cancel, and help are available until it finishes")
            return False
        return super().onecmd_plus_hooks(
            line,
            add_to_history=add_to_history,
            raise_keyboard_interrupt=raise_keyboard_interrupt,
            py_bridge_call=py_bridge_call,
            orig_rl_history_length=orig_rl_history_length,
        )

    def default(self, line: str) -> None:
        text = getattr(line, "command_and_args", str(line)).strip()
        if not text:
            return
        if self._handle_slash_command(text):
            return
        if self._current_interrupts():
            if text_has_approval(text):
                self.do_approve("")
                return
            if text_has_rejection(text):
                self.do_reject(text)
                return
            self.perror("pending approval; use approve or reject <reason> before sending a new request")
            return
        self._run_agent_turn(text)

    def _handle_slash_command(self, text: str) -> bool:
        if not text.startswith("/"):
            return False
        command, _, arg = text[1:].partition(" ")
        normalized = command.strip().lower()
        method_name = {
            "approve": "do_approve",
            "ask": "do_ask",
            "attach": "do_attach",
            "attachments": "do_attachments",
            "cancel": "do_cancel",
            "compress": "do_compress",
            "context": "do_context",
            "help": "do_help",
            "history": "do_history",
            "image": "do_image",
            "new": "do_new",
            "paste-image": "do_paste_image",
            "paste_image": "do_paste_image",
            "pending": "do_pending",
            "reject": "do_reject",
            "resume": "do_resume",
            "run-context": "do_run_context",
            "run_context": "do_run_context",
            "sessions": "do_sessions",
            "status": "do_status",
            "thread": "do_thread",
            "tools": "do_tools",
            "use": "do_use",
            "workspace": "do_workspace",
        }.get(normalized)
        if method_name:
            if self._is_agent_busy() and normalized not in BUSY_ALLOWED_COMMANDS:
                self.perror("AI terminal is busy; only /status, /cancel, and /help are available until it finishes")
                return True
            getattr(self, method_name)(arg)
            return True
        self.perror(f"unknown AI terminal command: /{command}")
        return True

    def _run_agent_turn(self, text: str) -> None:
        if self._is_agent_busy():
            self.perror("AI terminal is busy; use /status or /cancel before sending another request")
            return
        with self._turn_lock:
            self._current_turn_id += 1
            turn_id = self._current_turn_id
            self._current_turn_text = text
        worker = threading.Thread(
            target=self._run_agent_turn_worker,
            args=(turn_id, text),
            name=f"ai-terminal-turn-{turn_id}",
            daemon=True,
        )
        worker.start()
        self.poutput(f"[RUNNING] AI turn started: {turn_id}. Use /status to inspect or /cancel to stop waiting.")

    def _run_agent_turn_worker(self, turn_id: int, text: str) -> None:
        attachments = list(self._pending_attachments)
        try:
            message = HumanMessage(
                content=build_human_message_content(text, attachments),
                additional_kwargs=build_human_message_additional_kwargs(attachments),
            )
            final_state = self.graph.invoke(
                {"messages": [message]},
                config=self._graph_config(),
            )
        except Exception as error:
            if self._finish_agent_turn(turn_id, error=str(error)):
                self.perror(str(error))
            return

        if not self._finish_agent_turn(turn_id):
            return
        if attachments:
            self._pending_attachments.clear()
        self._last_error = ""
        self._sync_current_session_index()
        if self._print_pending_interrupt(final_state):
            return
        messages = list(final_state["messages"])
        last_message = self._last_assistant_message(messages)
        if last_message:
            self.poutput(last_message)
        self._async_alert("[DONE] AI turn finished.")

    def _finish_agent_turn(self, turn_id: int, *, error: str = "") -> bool:
        with self._turn_lock:
            if turn_id in self._cancelled_turn_ids:
                self._cancelled_turn_ids.discard(turn_id)
                if self._current_turn_id == turn_id:
                    self._current_turn_text = None
                return False
            if self._current_turn_id == turn_id:
                self._current_turn_text = None
            if error:
                self._last_error = error
        return True

    def _is_agent_busy(self) -> bool:
        with self._turn_lock:
            return self._current_turn_text is not None

    def _cancel_agent_turn(self) -> bool:
        with self._turn_lock:
            if self._current_turn_text is None:
                return False
            self._cancelled_turn_ids.add(self._current_turn_id)
            self._current_turn_text = None
        return True

    def _command_allowed_while_busy(self, line: str) -> bool:
        text = str(line).strip()
        if not text:
            return True
        if text.startswith("/"):
            text = text[1:].lstrip()
        command = text.split(None, 1)[0].lower() if text else ""
        return command in BUSY_ALLOWED_COMMANDS

    def _async_alert(self, message: str) -> None:
        try:
            self.async_alert(message)
        except RuntimeError:
            self.poutput(message)


@wrap_model_call(state_schema=AITerminalState, name="AITerminalImageAttachmentMiddleware")
def inject_image_attachments_for_model(
    request: ModelRequest[Any],
    handler: Any,
) -> ModelResponse[Any]:
    messages = expand_messages_image_attachments_for_model(list(request.messages))
    return handler(request.override(messages=messages))
