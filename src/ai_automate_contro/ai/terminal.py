from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
import warnings
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.session_compression import install_langgraph_warning_filter

install_langgraph_warning_filter()

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import emacs_insert_mode, vi_insert_mode
from prompt_toolkit.shortcuts.prompt import CompleteStyle
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

from langgraph.checkpoint.sqlite import SqliteSaver

from ai_automate_contro.ai.image_attachments import (
    ImageAttachment,
    attach_clipboard_images,
    build_human_message_additional_kwargs,
    build_human_message_content,
    expand_messages_image_attachments_for_model,
    image_attachment_placeholder,
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
    extract_interrupts,
    format_patch_approval_request,
    interrupt_action_requests,
    message_content_to_text,
)
from ai_automate_contro.ai.terminal_markdown import (
    MarkdownLiveRenderer,
    normalize_response_render_mode,
    render_markdown_to_ansi,
    terminal_supports_rich_markdown,
    terminal_supports_live_markdown,
)
from ai_automate_contro.ai.prompts.terminal import build_system_prompt
from ai_automate_contro.ai.terminal_state import AITerminalStateMixin
from ai_automate_contro.app.errors import format_error_for_terminal
from ai_automate_contro.support.terminal_style import terminal_input_style


SLASH_COMMAND_RE = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.*))?$")
BUSY_ALLOWED_COMMANDS = {"help", "keyboard", "pending", "status"}
SLASH_COMMANDS: dict[str, dict[str, str]] = {
    "approve": {"method": "do_approve", "description": "批准当前等待的受保护补丁操作"},
    "back": {"method": "", "description": "返回 plan 模式"},
    "compress": {"method": "do_compress", "description": "压缩并归档当前会话"},
    "exit": {"method": "", "description": "返回 plan 模式"},
    "help": {"method": "do_help", "description": "查看 AI 终端命令"},
    "history": {"method": "do_history", "description": "查看最近几条会话消息"},
    "image": {"method": "do_image", "description": "把图片文件加入下一条消息"},
    "keyboard": {"method": "do_keyboard", "description": "查看键盘快捷键和兼容说明"},
    "new": {"method": "do_new", "description": "新建一个会话"},
    "pending": {"method": "do_pending", "description": "查看等待审批的受保护操作"},
    "quit": {"method": "", "description": "退出终端"},
    "reject": {"method": "do_reject", "description": "拒绝当前等待审批的操作"},
    "render": {"method": "do_render", "description": "查看或切换 AI 回复渲染方式"},
    "resume": {"method": "do_resume", "description": "恢复已保存的会话"},
    "sessions": {"method": "do_sessions", "description": "列出已保存会话"},
    "status": {"method": "do_status", "description": "查看当前线程、上下文、checkpoint 和待发送图片"},
}
SLASH_COMPLETION_COMMANDS = {
    "approve",
    "back",
    "compress",
    "exit",
    "help",
    "history",
    "image",
    "keyboard",
    "new",
    "pending",
    "quit",
    "reject",
    "render",
    "resume",
    "sessions",
    "status",
}
IMAGE_PLACEHOLDER_STYLE = "class:image-placeholder"
IMAGE_PLACEHOLDER_PATTERN = "[图片 #"
IMAGE_PLACEHOLDER_RE = re.compile(r"\[(?:图片|Image) #(\d+)\]")
AI_INPUT_STYLE = terminal_input_style({"image-placeholder": "fg:#0087ff bold underline noreverse"})


