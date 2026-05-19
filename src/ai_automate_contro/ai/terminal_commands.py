from __future__ import annotations

import json

from ai_automate_contro.ai.image_attachments import (
    attach_clipboard_images,
    attach_image_file,
    image_attachment_placeholder,
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
    resolve_ai_terminal_session,
    session_index_path,
    update_ai_terminal_session_index,
)
from ai_automate_contro.ai.work_plan import format_work_plan_for_terminal


class AITerminalCommandsMixin:
    def do_status(self, _: str) -> None:
        """查看当前 AI 会话状态。"""
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
                "graph_recursion_limit": self.graph_recursion_limit,
                "estimated_usage_ratio": round(estimated_tokens / MODEL_CONTEXT_TOKEN_LIMIT, 4),
                "auto_compress_trigger_ratio": round(AUTO_COMPRESS_TRIGGER_TOKENS / MODEL_CONTEXT_TOKEN_LIMIT, 4),
            },
            "pending_approval": bool(interrupts),
            "pending_attachments": [attachment.to_dict() for attachment in self._pending_attachments],
            "context_state": self._context_state(),
        }
        self._emit_system_output(json.dumps(payload, ensure_ascii=False, indent=2))

    def do_plan(self, _: str) -> None:
        """查看当前 AI 工作计划。"""
        state_provider = getattr(self, "_work_plan_state", None)
        state = state_provider() if callable(state_provider) else {}
        items = state.get("items") if isinstance(state, dict) else []
        summary = state.get("summary") if isinstance(state, dict) else ""
        self._emit_system_output(format_work_plan_for_terminal(items, summary=summary))

    def do_sessions(self, arg: str) -> None:
        """列出已保存的 AI 会话：/sessions [limit|all] [--json]"""
        parts = [part for part in arg.split() if part]
        as_json = "--json" in parts
        parts = [part for part in parts if part != "--json"]
        limit = SESSION_LIST_LIMIT_DEFAULT
        if parts:
            if len(parts) > 1:
                self._emit_error("用法：/sessions [limit|all] [--json]")
                return
            if parts[0].lower() == "all":
                limit = SESSION_LIST_LIMIT_MAX
            else:
                try:
                    limit = int(parts[0])
                except ValueError:
                    self._emit_error("用法：/sessions [limit|all] [--json]")
                    return
        try:
            sessions = list_ai_terminal_sessions(self.checkpointer, project_root=self.project_root, limit=limit)
        except Exception as error:
            self._emit_error(error)
            return
        if as_json:
            self._emit_system_output(json.dumps([session.to_dict() for session in sessions], ensure_ascii=False, indent=2))
            return
        self._emit_system_output(format_sessions_table(sessions))

    def do_resume(self, arg: str) -> None:
        """恢复已保存的 AI 会话：/resume <thread-id-or-index>"""
        try:
            next_thread_id = resolve_ai_terminal_session(self.checkpointer, arg, project_root=self.project_root)
        except Exception as error:
            self._emit_error(error)
            return
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        session = current_ai_terminal_session(self.checkpointer, self.thread_id, project_root=self.project_root)
        self._emit_system_output(f"AI 会话线程：{self.thread_id}")
        if session is not None:
            self._emit_system_output(
                f"消息数={session.message_count} checkpoint 数={session.checkpoint_count} "
                f"最后时间={session.last_timestamp or '<未知>'}"
            )

    def do_new(self, arg: str) -> None:
        """新建 AI 会话线程：/new [thread-id]"""
        next_thread_id = arg.strip() or make_thread_id("thread")
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        self._emit_system_output(f"AI 会话线程：{self.thread_id}")

    def _add_image_file(self, arg: str) -> None:
        command = arg.strip()
        if not command:
            self._emit_error("用法：/image <image-path>")
            return
        try:
            attachment = attach_image_file(
                self.project_root,
                self.thread_id,
                command,
                pending_count=len(self._pending_attachments),
            )
        except Exception as error:
            self._emit_error(error)
            return
        self._pending_attachments.append(attachment)
        self._pending_attachment_placeholder_required.append(False)
        placeholder = image_attachment_placeholder(len(self._pending_attachments))
        self._emit_system_output(f"已添加图片：{placeholder}。可以继续输入文字。")

    def do_image(self, arg: str) -> None:
        """把图片文件加入下一条 AI 消息：/image <image-path>"""
        self._add_image_file(arg)

    def attach_clipboard_images(self) -> list[str]:
        attachments = attach_clipboard_images(
            self.project_root,
            self.thread_id,
            pending_count=len(self._pending_attachments),
        )
        self._pending_attachments.extend(attachments)
        self._pending_attachment_placeholder_required.extend(False for _ in attachments)
        start = len(self._pending_attachments) - len(attachments) + 1
        return [image_attachment_placeholder(index) for index in range(start, len(self._pending_attachments) + 1)]
