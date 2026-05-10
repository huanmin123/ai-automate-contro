from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_automate_contro.ai.service import service_config_for_artifact
from ai_automate_contro.ai.session_compression import make_thread_id
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text
from ai_automate_contro.ai.terminal_tool_registry import describe_ai_terminal_tool, list_ai_terminal_tools
from ai_automate_contro.plans.packages import find_latest_run_output, resolve_plan_path


class AITerminalCommandsMixin:
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
        update: dict[str, str] = {"current_plan_path": str(plan_path)}
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
        self._current_turn_text = None
        self._approval_resume_active = False
        self.poutput(f"AI terminal thread: {self.thread_id}")

    def do_new(self, arg: str) -> None:
        """Start a new AI terminal thread: new [thread-id]"""
        next_thread_id = arg.strip() or make_thread_id("thread")
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self.poutput(f"AI terminal thread: {self.thread_id}")

    def do_compress(self, arg: str) -> None:
        """Compress current AI terminal thread history: compress [reason]"""
        reason = arg.strip() or "manual"
        try:
            result = self._compress_current_thread(reason=reason)
        except Exception as error:
            self.perror(str(error))
            return
        self.poutput(json.dumps(result, ensure_ascii=False, indent=2))

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
            content = message_content_to_text(message.content).strip()
            if isinstance(message, AIMessage) and message.tool_calls:
                calls = ", ".join(str(call.get("name")) for call in message.tool_calls)
                content = f"tool_calls={calls}"
            if len(content) > 500:
                content = content[:497] + "..."
            self.poutput(f"{index:02d}. {role}: {content}")

    def do_exit(self, arg: str) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        self.last_result = True
        return True

    def do_quit(self, arg: object) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        return super().do_quit(arg)
