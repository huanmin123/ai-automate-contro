from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path
from typing import Any

import cmd2
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

warnings.filterwarnings("ignore", message=r"The default value of `allowed_objects`.*")
warnings.filterwarnings("ignore", message=r".*allowed_objects.*")
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

from ai_automate_contro.ai.langgraph_tools import build_langchain_tools
from ai_automate_contro.ai.terminal_approval import AITerminalApprovalMixin
from ai_automate_contro.ai.terminal_commands import AITerminalCommandsMixin
from ai_automate_contro.ai.terminal_config import build_chat_model, load_ai_terminal_config
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
        self.model = build_chat_model(self.config.service_config)
        self.graph = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=build_system_prompt(),
            state_schema=AITerminalState,
            middleware=[
                inject_ai_terminal_context,
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

    def default(self, line: str) -> None:
        text = line.strip()
        if not text:
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
