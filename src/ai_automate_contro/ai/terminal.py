from __future__ import annotations

import json
import sqlite3
import threading
import warnings
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ai_automate_contro.ai.session_compression import install_langgraph_warning_filter

install_langgraph_warning_filter()

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessageChunk, HumanMessage

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
    image_attachment_placeholder,
)
from ai_automate_contro.ai.langgraph_tools import build_langchain_tools
from ai_automate_contro.ai.file_search import assert_ripgrep_available
from ai_automate_contro.ai.terminal_approval import AITerminalApprovalMixin
from ai_automate_contro.ai.terminal_commands import AITerminalCommandsMixin
from ai_automate_contro.ai.terminal_config import build_chat_model, load_ai_terminal_config
from ai_automate_contro.ai.terminal_events import AITerminalEvent, AITerminalEventSink
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
from ai_automate_contro.ai.response_parsing import parse_json_response
from ai_automate_contro.ai.prompts.terminal import build_system_prompt
from ai_automate_contro.ai.terminal_state import AITerminalStateMixin
from ai_automate_contro.app.errors import format_error_for_terminal, is_external_ai_service_error


SLASH_COMMAND_RE = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.*))?$")
BUSY_ALLOWED_COMMANDS = {"help", "keyboard", "pending", "plan", "status", "todo"}
ASK_ONCE_CONFIRMATION_TIMEOUT_SECONDS = 1.5
SLASH_COMMANDS: dict[str, dict[str, str]] = {
    "approve": {"method": "do_approve", "description": "批准当前等待的受保护补丁操作"},
    "back": {"method": "", "description": "退出当前客户端"},
    "compact": {"method": "do_compress", "description": "压缩并归档当前会话"},
    "compress": {"method": "do_compress", "description": "压缩并归档当前会话"},
    "exit": {"method": "", "description": "退出当前客户端"},
    "help": {"method": "do_help", "description": "查看 AI 会话命令"},
    "history": {"method": "do_history", "description": "查看最近几条会话消息"},
    "image": {"method": "do_image", "description": "把图片文件加入下一条消息"},
    "keyboard": {"method": "do_keyboard", "description": "查看键盘快捷键和输入说明"},
    "new": {"method": "do_new", "description": "新建一个会话"},
    "pending": {"method": "do_pending", "description": "查看等待审批的受保护操作"},
    "plan": {"method": "do_plan", "description": "查看当前 AI 工作计划"},
    "quit": {"method": "", "description": "关闭客户端"},
    "reject": {"method": "do_reject", "description": "拒绝当前等待审批的操作"},
    "resume": {"method": "do_resume", "description": "恢复已保存的会话"},
    "sessions": {"method": "do_sessions", "description": "列出已保存会话"},
    "status": {"method": "do_status", "description": "查看当前线程、上下文、checkpoint 和待发送图片"},
    "todo": {"method": "do_plan", "description": "查看当前 AI 工作计划"},
}
IMAGE_PLACEHOLDER_RE = re.compile(r"\[(?:图片|Image) #(\d+)\]")


