from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol

from ai_automate_contro.ai.terminal_events import AITerminalEvent
from ai_automate_contro.client.events import ClientEvent
from ai_automate_contro.client.management import ClientManagementController


class AgentClientBackend(Protocol):
    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        """Yield UI-safe events for one user message."""

    async def submit_during_turn(self, message: str) -> bool:
        """Handle input that belongs to the active turn, such as manual confirmation."""

    async def attach_clipboard_images(self) -> list[str]:
        """Attach images from the clipboard and return placeholders to insert in the composer."""

    async def close(self) -> None:
        """Release backend resources."""


class FakeAgentBackend:
    """Deterministic backend used by the new client tests."""

    def __init__(self, *, response: str | None = None, delay: float = 0.0) -> None:
        self.response = response or "你好，我在。\n\n我可以帮你创建、运行、校验和调试 plan。"
        self.delay = delay

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        yield ClientEvent("status", text="正在处理")
        if "工具" in message or "weather" in message.lower() or "天气" in message:
            yield ClientEvent("tool_started", title="inspect_web_page", text="url=https://example.com")
            if self.delay:
                await asyncio.sleep(self.delay)
            yield ClientEvent("tool_finished", title="inspect_web_page", text="发现登录字段/验证信号")
        if "审批" in message:
            yield ClientEvent("approval_requested", text="AI 请求执行受保护工具。\n输入 /approve 批准执行。")
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

    async def attach_clipboard_images(self) -> list[str]:
        return []


class AITerminalBackend:
    """Adapter from the LangGraph AI runtime to the Textual event UI."""

    def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
        self.project_root = project_root
        self.service = service
        self.thread_id = thread_id
        self._terminal: Any | None = None
        self._management = ClientManagementController(project_root)

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        management_message = _management_payload(message, self._management)
        if management_message is not None:
            for event in await asyncio.to_thread(self._management.handle, management_message):
                yield event
            await self._sync_management_context_to_terminal(create=False)
            return
        if message.strip().startswith("/ai "):
            message = message.strip()[4:].lstrip()
        await self._sync_management_context_to_terminal(create=True)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[ClientEvent | None] = asyncio.Queue()

        def emit(event: ClientEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run_turn() -> None:
            try:
                terminal = self._require_terminal()
                terminal.run_client_turn(message, lambda event: emit(_client_event_from_terminal_event(event)))
            except SystemExit:
                emit(ClientEvent("exit_requested", text="已收到退出命令。"))
            except Exception as error:
                emit(ClientEvent("error", text=str(error)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = asyncio.create_task(asyncio.to_thread(run_turn))
        try:
            yield ClientEvent("status", text="正在处理")
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            await worker

    async def close(self) -> None:
        if self._terminal is not None:
            self._terminal.close()
            self._terminal = None

    async def submit_during_turn(self, message: str) -> bool:
        if self._management.is_management_input(message) and self._management.can_handle_during_turn(message):
            return False
        terminal = self._terminal
        if terminal is None or not terminal.can_handle_input_during_turn(message):
            return False
        await asyncio.to_thread(terminal.handle_input, message)
        return True

    async def attach_clipboard_images(self) -> list[str]:
        def attach() -> list[str]:
            terminal = self._require_terminal()
            return terminal.attach_clipboard_images()

        return await asyncio.to_thread(attach)

    def _require_terminal(self) -> Any:
        if self._terminal is None:
            from ai_automate_contro.ai.terminal import AITerminal

            self._terminal = AITerminal(self.project_root, service=self.service, thread_id=self.thread_id)
        return self._terminal

    async def _sync_management_context_to_terminal(self, *, create: bool) -> None:
        update = self._management.context_update()
        if not update:
            return

        def sync() -> None:
            if self._terminal is None and not create:
                return
            terminal = self._require_terminal()
            terminal._update_context_state(update)
            terminal._sync_current_session_index()

        await asyncio.to_thread(sync)


def _client_event_from_terminal_event(event: AITerminalEvent) -> ClientEvent:
    return ClientEvent(event.kind, text=event.text, title=event.title, data=dict(event.data))


def _chunk_text(text: str, *, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _management_payload(message: str, management: ClientManagementController) -> str | None:
    stripped = message.strip()
    if not stripped.startswith("/"):
        return None
    if stripped.startswith("/ai "):
        return None
    if stripped.startswith("/compact"):
        return None
    if management.is_management_input(stripped):
        return stripped
    return None
