from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_automate_contro.ai.image_attachments import (
    attach_clipboard_images,
    attach_image_file,
    format_pending_attachments,
)
from ai_automate_contro.ai.service import service_config_for_artifact
from ai_automate_contro.ai.session_compression import (
    AUTO_COMPRESS_TRIGGER_TOKENS,
    MODEL_CONTEXT_TOKEN_LIMIT,
    POST_COMPRESS_KEEP_TOKENS,
    count_ai_terminal_tokens,
    make_thread_id,
)
from ai_automate_contro.ai.session_store import (
    SESSION_LIST_LIMIT_DEFAULT,
    SESSION_LIST_LIMIT_MAX,
    current_ai_terminal_session,
    format_sessions_table,
    list_ai_terminal_sessions,
    remove_ai_terminal_session_from_index,
    resolve_ai_terminal_session,
    session_index_path,
    update_ai_terminal_session_index,
)
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text
from ai_automate_contro.ai.terminal_tool_registry import describe_ai_terminal_tool, list_ai_terminal_tools
from ai_automate_contro.plans.packages import find_latest_run_output, resolve_plan_path


class AITerminalCommandsMixin:
    def do_help(self, arg: str) -> None:
        """Show AI terminal commands: help [command]"""
        if arg.strip():
            super().do_help(arg)
            return
        self.poutput(
            "\n".join(
                [
                    "AI terminal commands:",
                    "  status                         Show current thread, context, checkpoints, and pending attachments.",
                    "  sessions [limit|all] [--json]  List saved AI conversations without printing full history.",
                    "  resume <thread-id-or-index>     Resume a saved conversation from sessions.",
                    "  new [thread-id]                 Start a new conversation thread.",
                    "  thread [thread-id]              Show or switch thread id directly.",
                    "  cancel                          Stop waiting for the current AI turn result.",
                    "  compress [reason]               Archive and summarize current conversation.",
                    "  history [limit]                 Show recent messages only.",
                    "  attach <image-path>             Attach an image to the next AI message.",
                    "  attach list|clear|remove <n>    Manage pending image attachments.",
                    "  paste_image                     Attach image content from the clipboard.",
                    "  use|workspace|run_context        Set current plan/debug/run context.",
                    "  tools [name]                    List AI terminal tools or one schema.",
                    "  pending|approve|reject <reason>  Manage protected patch approval.",
                    "Slash forms are also supported, for example /status, /sessions, /resume 1, /attach <path>, /paste-image.",
                ]
            )
        )

    def do_status(self, _: str) -> None:
        """Show current AI terminal status."""
        messages = self._current_messages()
        self._sync_current_session_index()
        session = current_ai_terminal_session(self.checkpointer, self.thread_id, project_root=self.project_root)
        interrupts = self._current_interrupts()
        estimated_tokens = count_ai_terminal_tokens(messages) if messages else 0
        payload = {
            "project_root": str(self.project_root),
            "service": self.config.service_name,
            "service_config": service_config_for_artifact(self.config.service_config),
            "model": self.model_name,
            "thread_id": self.thread_id,
            "busy": self._is_agent_busy(),
            "current_turn_text": self._current_turn_text or "",
            "last_error": self._last_error,
            "checkpoint_path": str(self.checkpoint_path),
            "session_index_path": str(session_index_path(self.project_root)),
            "checkpoint": session.to_dict() if session is not None else None,
            "messages": len(messages),
            "estimated_tokens": estimated_tokens,
            "context_window": {
                "model_context_token_limit": MODEL_CONTEXT_TOKEN_LIMIT,
                "auto_compress_trigger_tokens": AUTO_COMPRESS_TRIGGER_TOKENS,
                "post_compress_keep_tokens": POST_COMPRESS_KEEP_TOKENS,
                "estimated_usage_ratio": round(estimated_tokens / MODEL_CONTEXT_TOKEN_LIMIT, 4),
                "auto_compress_trigger_ratio": round(AUTO_COMPRESS_TRIGGER_TOKENS / MODEL_CONTEXT_TOKEN_LIMIT, 4),
            },
            "pending_approval": bool(interrupts),
            "pending_attachments": [attachment.to_dict() for attachment in self._pending_attachments],
            "context_state": self._context_state(),
        }
        self.poutput(json.dumps(payload, ensure_ascii=False, indent=2))

    def do_cancel(self, _: str) -> None:
        """Stop waiting for the current AI turn result."""
        if not self._cancel_agent_turn():
            self.poutput("cancel: no running AI turn")
            return
        self.poutput("cancel: current AI turn result will be ignored when it finishes")

    def do_sessions(self, arg: str) -> None:
        """List saved AI terminal sessions: sessions [limit|all] [--json]"""
        parts = [part for part in arg.split() if part]
        as_json = "--json" in parts
        parts = [part for part in parts if part != "--json"]
        limit = SESSION_LIST_LIMIT_DEFAULT
        if parts:
            if len(parts) > 1:
                self.perror("usage: sessions [limit|all] [--json]")
                return
            if parts[0].lower() == "all":
                limit = SESSION_LIST_LIMIT_MAX
            else:
                try:
                    limit = int(parts[0])
                except ValueError:
                    self.perror("usage: sessions [limit|all] [--json]")
                    return
        try:
            sessions = list_ai_terminal_sessions(self.checkpointer, project_root=self.project_root, limit=limit)
        except Exception as error:
            self.perror(str(error))
            return
        if as_json:
            self.poutput(json.dumps([session.to_dict() for session in sessions], ensure_ascii=False, indent=2))
            return
        self.poutput(format_sessions_table(sessions))

    def do_resume(self, arg: str) -> None:
        """Resume a saved AI terminal session: resume <thread-id-or-index>"""
        try:
            next_thread_id = resolve_ai_terminal_session(self.checkpointer, arg, project_root=self.project_root)
        except Exception as error:
            self.perror(str(error))
            return
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._pending_attachments.clear()
        session = current_ai_terminal_session(self.checkpointer, self.thread_id, project_root=self.project_root)
        self.poutput(f"AI terminal thread: {self.thread_id}")
        if session is not None:
            self.poutput(
                f"messages={session.message_count} checkpoints={session.checkpoint_count} "
                f"last={session.last_timestamp or '<unknown>'}"
            )

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
                    "pending_attachments": [attachment.to_dict() for attachment in self._pending_attachments],
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
        remove_ai_terminal_session_from_index(self.project_root, self.thread_id)
        self._pending_attachments.clear()
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
        self._sync_current_session_index()
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
        self._sync_current_session_index()
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
        self._sync_current_session_index()
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
        self._last_error = ""
        self._pending_attachments.clear()
        self.poutput(f"AI terminal thread: {self.thread_id}")

    def do_new(self, arg: str) -> None:
        """Start a new AI terminal thread: new [thread-id]"""
        next_thread_id = arg.strip() or make_thread_id("thread")
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._pending_attachments.clear()
        self.poutput(f"AI terminal thread: {self.thread_id}")

    def do_compress(self, arg: str) -> None:
        """Compress current AI terminal thread history: compress [reason]"""
        reason = arg.strip() or "manual"
        try:
            result = self._compress_current_thread(reason=reason)
        except Exception as error:
            self.perror(str(error))
            return
        self._sync_current_session_index()
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

    def do_attach(self, arg: str) -> None:
        """Attach an image to the next AI message: attach <image-path>|list|clear|remove <index>"""
        command = arg.strip()
        normalized = command.lower()
        if not command or normalized == "list":
            self.poutput(format_pending_attachments(self._pending_attachments))
            return
        if normalized == "clear":
            self._pending_attachments.clear()
            self.poutput("attachments cleared")
            return
        if normalized.startswith("remove "):
            raw_index = command.split(None, 1)[1].strip()
            try:
                index = int(raw_index)
            except ValueError:
                self.perror("usage: attach remove <index>")
                return
            if index < 1 or index > len(self._pending_attachments):
                self.perror(f"attachment index out of range: {index}")
                return
            removed = self._pending_attachments.pop(index - 1)
            self.poutput(f"removed attachment: {removed.file_name}")
            return
        try:
            attachment = attach_image_file(
                self.project_root,
                self.thread_id,
                command,
                pending_count=len(self._pending_attachments),
            )
        except Exception as error:
            self.perror(str(error))
            return
        self._pending_attachments.append(attachment)
        self.poutput(format_pending_attachments(self._pending_attachments))

    def do_attachments(self, arg: str) -> None:
        """Manage pending image attachments: attachments [list|clear|remove <index>]"""
        self.do_attach(arg)

    def do_image(self, arg: str) -> None:
        """Attach an image to the next AI message: image <image-path>"""
        self.do_attach(arg)

    def do_paste_image(self, _: str) -> None:
        """Attach image content from the clipboard to the next AI message."""
        try:
            attachments = attach_clipboard_images(
                self.project_root,
                self.thread_id,
                pending_count=len(self._pending_attachments),
            )
        except Exception as error:
            self.perror(str(error))
            return
        self._pending_attachments.extend(attachments)
        self.poutput(format_pending_attachments(self._pending_attachments))

    def do_exit(self, arg: str) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        self.last_result = True
        return True

    def do_quit(self, arg: object) -> bool:
        """Exit the AI terminal."""
        self._close_checkpoint_connection()
        return super().do_quit(arg)