class AITerminal(
    AITerminalApprovalMixin,
    AITerminalCommandsMixin,
    AITerminalStateMixin,
):
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
        self._ai_confirmation_lock = threading.Lock()
        self._ai_confirmation: AIConfirmationWait | None = None
        self._ask_once_mode = False
        self._client_event_sink_local = threading.local()
        self._client_event_sink: AITerminalEventSink | None = None
        self._approval_resume_active = False
        self._last_error: str = ""
        self._pending_attachments: list[ImageAttachment] = []
        self._pending_attachment_placeholder_required: list[bool] = []
        self.checkpoint_path = self.project_root / ".keygen" / "ai-terminal-checkpoints.sqlite"
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_connection = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpoint_connection)
        self.tools = build_langchain_tools(
            self.project_root,
            latest_user_approved=self._latest_user_approved,
            before_tool_call=self._before_tool_call,
            after_tool_call=self._after_tool_call,
            thread_id_provider=lambda: self.thread_id,
            manual_confirmation_handler=lambda prompt: self._wait_for_ai_confirmation(prompt, wait_type="manual_confirm"),
            inspection_confirmation_handler=lambda prompt: self._wait_for_ai_confirmation(prompt, wait_type="post_run_inspection"),
            run_event_handler=self._handle_plan_run_event,
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
    def _emit_system_output(self, value: Any) -> None:
        self._emit_event(AITerminalEvent("system_output", text=str(value)))

    def _emit_error(self, msg: object) -> None:
        text = self.format_error_message(msg)
        self._last_error = text
        self._emit_activity("遇到错误，准备停止或等待处理", category="review", phase="failed", source_kind="error")
        self._emit_event(AITerminalEvent("error", text=text))

    def format_error_message(self, msg: object) -> str:
        text = format_error_for_terminal(msg, project_root=self.project_root)
        if isinstance(msg, BaseException) and is_external_ai_service_error(msg):
            text = self._format_ai_service_error(text)
        return text

    def _format_ai_service_error(self, text: str) -> str:
        service = getattr(self.config, "service_name", "default")
        service_config = getattr(self.config, "service_config", {})
        model = service_config.get("model", self.model_name) if isinstance(service_config, dict) else self.model_name
        base_url = service_config.get("base_url", "") if isinstance(service_config, dict) else ""
        lines = [text, "", "AI service:"]
        lines.append(f"  service={service}")
        lines.append(f"  model={model}")
        if base_url:
            lines.append(f"  base_url={base_url}")
        lines.extend(
            [
                "",
                "这表示请求已经发到配置的 OpenAI-compatible 服务，但服务返回了错误或超时。",
                "项目不会自动降级、换模型或改协议；请检查服务额度、模型名、base_url、网络和服务状态。",
            ]
        )
        return "\n".join(lines)

    @contextmanager
    def client_event_sink(self, sink: AITerminalEventSink) -> Iterator[None]:
        local = getattr(self, "_client_event_sink_local", None)
        if local is None:
            local = threading.local()
            self._client_event_sink_local = local
        previous_sink = getattr(local, "sink", None)
        previous_fallback_sink = getattr(self, "_client_event_sink", None)
        local.sink = sink
        self._client_event_sink = sink
        try:
            yield
        finally:
            if previous_sink is None:
                try:
                    del local.sink
                except AttributeError:
                    pass
            else:
                local.sink = previous_sink
            self._client_event_sink = previous_fallback_sink

    def run_event_turn(self, line: str, sink: AITerminalEventSink) -> bool:
        """Run one UI client turn and emit structured events to the supplied sink."""
        with self.client_event_sink(sink):
            self.emit_client_status_snapshot()
            self._emit_activity("开始处理用户请求", category="thinking", phase="start", source_kind="turn")
            should_exit = self.handle_input(line)
            if should_exit:
                self._emit_event(AITerminalEvent("exit_requested", text="已收到退出命令。"))
            self._emit_activity("本轮事件处理完成", category="review", phase="done", source_kind="turn")
            self.emit_client_status_snapshot()
            return bool(should_exit)

    def client_status_snapshot(self) -> dict[str, Any]:
        """Return a small UI-safe status snapshot for agent clients."""
        try:
            pending_approval = bool(self._current_interrupts())
        except Exception:
            pending_approval = False
        return {
            "project_root": str(self.project_root),
            "service": self.config.service_name,
            "model": self.model_name,
            "thread_id": self.thread_id,
            "busy": self._is_agent_busy(),
            "pending_approval": pending_approval,
            "pending_attachments": len(self._pending_attachments),
            "context_state": self._context_state(),
            "last_error": self._last_error,
        }

    def emit_client_status_snapshot(self) -> None:
        self._emit_event(AITerminalEvent("context_updated", data=self.client_status_snapshot()))

    def _emit_event(self, event: AITerminalEvent) -> bool:
        local = getattr(self, "_client_event_sink_local", None)
        sink = getattr(local, "sink", None) if local is not None else None
        if sink is None:
            sink = getattr(self, "_client_event_sink", None)
        if sink is None:
            return False
        sink(event)
        return True

    def handle_input(self, line: str) -> bool:
        raw_text = str(line)
        if not raw_text.strip():
            return False
        text = raw_text.rstrip()
        handle_confirmation = getattr(self, "_handle_ai_confirmation_reply", None)
        if callable(handle_confirmation) and handle_confirmation(text):
            return False
        parsed_command = _parse_slash_command(text)
        if parsed_command is None:
            if text.startswith("/"):
                self._emit_error("AI 命令格式：必须写在行首，格式为 /command 或 /command <args>，命令名必须以英文字母开头。")
                return False
            if self._is_agent_busy():
                self._emit_error("AI 正在处理上一轮请求；请等待当前回复完成。")
                return False
            self.handle_user_request(text)
            return False
        command, arg = parsed_command
        normalized = command.lower().replace("-", "_")
        if self._is_agent_busy() and normalized not in BUSY_ALLOWED_COMMANDS:
            self._emit_error("AI 正在处理上一轮请求；请等待当前回复完成。")
            return False
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
        self.handle_user_request(text)
        return False

    def handle_user_request(self, line: str) -> None:
        raw_text = str(getattr(line, "command_and_args", str(line)))
        if not raw_text.strip():
            return
        text = raw_text.rstrip()
        if text.startswith("/") and self._handle_slash_command(text):
            return
        if self._current_interrupts():
            self._emit_error("当前有补丁审批等待处理；请先输入 /approve 或 /reject <原因>。")
            return
        self._run_agent_turn(text)

    def _wait_for_ai_confirmation(self, prompt: str, *, wait_type: str) -> bool:
        wait = AIConfirmationWait(prompt=str(prompt), wait_type=wait_type)
        with self._ai_confirmation_lock:
            if self._ai_confirmation is not None:
                raise RuntimeError("AI 模式已有一个等待确认的 plan。")
        self._ai_confirmation = wait
        self._emit_activity("等待用户确认", category="run", phase="start", source_kind="approval_requested")
        self._emit_event(AITerminalEvent("approval_requested", text=_format_ai_confirmation_prompt(wait)))
        if self._ask_once_mode:
            wait.event.wait(timeout=ASK_ONCE_CONFIRMATION_TIMEOUT_SECONDS)
            if not wait.event.is_set():
                wait.accepted = False
                with self._ai_confirmation_lock:
                    if self._ai_confirmation is wait:
                        self._ai_confirmation = None
                raise RuntimeError(
                    "当前 AI 请求已经启动需要人工确认的可见 Playwright 浏览器流程。"
                    "脚本化 ai ask 不会等待人工操作，也不能在进程结束后保留可继续接管的浏览器。"
                    "请在 Textual 客户端里重新发起这类需要人工介入的任务，"
                    "并在同一个正在运行的客户端和 Playwright 浏览器窗口中完成操作后回复“继续”。"
                )
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
            self._emit_system_output("确认：已理解为继续。")
            return True
        if decision == "reject":
            wait.accepted = False
            wait.event.set()
            self._emit_system_output("确认：已理解为停止。")
            return True
        self._emit_system_output("确认：我还不能确定你的意思。请直接说明是继续还是停止。")
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
            parsed = parse_json_response(raw)
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
                self._emit_error("AI 命令格式：必须写在行首，格式为 /command 或 /command <args>，命令名必须以英文字母开头。")
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
                self._emit_error("AI 正在处理上一轮请求；请等待当前回复完成。")
                return True
            getattr(self, method_name)(arg)
            return True
        self._emit_error(f"未知 AI 会话命令：/{command}")
        return True

    def _run_agent_turn(self, text: str) -> None:
        if self._is_agent_busy():
            self._emit_error("AI 正在处理上一轮请求；请等待当前回复完成。")
            return
        text, attachments = self._prepare_input_attachments(text)
        with self._turn_lock:
            self._current_turn_id += 1
            turn_id = self._current_turn_id
            self._current_turn_text = text
        self._emit_user_message(text)
        try:
            final_state, streamed = self._invoke_agent_text_streaming(text, attachments, turn_id=turn_id)
        except KeyboardInterrupt:
            self._finish_agent_turn(turn_id, error="AI 回复已被用户中断。")
            self._emit_error("AI 回复已被用户中断。")
            return
        except Exception as error:
            self._finish_agent_turn(turn_id, error=str(error))
            self._sync_current_session_index()
            self._emit_error(error)
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
            self._emit_assistant_message(last_message)

    def ask_once(self, text: str, event_sink: AITerminalEventSink | None = None) -> dict[str, Any]:
        """发送一条消息并等待 LangGraph agent 完成。"""
        normalized = text.strip()
        if not normalized:
            raise ValueError("ai ask 需要一条非空消息。")
        if self._is_agent_busy():
            raise RuntimeError("AI 正在处理上一轮请求；请等待当前轮次结束后再使用 ai ask。")
        if self._current_interrupts():
            raise RuntimeError("AI 会话有等待审批的操作；请进入 Textual 客户端后输入 /approve 或 /reject。")

        previous_ask_once_mode = self._ask_once_mode
        self._ask_once_mode = True
        normalized, attachments = self._prepare_input_attachments(normalized)
        with self.client_event_sink(event_sink) if event_sink is not None else _null_event_sink():
            self.emit_client_status_snapshot()
            self._emit_activity("开始处理脚本化 AI 请求", category="thinking", phase="start", source_kind="turn")
            try:
                final_state = self._invoke_agent_text(normalized, attachments)
            except Exception as error:
                self._last_error = str(error)
                self._sync_current_session_index()
                self._emit_error(error)
                raise
            finally:
                self._ask_once_mode = previous_ask_once_mode

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
        *,
        turn_id: int,
    ) -> tuple[dict[str, Any], bool]:
        message = HumanMessage(
            content=build_human_message_content(text, attachments),
            additional_kwargs=build_human_message_additional_kwargs(attachments),
        )
        return self._invoke_graph_streaming({"messages": [message]}, turn_id=turn_id)

    def _invoke_graph_streaming(self, graph_input: Any, *, turn_id: int | None = None) -> tuple[dict[str, Any], bool]:
        final_state: dict[str, Any] | None = None
        streamed = False
        suppress_stream_output = False
        indicator = self._start_thinking_indicator()
        try:
            for event in self.graph.stream(
                graph_input,
                config=self._graph_config(),
                stream_mode=["messages", "values"],
            ):
                if self._stream_turn_cancelled(turn_id):
                    suppress_stream_output = True
                    if turn_id is not None:
                        break
                mode, payload = _split_stream_event(event)
                if mode == "values" and isinstance(payload, dict):
                    final_state = payload
                    continue
                if mode != "messages":
                    continue
                if suppress_stream_output:
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
                    streamed = True
                self._stream_response_text(chunk_text)
        finally:
            if indicator is not None:
                self._stop_thinking_indicator(indicator)
        if streamed and not suppress_stream_output:
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

    def _emit_user_message(self, text: str) -> None:
        return

    def _emit_assistant_message(self, text: str) -> None:
        if self._emit_event(AITerminalEvent("assistant_delta", text=str(text))):
            self._emit_event(AITerminalEvent("assistant_done"))

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
        return self._agent_turn_cancelled(None)

    def _stream_turn_cancelled(self, turn_id: int | None) -> bool:
        if turn_id is None:
            checker = getattr(self, "_current_agent_turn_cancelled", None)
            if callable(checker):
                return bool(checker())
        return self._agent_turn_cancelled(turn_id)

    def _agent_turn_cancelled(self, turn_id: int | None) -> bool:
        lock = getattr(self, "_turn_lock", None)
        if lock is None:
            return False
        with lock:
            target_turn_id = self._current_turn_id if turn_id is None else turn_id
            return target_turn_id in self._cancelled_turn_ids

    def _command_allowed_while_busy(self, line: str) -> bool:
        text = str(line).rstrip()
        if not text:
            return True
        parsed_command = _parse_slash_command(text)
        if parsed_command is None:
            return False
        command = parsed_command[0].lower().replace("-", "_")
        return command in BUSY_ALLOWED_COMMANDS

    def can_handle_input_during_turn(self, line: str) -> bool:
        if self._current_ai_confirmation() is not None:
            return True
        return self._command_allowed_while_busy(line)

    def _stream_response_text(self, text: str) -> None:
        self._emit_event(AITerminalEvent("assistant_delta", text=str(text)))

    def _stream_response_newline(self) -> None:
        self._emit_event(AITerminalEvent("assistant_done"))

    def _start_thinking_indicator(self) -> Any:
        self._emit_event(AITerminalEvent("status", text="正在思考"))
        return None

    def _stop_thinking_indicator(self, indicator: Any) -> None:
        if indicator is not None:
            indicator.stop()


