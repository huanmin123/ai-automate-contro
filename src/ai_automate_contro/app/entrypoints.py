from __future__ import annotations

import os
import sys
from pathlib import Path

from ai_automate_contro.app.cli import run_cli, run_cplan_cli


def main() -> None:
    raise SystemExit(run_cli(_resolve_project_root()))


def cplan() -> None:
    raise SystemExit(run_cplan_cli(_resolve_project_root()))


def _resolve_project_root() -> Path:
    raw_project_root = os.environ.get("AI_AUTOMATE_PROJECT_ROOT")
    if raw_project_root:
        return Path(_normalize_path_text(raw_project_root)).resolve()
    return Path.cwd().resolve()


def _normalize_path_text(raw_path: str) -> str:
    text = raw_path.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    if os.name != "nt" and "\\" in text and not _looks_like_windows_absolute_path(text):
        text = text.replace("\\", "/")
    return text


def _looks_like_windows_absolute_path(text: str) -> bool:
    return len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}
