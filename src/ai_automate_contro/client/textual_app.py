from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from unicodedata import east_asian_width

from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.events import Paste, Resize
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Static, TextArea

from ai_automate_contro.client.backend import AITerminalBackend, AgentClientBackend
from ai_automate_contro.client.backend import CONFIRM_CURRENT_WAIT, FEEDBACK_OR_CORRECTION
from ai_automate_contro.client.commands import (
    APPROVAL_COMMANDS,
    CONTEXTUAL_COMMANDS,
    ClientCommandSpec,
    SCOPE_LABELS,
    client_command_suggestions,
    format_client_command_help,
)
from ai_automate_contro.client.events import ClientEvent


MAX_TOOL_DETAIL_CHARS = 420
MAX_COMPACT_EVENT_CHARS = 120
COMPOSER_MIN_LINES = 4
COMPOSER_MAX_LINES = 8
COMMAND_PALETTE_VISIBLE_ROWS = 8
THINKING_IDLE_TICKS = 3
THINKING_TICK_SECONDS = 0.35


@dataclass
class TurnSummary:
    message: str
    assistant_chars: int = 0
    tools_started: list[str] = None  # type: ignore[assignment]
    tools_done: list[str] = None  # type: ignore[assignment]
    tools_failed: list[str] = None  # type: ignore[assignment]
    plan_events: list[str] = None  # type: ignore[assignment]
    files: list[str] = None  # type: ignore[assignment]
    diffs: list[str] = None  # type: ignore[assignment]
    artifacts: list[str] = None  # type: ignore[assignment]
    activities: list[str] = None  # type: ignore[assignment]
    approvals: list[str] = None  # type: ignore[assignment]
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.tools_started = []
        self.tools_done = []
        self.tools_failed = []
        self.plan_events = []
        self.files = []
        self.diffs = []
        self.artifacts = []
        self.activities = []
        self.approvals = []
        self.errors = []

    def has_visible_work(self) -> bool:
        return any(
            (
                self.tools_started,
                self.tools_done,
                self.tools_failed,
                self.plan_events,
                self.files,
                self.diffs,
                self.artifacts,
                self.activities,
                self.approvals,
                self.errors,
            )
        )


class MessageBlock(Static):
    def __init__(self, text: str = "", *, role: str, **kwargs: Any) -> None:
        self.role = role
        self.text = text
        super().__init__(self._renderable(), classes=f"message {role}", **kwargs)

    def append(self, text: str) -> None:
        self.text += text
        self.update(self._renderable())

    def _renderable(self) -> object:
        if self.role == "assistant" and self.text:
            return Markdown(self.text, hyperlinks=False)
        if self.role == "user":
            return _prefix_lines(self.text, "› ")
        if self.role == "meta":
            return _prefix_lines(self.text, "· ")
        if self.role == "plan":
            return _event_line(self.text, "· ")
        if self.role == "file":
            return _event_line(self.text, "◆ ")
        if self.role == "artifact":
            return _event_line(self.text, "↳ ")
        if self.role == "activity":
            return _event_line(self.text, "· ")
        if self.role == "summary":
            return _prefix_lines(self.text, "✓ ")
        if self.role == "diff":
            return _render_diff_text(self.text)
        if self.role == "error":
            return _prefix_lines(self.text, "× ")
        if self.role == "approval":
            return _prefix_lines(self.text, "◇ ")
        return self.text


class ToolBlock(MessageBlock):
    def __init__(self, event: ClientEvent, *, show_details: bool) -> None:
        self.tool_name = _tool_event_name(event)
        self.phase = _tool_phase(event)
        self.event = event
        self.show_details = show_details
        super().__init__(_format_tool_event(event, show_details=show_details), role="tool")
        self._sync_phase_class()

    def update_event(self, event: ClientEvent, *, show_details: bool) -> None:
        self.phase = _tool_phase(event)
        self.event = event
        self.show_details = show_details
        self.text = _format_tool_event(event, show_details=show_details)
        self.update(self._renderable())
        self._sync_phase_class()

    def _sync_phase_class(self) -> None:
        self.set_class(self.show_details, "tool-details")
        self.set_class(self.phase == "running", "tool-running")
        self.set_class(self.phase == "done", "tool-done")
        self.set_class(self.phase == "failed", "tool-failed")


class MetaBlock(MessageBlock):
    pass


class PlanProgressBlock(MessageBlock):
    pass


class FileChangeBlock(MessageBlock):
    pass


class DiffBlock(MessageBlock):
    pass


class ArtifactBlock(MessageBlock):
    pass


class ActivityBlock(MessageBlock):
    pass


class TurnSummaryBlock(MessageBlock):
    pass


class ApprovalBlock(MessageBlock):
    pass


class PromptMarker(Static):
    pass


class CommandPalette(Static):
    def __init__(self) -> None:
        self.commands: list[ClientCommandSpec] = []
        self.selected_index = 0
        self.palette_offset = 0
        super().__init__("", id="command_palette")
        self.display = False

    def show_commands(self, commands: list[ClientCommandSpec], *, selected_index: int = 0) -> None:
        self.commands = commands
        self.selected_index = _clamp_index(selected_index, len(commands))
        self._sync_scroll_offset()
        if not commands:
            self.hide()
            return
        self.display = True
        self.update(self._render_text())

    def hide(self) -> None:
        self.commands = []
        self.selected_index = 0
        self.palette_offset = 0
        self.display = False
        self.update("")

    def move_selection(self, delta: int) -> None:
        if not self.commands:
            return
        self.selected_index = (self.selected_index + delta) % len(self.commands)
        self._sync_scroll_offset()
        self.update(self._render_text())

    def selected_command(self) -> ClientCommandSpec | None:
        if not self.commands:
            return None
        return self.commands[_clamp_index(self.selected_index, len(self.commands))]

    def _render_text(self) -> str:
        lines = []
        visible_commands = self.visible_commands()
        for offset, command in enumerate(visible_commands):
            index = self.palette_offset + offset
            marker = "›" if index == self.selected_index else " "
            scope = SCOPE_LABELS.get(command.scope, command.scope)
            lines.append(f"{marker} /{command.name:<10} {scope:<4} {command.description}")
        return "\n".join(lines)

    def visible_commands(self) -> list[ClientCommandSpec]:
        end = self.palette_offset + COMMAND_PALETTE_VISIBLE_ROWS
        return self.commands[self.palette_offset : end]

    def _sync_scroll_offset(self) -> None:
        command_count = len(self.commands)
        if command_count <= COMMAND_PALETTE_VISIBLE_ROWS:
            self.palette_offset = 0
            return
        if self.selected_index < self.palette_offset:
            self.palette_offset = self.selected_index
        elif self.selected_index >= self.palette_offset + COMMAND_PALETTE_VISIBLE_ROWS:
            self.palette_offset = self.selected_index - COMMAND_PALETTE_VISIBLE_ROWS + 1
        max_offset = max(0, command_count - COMMAND_PALETTE_VISIBLE_ROWS)
        self.palette_offset = min(max(self.palette_offset, 0), max_offset)


class WorkPlanPanel(Static):
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []
        self.summary = ""
        super().__init__("", id="work_plan_panel")
        self.display = False

    def update_plan(self, items: Any, *, summary: Any = "") -> None:
        self.items = _normalize_work_plan_items_for_ui(items)
        self.summary = _single_line_preview(str(summary or ""), limit=120) if summary else ""
        if not self.items:
            self.display = False
            self.update("")
            return
        self.display = True
        self.update(self._render_text())

    def _render_text(self) -> str:
        total = len(self.items)
        completed = sum(1 for item in self.items if item.get("status") == "completed")
        lines = [f"计划 {completed}/{total}"]
        if self.summary:
            lines[0] += f" · {self.summary}"
        visible_items = _visible_work_plan_items(self.items)
        for item in visible_items:
            status = item.get("status") or "pending"
            marker = {
                "completed": "✓",
                "in_progress": "●",
                "pending": "○",
            }.get(status, "○")
            title = item.get("title") or ""
            line = f"{marker} {title}"
            if item.get("note"):
                line += f" · {item['note']}"
            lines.append(line)
        hidden_completed = max(0, completed - sum(1 for item in visible_items if item.get("status") == "completed"))
        if hidden_completed:
            lines.append(f"✓ 已完成 {hidden_completed} 项")
        return "\n".join(lines)


class PendingQueuePanel(Static):
    def __init__(self) -> None:
        self.messages: list[str] = []
        super().__init__("", id="pending_queue_panel")
        self.display = False

    def update_queue(self, messages: list[str]) -> None:
        self.messages = [message for message in messages if message.strip()]
        if not self.messages:
            self.display = False
            self.update("")
            return
        self.display = True
        self.update(self._render_text())

    def _render_text(self) -> str:
        lines = [f"待处理 {len(self.messages)} 条"]
        for index, message in enumerate(self.messages[:5], start=1):
            lines.append(f"{index}. {_single_line_preview(message, limit=120)}")
        hidden = len(self.messages) - 5
        if hidden > 0:
            lines.append(f"+ {hidden} 条")
        return "\n".join(lines)