class AITerminal(
    AITerminalApprovalMixin,
    AITerminalCommandsMixin,
    AITerminalStateMixin,
):
    intro = "AI 自动化终端。输入 /help 查看命令。"

    def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
        self.project_root = project_root.resolve()
        assert_ripgrep_available()
        self.config = load_ai_terminal_config(self.project_root, service_name=service)
        self.model_name = str(self.config.service_config["model"])
        self.graph_recursion_limit = int(self.config.service_config.get("graph_recursion_limit", 128))
        self.thread_id = thread_id
        self._current_turn_text: str | None = None
        self._current_turn_id: int = 0
        self._cancelled_turn_ids: set[int] = set()
        self._turn_lock = threading.Lock()
        self._output_lock = threading.Lock()
        self._ai_confirmation_lock = threading.Lock()
        self._ai_confirmation: AIConfirmationWait | None = None
        self._approval_resume_active = False
        self._last_error: str = ""
        self._pending_attachments: list[ImageAttachment] = []
        self._pending_attachment_placeholder_required: list[bool] = []
        self._ai_prompt_session: Any | None = None
        self.response_render_mode = normalize_response_render_mode(
            self.config.service_config.get("terminal_render_mode", "markdown")
        )
        self.checkpoint_path = self.project_root / ".keygen" / "ai-terminal-checkpoints.sqlite"
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_connection = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.tools = build_langchain_tools(
            self.project_root,
            latest_user_approved=self._latest_user_approved,
            after_tool_call=self._after_tool_call,
            thread_id_provider=lambda: self.thread_id,
            manual_confirmation_handler=lambda prompt: self._wait_for_ai_confirmation(prompt, wait_type="manual_confirm"),
            inspection_confirmation_handler=lambda prompt: self._wait_for_ai_confirmation(prompt, wait_type="post_run_inspection"),
        )
        self.model = build_chat_model(self.config.service_config, service_name=self.config.service_name)
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

    def poutput(self, value: Any) -> None:
        print(str(value))

    def perror(self, msg: object, *args: Any, **kwargs: Any) -> None:
        print(format_error_for_terminal(msg, project_root=self.project_root))

    def onecmd(self, line: str) -> bool:
        raw_text = str(line)
        if not raw_text.strip():
            return False
        text = raw_text.rstrip()
        handle_confirmation = getattr(self, "_handle_ai_confirmation_reply", None)
        if callable(handle_confirmation) and handle_confirmation(text):
            return False
        if self._is_agent_busy() and not self._command_allowed_while_busy(line):
            self.perror("AI 终端正在处理上一轮请求；请等待当前回复完成。")
            return False
        parsed_command = _parse_slash_command(text)
        if parsed_command is None:
            if text.startswith("/"):
                self.perror("AI 命令格式：必须写在行首，格式为 /command 或 /command <args>，命令名必须以英文字母开头。")
                return False
            self.default(text)
            return False
        command, arg = parsed_command
        normalized = command.lower().replace("-", "_")
        if normalized in {"exit", "back"}:
            return True
        if normalized == "quit":
            raise SystemExit(0)
        command_spec = SLASH_COMMANDS.get(normalized)
        method_name = command_spec["method"] if command_spec else None
        if method_name:
            method = getattr(self, method_name)
            method(arg)
            return False
        self.default(text)
        return False

    def default(self, line: str) -> None:
        text = getattr(line, "command_and_args", str(line)).strip()
        if not text:
            return
        if text.startswith("/") and self._handle_slash_command(text):
            return
        if self._current_interrupts():
            self.perror("当前有补丁审批等待处理；请先输入 /approve 或 /reject <原因>。")
            return
        self._run_agent_turn(text)

    def _wait_for_ai_confirmation(self, prompt: str, *, wait_type: str) -> bool:
        wait = AIConfirmationWait(prompt=str(prompt), wait_type=wait_type)
        with self._ai_confirmation_lock:
            if self._ai_confirmation is not None:
                raise RuntimeError("AI 模式已有一个等待确认的 plan。")
            self._ai_confirmation = wait
        self.poutput(_format_ai_confirmation_prompt(wait))
        wait.event.wait()
        with self._ai_confirmation_lock:
            if self._ai_confirmation is wait:
                self._ai_confirmation = None
        return bool(wait.accepted)

    def _handle_ai_confirmation_reply(self, text: str) -> bool:
        wait = self._current_ai_confirmation()
        if wait is None:
            return False
        decision = self._classify_ai_confirmation_reply(text, wait)
        if decision == "approve":
            wait.accepted = True
            wait.event.set()
            self.poutput("AI确认：已理解为继续。")
            return True
        if decision == "reject":
            wait.accepted = False
            wait.event.set()
            self.poutput("AI确认：已理解为停止。")
            return True
        self.poutput("AI确认：我还不能确定你的意思。请直接说明是继续还是停止。")
        return True

    def _classify_ai_confirmation_reply(self, text: str, wait: "AIConfirmationWait") -> str:
        try:
            messages = [
                (
                    "system",
                    "你是确认意图分类器。只判断用户是否同意继续一个正在等待人工确认的自动化 plan。"
                    "只能返回 JSON：{\"decision\":\"approve|reject|unclear\"}。"
                    "approve 表示用户同意继续、确认完成、允许下一步；"
                    "reject 表示用户要求停止、取消、不同意继续；"
                    "unclear 表示用户只是在提问、描述状态、犹豫或意图不明确。"
                    "不要执行任务，不要解释。",
                ),
                (
                    "user",
                    f"等待类型：{wait.wait_type}\n确认提示：{wait.prompt}\n用户回复：{text}",
                ),
            ]
            response = self.model.invoke(messages)
            raw = message_content_to_text(getattr(response, "content", response))
            parsed = json.loads(raw)
            decision = str(parsed.get("decision", "")).strip().lower()
            if decision in {"approve", "reject", "unclear"}:
                return decision
        except Exception:
            pass
        return classify_ai_confirmation_reply(text)

    def _current_ai_confirmation(self) -> "AIConfirmationWait | None":
        lock = getattr(self, "_ai_confirmation_lock", None)
        if lock is None:
            return None
        with lock:
            return self._ai_confirmation

    def _handle_slash_command(self, text: str) -> bool:
        parsed_command = _parse_slash_command(text)
        if parsed_command is None:
            if str(text).startswith("/"):
                self.perror("AI 命令格式：必须写在行首，格式为 /command 或 /command <args>，命令名必须以英文字母开头。")
                return True
            return False
        command, arg = parsed_command
        normalized = command.lower().replace("-", "_")
        if normalized in {"exit", "back"}:
            return True
        if normalized == "quit":
            raise SystemExit(0)
        command_spec = SLASH_COMMANDS.get(normalized)
        method_name = command_spec["method"] if command_spec else None
        if method_name:
            if self._is_agent_busy() and normalized not in BUSY_ALLOWED_COMMANDS:
                self.perror("AI 终端正在处理上一轮请求；请等待当前回复完成。")
                return True
            getattr(self, method_name)(arg)
            return True
        self.perror(f"未知 AI 终端命令：/{command}")
        return True

    def _run_agent_turn(self, text: str) -> None:
        if self._is_agent_busy():
            self.perror("AI 终端正在处理上一轮请求；请等待当前回复完成。")
            return
        text, attachments = self._prepare_input_attachments(text)
        with self._turn_lock:
            self._current_turn_id += 1
            turn_id = self._current_turn_id
            self._current_turn_text = text
        self._print_user_message(text)
        try:
            final_state, streamed = self._invoke_agent_text_streaming(text, attachments)
        except KeyboardInterrupt:
            self._finish_agent_turn(turn_id, error="AI 回复已被用户中断。")
            self.perror("AI 回复已被用户中断。")
            return
        except Exception as error:
            self._finish_agent_turn(turn_id, error=str(error))
            self._sync_current_session_index()
            self.perror(error)
            return

        if not self._finish_agent_turn(turn_id):
            return
        if attachments:
            self._clear_pending_attachments()
        self._last_error = ""
        self._sync_current_session_index()
        if self._print_pending_interrupt(final_state):
            return
        if streamed:
            return
        messages = list(final_state.get("messages", []))
        last_message = self._last_assistant_message(messages)
        if last_message:
            self._print_assistant_message(last_message)

    def ask_once(self, text: str) -> dict[str, Any]:
        """发送一条消息并等待 LangGraph agent 完成。"""
        normalized = text.strip()
        if not normalized:
            raise ValueError("ai ask 需要一条非空消息。")
        if self._is_agent_busy():
            raise RuntimeError("AI 终端正在处理上一轮请求；请等待当前轮次结束后再使用 ai ask。")
        if self._current_interrupts():
            raise RuntimeError("AI 终端有等待审批的操作；请进入交互式线程后 approve 或 reject。")

        normalized, attachments = self._prepare_input_attachments(normalized)
        try:
            final_state = self._invoke_agent_text(normalized, attachments)
        except Exception as error:
            self._last_error = str(error)
            self._sync_current_session_index()
            raise

        if attachments:
            self._clear_pending_attachments()
        self._last_error = ""
        self._sync_current_session_index()

        messages = list(final_state.get("messages", []))
        interrupts = extract_interrupts(final_state) or self._current_interrupts()
        return {
            "ok": True,
            "thread_id": self.thread_id,
            "model": self.model_name,
            "pending_approval": bool(interrupts),
            "approval_requests": interrupt_action_requests(interrupts),
            "assistant_message": self._last_assistant_message(messages),
            "messages": len(messages),
            "checkpoint_path": str(self.checkpoint_path),
            "context_state": self._context_state(),
        }

    def _invoke_agent_text(self, text: str, attachments: list[ImageAttachment]) -> dict[str, Any]:
        message = HumanMessage(
            content=build_human_message_content(text, attachments),
            additional_kwargs=build_human_message_additional_kwargs(attachments),
        )
        return self.graph.invoke(
            {"messages": [message]},
            config=self._graph_config(),
        )

    def _invoke_agent_text_streaming(
        self,
        text: str,
        attachments: list[ImageAttachment],
    ) -> tuple[dict[str, Any], bool]:
        message = HumanMessage(
            content=build_human_message_content(text, attachments),
            additional_kwargs=build_human_message_additional_kwargs(attachments),
        )
        return self._invoke_graph_streaming({"messages": [message]})

    def _invoke_graph_streaming(self, graph_input: Any) -> tuple[dict[str, Any], bool]:
        final_state: dict[str, Any] | None = None
        streamed = False
        suppress_stream_output = False
        indicator = self._start_thinking_indicator()
        markdown_renderer: MarkdownLiveRenderer | None = None
        render_markdown = self._should_render_stream_markdown()
        try:
            for event in self.graph.stream(
                graph_input,
                config=self._graph_config(),
                stream_mode=["messages", "values"],
            ):
                if self._current_agent_turn_cancelled():
                    suppress_stream_output = True
                mode, payload = _split_stream_event(event)
                if mode == "values" and isinstance(payload, dict):
                    final_state = payload
                    continue
                if mode != "messages":
                    continue
                if suppress_stream_output:
                    if markdown_renderer is not None:
                        markdown_renderer.finish()
                        markdown_renderer = None
                    if indicator is not None:
                        self._stop_thinking_indicator(indicator)
                        indicator = None
                    continue
                chunk_text = _stream_message_text(payload)
                if not chunk_text:
                    continue
                if not streamed:
                    self._stop_thinking_indicator(indicator)
                    indicator = None
                    if render_markdown:
                        markdown_renderer = MarkdownLiveRenderer()
                    else:
                        self._stream_response_text("AI> ")
                    streamed = True
                if markdown_renderer is not None:
                    markdown_renderer.push(chunk_text)
                else:
                    self._stream_response_text(chunk_text)
        finally:
            if markdown_renderer is not None:
                markdown_renderer.finish()
            if indicator is not None:
                self._stop_thinking_indicator(indicator)
        if streamed and markdown_renderer is None:
            self._stream_response_newline()
        if final_state is None:
            state = self.graph.get_state(self._graph_config())
            values = getattr(state, "values", {})
            final_state = values if isinstance(values, dict) else {}
        return final_state, streamed

    def _prepare_input_attachments(self, text: str) -> tuple[str, list[ImageAttachment]]:
        text, attachments, required = reconcile_pending_image_attachments(
            text,
            self._pending_attachments,
            self._pending_attachment_placeholder_required,
            preserve_when_absent=False,
        )
        self._pending_attachments = attachments
        self._pending_attachment_placeholder_required = required
        return text, list(attachments)

    def _clear_pending_attachments(self) -> None:
        self._pending_attachments.clear()
        self._pending_attachment_placeholder_required.clear()

    def _print_user_message(self, text: str) -> None:
        self.poutput(f"你> {format_user_terminal_message(text)}")

    def _print_assistant_message(self, text: str) -> None:
        if self._should_render_final_markdown():
            print("AI>")
            print(render_markdown_to_ansi(text), end="")
            return
        self.poutput(f"AI> {text}")

    def _should_render_stream_markdown(self) -> bool:
        return (
            getattr(self, "response_render_mode", "plain") == "markdown"
            and terminal_supports_rich_markdown()
        )

    def _should_render_final_markdown(self) -> bool:
        return (
            getattr(self, "response_render_mode", "plain") == "markdown"
            and terminal_supports_rich_markdown()
        )

    def close(self) -> None:
        wait: AIConfirmationWait | None = None
        lock = getattr(self, "_ai_confirmation_lock", None)
        if lock is not None:
            with lock:
                wait = self._ai_confirmation
                self._ai_confirmation = None
        if wait is not None and not wait.event.is_set():
            wait.accepted = False
            wait.event.set()
        self._close_checkpoint_connection()

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

    def _current_agent_turn_cancelled(self) -> bool:
        lock = getattr(self, "_turn_lock", None)
        if lock is None:
            return False
        with lock:
            return self._current_turn_id in self._cancelled_turn_ids

    def _command_allowed_while_busy(self, line: str) -> bool:
        text = str(line).rstrip()
        if not text:
            return True
        parsed_command = _parse_slash_command(text)
        if parsed_command is None:
            return False
        command = parsed_command[0].lower().replace("-", "_")
        return command in BUSY_ALLOWED_COMMANDS

    def _stream_response_text(self, text: str) -> None:
        lock = getattr(self, "_output_lock", None)
        if lock is None:
            print(text, end="", flush=True)
            return
        with lock:
            print(text, end="", flush=True)

    def _stream_response_newline(self) -> None:
        lock = getattr(self, "_output_lock", None)
        if lock is None:
            print("", flush=True)
            return
        with lock:
            print("", flush=True)

    def _start_thinking_indicator(self) -> Any:
        if not sys.stdout.isatty():
            return None
        indicator = _ThinkingIndicator(lock=getattr(self, "_output_lock", threading.Lock()))
        indicator.start()
        return indicator

    def _stop_thinking_indicator(self, indicator: Any) -> None:
        if indicator is not None:
            indicator.stop()

    def _read_ai_input_with_images(
        self,
        prompt: str,
        *,
        bottom_toolbar: Any | None = None,
        on_escape: Any | None = None,
    ) -> str:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.patch_stdout import patch_stdout

        bindings = KeyBindings()

        @bindings.add("backspace")
        @bindings.add("c-h")
        def _(event: Any) -> None:
            if not remove_image_placeholder_near_cursor(
                event.current_buffer,
                self._pending_attachments,
                prefer_before=True,
                placeholder_required=self._pending_attachment_placeholder_required,
            ):
                event.current_buffer.delete_before_cursor()

        @bindings.add("delete")
        def _(event: Any) -> None:
            if not remove_image_placeholder_near_cursor(
                event.current_buffer,
                self._pending_attachments,
                prefer_before=False,
                placeholder_required=self._pending_attachment_placeholder_required,
            ):
                event.current_buffer.delete()

        @bindings.add("c-j")
        @bindings.add("escape", "enter")
        @bindings.add("escape", "c-m")
        def _(event: Any) -> None:
            event.current_buffer.insert_text("\n")

        @bindings.add("escape")
        def _(event: Any) -> None:
            if callable(on_escape):
                on_escape()

        @bindings.add("enter")
        def _(event: Any) -> None:
            buffer = event.current_buffer
            if buffer.complete_state and buffer.complete_state.current_completion:
                buffer.apply_completion(buffer.complete_state.current_completion)
                return
            buffer.validate_and_handle()

        @bindings.add("up")
        def _(event: Any) -> None:
            if not select_completion_candidate(event.current_buffer, previous=True):
                event.current_buffer.auto_up(count=event.arg)

        @bindings.add("down")
        def _(event: Any) -> None:
            if not select_completion_candidate(event.current_buffer, previous=False):
                event.current_buffer.auto_down(count=event.arg)

        @bindings.add("<any>", filter=emacs_insert_mode | vi_insert_mode)
        def _(event: Any) -> None:
            snap_buffer_cursor_out_of_image_placeholder(event.current_buffer)
            buffer = event.current_buffer
            buffer.insert_text(event.data * event.arg)
            refresh_slash_completion(buffer)

        @bindings.add("escape", "v")
        @bindings.add("c-v")
        def _(event: Any) -> None:
            try:
                attachments = attach_clipboard_images(
                    self.project_root,
                    self.thread_id,
                    pending_count=len(self._pending_attachments),
                )
            except Exception as error:
                if _insert_clipboard_text(event.current_buffer):
                    return
                event.app.output.write(f"\r\n{format_error_for_terminal(error, project_root=self.project_root)}\r\n")
                return
            self._pending_attachments.extend(attachments)
            self._pending_attachment_placeholder_required.extend([True] * len(attachments))
            placeholders = [
                image_attachment_placeholder(index)
                for index in range(
                    len(self._pending_attachments) - len(attachments) + 1,
                    len(self._pending_attachments) + 1,
                )
            ]
            buffer = event.current_buffer
            prefix = "" if not buffer.text or buffer.text.endswith((" ", "\n")) else " "
            suffix = " " if buffer.text[buffer.cursor_position:] and not buffer.text[buffer.cursor_position:].startswith(" ") else ""
            buffer.insert_text(prefix + " ".join(placeholders) + suffix)

        @bindings.add("/")
        def _(event: Any) -> None:
            buffer = event.current_buffer
            buffer.insert_text("/")
            refresh_slash_completion(buffer)

        if self._ai_prompt_session is None:
            self._ai_prompt_session = PromptSession(history=InMemoryHistory(), erase_when_done=True)
            attach_image_placeholder_cursor_guard(self._ai_prompt_session.default_buffer)
        with patch_stdout():
            toolbar = bottom_toolbar() if callable(bottom_toolbar) else bottom_toolbar
            return self._ai_prompt_session.prompt(
                prompt,
                key_bindings=bindings,
                completer=SlashCommandCompleter(),
                complete_while_typing=True,
                complete_in_thread=True,
                complete_style=CompleteStyle.COLUMN,
                reserve_space_for_menu=0,
                enable_history_search=True,
                multiline=False,
                bottom_toolbar=toolbar or None,
                lexer=ImagePlaceholderLexer(),
                style=AI_INPUT_STYLE,
            )


