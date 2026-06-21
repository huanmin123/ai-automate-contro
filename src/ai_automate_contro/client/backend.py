from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol

from ai_automate_contro.ai.terminal_events import AITerminalEvent
from ai_automate_contro.app.errors import format_error_for_terminal
from ai_automate_contro.client.events import ClientEvent


INTERRUPT_GRACE_SECONDS = 1.0
CONFIRM_CURRENT_WAIT = "confirm_current_wait"
FEEDBACK_OR_CORRECTION = "feedback_or_correction"
ACTIVE_TURN_INPUT_INTENTS = {CONFIRM_CURRENT_WAIT, FEEDBACK_OR_CORRECTION}


class AgentClientBackend(Protocol):
    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        """Yield UI-safe events for one user message."""

    async def submit_during_turn(self, message: str) -> bool:
        """Handle input that belongs to the active turn, such as manual confirmation."""

    async def confirm_active_wait(self, message: str) -> AsyncIterator[ClientEvent]:
        """Confirm, stop, or close the current visible wait and yield any resulting events."""

    async def classify_active_turn_input(self, message: str, *, context: dict[str, Any] | None = None) -> str:
        """Classify whether busy-turn input confirms the wait or corrects the task."""

    async def attach_clipboard_images(self) -> list[str]:
        """Attach images from the clipboard and return placeholders to insert in the composer."""

    async def status_snapshot(self) -> dict[str, Any]:
        """Return a small UI-safe status snapshot for the client chrome."""

    async def check_service(self, message: str = "只回复 ok") -> dict[str, Any]:
        """Send one real AI request for connectivity diagnostics."""

    async def interrupt(self) -> ClientEvent:
        """Request cancellation of the active AI turn."""

    async def close(self) -> None:
        """Release backend resources."""


class FakeAgentBackend:
    """Deterministic backend used by the new client tests."""

    def __init__(self, *, response: str | None = None, delay: float = 0.0) -> None:
        self.response = response or "你好，我在。\n\n我可以帮你创建、运行、校验和调试 plan。"
        self.delay = delay

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        yield ClientEvent("status", text="正在处理")
        if "计划" in message or "todo" in message.lower():
            yield ClientEvent("activity", text="更新工作计划", data={"category": "plan", "phase": "done"})
            yield ClientEvent(
                "work_plan_updated",
                text="当前工作计划：0/3 完成",
                data={
                    "summary": "演示复杂任务计划",
                    "items": [
                        {"title": "确认目标", "status": "completed"},
                        {"title": "检查工具输出", "status": "in_progress"},
                        {"title": "总结结果", "status": "pending"},
                    ],
                },
            )
        if "工具" in message or "weather" in message.lower() or "天气" in message:
            yield ClientEvent("activity", text="准备调用 inspect_web_page", data={"category": "tool", "phase": "start"})
            yield ClientEvent("tool_started", title="inspect_web_page", text="url=https://example.com")
            if self.delay:
                await asyncio.sleep(self.delay)
            yield ClientEvent("tool_finished", title="inspect_web_page", text="发现登录字段/验证信号")
            yield ClientEvent("activity", text="完成 inspect_web_page", data={"category": "tool", "phase": "done"})
        if "审批" in message:
            yield ClientEvent(
                "approval_requested",
                text="AI 请求执行受保护工具。\n输入 /approve 批准执行。",
                data={"approval_kind": "tool_approval"},
            )
        if "错误" in message:
            yield ClientEvent("error", text="模拟错误")
        for chunk in _chunk_text(self.response, size=3):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield ClientEvent("assistant_delta", text=chunk)
        yield ClientEvent("assistant_done")

    async def close(self) -> None:
        return None

    async def submit_during_turn(self, message: str) -> bool:
        return False

    async def confirm_active_wait(self, message: str) -> AsyncIterator[ClientEvent]:
        if False:
            yield ClientEvent("status", text="")
        return

    async def classify_active_turn_input(self, message: str, *, context: dict[str, Any] | None = None) -> str:
        return FEEDBACK_OR_CORRECTION

    async def attach_clipboard_images(self) -> list[str]:
        return []

    async def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": "fake",
            "busy": False,
            "pending_approval": False,
            "context_state": {},
        }

    async def check_service(self, message: str = "只回复 ok") -> dict[str, Any]:
        return {
            "ok": True,
            "check": "fake_ai_service",
            "service": "fake",
            "model": "fake",
            "thread_id": "fake",
            "assistant_message": "ok",
        }

    async def interrupt(self) -> ClientEvent:
        return ClientEvent("interrupted", text="已中断当前任务。")