class Composer(TextArea):
    BINDINGS = [
        Binding("enter", "submit", "发送", show=False),
        Binding("up", "cursor_up", "上一项", show=False),
        Binding("down", "cursor_down", "下一项", show=False),
    ]

    @dataclass
    class Submitted(Message):
        composer: "Composer"
        value: str

        @property
        def control(self) -> "Composer":
            return self.composer

    @dataclass
    class PaletteRequested(Message):
        composer: "Composer"
        action: str

        @property
        def control(self) -> "Composer":
            return self.composer

    def action_submit(self) -> None:
        self.post_message(self.Submitted(self, self.text.strip()).set_sender(self))

    def action_newline(self) -> None:
        self.insert("\n")

    def action_paste(self) -> None:
        # Text paste is handled by Textual's Paste event. This action is the
        # image-clipboard fallback for terminals that surface Ctrl+V as a key.
        self._log_input_debug("action_paste", before_text=self.text)
        self.post_message(self.PaletteRequested(self, "paste").set_sender(self))

    def action_cursor_up(self, select: bool = False) -> None:
        if not select and _is_palette_input(self.text):
            self._move_palette_selection("up")
            return
        super().action_cursor_up(select=select)

    def action_cursor_down(self, select: bool = False) -> None:
        if not select and _is_palette_input(self.text):
            self._move_palette_selection("down")
            return
        super().action_cursor_down(select=select)

    def _move_palette_selection(self, direction: str) -> None:
        try:
            palette = self.app.query_one("#command_palette", CommandPalette)
        except NoMatches:
            self.post_message(self.PaletteRequested(self, direction).set_sender(self))
            return
        palette.move_selection(-1 if direction == "up" else 1)

    async def _on_key(self, event: Any) -> None:
        self._log_input_debug("key", event=event, before_text=self.text)
        aliases = set(getattr(event, "aliases", []))
        if _is_newline_key_event(event):
            event.stop()
            event.prevent_default()
            self.action_newline()
            self._log_input_debug("key_handled_newline", event=event, after_text=self.text)
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if self._consume_line_continuation():
                self.action_newline()
                self._log_input_debug("key_handled_line_continuation", event=event, after_text=self.text)
                return
            self.action_submit()
            self._log_input_debug("key_handled_submit", event=event, after_text=self.text)
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.post_message(self.PaletteRequested(self, "complete").set_sender(self))
            self._log_input_debug("key_handled_palette_complete", event=event, after_text=self.text)
            return
        palette_direction = _palette_move_direction(event)
        if palette_direction is not None and _is_palette_input(self.text):
            event.stop()
            event.prevent_default()
            self.post_message(self.PaletteRequested(self, palette_direction).set_sender(self))
            self._log_input_debug("key_handled_palette_move", event=event, after_text=self.text)
            return
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.post_message(self.PaletteRequested(self, "escape").set_sender(self))
            self._log_input_debug("key_handled_escape", event=event, after_text=self.text)
            return
        await super()._on_key(event)
        self._log_input_debug("key_after_super", event=event, after_text=self.text)

    async def _on_paste(self, event: Paste) -> None:
        self._log_input_debug("paste", event=event, paste_text=event.text, before_text=self.text)
        if event.text:
            event.stop()
            event.prevent_default()
            await super()._on_paste(event)
            self._log_input_debug("paste_after_super", event=event, paste_text=event.text, after_text=self.text)
            return
        self.post_message(self.PaletteRequested(self, "paste").set_sender(self))
        self._log_input_debug("paste_empty_requested_clipboard", event=event, after_text=self.text)

    def _consume_line_continuation(self) -> bool:
        text = self.text
        stripped = text.rstrip(" \t")
        if not stripped.endswith("\\") or stripped.endswith("\\\\"):
            return False
        self.load_text(stripped[:-1])
        _move_composer_cursor_to_end(self)
        return True

    def _log_input_debug(
        self,
        phase: str,
        *,
        event: Any | None = None,
        paste_text: str | None = None,
        before_text: str | None = None,
        after_text: str | None = None,
    ) -> None:
        app = getattr(self, "app", None)
        logger = getattr(app, "_log_composer_input_debug", None)
        if not callable(logger):
            return
        logger(
            phase,
            event=_event_debug_payload(event),
            paste_text=_text_debug_payload(paste_text),
            before_text=_text_debug_payload(before_text),
            after_text=_text_debug_payload(after_text),
            cursor_location=getattr(self, "cursor_location", None),
            selection_start=getattr(self.selection, "start", None),
            selection_end=getattr(self.selection, "end", None),
        )


