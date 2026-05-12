from __future__ import annotations

import io
import sys
import time
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from rich.theme import Theme


RESPONSE_RENDER_MODES = {"markdown", "plain"}
MARKDOWN_THEME = Theme(
    {
        "markdown.code": "bold cyan",
        "markdown.code_block": "cyan",
        "markdown.h1": "bold",
        "markdown.h2": "bold",
        "markdown.h3": "bold",
        "markdown.h4": "bold",
        "markdown.h5": "bold",
        "markdown.h6": "bold",
    }
)


def normalize_response_render_mode(value: object, *, default: str = "markdown") -> str:
    raw = str(value or "").strip().lower()
    if raw in {"md", "markdown", "rich"}:
        return "markdown"
    if raw in {"plain", "raw", "text"}:
        return "plain"
    if default not in RESPONSE_RENDER_MODES:
        return "markdown"
    return default


def terminal_supports_rich_markdown() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def terminal_supports_live_markdown() -> bool:
    return terminal_supports_rich_markdown()


def render_markdown_to_ansi(markdown_text: str, *, width: int = 100) -> str:
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=True,
        color_system="truecolor",
        width=width,
        legacy_windows=False,
        theme=MARKDOWN_THEME,
    )
    console.print(_markdown_renderable(markdown_text))
    return stream.getvalue()


class MarkdownLiveRenderer:
    def __init__(self, *, refresh_per_second: int = 12) -> None:
        self.console = Console(legacy_windows=False, theme=MARKDOWN_THEME)
        self.refresh_per_second = refresh_per_second
        self.buffer = ""
        self.live: Live | None = None
        self._last_update = 0.0

    def push(self, text: str) -> None:
        if not text:
            return
        self.buffer += text
        if self.live is None:
            self.live = Live(
                _assistant_renderable(self.buffer),
                console=self.console,
                refresh_per_second=self.refresh_per_second,
                transient=False,
            )
            self.live.start(refresh=True)
            self._last_update = time.monotonic()
            return
        now = time.monotonic()
        if now - self._last_update >= 0.08 or "\n" in text:
            self.live.update(_assistant_renderable(self.buffer), refresh=True)
            self._last_update = now

    def finish(self) -> None:
        if self.live is None:
            return
        self.live.update(_assistant_renderable(self.buffer), refresh=True)
        self.live.stop()
        self.live = None


def _assistant_renderable(markdown_text: str) -> Any:
    return Group(Text("AI>", style="bold cyan"), _markdown_renderable(markdown_text))


def _markdown_renderable(markdown_text: str) -> Markdown:
    return Markdown(markdown_text or "", code_theme="ansi_light", hyperlinks=False)
