from __future__ import annotations

import json
import platform

from langchain_core.messages import AIMessage

from ai_automate_contro.ai.image_attachments import (
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
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text
from ai_automate_contro.ai.terminal_markdown import normalize_response_render_mode


COMMAND_SYNTAX_HELP = (
    "命令语法：命令必须写在输入行最开头，格式为 /command 或 /command <args>；"
    "/ 后面的命令名必须以英文字母开头；命令和参数之间至少一个空格；"
    "普通文字中间的 /xxx 不会被当作命令。"
)


def format_keyboard_shortcuts_for_terminal(system_name: str | None = None) -> str:
    normalized_system = (system_name or platform.system()).strip().lower()
    is_macos = normalized_system == "darwin"
    is_windows = normalized_system == "windows"
    if is_macos:
        send_key = "Enter"
        newline_ctrl = "Control+J"
        newline_alt = "Option+Enter"
        paste_shortcut = "Control+V / Option+V"
        paste_note = "Command+V 通常由终端自身处理文本粘贴；要让 AI 终端读取剪贴板图片，请用 Control+V，或在终端把 Option 当 Meta 发送时用 Option+V。"
        system_note = "当前系统：macOS。下列按键按 macOS 终端习惯显示。"
    elif is_windows:
        send_key = "Enter"
        newline_ctrl = "Ctrl+J"
        newline_alt = "Alt+Enter"
        paste_shortcut = "Ctrl+V"
        paste_note = "Windows Terminal / PowerShell 里 Ctrl+V 通常用于粘贴；本工具会优先尝试读取剪贴板图片，失败时回退为粘贴文本。"
        system_note = "当前系统：Windows。"
    else:
        send_key = "Enter"
        newline_ctrl = "Ctrl+J"
        newline_alt = "Alt+Enter"
        paste_shortcut = "Ctrl+V"
        paste_note = "Linux/Unix 终端对 Ctrl+V、Alt 组合键的处理取决于终端模拟器配置。"
        system_note = f"当前系统：{system_name or platform.system() or '未知'}。终端快捷键可能受终端模拟器配置影响。"

    return "\n".join(
        [
            "AI 终端键盘快捷键：",
            f"  {system_note}",
            f"  {send_key:<25} 发送当前消息。",
            f"  {newline_ctrl:<25} 插入换行，跨平台最稳定。",
            f"  {newline_alt:<25} 插入换行；需要终端把这个组合键传给程序。",
            "  Esc                       在 AI 正在处理时，将下一条消息标记为强制接入。",
            f"  {paste_shortcut:<25} 从剪贴板粘贴图片，并在输入行插入 [图片 #n]。",
            "  /                         展开 AI 命令补全；继续输入前缀可过滤。",
            "  Up / Down                 在命令补全候选里移动；无候选时按多行输入内容移动。",
            "  Backspace / Delete        删除图片占位时会整张图片一起移除并重新编号。",
            "",
            "兼容说明：",
            "  普通 Enter 始终发送消息。",
            "  需要稳定换行时请用 Ctrl+J；Alt/Option+Enter 依赖当前终端支持。",
            f"  {paste_note}",
            "  已保存成文件的图片可用 /image <image-path> 添加。",
        ]
    )


class AITerminalCommandsMixin:
    def do_help(self, arg: str) -> None:
        """查看 AI 终端命令：/help"""
        self.poutput(
            "\n".join(
                [
                    "AI 终端命令：",
                    "  /status                         查看当前线程、上下文、checkpoint 和待发送图片。",
                    "  /sessions [limit|all] [--json]  列出已保存会话，不打印完整历史。",
                    "  /resume <thread-id-or-index>    从 sessions 列表恢复会话。",
                    "  /new [thread-id]                新建会话。",
                    "  /compress [reason]              压缩并归档当前会话。",
                    "  /history [limit]                只查看最近几条消息。",
                    "  /keyboard                       查看当前系统的键盘快捷键和兼容说明。",
                    "  /render [markdown|plain]        查看或切换 AI 回复显示方式。",
                    "  /image <image-path>             兜底：把本地图片文件加入下一条消息。",
                    "  /pending | /approve | /reject <reason>  处理受保护补丁审批。",
                    "  /exit 或 /back                  返回 plan 模式。",
                    "  /quit                           退出终端。",
                    COMMAND_SYNTAX_HELP,
                    "上下文会在选择、运行和调试 plan 时自动更新，通常不需要手动设置。",
                ]
            )
        )

    def do_status(self, _: str) -> None:
        """查看当前 AI 终端状态。"""
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
            "response_render_mode": getattr(self, "response_render_mode", "plain"),
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
        self.poutput(json.dumps(payload, ensure_ascii=False, indent=2))

    def do_keyboard(self, _: str) -> None:
        """查看 AI 终端键盘快捷键。"""
        self.poutput(format_keyboard_shortcuts_for_terminal())

    def do_sessions(self, arg: str) -> None:
        """列出已保存的 AI 会话：/sessions [limit|all] [--json]"""
        parts = [part for part in arg.split() if part]
        as_json = "--json" in parts
        parts = [part for part in parts if part != "--json"]
        limit = SESSION_LIST_LIMIT_DEFAULT
        if parts:
            if len(parts) > 1:
                self.perror("用法：/sessions [limit|all] [--json]")
                return
            if parts[0].lower() == "all":
                limit = SESSION_LIST_LIMIT_MAX
            else:
                try:
                    limit = int(parts[0])
                except ValueError:
                    self.perror("用法：/sessions [limit|all] [--json]")
                    return
        try:
            sessions = list_ai_terminal_sessions(self.checkpointer, project_root=self.project_root, limit=limit)
        except Exception as error:
            self.perror(error)
            return
        if as_json:
            self.poutput(json.dumps([session.to_dict() for session in sessions], ensure_ascii=False, indent=2))
            return
        self.poutput(format_sessions_table(sessions))

    def do_resume(self, arg: str) -> None:
        """恢复已保存的 AI 会话：/resume <thread-id-or-index>"""
        try:
            next_thread_id = resolve_ai_terminal_session(self.checkpointer, arg, project_root=self.project_root)
        except Exception as error:
            self.perror(error)
            return
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        session = current_ai_terminal_session(self.checkpointer, self.thread_id, project_root=self.project_root)
        self.poutput(f"AI 终端线程：{self.thread_id}")
        if session is not None:
            self.poutput(
                f"消息数={session.message_count} checkpoint 数={session.checkpoint_count} "
                f"最后时间={session.last_timestamp or '<未知>'}"
            )

    def do_render(self, arg: str) -> None:
        """查看或设置 AI 回复显示方式：/render [markdown|plain]"""
        raw = arg.strip().lower()
        if not raw or raw == "status":
            self.poutput(f"AI 回复显示方式：{getattr(self, 'response_render_mode', 'plain')}")
            return
        if raw not in {"markdown", "md", "rich", "plain", "raw", "text"}:
            self.perror("用法：/render [markdown|plain]")
            return
        self.response_render_mode = normalize_response_render_mode(raw)
        self.poutput(f"AI 回复显示方式：{self.response_render_mode}")

    def do_new(self, arg: str) -> None:
        """新建 AI 终端线程：/new [thread-id]"""
        next_thread_id = arg.strip() or make_thread_id("thread")
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        self.poutput(f"AI 终端线程：{self.thread_id}")

    def do_compress(self, arg: str) -> None:
        """压缩当前 AI 终端会话历史：/compress [reason]"""
        reason = arg.strip() or "manual"
        try:
            result = self._compress_current_thread(reason=reason)
        except Exception as error:
            self.perror(error)
            return
        self._sync_current_session_index()
        self.poutput(json.dumps(result, ensure_ascii=False, indent=2))

    def do_history(self, arg: str) -> None:
        """查看最近的会话消息：/history [limit]"""
        try:
            limit = int(arg.strip()) if arg.strip() else 12
        except ValueError:
            self.perror("用法：/history [limit]")
            return
        if limit <= 0:
            self.perror("数量必须大于 0。")
            return
        messages = self._current_messages()[-limit:]
        if not messages:
            self.poutput("历史记录：<空>")
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

    def _add_image_file(self, arg: str) -> None:
        command = arg.strip()
        if not command:
            self.perror("用法：/image <image-path>")
            return
        try:
            attachment = attach_image_file(
                self.project_root,
                self.thread_id,
                command,
                pending_count=len(self._pending_attachments),
            )
        except Exception as error:
            self.perror(error)
            return
        self._pending_attachments.append(attachment)
        self._pending_attachment_placeholder_required.append(False)
        placeholder = image_attachment_placeholder(len(self._pending_attachments))
        self.poutput(f"已添加图片：{placeholder}。可以继续输入文字。")

    def do_image(self, arg: str) -> None:
        """把图片文件加入下一条 AI 消息：/image <image-path>"""
        self._add_image_file(arg)
