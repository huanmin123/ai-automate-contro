from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unicodedata import east_asian_width

from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.events import Paste, Resize
from textual.message import Message
from textual.widgets import Static, TextArea

from ai_automate_contro.client.backend import AITerminalBackend, AgentClientBackend
from ai_automate_contro.client.commands import (
    ClientCommandSpec,
    client_command_suggestions,
    format_client_command_help,
)
from ai_automate_contro.client.events import ClientEvent


MAX_TOOL_DETAIL_CHARS = 420


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
            return Markdown(self.text)
        return self.text


class CommandPalette(Static):
    def __init__(self) -> None:
        self.commands: list[ClientCommandSpec] = []
        self.selected_index = 0
        super().__init__("", id="command_palette")
        self.display = False

    def show_commands(self, commands: list[ClientCommandSpec], *, selected_index: int = 0) -> None:
        self.commands = commands
        self.selected_index = _clamp_index(selected_index, len(commands))
        if not commands:
            self.hide()
            return
        self.display = True
        self.update(self._render_text())

    def hide(self) -> None:
        self.commands = []
        self.selected_index = 0
        self.display = False
        self.update("")

    def move_selection(self, delta: int) -> None:
        if not self.commands:
            return
        self.selected_index = (self.selected_index + delta) % len(self.commands)
        self.update(self._render_text())

    def selected_command(self) -> ClientCommandSpec | None:
        if not self.commands:
            return None
        return self.commands[_clamp_index(self.selected_index, len(self.commands))]

    def _render_text(self) -> str:
        lines = []
        for index, command in enumerate(self.commands):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} /{command.name:<10} {command.description}")
        return "\n".join(lines)