class SlashCommandCompleter(Completer):
    def get_completions(self, document: Any, complete_event: Any) -> Any:
        text = document.text_before_cursor
        if not _is_slash_completion_context(document.text, document.cursor_position):
            return
        command_text = text[1:]
        if " " in command_text:
            return
        prefix = command_text.lower()
        for name, spec in sorted(SLASH_COMMANDS.items()):
            if name not in SLASH_COMPLETION_COMMANDS:
                continue
            if not name.startswith(prefix):
                continue
            yield Completion(
                "/" + name,
                start_position=-len(text),
                display="/" + name,
                display_meta=spec["description"],
            )


def refresh_slash_completion(buffer: Any) -> None:
    if _is_slash_completion_context(buffer.text, buffer.cursor_position):
        buffer.start_completion(select_first=False)
        return
    complete_state = getattr(buffer, "complete_state", None)
    if complete_state is not None:
        buffer.cancel_completion()


@dataclass
class AIConfirmationWait:
    prompt: str
    wait_type: str
    event: Any
    accepted: bool | None = None

    def __init__(self, *, prompt: str, wait_type: str) -> None:
        self.prompt = prompt
        self.wait_type = wait_type
        self.event = threading.Event()
        self.accepted = None


def _format_ai_confirmation_prompt(wait: AIConfirmationWait) -> str:
    label = "运行后检查" if wait.wait_type == "post_run_inspection" else "人工确认"
    return f"AI> [{label}] {wait.prompt}\n你可以直接用自然语言回复，我会判断是继续还是停止。"


