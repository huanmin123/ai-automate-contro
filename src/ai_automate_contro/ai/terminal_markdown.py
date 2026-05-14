from __future__ import annotations

import io
import os
import sys
from typing import TextIO

from rich.console import Console
from rich.markdown import Markdown
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


def terminal_supports_rich_markdown(stream: TextIO | None = None) -> bool:
    stream = stream or sys.stdout
    if not bool(getattr(stream, "isatty", lambda: False)()):
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    clicolor_force = os.environ.get("CLICOLOR_FORCE", "").strip().lower()
    if os.environ.get("CLICOLOR") == "0" and clicolor_force in {"", "0", "false", "no", "off"}:
        return False
    console = Console(file=stream, legacy_windows=False, theme=MARKDOWN_THEME)
    return bool(
        console.is_terminal
        and not getattr(console, "is_dumb_terminal", False)
        and console.color_system is not None
    )


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


def _markdown_renderable(markdown_text: str) -> Markdown:
    return Markdown(markdown_text or "", code_theme="ansi_light", style="none", hyperlinks=False)

