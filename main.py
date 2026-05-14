from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_terminal_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def resolve_project_root(source_root: Path) -> Path:
    raw_project_root = os.environ.get("AI_AUTOMATE_PROJECT_ROOT")
    if raw_project_root:
        return Path(normalize_startup_path_text(raw_project_root)).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root


def normalize_startup_path_text(raw_path: str) -> str:
    text = raw_path.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    if os.name != "nt" and "\\" in text and not _looks_like_windows_absolute_path(text):
        text = text.replace("\\", "/")
    return text


def _looks_like_windows_absolute_path(text: str) -> bool:
    return len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}


configure_terminal_encoding()
SOURCE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = resolve_project_root(SOURCE_ROOT)
if not getattr(sys, "frozen", False):
    SRC_DIR = SOURCE_ROOT / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

from ai_automate_contro.app.cli import run_cli


def main() -> None:
    raise SystemExit(run_cli(PROJECT_ROOT))


if __name__ == "__main__":
    main()