def check_ai_terminal_service(
    project_root: Path,
    *,
    service: str = "default",
    thread_id: str = "ai-check",
    message: str = "只回复 ok",
) -> dict[str, Any]:
    """Send one real AI request through the same terminal path used by the Textual client."""
    terminal: AITerminal | None = None
    try:
        terminal = AITerminal(project_root, service=service, thread_id=thread_id)
        result = terminal.ask_once(message)
        return {
            "ok": True,
            "check": "ai_terminal_service",
            "service": terminal.config.service_name,
            "model": terminal.model_name,
            "thread_id": terminal.thread_id,
            "assistant_message": result.get("assistant_message", ""),
            "pending_approval": bool(result.get("pending_approval")),
            "checkpoint_path": result.get("checkpoint_path", ""),
            "context_state": result.get("context_state", {}),
        }
    except Exception as error:
        if terminal is not None:
            formatted_error = terminal.format_error_message(error)
            model = terminal.model_name
            resolved_service = terminal.config.service_name
            service_config = terminal.config.service_config
        else:
            formatted_error = format_error_for_terminal(error, project_root=project_root)
            model = ""
            resolved_service = service
            service_config = {}
        base_url = service_config.get("base_url", "") if isinstance(service_config, dict) else ""
        return {
            "ok": False,
            "check": "ai_terminal_service",
            "service": resolved_service,
            "model": model,
            "base_url": base_url,
            "thread_id": thread_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "formatted_error": formatted_error,
        }
    finally:
        if terminal is not None:
            terminal.close()


@contextmanager
def _null_event_sink() -> Iterator[None]:
    yield


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
    guidance = "你可以直接用自然语言回复，我会判断是继续还是停止。"
    if wait.wait_type == "manual_confirm":
        guidance = "请在当前已经打开的 Playwright 浏览器窗口完成操作；完成后回到这里输入“继续”，要停止就输入“停止”。"
    elif wait.wait_type == "post_run_inspection":
        guidance = "请检查当前 Playwright 浏览器窗口和运行产物；确认通过后输入“继续”，要停止就输入“停止”。"
    return f"[{label}] {wait.prompt}\n{guidance}"


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