class AICTextualApp(App[None]):
    CSS = """
    Screen {
        background: #101214;
        color: #e7e2d8;
    }

    #root {
        height: 100%;
        background: #101214;
    }

    #transcript {
        height: 1fr;
        padding: 1 0 0 0;
        background: #101214;
    }

    #input_panel {
        height: auto;
        padding: 0 0 1 0;
        background: #101214;
    }

    #command_palette {
        max-height: 10;
        margin: 0 0 1 0;
        padding: 1 1;
        color: #b8b2a7;
        background: #1a1d20;
        border-left: tall #3a4047;
    }

    #work_plan_panel {
        max-height: 8;
        margin: 0 0 1 0;
        padding: 1 1;
        color: #d3cab8;
        background: #171a1d;
        border-left: tall #d9a441;
    }

    #pending_queue_panel {
        max-height: 7;
        margin: 0 0 1 0;
        padding: 1 1;
        color: #c8d0dc;
        background: #15191e;
        border-left: tall #6f7a86;
    }

    #composer_row {
        height: auto;
        min-height: 7;
        background: #2d3035;
        padding: 1 1 2 1;
    }

    #prompt_marker {
        width: 3;
        min-height: 1;
        color: #f0c674;
        background: #2d3035;
        padding: 0 0;
        text-style: bold;
    }

    #composer {
        height: 4;
        min-height: 4;
        max-height: 8;
        width: 1fr;
        margin: 0 0;
        padding: 0 0;
        border: none;
        background: #2d3035;
        color: #fff7e8;
        scrollbar-size: 0 0;
    }

    #composer:focus {
        border: none;
        background: #2d3035;
    }

    #composer .text-area--cursor-line {
        background: #33373d;
    }

    #composer .text-area--cursor {
        color: #101214;
        background: #ffd166;
        text-style: reverse bold;
    }

    #composer .text-area--selection {
        background: #56606b;
        color: #fffaf0;
    }

    #composer .text-area--placeholder {
        color: #c8c2b7;
        text-style: bold;
    }

    #status {
        height: 1;
        padding: 0 0;
        color: #8f96a0;
        background: #101214;
    }

    .message {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 0;
    }

    .user {
        background: #2a2e33;
        color: #f3efe7;
        min-height: 1;
        padding: 1 1;
    }

    .assistant {
        background: #101214;
        color: #e7e2d8;
        padding: 0 0 0 1;
    }

    .tool {
        color: #b8b2a7;
        background: #101214;
        height: 1;
        min-height: 1;
        max-height: 1;
        margin: 0 0;
        padding: 0 0 0 1;
    }

    .tool-details {
        height: auto;
        max-height: 12;
        margin: 0 0 1 0;
        padding: 1 1;
        background: #16191c;
    }

    .tool-running {
        color: #d7c27d;
    }

    .tool-done {
        color: #9fbf8f;
    }

    .tool-failed {
        color: #ffb4ab;
        background: #101214;
    }

    .meta {
        color: #a7afba;
        background: #101214;
        padding: 0 0 0 1;
    }

    .plan {
        color: #bec6d2;
        background: #101214;
        height: auto;
        min-height: 1;
        margin: 0 0;
        padding: 0 0 0 1;
    }

    .file {
        color: #d6d0c4;
        background: #101214;
        height: auto;
        min-height: 1;
        margin: 0 0;
        padding: 0 0 0 1;
    }

    .artifact {
        color: #b7c5d6;
        background: #101214;
        height: auto;
        min-height: 1;
        margin: 0 0;
        padding: 0 0 0 1;
    }

    .activity {
        color: #9aa2ad;
        background: #101214;
        height: auto;
        min-height: 1;
        margin: 0 0;
        padding: 0 0 0 1;
    }

    .summary {
        color: #cbd7c5;
        background: #111812;
        padding: 1 1;
        border-left: tall #7fb069;
    }

    .diff {
        color: #d6d0c4;
        background: #121416;
        padding: 1 1;
        border-left: tall #7a6f55;
    }

    .approval {
        color: #9ccfd8;
        background: #142329;
        padding: 1 1;
        border-left: tall #2f8f9d;
    }

    .error {
        color: #ffb4ab;
        background: #2b1718;
        padding: 1 1;
        border-left: tall #ff6b6b;
    }

    """

    BINDINGS = [
        ("ctrl+c", "quit", "退出"),
        ("ctrl+q", "quit", "退出"),
    ]

    def __init__(
        self,
        backend: AgentClientBackend,
        *,
        project_root: Path | None = None,
        title: str = "ai-automate-contro",
    ) -> None:
        super().__init__()
        self.backend = backend
        self.project_root = project_root.resolve() if project_root is not None else Path.cwd().resolve()
        self.title = title
        self._queue: deque[str] = deque()
        self._busy = False
        self._drain_scheduled = False
        self._current_assistant: MessageBlock | None = None
        self._current_assistant_record_index: int | None = None
        self._active_tools: dict[str, ToolBlock] = {}
        self._show_tool_details = False
        self._transcript_records: list[tuple[str, str]] = []
        self._status_message = "就绪"
        self._backend_status: dict[str, Any] = {}
        self._thinking = False
        self._thinking_tick = 0
        self._assistant_idle_ticks = 0
        self._thinking_timer: Timer | None = None
        self._active_turn_id: int | None = None
        self._active_turn_task: asyncio.Task[None] | None = None
        self._interrupting = False
        self._turn_sequence = 0
        self._suppressed_turn_ids: set[int] = set()
        self._active_summary: TurnSummary | None = None
        self._pre_echoed_queue_messages: deque[str] = deque()
        self._input_debug_enabled = os.environ.get("AIC_TEXTUAL_INPUT_DEBUG", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self._input_debug_path = self.project_root / ".keygen" / "textual-input-debug.jsonl"

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield VerticalScroll(id="transcript")
            with Vertical(id="input_panel"):
                yield CommandPalette()
                yield WorkPlanPanel()
                yield PendingQueuePanel()
                with Horizontal(id="composer_row"):
                    yield PromptMarker("›", id="prompt_marker")
                    yield Composer(
                        "",
                        soft_wrap=True,
                        tab_behavior="focus",
                        show_line_numbers=False,
                        highlight_cursor_line=False,
                        placeholder="Enter 发送；Shift/Alt+Enter 或行尾 \\ 后 Enter 换行；/help 查看命令",
                        compact=True,
                        id="composer",
                    )
                yield Static("", id="status")

    def on_mount(self) -> None:
        self.query_one("#composer", Composer).focus()
        self._sync_composer_height()
        self._set_status("就绪")
        self._thinking_timer = self.set_interval(
            THINKING_TICK_SECONDS,
            self._tick_thinking_indicator,
            name="thinking-indicator",
            pause=True,
        )
        self.run_worker(self._refresh_backend_status(), name="initial-status", exclusive=False)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "composer":
            self._sync_composer_height()
            self._sync_command_palette()

    def on_resize(self, _: Resize) -> None:
        self._sync_composer_height()

    async def on_key(self, event: Any) -> None:
        if event.key != "escape":
            palette_direction = _palette_move_direction(event)
            if palette_direction is None:
                return
            try:
                composer = self.query_one("#composer", Composer)
            except NoMatches:
                return
            if not _is_palette_input(composer.text):
                return
            event.stop()
            event.prevent_default()
            self._palette().move_selection(-1 if palette_direction == "up" else 1)
            return
        event.stop()
        event.prevent_default()
        self._handle_escape_key()

    async def on_composer_submitted(self, event: Composer.Submitted) -> None:
        text = event.value.strip()
        if self._handle_palette_submit_completion(text):
            return
        event.composer.clear()
        self._sync_composer_height()
        self._hide_command_palette()
        if not text:
            return
        if await self._handle_local_command(text):
            return
        if self._has_active_wait():
            await self._add_message(text, role="user")
            self._set_status("已收到输入，正在判断")
            self.run_worker(self._route_active_turn_input(text, pre_echoed=True), name="active-turn-input", exclusive=False)
            return
        if self._busy and await self.backend.submit_during_turn(text):
            await self._add_message(text, role="user")
            return
        self._enqueue_user_message(text)
        self._schedule_queue_drain()

    def on_composer_palette_requested(self, event: Composer.PaletteRequested) -> None:
        event.stop()
        self._log_composer_input_debug(
            "palette_requested",
            action=event.action,
            composer_text=_text_debug_payload(event.composer.text),
        )
        if event.action == "escape":
            self._handle_escape_key()
            return
        if event.action == "hide":
            self._hide_command_palette()
            return
        if event.action == "paste":
            self.run_worker(self._paste_from_clipboard(event.composer), name="composer-paste", exclusive=False)
            return
        palette = self._palette()
        if event.action == "up":
            palette.move_selection(-1)
            return
        if event.action == "down":
            palette.move_selection(1)
            return
        if event.action == "complete":
            if not palette.commands:
                self._sync_command_palette()
            selected = palette.selected_command()
            if selected is None:
                return
            event.composer.load_text(f"/{selected.name} ")
            _move_composer_cursor_to_end(event.composer)
            self._sync_composer_height()
            self._hide_command_palette()

    def _handle_escape_key(self) -> None:
        if not self._busy:
            self._hide_command_palette()
            return
        if self._interrupting:
            self._set_status("正在中断")
            return
        self.run_worker(self._interrupt_active_turn(), name="interrupt-active-turn", exclusive=False)

    async def _route_active_turn_input(self, text: str, *, pre_echoed: bool = False) -> None:
        try:
            intent = await self.backend.classify_active_turn_input(text)
        except Exception as error:
            await self._add_message(_format_error_text(str(error)), role="error")
            intent = FEEDBACK_OR_CORRECTION
        if intent == CONFIRM_CURRENT_WAIT:
            self._set_status("已收到输入，正在继续")
            await self._confirm_active_wait(text)
            return
        self._set_status("已收到反馈，正在介入")
        if pre_echoed:
            await self._intervene_with_pre_echoed_input(text)
        else:
            self._enqueue_user_message(text)
            self._handle_escape_key() if self._busy else self._schedule_queue_drain()

    async def _submit_during_active_turn(self, text: str) -> None:
        try:
            handled = await self.backend.submit_during_turn(text)
        except Exception as error:
            await self._add_message(_format_error_text(str(error)), role="error")
            self._set_status("输入处理失败")
            return
        if not handled:
            await self._add_message("当前等待没有接收这条输入，请重新发送或按 Esc 介入。", role="error")
            self._set_status("输入未被接收")

    async def _confirm_active_wait(self, text: str) -> None:
        saw_error = False
        try:
            async for event in self.backend.confirm_active_wait(text):
                if event.kind == "error":
                    saw_error = True
                await self._handle_client_event(event)
        except Exception as error:
            await self._add_message(_format_error_text(str(error)), role="error")
            self._set_status("输入处理失败")
            return
        if saw_error:
            self._set_status("输入未被接收")
            return
        await self._refresh_backend_status()

    async def _intervene_with_pre_echoed_input(self, text: str) -> None:
        self._pre_echoed_queue_messages.append(text)
        self._queue.appendleft(text)
        self._sync_queue_panel()
        self._set_status("正在介入")
        if self._busy:
            await self._interrupt_active_turn()
            return
        try:
            event = await self.backend.interrupt()
            wait_for_idle = getattr(self.backend, "wait_for_idle_after_interrupt", None)
            if callable(wait_for_idle):
                await wait_for_idle()
        except Exception as error:
            await self._add_message(_format_error_text(str(error)), role="error")
            self._set_status("中断失败")
            return
        if event.kind == "interrupted":
            await self._add_message(
                _format_interruption_text(event.text, queued_count=1, intervention_text=text),
                role="meta",
            )
        else:
            await self._handle_client_event(event)
        await self._refresh_backend_status()
        self._schedule_queue_drain()

    async def _drain_queue(self) -> None:
        self._drain_scheduled = False
        self._busy = True
        drain_task = asyncio.current_task()
        try:
            while self._queue:
                messages = self._take_queued_messages()
                if not messages:
                    continue
                message = "\n\n".join(messages)
                if not self._consume_pre_echoed_queue_message(message):
                    await self._add_message(message, role="user")
                turn_task = asyncio.create_task(self._run_turn(message), name="agent-turn")
                self._active_turn_task = turn_task
                try:
                    await turn_task
                except asyncio.CancelledError:
                    if drain_task is not None and drain_task.cancelling():
                        turn_task.cancel()
                        raise
                    # Esc cancels only the active turn. The queue drain must
                    # continue so intervention messages can run immediately.
                    continue
                finally:
                    if self._active_turn_task is turn_task:
                        self._active_turn_task = None
        finally:
            self._busy = False
            self._drain_scheduled = False
            self._sync_queue_panel()
            if not self._queue:
                await self._refresh_backend_status()
            self._current_assistant = None
            self._current_assistant_record_index = None
            self._active_turn_task = None
            self._stop_thinking_indicator()
            self._set_status("等待人工确认" if self._backend_status.get("pending_approval") else "就绪")

    async def _interrupt_active_turn(self) -> None:
        self._interrupting = True
        queued_count, intervention_text = self._promote_queue_for_intervention()
        active_turn_id = self._active_turn_id
        if active_turn_id is not None:
            self._suppressed_turn_ids.add(active_turn_id)
        active_turn_task = self._active_turn_task
        self._stop_thinking_indicator()
        self._current_assistant = None
        self._current_assistant_record_index = None
        self._mark_active_tools_interrupted()
        self._set_status("正在介入" if intervention_text else "正在中断")
        try:
            event = await self.backend.interrupt()
        except Exception as error:
            await self._add_message(_format_error_text(str(error)), role="error")
            self._set_status("中断失败")
            return
        finally:
            self._interrupting = False
        try:
            if event.kind == "interrupted":
                await self._add_message(
                    _format_interruption_text(event.text, queued_count=queued_count, intervention_text=intervention_text),
                    role="meta",
                )
            else:
                await self._handle_client_event(event)
            await self._refresh_backend_status()
            if active_turn_task is not None and not active_turn_task.done():
                active_turn_task.cancel()
            self._set_status(f"已介入 {queued_count} 条" if intervention_text else "就绪")
        finally:
            self._interrupting = False

    async def _run_turn(self, message: str) -> None:
        self._turn_sequence += 1
        turn_id = self._turn_sequence
        self._active_turn_id = turn_id
        self._current_assistant = None
        self._active_summary = TurnSummary(message=message)
        self._start_thinking_indicator("正在思考")
        try:
            async for client_event in self.backend.stream(message):
                if turn_id in self._suppressed_turn_ids:
                    continue
                await self._handle_client_event(client_event)
        except asyncio.CancelledError:
            raise
        finally:
            summary = self._active_summary
            if summary is not None and turn_id not in self._suppressed_turn_ids:
                await self._emit_turn_summary(summary)
            self._active_summary = None
            self._suppressed_turn_ids.discard(turn_id)
            if self._active_turn_id == turn_id:
                self._active_turn_id = None
            if self._active_turn_task is asyncio.current_task():
                self._active_turn_task = None
            self._stop_thinking_indicator()

    async def _handle_client_event(self, event: ClientEvent) -> None:
        if event.kind == "status":
            self._start_thinking_indicator(event.text or "正在处理")
            return
        if event.kind == "context_updated":
            self._backend_status = dict(event.data)
            self._sync_work_plan_from_status()
            self._render_status()
            return
        if event.kind == "work_plan_updated":
            self._record_turn_event(event)
            self._update_work_plan(event.data.get("items"), summary=event.data.get("summary", ""))
            return
        if event.kind == "activity":
            if _should_record_activity_event(event):
                self._record_turn_event(event)
            if _should_render_activity_event(event):
                await self._add_message(_format_activity_event(event), role="activity")
            return
        if event.kind == "assistant_delta":
            self._record_turn_event(event)
            self._pause_thinking_indicator()
            if self._current_assistant is None:
                self._current_assistant = await self._add_message("", role="assistant")
                self._current_assistant_record_index = len(self._transcript_records) - 1
            self._current_assistant.append(event.text)
            self._append_current_assistant_record(event.text)
            await self._scroll_end()
            return
        if event.kind == "assistant_done":
            self._record_turn_event(event)
            self._current_assistant = None
            self._current_assistant_record_index = None
            self._stop_thinking_indicator()
            await self._scroll_end()
            return
        if event.kind == "tool_started":
            self._record_turn_event(event)
            self._start_thinking_indicator("正在处理工具")
            await self._handle_tool_event(event)
            return
        if event.kind == "tool_finished":
            self._record_turn_event(event)
            await self._handle_tool_event(event)
            self._start_thinking_indicator("正在思考")
            return
        if event.kind == "system_output":
            await self._add_message(event.text, role="meta")
            return
        if event.kind == "plan_progress":
            self._record_turn_event(event)
            await self._add_message(event.text, role="plan")
            return
        if event.kind == "file_changed":
            self._record_turn_event(event)
            await self._add_message(event.text or _format_file_change_event(event), role="file")
            return
        if event.kind == "diff":
            self._record_turn_event(event)
            await self._add_message(event.text or _format_diff_event(event), role="diff")
            return
        if event.kind == "artifact":
            self._record_turn_event(event)
            await self._add_message(event.text or _format_artifact_event(event), role="artifact")
            return
        if event.kind == "approval_requested":
            self._record_turn_event(event)
            self._stop_thinking_indicator()
            self._set_status("等待人工确认")
            await self._add_message(_format_approval_text(event.text), role="approval")
            self._backend_status["pending_approval"] = True
            self._render_status()
            return
        if event.kind == "error":
            self._record_turn_event(event)
            self._stop_thinking_indicator()
            await self._add_message(_format_error_text(event.text), role="error")
            return
        if event.kind == "interrupted":
            self._stop_thinking_indicator()
            await self._add_message(event.text or "已中断当前任务。", role="meta")
            return
        if event.kind == "exit_requested":
            self._stop_thinking_indicator()
            self._set_status(event.text or "正在关闭")
            await self.backend.close()
            self.exit()

    async def _add_message(self, text: str, *, role: str) -> MessageBlock:
        block_type = _message_block_type(role)
        block = block_type(text, role=role)
        transcript = self.query_one("#transcript", VerticalScroll)
        await transcript.mount(block)
        self._transcript_records.append((role, text))
        await self._scroll_end()
        return block

    def _append_current_assistant_record(self, text: str) -> None:
        index = self._current_assistant_record_index
        if index is None or index < 0 or index >= len(self._transcript_records):
            return
        role, previous = self._transcript_records[index]
        if role != "assistant":
            return
        self._transcript_records[index] = (role, previous + text)

    async def _handle_tool_event(self, event: ClientEvent) -> None:
        name = _tool_event_name(event)
        if event.kind == "tool_started":
            block = ToolBlock(event, show_details=self._show_tool_details)
            transcript = self.query_one("#transcript", VerticalScroll)
            await transcript.mount(block)
            self._active_tools[name] = block
            self._transcript_records.append(("tool", block.text))
            await self._scroll_end()
            return
        block = self._active_tools.pop(name, None)
        if block is None:
            block = ToolBlock(event, show_details=self._show_tool_details)
            transcript = self.query_one("#transcript", VerticalScroll)
            await transcript.mount(block)
            self._transcript_records.append(("tool", block.text))
            await self._scroll_end()
            return
        block.update_event(event, show_details=self._show_tool_details)
        self._replace_transcript_tool_record(name, block.text)
        await self._scroll_end()

    def _replace_transcript_tool_record(self, tool_name: str, text: str) -> None:
        for index in range(len(self._transcript_records) - 1, -1, -1):
            role, previous = self._transcript_records[index]
            if role == "tool" and _transcript_tool_name(previous) == tool_name:
                self._transcript_records[index] = (role, text)
                return
        self._transcript_records.append(("tool", text))

    def _mark_active_tools_interrupted(self) -> None:
        for name, block in list(self._active_tools.items()):
            event = ClientEvent(
                "tool_finished",
                title=name,
                text="已中断",
                data={"phase": "failed", "ok": False},
            )
            block.update_event(event, show_details=self._show_tool_details)
            self._replace_transcript_tool_record(name, block.text)
        self._active_tools.clear()

    def _record_turn_event(self, event: ClientEvent) -> None:
        summary = self._active_summary
        if summary is None:
            return
        if event.kind == "assistant_delta":
            summary.assistant_chars += len(event.text or "")
            return
        if event.kind == "tool_started":
            _append_unique(summary.tools_started, _tool_event_name(event))
            return
        if event.kind == "tool_finished":
            name = _tool_event_name(event)
            if _tool_phase(event) == "failed":
                _append_unique(summary.tools_failed, name)
            else:
                _append_unique(summary.tools_done, name)
            return
        if event.kind == "plan_progress":
            if _resolves_pending_approval(event.text):
                summary.approvals.clear()
            _append_limited(summary.plan_events, event.text, limit=8)
            return
        if event.kind == "work_plan_updated":
            _append_limited(summary.plan_events, "工作计划已更新", limit=8)
            return
        if event.kind == "activity":
            if not _should_record_activity_event(event):
                return
            _append_limited(summary.activities, event.text or _format_activity_event(event), limit=10)
            return
        if event.kind == "file_changed":
            _append_unique(summary.files, event.text or _format_file_change_event(event))
            return
        if event.kind == "diff":
            _append_unique(summary.diffs, _format_diff_event(event))
            return
        if event.kind == "artifact":
            _append_unique(summary.artifacts, event.text or _format_artifact_event(event))
            return
        if event.kind == "system_output":
            if _resolves_pending_approval(event.text):
                summary.approvals.clear()
            return
        if event.kind == "approval_requested":
            _append_limited(summary.approvals, _single_line_preview(event.text, limit=100), limit=4)
            return
        if event.kind == "error":
            _append_limited(summary.errors, _single_line_preview(event.text, limit=120), limit=4)

    async def _emit_turn_summary(self, summary: TurnSummary) -> None:
        if not summary.has_visible_work():
            return
        await self._add_message(_format_turn_summary(summary), role="summary")

    def _promote_queue_for_intervention(self) -> tuple[int, str]:
        if not self._queue:
            return 0, ""
        messages = [message.strip() for message in self._queue if message.strip()]
        self._queue.clear()
        if not messages:
            self._sync_queue_panel()
            return 0, ""
        intervention_text = "\n\n".join(messages)
        self._queue.appendleft(intervention_text)
        self._sync_queue_panel()
        return len(messages), intervention_text

    def _enqueue_user_message(self, text: str) -> None:
        self._queue.append(text)
        self._sync_queue_panel()
        self._set_status(f"排队 {len(self._queue)} 条")

    def _take_queued_messages(self) -> list[str]:
        messages: list[str] = []
        while self._queue and not messages:
            first = self._queue.popleft().strip()
            if not first:
                continue
            messages.append(first)
            if _is_command_input(first):
                break
            while self._queue and not _is_command_input(self._queue[0]):
                next_message = self._queue.popleft().strip()
                if next_message:
                    messages.append(next_message)
        self._sync_queue_panel()
        return messages

    def _consume_pre_echoed_queue_message(self, message: str) -> bool:
        if not self._pre_echoed_queue_messages:
            return False
        if self._pre_echoed_queue_messages[0] == message:
            self._pre_echoed_queue_messages.popleft()
            return True
        try:
            self._pre_echoed_queue_messages.remove(message)
            return True
        except ValueError:
            return False

    def _schedule_queue_drain(self) -> None:
        if self._busy or self._drain_scheduled:
            return
        self._drain_scheduled = True
        self.run_worker(self._drain_queue(), name="agent-turns", exclusive=True)

    async def _scroll_end(self) -> None:
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.scroll_end(animate=False)

    def _set_status(self, text: str) -> None:
        self._status_message = text
        self._render_status()

    def _start_thinking_indicator(self, text: str = "正在思考") -> None:
        self._thinking = True
        self._assistant_idle_ticks = 0
        self._status_message = _thinking_base_text(text)
        timer = self._thinking_timer
        if timer is not None:
            timer.resume()
        self._render_status()

    def _pause_thinking_indicator(self) -> None:
        self._assistant_idle_ticks = 0
        if self._thinking:
            self._thinking = False
            self._status_message = "正在回复"
            self._render_status()

    def _stop_thinking_indicator(self) -> None:
        self._thinking = False
        self._assistant_idle_ticks = 0
        timer = self._thinking_timer
        if timer is not None:
            timer.pause()

    def _tick_thinking_indicator(self) -> None:
        if self._thinking:
            self._thinking_tick += 1
            self._render_status()
            return
        if self._busy and self._current_assistant is not None:
            self._assistant_idle_ticks += 1
            if self._assistant_idle_ticks >= THINKING_IDLE_TICKS:
                self._start_thinking_indicator("正在思考")

    def _render_status(self) -> None:
        try:
            self.query_one("#status", Static).update(self._format_status_line())
        except NoMatches:
            pass

    def _sync_work_plan_from_status(self) -> None:
        data = self._backend_status
        if not isinstance(data, dict):
            return
        context_state = data.get("context_state") if isinstance(data.get("context_state"), dict) else {}
        if "work_plan_items" not in context_state and "work_plan_summary" not in context_state:
            return
        self._update_work_plan(
            context_state.get("work_plan_items"),
            summary=context_state.get("work_plan_summary", ""),
        )

    def _update_work_plan(self, items: Any, *, summary: Any = "") -> None:
        try:
            self.query_one("#work_plan_panel", WorkPlanPanel).update_plan(items, summary=summary)
        except NoMatches:
            return

    def _sync_queue_panel(self) -> None:
        try:
            self.query_one("#pending_queue_panel", PendingQueuePanel).update_queue(list(self._queue))
        except NoMatches:
            return

    def _current_work_plan_text(self) -> str:
        try:
            panel = self.query_one("#work_plan_panel", WorkPlanPanel)
        except NoMatches:
            return "当前没有工作计划。"
        if not panel.items:
            return "当前没有工作计划。复杂任务开始后，AI 会在输入框上方维护一个可见计划。"
        return panel._render_text()

    async def _refresh_backend_status(self) -> None:
        try:
            self._backend_status = await self.backend.status_snapshot()
        except Exception:
            return
        self._render_status()

    def _sync_composer_height(self) -> None:
        try:
            composer = self.query_one("#composer", Composer)
        except NoMatches:
            return
        content_width = max(20, composer.size.width - 2)
        lines = _wrapped_visual_line_count(composer.text, content_width)
        composer.styles.height = min(COMPOSER_MAX_LINES, max(COMPOSER_MIN_LINES, lines))

    def _sync_command_palette(self) -> None:
        try:
            composer = self.query_one("#composer", Composer)
        except NoMatches:
            return
        commands = self._filter_contextual_commands(client_command_suggestions(composer.text))
        self._palette().show_commands(commands)

    def _filter_contextual_commands(self, commands: list[ClientCommandSpec]) -> list[ClientCommandSpec]:
        if not commands:
            return []
        if not self._is_palette_contextual():
            return [command for command in commands if command.name not in CONTEXTUAL_COMMANDS]
        return [
            command
            for command in commands
            if command.name not in CONTEXTUAL_COMMANDS or self._contextual_command_available(command.name)
        ]

    def _is_palette_contextual(self) -> bool:
        return bool(self._backend_status.get("pending_approval"))

    def _has_active_wait(self) -> bool:
        return bool(self._backend_status.get("pending_approval")) and self._busy

    def _contextual_command_available(self, name: str) -> bool:
        if name in APPROVAL_COMMANDS:
            return bool(self._backend_status.get("pending_approval"))
        return True

    def _hide_command_palette(self) -> None:
        try:
            self._palette().hide()
        except NoMatches:
            return

    def _palette(self) -> CommandPalette:
        return self.query_one("#command_palette", CommandPalette)

    def _handle_palette_submit_completion(self, text: str) -> bool:
        if not text or not _is_palette_input(text):
            return False
        palette = self._palette()
        selected = palette.selected_command()
        if selected is None:
            return False
        prefix = text.strip()[1:].lower()
        if selected.name == prefix:
            return False
        composer = self.query_one("#composer", Composer)
        composer.load_text(f"/{selected.name} ")
        _move_composer_cursor_to_end(composer)
        self._sync_composer_height()
        self._hide_command_palette()
        return True

    async def _handle_local_command(self, text: str) -> bool:
        command, arg = _parse_local_command(text)
        if command is None:
            return False
        if command == "check":
            await self._run_service_check(arg)
            return True
        if command == "help":
            await self._add_message(format_client_command_help(), role="meta")
            return True
        if command == "status":
            if arg:
                await self._add_message("用法：/status", role="error")
                return True
            await self._refresh_backend_status()
            await self._add_message(
                _format_client_status_snapshot(
                    self._backend_status,
                    queued_count=len(self._queue),
                    busy=self._busy,
                ),
                role="meta",
            )
            return True
        if command == "plan":
            await self._add_message(self._current_work_plan_text(), role="meta")
            return True
        if command == "clear":
            await self._clear_transcript()
            return True
        if command == "copy-last":
            try:
                path = self._write_last_assistant_message(arg)
            except Exception as error:
                await self._add_message(str(error), role="error")
                return True
            await self._add_message(f"最近一条 AI 回复已写入：{path}", role="meta")
            return True
        if command == "details":
            self._show_tool_details = not self._show_tool_details
            state = "开启" if self._show_tool_details else "关闭"
            self._rerender_tool_blocks()
            await self._add_message(f"工具细节显示：{state}", role="meta")
            return True
        if command == "export":
            path = self._export_transcript(arg)
            await self._add_message(f"已导出当前对话：{path}", role="meta")
            return True
        if command == "exit":
            self._stop_thinking_indicator()
            self._set_status("正在关闭")
            await self.backend.close()
            self.exit()
            return True
        return False

    async def _run_service_check(self, arg: str) -> None:
        await self._add_message("正在检查当前 AI 服务...", role="meta")
        self._set_status("检查 AI 服务")
        result = await self.backend.check_service(arg or "只回复 ok")
        if result.get("ok"):
            lines = [
                "AI 服务可用",
                f"service={result.get('service', '')}",
                f"model={result.get('model', '')}",
                f"thread={result.get('thread_id', '')}",
            ]
            assistant_message = str(result.get("assistant_message") or "").strip()
            if assistant_message:
                lines.extend(["", f"回复：{assistant_message}"])
            await self._add_message("\n".join(lines), role="meta")
            self._set_status("AI 服务可用")
            return
        error_text = str(result.get("formatted_error") or result.get("error") or "AI 服务检查失败。")
        await self._add_message(error_text, role="error")
        self._set_status("AI 服务检查失败")

    async def _paste_from_clipboard(self, composer: Composer) -> None:
        self._log_composer_input_debug("clipboard_image_probe_start", composer_text=_text_debug_payload(composer.text))
        if self._busy:
            self._set_status("AI 正在处理，图片请在当前回复结束后粘贴")
            await self._add_message("当前 AI 正在处理，图片请在回复结束后再粘贴。", role="meta")
            return
        try:
            placeholders = await self.backend.attach_clipboard_images()
        except Exception as error:
            self._log_composer_input_debug("clipboard_image_probe_error", error=type(error).__name__)
            await self._add_message(str(error), role="error")
            return
        self._log_composer_input_debug(
            "clipboard_image_probe_result",
            placeholder_count=len(placeholders),
            composer_text=_text_debug_payload(composer.text),
        )
        if not placeholders:
            return
        _insert_attachment_placeholders(composer, placeholders)
        self._log_composer_input_debug(
            "clipboard_image_placeholders_inserted",
            placeholder_count=len(placeholders),
            composer_text=_text_debug_payload(composer.text),
        )
        self._sync_composer_height()
        self._sync_command_palette()
        self._set_status(f"已添加图片 {' '.join(placeholders)}")

    def _log_composer_input_debug(self, phase: str, **fields: Any) -> None:
        if not self._input_debug_enabled:
            return
        event = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "phase": phase,
            "fields": _json_safe_debug_payload(fields),
        }
        try:
            self._input_debug_path.parent.mkdir(parents=True, exist_ok=True)
            with self._input_debug_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except Exception:
            return

    async def _clear_transcript(self) -> None:
        transcript = self.query_one("#transcript", VerticalScroll)
        for child in list(transcript.children):
            await child.remove()
        self._current_assistant = None
        self._active_tools.clear()
        self._transcript_records.clear()
        self._pre_echoed_queue_messages.clear()
        self._set_status("已清空")

    def _format_status_line(self) -> str:
        data = self._backend_status
        if not isinstance(data, dict):
            data = {}
        context_state = data.get("context_state") if isinstance(data.get("context_state"), dict) else {}
        plan = context_state.get("current_plan_path") or ""
        debug_workspace = context_state.get("current_debug_workspace") or ""
        output_dir = context_state.get("latest_output_dir") or ""
        thread_id = str(data.get("thread_id") or "").strip()
        service = str(data.get("service") or "").strip()
        pending_attachments = data.get("pending_attachments") or 0
        display_status = self._display_status_message()
        if data.get("pending_approval") and not _is_active_input_status(display_status):
            status_message = "等待人工确认"
        else:
            status_message = display_status
        parts = [status_message]
        if service:
            parts.append(service)
        if thread_id:
            parts.append(f"thread {thread_id}")
        if plan:
            parts.append(f"plan {_short_path(plan, self.project_root)}")
        work_items = context_state.get("work_plan_items")
        if isinstance(work_items, list) and work_items:
            active = next((item for item in work_items if isinstance(item, dict) and item.get("status") == "in_progress"), None)
            if isinstance(active, dict) and active.get("title"):
                parts.append(f"todo {_single_line_preview(str(active.get('title')), limit=36)}")
            else:
                completed = sum(1 for item in work_items if isinstance(item, dict) and item.get("status") == "completed")
                parts.append(f"todo {completed}/{len(work_items)}")
        if debug_workspace:
            parts.append(f"debug {_short_path(debug_workspace, self.project_root)}")
        if output_dir:
            parts.append(f"output {_short_path(output_dir, self.project_root)}")
        if self._queue:
            parts.append(f"queued {len(self._queue)}")
        if data.get("busy") or self._busy:
            parts.append("working")
        if data.get("pending_approval"):
            parts.append("approval")
        if pending_attachments:
            parts.append(f"images {pending_attachments}")
        return " | ".join(parts)

    def _display_status_message(self) -> str:
        if not self._thinking:
            return self._status_message
        dots = "." * (self._thinking_tick % 4)
        return f"{_thinking_base_text(self._status_message)}{dots}"

    def _export_transcript(self, arg: str) -> Path:
        raw_path = arg.strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self.project_root / ".keygen" / "client-exports" / f"transcript-{timestamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_format_transcript_markdown(self._transcript_records), encoding="utf-8")
        return path

    def _write_last_assistant_message(self, arg: str) -> Path:
        text = ""
        for role, record_text in reversed(self._transcript_records):
            if role == "assistant" and record_text.strip():
                text = record_text
                break
        if not text:
            raise ValueError("当前没有可写入的 AI 回复。")
        raw_path = arg.strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
        else:
            path = self.project_root / ".keygen" / "client-exports" / "last-assistant.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path

    def _rerender_tool_blocks(self) -> None:
        for block in self.query(ToolBlock):
            block.update_event(block.event, show_details=self._show_tool_details)
        self._sync_tool_transcript_records()

    def _sync_tool_transcript_records(self) -> None:
        remaining: dict[str, str] = {block.tool_name: block.text for block in self.query(ToolBlock)}
        next_records: list[tuple[str, str]] = []
        for role, text in self._transcript_records:
            if role != "tool":
                next_records.append((role, text))
                continue
            tool_name = _transcript_tool_name(text)
            if tool_name in remaining:
                next_records.append((role, remaining.pop(tool_name)))
            else:
                next_records.append((role, text))
        self._transcript_records = next_records

    async def action_quit(self) -> None:
        await self.backend.close()
        self.exit()