def classify_ai_confirmation_reply(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text).strip().lower())
    if not normalized:
        return "unclear"
    reject_tokens = (
        "不要继续",
        "别继续",
        "不继续",
        "不能继续",
        "别导入",
        "不要导入",
        "不导入",
        "不要",
        "不行",
        "不可以",
        "不确认",
        "不同意",
        "有问题",
        "不对",
        "停止",
        "终止",
        "取消",
        "算了",
        "停",
        "退出",
        "否",
        "no",
        "stop",
        "cancel",
        "reject",
        "abort",
        "quit",
        "exit",
    )
    approve_tokens = (
        "继续",
        "接着",
        "接下来",
        "下一步",
        "确认",
        "可以",
        "可",
        "没问题",
        "没毛病",
        "通过",
        "同意",
        "批准",
        "好了",
        "好啦",
        "好",
        "行",
        "对",
        "看到了",
        "完成",
        "完成了",
        "弄吧",
        "去做",
        "导入",
        "追加导入",
        "开始",
        "执行",
        "yes",
        "y",
        "ok",
        "okay",
        "go",
        "continue",
        "proceed",
        "approve",
        "approved",
        "done",
    )
    if any(token in normalized for token in reject_tokens):
        return "reject"
    if any(token in normalized for token in approve_tokens):
        return "approve"
    return "unclear"


