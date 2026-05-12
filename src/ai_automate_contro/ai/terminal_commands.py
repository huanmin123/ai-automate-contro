from __future__ import annotations

import json
from pathlib import Path

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
    remove_ai_terminal_session_from_index,
    resolve_ai_terminal_session,
    session_index_path,
    update_ai_terminal_session_index,
)
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text
from ai_automate_contro.ai.terminal_markdown import normalize_response_render_mode
from ai_automate_contro.ai.terminal_tool_registry import describe_ai_terminal_tool, list_ai_terminal_tools
from ai_automate_contro.plans.packages import find_latest_run_output, resolve_plan_path


class AITerminalCommandsMixin:
    def do_help(self, arg: str) -> None:
        """查看 AI 终端命令：help [command]"""
        self.poutput(
            "\n".join(
                [
                    "AI 终端命令：",
                    "  status                         查看当前线程、上下文、checkpoint 和待发送图片。",
                    "  sessions [limit|all] [--json]  列出已保存会话，不打印完整历史。",
                    "  resume <thread-id-or-index>     从 sessions 列表恢复会话。",
                    "  new [thread-id]                 新建会话。",
                    "  thread [thread-id]              查看或直接切换线程 id。",
                    "  compress [reason]               压缩并归档当前会话。",
                    "  history [limit]                 只查看最近几条消息。",
                    "  render [markdown|plain]         查看或切换 AI 回复显示方式。",
                    "  Alt+V / Ctrl+V                  从剪贴板粘贴截图，并在输入行显示 [图片 #n]。",
                    "  image <image-path>              兜底：把本地图片文件加入下一条消息。",
                    "  use|workspace|run_context        设置当前 plan、调试工作区或运行输出上下文。",
                    "  tools [name]                    列出 AI 终端工具，或查看某个工具 schema。",
                    "  pending|approve|reject <reason>  处理受保护补丁审批。",
                    "也支持斜杠形式，例如 /status、/sessions、/resume 1。",
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

    def do_cancel(self, _: str) -> None:
        """清理上一轮残留的忙碌状态。"""
        if not self._cancel_agent_turn():
            self.poutput("取消：当前没有正在等待的 AI 回复。")
            return
        self.poutput("取消：已清理残留的 AI 等待状态。")

    def do_sessions(self, arg: str) -> None:
        """列出已保存的 AI 会话：sessions [limit|all] [--json]"""
        parts = [part for part in arg.split() if part]
        as_json = "--json" in parts
        parts = [part for part in parts if part != "--json"]
        limit = SESSION_LIST_LIMIT_DEFAULT
        if parts:
            if len(parts) > 1:
                self.perror("用法：sessions [limit|all] [--json]")
                return
            if parts[0].lower() == "all":
                limit = SESSION_LIST_LIMIT_MAX
            else:
                try:
                    limit = int(parts[0])
                except ValueError:
                    self.perror("用法：sessions [limit|all] [--json]")
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
        """恢复已保存的 AI 会话：resume <thread-id-or-index>"""
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

    def do_context(self, _: str) -> None:
        """查看当前 AI 终端上下文。"""
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
                    "response_render_mode": getattr(self, "response_render_mode", "plain"),
                    "checkpoints": self._checkpoint_count(),
                    "pending_attachments": [attachment.to_dict() for attachment in self._pending_attachments],
                    "state": self._context_state(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def do_tools(self, arg: str) -> None:
        """列出 AI 终端工具，或查看某个工具 schema：tools [name]"""
        tool_name = arg.strip()
        if tool_name:
            try:
                payload = describe_ai_terminal_tool(tool_name)
            except Exception as error:
                self.perror(error)
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

    def do_render(self, arg: str) -> None:
        """查看或设置 AI 回复显示方式：render [markdown|plain]"""
        raw = arg.strip().lower()
        if not raw or raw == "status":
            self.poutput(f"AI 回复显示方式：{getattr(self, 'response_render_mode', 'plain')}")
            return
        if raw not in {"markdown", "md", "rich", "plain", "raw", "text"}:
            self.perror("用法：render [markdown|plain]")
            return
        self.response_render_mode = normalize_response_render_mode(raw)
        self.poutput(f"AI 回复显示方式：{self.response_render_mode}")

    def do_reset(self, _: str) -> None:
        """删除当前 AI 终端线程的 checkpoint。"""
        self.checkpointer.delete_thread(self.thread_id)
        remove_ai_terminal_session_from_index(self.project_root, self.thread_id)
        self._clear_pending_attachments()
        self.poutput(f"AI 终端线程已重置：{self.thread_id}")

    def do_use(self, arg: str) -> None:
        """设置或查看当前 plan 上下文：use [plan.json-or-package-dir]"""
        raw_path = arg.strip()
        if not raw_path:
            plan_path = self._context_state().get("current_plan_path") or "<无>"
            self.poutput(f"当前 plan：{plan_path}")
            return
        try:
            plan_path = resolve_plan_path(raw_path)
            latest_output = find_latest_run_output(plan_path.parent)
        except Exception as error:
            self.perror(error)
            return
        update: dict[str, str] = {"current_plan_path": str(plan_path)}
        if latest_output is not None:
            update["latest_output_dir"] = str(latest_output)
        self._update_context_state(update)
        self._sync_current_session_index()
        self.poutput(f"当前 plan：{plan_path}")
        if latest_output is not None:
            self.poutput(f"最近输出：{latest_output}")

    def do_workspace(self, arg: str) -> None:
        """设置或查看当前调试工作区：workspace [output/debug/<run>]"""
        raw_path = arg.strip()
        if not raw_path:
            workspace = self._context_state().get("current_debug_workspace") or "<无>"
            self.poutput(f"当前调试工作区：{workspace}")
            return
        workspace = Path(raw_path).resolve()
        if not workspace.exists():
            self.perror(f"调试工作区不存在：{workspace}")
            return
        self._update_context_state({"current_debug_workspace": str(workspace)})
        self._sync_current_session_index()
        self.poutput(f"当前调试工作区：{workspace}")

    def do_run_context(self, arg: str) -> None:
        """设置或查看最近运行输出上下文：run_context [output-dir]"""
        raw_path = arg.strip()
        if not raw_path:
            output_dir = self._context_state().get("latest_output_dir") or "<无>"
            self.poutput(f"最近输出：{output_dir}")
            return
        output_dir = Path(raw_path).resolve()
        if not output_dir.exists():
            self.perror(f"run output does not exist: {output_dir}")
            return
        self._update_context_state({"latest_output_dir": str(output_dir)})
        self._sync_current_session_index()
        self.poutput(f"最近输出：{output_dir}")

    def do_ask(self, arg: str) -> None:
        """发送一条用户消息给 AI 终端：ask <message>"""
        self.default(arg)

    def do_thread(self, arg: str) -> None:
        """查看或切换线程：thread [thread-id]"""
        next_thread_id = arg.strip()
        if not next_thread_id:
            self.poutput(self.thread_id)
            return
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        self.poutput(f"AI 终端线程：{self.thread_id}")

    def do_new(self, arg: str) -> None:
        """新建 AI 终端线程：new [thread-id]"""
        next_thread_id = arg.strip() or make_thread_id("thread")
        self.thread_id = next_thread_id
        self._current_turn_text = None
        self._approval_resume_active = False
        self._last_error = ""
        self._clear_pending_attachments()
        self.poutput(f"AI 终端线程：{self.thread_id}")

    def do_compress(self, arg: str) -> None:
        """压缩当前 AI 终端会话历史：compress [reason]"""
        reason = arg.strip() or "manual"
        try:
            result = self._compress_current_thread(reason=reason)
        except Exception as error:
            self.perror(error)
            return
        self._sync_current_session_index()
        self.poutput(json.dumps(result, ensure_ascii=False, indent=2))

    def do_history(self, arg: str) -> None:
        """查看最近的会话消息：history [limit]"""
        try:
            limit = int(arg.strip()) if arg.strip() else 12
        except ValueError:
            self.perror("用法：history [limit]")
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
            self.perror("用法：image <image-path>")
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
        """把图片文件加入下一条 AI 消息：image <image-path>"""
        self._add_image_file(arg)

    def do_exit(self, arg: str) -> bool:
        """退出 AI 终端。"""
        self._close_checkpoint_connection()
        return True

    def do_quit(self, arg: object) -> bool:
        """退出 AI 终端。"""
        self._close_checkpoint_connection()
        return True