def run_textual_client(project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
    app = AICTextualApp(
        AITerminalBackend(project_root, service=service, thread_id=thread_id),
        project_root=project_root,
    )
    app.run()


def _wrapped_visual_line_count(text: str, width: int) -> int:
    lines = str(text).split("\n") or [""]
    total = 0
    for line in lines:
        visual_width = _terminal_cell_width(line)
        total += max(1, (visual_width + width - 1) // width)
    return total


def _normalize_work_plan_items_for_ui(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, str]] = []
    for raw_item in items[:12]:
        if not isinstance(raw_item, dict):
            continue
        title = _single_line_preview(str(raw_item.get("title") or raw_item.get("step") or ""), limit=96)
        status = str(raw_item.get("status") or "pending").strip()
        if not title or status not in {"pending", "in_progress", "completed"}:
            continue
        note = _single_line_preview(str(raw_item.get("note") or ""), limit=120)
        item = {"title": title, "status": status}
        if note:
            item["note"] = note
        normalized.append(item)
    return normalized


def _visible_work_plan_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(items) <= 6:
        return list(items)
    visible: list[dict[str, str]] = []
    active_index = next((index for index, item in enumerate(items) if item.get("status") == "in_progress"), -1)
    if active_index >= 0:
        start = max(0, active_index - 1)
        end = min(len(items), active_index + 4)
        visible.extend(items[start:end])
    else:
        visible.extend([item for item in items if item.get("status") != "completed"][:5])
    if len(visible) < 6:
        for item in reversed(items):
            if item.get("status") == "completed" and item not in visible:
                visible.insert(0, item)
            if len(visible) >= 6:
                break
    return visible[:6]


def _prefix_lines(text: str, prefix: str) -> str:
    lines = str(text).splitlines() or [""]
    if len(lines) == 1:
        return prefix + lines[0]
    continuation = " " * _terminal_cell_width(prefix)
    return "\n".join((prefix if index == 0 else continuation) + line for index, line in enumerate(lines))


def _event_line(text: str, prefix: str, *, limit: int = MAX_COMPACT_EVENT_CHARS) -> str:
    return prefix + _single_line_preview(text, limit=limit)


def _render_diff_text(text: str) -> Text:
    rendered = Text()
    lines = str(text or "").splitlines()
    if not lines:
        return Text("diff")
    for index, line in enumerate(lines):
        if index:
            rendered.append("\n")
        style = ""
        if line.startswith("diff ") or line.startswith("index ") or line.startswith("@@"):
            style = "bold #d9c384"
        elif line.startswith("+++") or line.startswith("---"):
            style = "#b7c5d6"
        elif line.startswith("+"):
            style = "#8fd694"
        elif line.startswith("-"):
            style = "#ff9b9b"
        rendered.append(line, style=style)
    return rendered


def _thinking_base_text(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return "正在思考"
    return stripped.rstrip(".。…")


def _is_active_input_status(text: str) -> bool:
    value = str(text or "").strip()
    return value.startswith("已收到输入") or value.startswith("输入处理失败") or value.startswith("输入未被接收")


def _message_block_type(role: str) -> type[MessageBlock]:
    if role == "meta":
        return MetaBlock
    if role == "plan":
        return PlanProgressBlock
    if role == "file":
        return FileChangeBlock
    if role == "diff":
        return DiffBlock
    if role == "artifact":
        return ArtifactBlock
    if role == "activity":
        return ActivityBlock
    if role == "summary":
        return TurnSummaryBlock
    if role == "approval":
        return ApprovalBlock
    return MessageBlock


def _terminal_cell_width(text: str) -> int:
    total = 0
    for char in text:
        total += 2 if east_asian_width(char) in {"F", "W"} else 1
    return total


def _short_path(value: Any, project_root: Path) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        if path.is_absolute():
            try:
                return str(path.relative_to(project_root))
            except ValueError:
                home = Path(os.path.expanduser("~"))
                try:
                    return "~/" + str(path.relative_to(home))
                except ValueError:
                    pass
        parts = path.parts
        if len(parts) > 4:
            return str(Path(*parts[-4:]))
        return str(path)
    except Exception:
        return text


def _format_client_status_snapshot(data: dict[str, Any], *, queued_count: int, busy: bool) -> str:
    if not isinstance(data, dict):
        data = {}
    context_state = data.get("context_state") if isinstance(data.get("context_state"), dict) else {}
    service = str(data.get("service") or "").strip() or "<未初始化>"
    model = str(data.get("model") or "").strip() or "<未知模型>"
    thread_id = str(data.get("thread_id") or "").strip() or "<无>"
    plan = context_state.get("current_plan_path") or ""
    debug_workspace = context_state.get("current_debug_workspace") or ""
    output_dir = context_state.get("latest_output_dir") or ""
    pending_attachments = data.get("pending_attachments") or 0
    pending_approval = bool(data.get("pending_approval"))
    ai_busy = bool(data.get("busy") or busy)
    lines = [
        "状态：",
        f"  AI      {'忙碌' if ai_busy else '就绪'} | service={service} | model={model} | thread={thread_id}",
        f"  plan    {plan or '<无>'}",
        f"  debug   {debug_workspace or '<无>'}",
        f"  output  {output_dir or '<无>'}",
        f"  queue   {queued_count}",
        f"  approval {'pending' if pending_approval else 'none'}",
        f"  images  {pending_attachments}",
    ]
    last_error = str(data.get("last_error") or "").strip()
    if last_error:
        lines.append(f"  error   {_single_line_preview(last_error, limit=140)}")
    return "\n".join(lines)


def _format_tool_event(event: ClientEvent, *, show_details: bool) -> str:
    title = _tool_event_name(event)
    status = _tool_phase(event)
    summary = _tool_summary(event)
    phase_label = {
        "running": "运行中",
        "done": "完成",
        "failed": "失败",
    }.get(status, status)
    header = f"工具 {phase_label} {title}"
    if not show_details:
        if not summary:
            return header
        return f"{header} {_single_line_preview(summary, limit=MAX_COMPACT_EVENT_CHARS)}"
    detail_lines = [header]
    if summary:
        detail_lines.extend(["", summary])
    arguments = event.data.get("arguments")
    if isinstance(arguments, dict) and arguments:
        detail_lines.extend(["", "参数:", _format_json_block(arguments)])
    result = event.data.get("result")
    if isinstance(result, dict) and result:
        detail_lines.extend(["", "结果:", _format_json_block(result)])
    return "\n".join(detail_lines)


def _format_file_change_event(event: ClientEvent) -> str:
    data = event.data
    label = {
        "created": "创建",
        "updated": "写入",
        "appended": "追加",
        "patched": "修改",
        "applied": "应用",
    }.get(str(data.get("action") or ""), "变更")
    path = data.get("relative_path") or data.get("path") or event.title or "<unknown>"
    parts = [f"文件 {label}", _short_path(path, Path.cwd())]
    if data.get("bytes") not in {None, ""}:
        parts.append(f"{data.get('bytes')} bytes")
    if data.get("detail"):
        parts.append(str(data.get("detail")))
    return " · ".join(str(part) for part in parts if str(part or "").strip())


def _format_diff_event(event: ClientEvent) -> str:
    data = event.data
    changed_files = data.get("changed_files") if isinstance(data.get("changed_files"), list) else []
    patch_path = data.get("patch_path") or event.title or ""
    parts = ["diff"]
    if patch_path:
        parts.append(_short_path(patch_path, Path.cwd()))
    if changed_files:
        parts.append("files=" + ", ".join(str(item) for item in changed_files[:6]))
        if len(changed_files) > 6:
            parts.append("...")
    if data.get("truncated"):
        parts.append("truncated")
    return " · ".join(parts)


def _format_artifact_event(event: ClientEvent) -> str:
    data = event.data
    label = {
        "output_dir": "输出目录",
        "patch": "补丁文件",
    }.get(str(data.get("artifact_type") or ""), "产物")
    parts = [label]
    if data.get("path"):
        parts.append(_short_path(data.get("path"), Path.cwd()))
    if data.get("status"):
        parts.append(f"status={data.get('status')}")
    if data.get("bytes") not in {None, ""}:
        parts.append(f"{data.get('bytes')} bytes")
    changed_files = data.get("changed_files") if isinstance(data.get("changed_files"), list) else []
    if changed_files:
        parts.append(f"files={len(changed_files)}")
    return " · ".join(str(part) for part in parts if str(part or "").strip())


def _format_activity_event(event: ClientEvent) -> str:
    text = str(event.text or "").strip()
    if not text:
        text = str(event.title or "").strip() or "活动"
    category = str(event.data.get("category") or "").strip()
    phase = str(event.data.get("phase") or "").strip()
    prefix = {
        "thinking": "思考",
        "plan": "计划",
        "tool": "工具",
        "search": "搜索",
        "file": "文件",
        "run": "运行",
        "context": "上下文",
        "review": "回顾",
    }.get(category, "")
    phase_label = {
        "start": "开始",
        "done": "完成",
        "failed": "失败",
        "next": "下一步",
    }.get(phase, "")
    parts = [part for part in (prefix, phase_label, text) if part]
    return " · ".join(parts) if parts else text


def _should_render_activity_event(event: ClientEvent) -> bool:
    source_kind = str(event.data.get("source_kind") or "").strip()
    if source_kind in {
        "tool_started",
        "tool_finished",
        "plan_progress",
        "file_changed",
        "diff",
        "artifact",
        "approval_requested",
        "error",
    }:
        return False
    category = str(event.data.get("category") or "").strip()
    if category in {"thinking", "tool", "run", "file", "review"}:
        return False
    return True


def _should_record_activity_event(event: ClientEvent) -> bool:
    if not _should_render_activity_event(event):
        return False
    category = str(event.data.get("category") or "").strip()
    return category in {"plan", "context"} or not category


def _format_turn_summary(summary: TurnSummary) -> str:
    lines = ["本轮结果"]
    if summary.tools_done or summary.tools_failed:
        parts = []
        if summary.tools_done:
            parts.append("完成 " + ", ".join(summary.tools_done[:8]))
        if summary.tools_failed:
            parts.append("失败 " + ", ".join(summary.tools_failed[:8]))
        lines.append("工具：" + "；".join(parts))
    elif summary.tools_started:
        lines.append("工具：" + ", ".join(summary.tools_started[:8]))
    if summary.files:
        lines.append("文件：" + _join_summary_items(summary.files))
    if summary.diffs:
        lines.append("Diff：" + _join_summary_items(summary.diffs))
    if summary.artifacts:
        lines.append("产物：" + _join_summary_items(summary.artifacts))
    if summary.plan_events:
        lines.append("Plan：" + _summarize_plan_events(summary.plan_events))
    if summary.activities:
        lines.append("进度：" + _summarize_activities(summary.activities))
    if summary.approvals:
        lines.append("等待确认：" + _join_summary_items(summary.approvals, limit=2))
    if summary.errors:
        lines.append("错误：" + _join_summary_items(summary.errors, limit=2))
    if summary.assistant_chars and len(lines) == 1:
        lines.append(f"回复：{summary.assistant_chars} 字符")
    next_step = _summary_next_step(summary)
    if next_step:
        lines.append("下一步：" + next_step)
    return "\n".join(lines)


def _join_summary_items(items: list[str], *, limit: int = 4) -> str:
    compacted = [_single_line_preview(item, limit=120) for item in items if str(item or "").strip()]
    visible = compacted[:limit]
    if len(compacted) > limit:
        visible.append(f"... 还有 {len(compacted) - limit} 项")
    return "；".join(visible)


def _summarize_plan_events(events: list[str]) -> str:
    if not events:
        return ""
    starts = sum(1 for event in events if "开始" in event and "步骤" in event)
    failures = [event for event in events if "失败" in event or "运行错误" in event]
    waits = [event for event in events if "等待" in event]
    finished = [event for event in events if "plan 结束" in event]
    parts = []
    if waits:
        if starts:
            parts.append(f"最近步骤进度 {starts} 条")
        parts.append(_single_line_preview(waits[-1], limit=100))
    if failures:
        if starts and not waits:
            parts.append(f"最近步骤进度 {starts} 条")
        parts.append(_single_line_preview(failures[-1], limit=100))
    elif finished:
        parts.append(_single_line_preview(finished[-1], limit=80))
    elif starts and not waits:
        parts.append(f"最近步骤进度 {starts} 条")
    if not parts:
        parts.append(_single_line_preview(events[-1], limit=100))
    return "；".join(parts)


def _summarize_activities(activities: list[str]) -> str:
    compacted = [_single_line_preview(item, limit=80) for item in activities if str(item or "").strip()]
    if not compacted:
        return ""
    if len(compacted) <= 3:
        return "；".join(compacted)
    return "；".join(compacted[:2] + [f"... 还有 {len(compacted) - 2} 项"])


def _summary_next_step(summary: TurnSummary) -> str:
    if summary.errors or summary.approvals:
        return ""
    if summary.tools_failed:
        return "查看失败工具结果，决定是否调试或让用户补充信息。"
    if summary.diffs or summary.files:
        return "检查变更内容，必要时运行校验。"
    if summary.plan_events:
        real_plan_progress = any(
            "步骤" in event
            or "plan 开始" in event
            or "plan 结束" in event
            or "等待" in event
            or "失败" in event
            or "运行错误" in event
            for event in summary.plan_events
        )
        if not real_plan_progress and summary.activities:
            return "按可见计划继续推进。"
        if any("失败" in event or "运行错误" in event for event in summary.plan_events):
            return "查看运行日志和失败页面状态，定位后再修复 plan。"
        if any("等待" in event for event in summary.plan_events):
            return "等待你在当前 Playwright 浏览器窗口完成确认。"
        if any("plan 结束" in event for event in summary.plan_events):
            return "查看输出产物并做验收总结。"
        return "继续观察 plan 运行进度。"
    if summary.activities:
        return "按可见计划继续推进。"
    if summary.tools_done:
        return "根据工具结果继续分析或执行下一步。"
    if summary.artifacts:
        return "查看产物并确认是否满足目标。"
    return ""


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _append_limited(items: list[str], value: str, *, limit: int) -> None:
    text = str(value or "").strip()
    if text and len(items) < limit:
        items.append(text)


def _tool_event_name(event: ClientEvent) -> str:
    raw = event.data.get("tool_name") or event.title or "tool"
    return str(raw)


def _tool_summary(event: ClientEvent) -> str:
    text = event.text.strip()
    return text


def _tool_phase(event: ClientEvent) -> str:
    if event.kind == "tool_started":
        return "running"
    phase = str(event.data.get("phase") or "").strip().lower()
    if phase in {"done", "failed"}:
        return phase
    ok = event.data.get("ok")
    return "done" if ok is not False else "failed"


def _format_json_block(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _transcript_tool_name(text: str) -> str:
    first_line = text.splitlines()[0] if text else ""
    parts = first_line.split()
    if len(parts) >= 3 and parts[0] in {"tool", "工具"}:
        return parts[2]
    prefix = "tool "
    if not first_line.startswith(prefix) or "：" not in first_line:
        return parts[2] if len(parts) >= 3 and parts[0] == "tool" else ""
    _, _, rest = first_line.partition("：")
    return rest.split(" ", 1)[0].strip()


def _format_approval_text(text: str) -> str:
    body = str(text or "").strip()
    body = _strip_bracketed_label(body)
    title = "需要你确认"
    if not body:
        return title
    extra = _approval_guidance(body)
    if extra:
        return f"{title}\n{body}\n\n{extra}"
    return f"{title}\n{body}"


def _format_error_text(text: str) -> str:
    body = str(text or "").strip()
    if body.startswith("错误："):
        body = body[len("错误：") :].strip()
    return "error\n" + body if body else "error"


def _format_interruption_text(
    text: str | None,
    *,
    queued_count: int,
    intervention_text: str,
) -> str:
    base = str(text or "").strip() or "已中断当前任务。"
    if not intervention_text:
        return base
    preview = _single_line_preview(intervention_text, limit=80)
    return f"{base}\n已介入排队消息 {queued_count} 条，下一轮优先处理：{preview}"


def _single_line_preview(text: str, *, limit: int) -> str:
    preview = " ".join(str(text or "").split())
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 3)].rstrip() + "..."


def _strip_bracketed_label(text: str) -> str:
    if not text.startswith("[") or "]" not in text:
        return text
    _, _, rest = text.partition("]")
    return rest.strip()


def _is_single_line_slash_input(text: str) -> bool:
    stripped = str(text).strip()
    return stripped.startswith("/") and "\n" not in stripped


def _is_command_input(text: str) -> bool:
    return str(text).lstrip().startswith("/")


def _is_palette_input(text: str) -> bool:
    raw = str(text)
    return raw.startswith("/") and "\n" not in raw and " " not in raw and "\t" not in raw


def _palette_move_direction(event: Any) -> str | None:
    key = str(getattr(event, "key", "")).lower()
    aliases = {str(alias).lower() for alias in getattr(event, "aliases", []) or []}
    if key in {"up", "cursor_up"} or {"up", "cursor_up"} & aliases:
        return "up"
    if key in {"down", "cursor_down"} or {"down", "cursor_down"} & aliases:
        return "down"
    return None


def _is_newline_key_event(event: Any) -> bool:
    key = str(getattr(event, "key", "")).lower()
    aliases = {str(alias).lower() for alias in getattr(event, "aliases", []) or []}
    newline_keys = {"newline", "shift+enter", "alt+enter", "option+enter", "meta+enter"}
    return key in newline_keys or bool(newline_keys & aliases)


def _parse_local_command(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, ""
    command, _, arg = stripped[1:].partition(" ")
    normalized = command.lower()
    if normalized in {"check", "help", "clear", "copy-last", "details", "exit", "export", "plan", "status"}:
        return normalized, arg.strip()
    return None, ""


GROUPABLE_TRANSCRIPT_ROLES = frozenset(
    {"activity", "approval", "artifact", "diff", "error", "file", "meta", "plan", "summary", "tool"}
)


def _format_transcript_markdown(records: list[tuple[str, str]]) -> str:
    lines = ["# AI Client Transcript", ""]
    index = 0
    while index < len(records):
        role, text = records[index]
        title = {
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool",
            "plan": "Plan",
            "file": "File",
            "diff": "Diff",
            "artifact": "Artifact",
            "summary": "Summary",
            "error": "Error",
        }.get(role, role.title())
        if role in GROUPABLE_TRANSCRIPT_ROLES:
            group = [text.rstrip()]
            index += 1
            while index < len(records) and records[index][0] == role:
                group.append(records[index][1].rstrip())
                index += 1
            body = "\n".join(item for item in group if item)
            lines.extend([f"## {title}", "", body, ""])
            continue
        lines.extend([f"## {title}", "", text.rstrip(), ""])
        index += 1
    return "\n".join(lines).rstrip() + "\n"


def _approval_guidance(body: str) -> str:
    if (
        "直接回复" in body
        or "回复“继续”" in body
        or "回复\"继续\"" in body
        or "输入“继续”" in body
        or "输入\"继续\"" in body
        or "输入“停止”" in body
        or "输入\"停止\"" in body
        or "要停止就输入“停止”" in body
        or "要停止就输入\"停止\"" in body
    ):
        return ""
    if _looks_like_browser_handoff(body):
        return "请在当前已经打开的 Playwright 浏览器窗口完成操作。完成后回到这里输入“继续”；要停止就输入“停止”。"
    if "/approve" in body or "/reject" in body:
        return ""
    return "可以直接回复“继续”或“停止”。"


def _resolves_pending_approval(text: str | None) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return any(
        signal in value
        for signal in (
            "人工确认已继续",
            "运行后检查已继续",
            "确认：已理解为继续。",
            "确认输入：",
        )
    )


def _looks_like_browser_handoff(body: str) -> bool:
    signals = (
        "人工确认",
        "运行后检查",
        "manual_confirm",
        "post_run_inspection",
        "浏览器",
        "Playwright",
        "登录",
        "验证码",
        "验证",
    )
    return any(signal in body for signal in signals)


def _clamp_index(index: int, length: int) -> int:
    if length <= 0:
        return 0
    return max(0, min(index, length - 1))


def _event_debug_payload(event: Any | None) -> dict[str, Any]:
    if event is None:
        return {}
    character = getattr(event, "character", None)
    event_text = getattr(event, "text", None)
    return {
        "class": event.__class__.__name__,
        "key": getattr(event, "key", None),
        "aliases": list(getattr(event, "aliases", []) or []),
        "character": _text_debug_payload(character),
        "text": _text_debug_payload(event_text),
    }


def _text_debug_payload(text: Any) -> dict[str, Any]:
    if text is None:
        return {"present": False}
    value = str(text)
    line_count = value.count("\n") + 1 if value else 0
    return {
        "present": True,
        "length": len(value),
        "lines": line_count,
        "sha256_12": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
    }


def _json_safe_debug_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_debug_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_debug_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _move_composer_cursor_to_end(composer: Composer) -> None:
    line = composer.text.split("\n")[-1]
    row = composer.text.count("\n")
    location = (row, len(line))
    composer.selection = composer.selection.__class__(location, location)


def _insert_attachment_placeholders(composer: Composer, placeholders: list[str]) -> None:
    prefix = " ".join(placeholders)
    if not prefix:
        return
    insert_text = _spaced_insert_text(composer.text, composer.selection.end, prefix)
    result = composer.insert(insert_text)
    composer.move_cursor(result.end_location)


def _spaced_insert_text(text: str, location: tuple[int, int], insert: str) -> str:
    lines = text.split("\n")
    row, column = location
    line = lines[row] if 0 <= row < len(lines) else ""
    before_char = line[column - 1] if column > 0 and column <= len(line) else ""
    after_char = line[column] if 0 <= column < len(line) else ""
    leading = "" if not before_char or before_char.isspace() else " "
    trailing = "" if after_char and after_char.isspace() else " "
    return f"{leading}{insert}{trailing}"