class AITerminalBackend:
    """Event backend that feeds the Textual client from the LangGraph AI runtime."""

    def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
        self.project_root = project_root
        self.service = service
        self._base_thread_id = thread_id
        self.thread_id = thread_id
        self._terminal: Any | None = None
        self._active_queue: asyncio.Queue[ClientEvent | None] | None = None
        self._active_worker: asyncio.Task[None] | None = None
        self._turn_interrupted = False
        self._retired_terminals: set[int] = set()
        self._retired_workers: set[asyncio.Task[Any]] = set()
        self._needs_intervention_fork = False
        self._thread_fork_count = 0
        self._last_stable_state: dict[str, Any] | None = None
        self._fork_seed_state: dict[str, Any] | None = None

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        await self._prepare_interrupted_terminal_for_next_turn()

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ClientEvent | None] = asyncio.Queue()
        self._active_queue = queue
        self._turn_interrupted = False

        def emit(event: ClientEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run_turn() -> None:
            terminal: Any | None = None
            try:
                terminal = self._require_terminal()
                self._last_stable_state = _terminal_state_snapshot(terminal)
                terminal.run_event_turn(message, lambda event: emit(_client_event_from_terminal_event(event)))
            except SystemExit:
                emit(ClientEvent("exit_requested", text="已收到退出命令。"))
            except Exception as error:
                if terminal is not None:
                    error_text = terminal.format_error_message(error)
                else:
                    error_text = format_error_for_terminal(error, project_root=self.project_root)
                emit(ClientEvent("error", text=error_text))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = asyncio.create_task(asyncio.to_thread(run_turn))
        self._active_worker = worker
        try:
            yield ClientEvent("status", text="正在处理")
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if self._turn_interrupted and not worker.done():
                self._retire_active_terminal(worker)
                worker.add_done_callback(_consume_task_exception)
            else:
                await worker
            self._active_queue = None
            if self._active_worker is worker:
                self._active_worker = None
            self._turn_interrupted = False

    async def close(self) -> None:
        if self._terminal is not None:
            self._terminal.close()
            self._terminal = None

    async def submit_during_turn(self, message: str) -> bool:
        terminal = self._terminal
        if terminal is None or not terminal.can_handle_input_during_turn(message):
            return False
        if hasattr(terminal, "submit_ai_confirmation_reply"):
            confirmation = getattr(terminal, "_current_ai_confirmation", lambda: None)()
            if confirmation is not None:
                classifier = getattr(terminal, "classify_active_turn_input", None)
                if callable(classifier):
                    intent = await asyncio.to_thread(terminal.classify_active_turn_input, message)
                    if intent != CONFIRM_CURRENT_WAIT:
                        return False
                return bool(await asyncio.to_thread(terminal.submit_ai_confirmation_reply, message))
        await asyncio.to_thread(terminal.handle_input, message)
        return True

    async def confirm_active_wait(self, message: str) -> AsyncIterator[ClientEvent]:
        terminal = self._terminal
        if terminal is not None and hasattr(terminal, "submit_ai_confirmation_reply"):
            handled = await asyncio.to_thread(terminal.submit_ai_confirmation_reply, message)
            if handled:
                yield ClientEvent("status", text="确认已发送")
                return
        yield ClientEvent("error", text="当前等待没有接收这条输入，请重新发送或按 Esc 介入。")

    async def classify_active_turn_input(self, message: str, *, context: dict[str, Any] | None = None) -> str:
        wait_prompt = ""
        wait_type = ""
        terminal = self._terminal
        if terminal is None and wait_type:
            try:
                terminal = await asyncio.to_thread(self._try_require_terminal)
            except Exception:
                terminal = None
        if terminal is not None and hasattr(terminal, "classify_active_turn_input"):
            intent = await asyncio.to_thread(
                terminal.classify_active_turn_input,
                message,
                prompt=wait_prompt,
                wait_type=wait_type,
                context=context,
            )
            if intent in ACTIVE_TURN_INPUT_INTENTS:
                return intent
        return _fallback_active_turn_input_intent(message)

    async def attach_clipboard_images(self) -> list[str]:
        def attach() -> list[str]:
            terminal = self._require_terminal()
            return terminal.attach_clipboard_images()

        return await asyncio.to_thread(attach)

    async def status_snapshot(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._status_snapshot_sync)

    async def check_service(self, message: str = "只回复 ok") -> dict[str, Any]:
        from ai_automate_contro.ai.terminal import check_ai_terminal_service

        return await asyncio.to_thread(
            check_ai_terminal_service,
            self.project_root,
            service=self.service,
            thread_id=f"{self.thread_id}-service-check",
            message=message,
        )

    async def interrupt(self) -> ClientEvent:
        terminal_cancelled = False
        terminal = self._terminal
        if terminal is not None:
            terminal_cancelled = await asyncio.to_thread(terminal._cancel_agent_turn)
        self._turn_interrupted = True
        queue = self._active_queue
        if queue is not None:
            queue.put_nowait(None)
        worker = self._active_worker
        if worker is not None and not worker.done():
            self._retire_active_terminal(worker)
            self._needs_intervention_fork = True
        if terminal_cancelled:
            return ClientEvent("interrupted", text="已中断当前 AI 回复。旧请求如果稍后返回，会被隔离，避免污染新会话。")
        return ClientEvent("interrupted", text="已请求中断当前任务。")

    def _require_terminal(self) -> Any:
        if self._terminal is None:
            from ai_automate_contro.ai.terminal import AITerminal

            self._terminal = AITerminal(self.project_root, service=self.service, thread_id=self.thread_id)
            seed_state = self._fork_seed_state
            self._fork_seed_state = None
            if seed_state is not None:
                self._terminal.graph.update_state(self._terminal._graph_config(), copy.deepcopy(seed_state))
        return self._terminal

    def _retire_active_terminal(self, worker: asyncio.Task[Any] | None = None) -> None:
        terminal = self._terminal
        if terminal is None:
            return
        terminal_id = id(terminal)
        if terminal_id in self._retired_terminals:
            return
        self._retired_terminals.add(terminal_id)
        self._terminal = None
        if worker is None:
            _close_terminal_quietly(terminal)
            self._retired_terminals.discard(terminal_id)
            return
        self._retired_workers.add(worker)

        def close_when_done(task: asyncio.Task[Any]) -> None:
            try:
                task.result()
            except BaseException:
                pass
            _close_terminal_quietly(terminal)
            self._retired_terminals.discard(terminal_id)
            self._retired_workers.discard(task)

        worker.add_done_callback(close_when_done)

    async def _prepare_interrupted_terminal_for_next_turn(self) -> None:
        if not self._needs_intervention_fork:
            return
        alive_workers = {worker for worker in self._retired_workers if not worker.done()}
        if alive_workers:
            await asyncio.wait(alive_workers, timeout=INTERRUPT_GRACE_SECONDS)
        self._fork_thread_for_intervention()
        self._needs_intervention_fork = False

    def _fork_thread_for_intervention(self) -> None:
        self._thread_fork_count += 1
        self.thread_id = f"{self._base_thread_id}-intervention-{self._thread_fork_count}"
        self._fork_seed_state = copy.deepcopy(self._last_stable_state or {})
        self._terminal = None

    def _status_snapshot_sync(self) -> dict[str, Any]:
        terminal_data: dict[str, Any] = {}
        if self._terminal is not None:
            terminal_data = dict(self._terminal.client_status_snapshot())
        elif self.thread_id:
            terminal_data = {"thread_id": self.thread_id, "service": self.service}
        return terminal_data

    def _try_require_terminal(self) -> Any | None:
        try:
            return self._require_terminal()
        except Exception:
            return None

    def _context_event(self) -> ClientEvent:
        return ClientEvent("context_updated", data=self._status_snapshot_sync())


def _client_event_from_terminal_event(event: AITerminalEvent) -> ClientEvent:
    return ClientEvent(event.kind, text=event.text, title=event.title, data=dict(event.data))


def _activity_from_client_event(event: ClientEvent) -> ClientEvent | None:
    if event.kind == "activity":
        return None
    if event.kind == "tool_started":
        return ClientEvent(
            "activity",
            text=f"调用工具 {_event_title(event)}",
            data={"category": "tool", "phase": "start", "source_kind": event.kind},
        )
    if event.kind == "tool_finished":
        phase = "failed" if event.data.get("ok") is False or event.data.get("phase") == "failed" else "done"
        return ClientEvent(
            "activity",
            text=f"{'工具失败' if phase == 'failed' else '工具完成'} {_event_title(event)}",
            data={"category": "tool", "phase": phase, "source_kind": event.kind},
        )
    if event.kind == "work_plan_updated":
        return ClientEvent(
            "activity",
            text="更新工作计划",
            data={"category": "plan", "phase": "done", "source_kind": event.kind},
        )
    if event.kind == "plan_progress":
        return ClientEvent(
            "activity",
            text=event.text,
            data={"category": "run", "phase": _activity_phase_from_text(event.text), "source_kind": event.kind},
        )
    if event.kind == "file_changed":
        return ClientEvent(
            "activity",
            text=event.text or "文件变更",
            data={"category": "file", "phase": "done", "source_kind": event.kind},
        )
    if event.kind == "diff":
        return ClientEvent(
            "activity",
            text="生成 diff",
            data={"category": "file", "phase": "done", "source_kind": event.kind},
        )
    if event.kind == "artifact":
        return ClientEvent(
            "activity",
            text=event.text or "产物更新",
            data={"category": "run", "phase": "done", "source_kind": event.kind},
        )
    if event.kind == "context_updated":
        context_state = event.data.get("context_state") if isinstance(event.data.get("context_state"), dict) else {}
        if context_state.get("latest_compression_summary_path") or context_state.get("latest_compression_archive_dir"):
            return ClientEvent(
                "activity",
                text="上下文已压缩归档",
                data={"category": "context", "phase": "done", "source_kind": event.kind},
            )
    if event.kind == "approval_requested":
        return ClientEvent(
            "activity",
            text="等待用户确认",
            data={"category": "run", "phase": "start", "source_kind": event.kind},
        )
    if event.kind == "error":
        return ClientEvent(
            "activity",
            text="遇到错误，准备停止或等待处理",
            data={"category": "review", "phase": "failed", "source_kind": event.kind},
        )
    return None


def _event_title(event: ClientEvent) -> str:
    return str(event.data.get("tool_name") or event.title or "tool")


def _activity_phase_from_text(text: str) -> str:
    lowered = str(text or "").lower()
    if "失败" in lowered or "error" in lowered:
        return "failed"
    if "完成" in lowered or "结束" in lowered or "finished" in lowered:
        return "done"
    return "start"


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except BaseException:
        return


def _close_terminal_quietly(terminal: Any) -> None:
    try:
        terminal.close()
    except BaseException:
        return


def _terminal_state_snapshot(terminal: Any) -> dict[str, Any] | None:
    try:
        state = terminal.graph.get_state(terminal._graph_config())
        values = getattr(state, "values", {})
    except BaseException:
        return None
    if not isinstance(values, dict):
        return None
    return dict(values)


def _chunk_text(text: str, *, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _fallback_active_turn_input_intent(message: str) -> str:
    try:
        from ai_automate_contro.ai.terminal import classify_ai_confirmation_reply

        if classify_ai_confirmation_reply(message) in {"approve", "reject"}:
            return CONFIRM_CURRENT_WAIT
    except Exception:
        pass
    return FEEDBACK_OR_CORRECTION