class _ThinkingIndicator:
    frames = ("AI 正在思考", "AI 正在思考.", "AI 正在思考..", "AI 正在思考...")

    def __init__(self, *, lock: threading.Lock) -> None:
        self.lock = lock
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ai-terminal-thinking-indicator", daemon=True)
        self.started = False

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)
        if self.started:
            self._clear_line()

    def _run(self) -> None:
        frame_index = 0
        while not self.stop_event.is_set():
            with self.lock:
                print(f"\r{self.frames[frame_index % len(self.frames)]:<32}", end="", flush=True)
            self.started = True
            frame_index += 1
            self.stop_event.wait(0.35)

    def _clear_line(self) -> None:
        with self.lock:
            print("\r" + " " * 32 + "\r", end="", flush=True)


class ImagePlaceholderLexer(Lexer):
    def lex_document(self, document: Document) -> Any:
        lines = document.lines

        def get_line(lineno: int) -> list[tuple[str, str]]:
            if lineno >= len(lines):
                return []
            return style_image_placeholders(lines[lineno])

        return get_line


def style_image_placeholders(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in IMAGE_PLACEHOLDER_RE.finditer(text):
        if match.start() > cursor:
            parts.append(("", text[cursor : match.start()]))
        parts.append((IMAGE_PLACEHOLDER_STYLE, match.group(0)))
        cursor = match.end()
    if cursor < len(text):
        parts.append(("", text[cursor:]))
    return parts


def remove_image_placeholder_near_cursor(
    buffer: Any,
    attachments: list[ImageAttachment],
    *,
    prefer_before: bool,
    placeholder_required: list[bool] | None = None,
) -> bool:
    text = str(buffer.text)
    cursor = int(buffer.cursor_position)
    match = find_image_placeholder_for_delete(text, cursor, prefer_before=prefer_before)
    if match is None:
        return False
    start, end, index = match
    if index < 1 or index > len(attachments):
        return False
    next_text = text[:start] + text[end:]
    required = placeholder_required or [True] * len(attachments)
    next_text, next_attachments, next_required = reconcile_pending_image_attachments(
        next_text,
        attachments,
        required,
        preserve_when_absent=False,
    )
    attachments[:] = next_attachments
    if placeholder_required is not None:
        placeholder_required[:] = next_required
    buffer.text = next_text
    buffer.cursor_position = min(start, len(next_text))
    return True


def find_image_placeholder_for_delete(
    text: str,
    cursor: int,
    *,
    prefer_before: bool,
) -> tuple[int, int, int] | None:
    matches = list(IMAGE_PLACEHOLDER_RE.finditer(text))
    if prefer_before:
        for match in reversed(matches):
            if match.end() == cursor or match.start() < cursor <= match.end():
                return match.start(), match.end(), int(match.group(1))
        return None
    for match in matches:
        if match.start() == cursor or match.start() <= cursor < match.end():
            return match.start(), match.end(), int(match.group(1))
    return None


def attach_image_placeholder_cursor_guard(buffer: Any) -> None:
    if getattr(buffer, "_ai_image_placeholder_cursor_guard_attached", False):
        return

    state = {"last_position": int(getattr(buffer, "cursor_position", 0)), "guarding": False}

    def guard_cursor(current_buffer: Any) -> None:
        if state["guarding"]:
            state["last_position"] = int(current_buffer.cursor_position)
            return
        cursor = int(current_buffer.cursor_position)
        next_cursor = snap_cursor_out_of_image_placeholder(
            str(current_buffer.text),
            cursor,
            previous_cursor=int(state["last_position"]),
        )
        if next_cursor != cursor:
            state["guarding"] = True
            try:
                current_buffer.cursor_position = next_cursor
            finally:
                state["guarding"] = False
        state["last_position"] = int(current_buffer.cursor_position)

    buffer.on_cursor_position_changed += guard_cursor
    setattr(buffer, "_ai_image_placeholder_cursor_guard_attached", True)


def snap_cursor_out_of_image_placeholder(
    text: str,
    cursor: int,
    *,
    previous_cursor: int | None = None,
) -> int:
    for match in IMAGE_PLACEHOLDER_RE.finditer(text):
        start = match.start()
        end = match.end()
        if start < cursor < end:
            if previous_cursor is not None:
                if previous_cursor <= start:
                    return end
                if previous_cursor >= end:
                    return start
            return start if cursor - start <= end - cursor else end
    return cursor


def snap_buffer_cursor_out_of_image_placeholder(buffer: Any) -> bool:
    cursor = int(buffer.cursor_position)
    next_cursor = snap_cursor_out_of_image_placeholder(str(buffer.text), cursor)
    if next_cursor == cursor:
        return False
    buffer.cursor_position = next_cursor
    return True


def select_completion_candidate(buffer: Any, *, previous: bool) -> bool:
    state = getattr(buffer, "complete_state", None)
    completions = list(getattr(state, "completions", []) or [])
    if not completions:
        return False
    if getattr(state, "complete_index", None) is None:
        buffer.go_to_completion(len(completions) - 1 if previous else 0)
    elif previous:
        buffer.complete_previous()
    else:
        buffer.complete_next()
    return True


def _is_slash_completion_context(text: str, cursor: int) -> bool:
    before_cursor = text[:cursor]
    return before_cursor.startswith("/") and "\n" not in before_cursor and " " not in before_cursor


def _parse_slash_command(text: str) -> tuple[str, str] | None:
    match = SLASH_COMMAND_RE.fullmatch(str(text).rstrip())
    if match is None:
        return None
    return match.group(1), (match.group(2) or "").strip()


def reconcile_image_placeholders(
    text: str,
    attachments: list[ImageAttachment],
    *,
    preserve_when_absent: bool = True,
) -> tuple[str, list[ImageAttachment]]:
    text, attachments, _ = reconcile_pending_image_attachments(
        text,
        attachments,
        [True] * len(attachments),
        preserve_when_absent=preserve_when_absent,
    )
    return text, attachments


def reconcile_pending_image_attachments(
    text: str,
    attachments: list[ImageAttachment],
    placeholder_required: list[bool],
    *,
    preserve_when_absent: bool = True,
) -> tuple[str, list[ImageAttachment], list[bool]]:
    if not attachments:
        return text, [], []

    required = list(placeholder_required[: len(attachments)])
    if len(required) < len(attachments):
        required.extend([True] * (len(attachments) - len(required)))

    matches = list(IMAGE_PLACEHOLDER_RE.finditer(text))
    if not matches:
        kept = [
            (attachment, is_required)
            for attachment, is_required in zip(attachments, required, strict=True)
            if preserve_when_absent or not is_required
        ]
        return text, [item[0] for item in kept], [item[1] for item in kept]

    kept_attachments: list[ImageAttachment] = []
    kept_required: list[bool] = []
    next_index_by_old_index: dict[int, int] = {}
    used_old_indexes: set[int] = set()
    for match in matches:
        old_index = int(match.group(1))
        if old_index < 1 or old_index > len(attachments) or old_index in used_old_indexes:
            continue
        used_old_indexes.add(old_index)
        kept_attachments.append(attachments[old_index - 1])
        kept_required.append(required[old_index - 1])
        next_index_by_old_index[old_index] = len(kept_attachments)

    for old_index, (attachment, is_required) in enumerate(zip(attachments, required, strict=True), start=1):
        if is_required or old_index in used_old_indexes:
            continue
        kept_attachments.append(attachment)
        kept_required.append(is_required)
        next_index_by_old_index[old_index] = len(kept_attachments)

    if not kept_attachments:
        return text, [], []

    def replace(match: re.Match[str]) -> str:
        old_index = int(match.group(1))
        next_index = next_index_by_old_index.get(old_index)
        if next_index is None:
            return match.group(0)
        return image_attachment_placeholder(next_index)

    return IMAGE_PLACEHOLDER_RE.sub(replace, text), kept_attachments, kept_required


def format_user_terminal_message(text: str) -> str:
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\n... ")


def _split_stream_event(event: Any) -> tuple[str | None, Any]:
    if isinstance(event, tuple) and len(event) == 2 and isinstance(event[0], str):
        return event[0], event[1]
    return None, event


def _stream_message_text(payload: Any) -> str:
    message = payload[0] if isinstance(payload, tuple) and payload else payload
    if not _is_ai_stream_message(message):
        return ""
    content = getattr(message, "content", "")
    return message_content_to_text(content)


def _is_ai_stream_message(message: Any) -> bool:
    if isinstance(message, AIMessageChunk):
        return True
    return str(getattr(message, "type", "")).lower() == "ai"


@wrap_model_call(state_schema=AITerminalState, name="AITerminalImageAttachmentMiddleware")
def inject_image_attachments_for_model(
    request: ModelRequest[Any],
    handler: Any,
) -> ModelResponse[Any]:
    messages = expand_messages_image_attachments_for_model(list(request.messages))
    return handler(request.override(messages=messages))


def _insert_clipboard_text(buffer: Any) -> bool:
    try:
        import pyperclip

        text = pyperclip.paste()
    except Exception:
        return False
    if not isinstance(text, str) or not text:
        return False
    buffer.insert_text(text)
    return True