class Composer(TextArea):
    BINDINGS = [
        Binding("enter", "submit", "发送", show=False),
        Binding("ctrl+j", "newline", "换行", show=False),
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
        self.post_message(self.PaletteRequested(self, "paste").set_sender(self))

    async def _on_key(self, event: Any) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.action_submit()
            return
        if event.key == "ctrl+j":
            event.stop()
            event.prevent_default()
            self.action_newline()
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.post_message(self.PaletteRequested(self, "complete").set_sender(self))
            return
        if event.key in {"up", "down"} and _is_palette_input(self.text):
            event.stop()
            event.prevent_default()
            self.post_message(self.PaletteRequested(self, event.key).set_sender(self))
            return
        if event.key == "escape":
            self.post_message(self.PaletteRequested(self, "hide").set_sender(self))
        await super()._on_key(event)

    async def _on_paste(self, event: Paste) -> None:
        if event.text:
            await super()._on_paste(event)


class AICTextualApp(App[None]):
    CSS = """
    Screen {
        background: #ffffff;
        color: #1f2328;
    }

    #root {
        height: 100%;
    }

    #transcript {
        height: 1fr;
        padding: 1 2;
        background: #ffffff;
    }

    #status {
        height: 1;
        padding: 0 2;
        color: #8c959f;
        background: #ffffff;
    }

    #command_palette {
        max-height: 8;
        margin: 0 2 0 2;
        padding: 0 1;
        color: #57606a;
        background: #f6f8fa;
    }

    #composer {
        height: 1;
        min-height: 1;
        max-height: 6;
        margin: 0 2 1 2;
        padding: 0 1;
        border: none;
        background: #eeeeee;
        color: #1f2328;
        scrollbar-size: 0 0;
    }

    #composer:focus {
        border: none;
        background: #eeeeee;
    }

    #composer .text-area--cursor-line {
        background: #eeeeee;
    }

    #composer .text-area--selection {
        background: #d0d7de;
        color: #1f2328;
    }

    #composer .text-area--placeholder {
        color: #8c959f;
    }

    .message {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    .user {
        background: #eeeeee;
        color: #1f2328;
        min-height: 1;
    }

    .assistant {
        background: #ffffff;
        color: #1f2328;
    }

    .tool {
        color: #6e7781;
        background: #ffffff;
    }

    .error {
        color: #b42318;
        background: #fff5f5;
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
        self._current_assistant: MessageBlock | None = None
        self._show_tool_details = False
        self._transcript_records: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield VerticalScroll(id="transcript")
            yield Static("", id="status")
            yield CommandPalette()
            yield Composer(
                "",
                soft_wrap=True,
                tab_behavior="focus",
                show_line_numbers=False,
                highlight_cursor_line=False,
                placeholder="描述需求，/ 打开命令，Enter 发送，Ctrl+J 换行",
                compact=True,
                id="composer",
            )

    def on_mount(self) -> None:
        self.query_one("#composer", Composer).focus()
        self._sync_composer_height()
        self._set_status("就绪")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "composer":
            self._sync_composer_height()
            self._sync_command_palette()

    def on_resize(self, _: Resize) -> None:
        self._sync_composer_height()

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
        await self._add_message(text, role="user")
        if self._busy and await self.backend.submit_during_turn(text):
            return
        self._queue.append(text)
        if not self._busy:
            self.run_worker(self._drain_queue(), name="agent-turns", exclusive=True)
        else:
            self._set_status(f"排队 {len(self._queue)} 条")

    def on_composer_palette_requested(self, event: Composer.PaletteRequested) -> None:
        event.stop()
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

    async def _drain_queue(self) -> None:
        self._busy = True
        try:
            while self._queue:
                message = self._queue.popleft()
                await self._run_turn(message)
        finally:
            self._busy = False
            self._current_assistant = None
            self._set_status("就绪")

    async def _run_turn(self, message: str) -> None:
        self._current_assistant = None
        async for client_event in self.backend.stream(message):
            await self._handle_client_event(client_event)

    async def _handle_client_event(self, event: ClientEvent) -> None:
        if event.kind == "status":
            self._set_status(event.text or "正在处理")
            return
        if event.kind == "assistant_delta":
            if self._current_assistant is None:
                self._current_assistant = await self._add_message("", role="assistant")
            self._current_assistant.append(event.text)
            await self._scroll_end()
            return
        if event.kind == "assistant_done":
            self._current_assistant = None
            await self._scroll_end()
            return
        if event.kind in {"tool_started", "tool_finished"}:
            title = event.title or "tool"
            await self._add_message(_format_tool_event(event, show_details=self._show_tool_details), role="tool")
            return
        if event.kind == "terminal_output":
            await self._add_message(event.text, role="tool")
            return
        if event.kind == "approval_requested":
            await self._add_message(f"[等待审批] {event.text}", role="tool")
            return
        if event.kind == "error":
            text = event.text if event.text.startswith("错误：") else f"错误：{event.text}"
            await self._add_message(text, role="error")
            return
        if event.kind == "exit_requested":
            self._set_status(event.text or "正在关闭")
            await self.backend.close()
            self.exit()

    async def _add_message(self, text: str, *, role: str) -> MessageBlock:
        block = MessageBlock(text, role=role)
        transcript = self.query_one("#transcript", VerticalScroll)
        await transcript.mount(block)
        self._transcript_records.append((role, text))
        await self._scroll_end()
        return block

    async def _scroll_end(self) -> None:
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.scroll_end(animate=False)

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#status", Static).update(text)
        except NoMatches:
            return

    def _sync_composer_height(self) -> None:
        try:
            composer = self.query_one("#composer", Composer)
        except NoMatches:
            return
        content_width = max(20, composer.size.width - 2)
        lines = _wrapped_visual_line_count(composer.text, content_width)
        composer.styles.height = min(6, max(1, lines))

    def _sync_command_palette(self) -> None:
        try:
            composer = self.query_one("#composer", Composer)
        except NoMatches:
            return
        commands = client_command_suggestions(composer.text)
        self._palette().show_commands(commands)

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
        prefix = text.strip()[1:].lower().replace("-", "_")
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
        if command == "help":
            await self._add_message(format_client_command_help(), role="tool")
            return True
        if command == "details":
            self._show_tool_details = not self._show_tool_details
            state = "开启" if self._show_tool_details else "关闭"
            await self._add_message(f"工具细节显示：{state}", role="tool")
            return True
        if command == "export":
            path = self._export_transcript(arg)
            await self._add_message(f"已导出当前对话：{path}", role="tool")
            return True
        return False

    async def _paste_from_clipboard(self, composer: Composer) -> None:
        clipboard_text = self.app.clipboard
        if clipboard_text:
            composer.insert(clipboard_text)
            self._sync_composer_height()
            self._sync_command_palette()
            return
        try:
            placeholders = await self.backend.attach_clipboard_images()
        except Exception as error:
            await self._add_message(str(error), role="error")
            return
        if not placeholders:
            return
        _insert_attachment_placeholders(composer, placeholders)
        self._sync_composer_height()
        self._sync_command_palette()
        self._set_status(f"已添加图片 {' '.join(placeholders)}")

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


def _terminal_cell_width(text: str) -> int:
    total = 0
    for char in text:
        total += 2 if east_asian_width(char) in {"F", "W"} else 1
    return total


def _format_tool_event(event: ClientEvent, *, show_details: bool) -> str:
    title = event.title or "tool"
    if event.kind == "tool_started":
        label = "tool"
        state = "running"
    else:
        label = "tool"
        state = "done"
    text = event.text.strip()
    if not show_details and len(text) > MAX_TOOL_DETAIL_CHARS:
        text = text[: MAX_TOOL_DETAIL_CHARS - 1].rstrip() + "..."
    if not text:
        return f"{label} {state}: {title}"
    return f"{label} {state}: {title}\n{text}" if show_details else f"{label} {state}: {title} {text}"


def _is_single_line_slash_input(text: str) -> bool:
    stripped = str(text).strip()
    return stripped.startswith("/") and "\n" not in stripped


def _is_palette_input(text: str) -> bool:
    raw = str(text)
    return raw.startswith("/") and "\n" not in raw and " " not in raw and "\t" not in raw


def _parse_local_command(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, ""
    command, _, arg = stripped[1:].partition(" ")
    normalized = command.lower().replace("-", "_")
    if normalized in {"help", "details", "export"}:
        return normalized, arg.strip()
    return None, ""


def _format_transcript_markdown(records: list[tuple[str, str]]) -> str:
    lines = ["# AI Client Transcript", ""]
    for role, text in records:
        title = {
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool",
            "error": "Error",
        }.get(role, role.title())
        lines.extend([f"## {title}", "", text.rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def _clamp_index(index: int, length: int) -> int:
    if length <= 0:
        return 0
    return max(0, min(index, length - 1))


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
