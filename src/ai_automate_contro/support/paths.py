from __future__ import annotations

import os
import re
from pathlib import Path


WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_UNC_PATH_RE = re.compile(r"^\\\\[^\\/]+[\\/][^\\/]+")
COMMON_PROJECT_PATH_ROOTS = (
    "plans",
    "test-plans",
    "handbook",
    "docs",
    "src",
    "resources",
    "sub-plans",
    "output",
)


def normalize_path_text(raw_path: str | Path) -> str:
    """Normalize user/plan path text before handing it to pathlib.

    On POSIX, ``Path(".\\plans\\demo")`` treats backslashes as literal file
    name characters. Most project docs and older plans use Windows-style
    separators, so convert those relative paths to POSIX separators at the
    boundary. Native Windows behavior is left untouched.
    """
    text = str(raw_path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    if os.name != "nt" and "\\" in text and not looks_like_windows_absolute_path(text):
        text = text.replace("\\", "/")
    return text


def path_from_text(raw_path: str | Path) -> Path:
    return Path(normalize_path_text(raw_path))


def resolve_path_text(raw_path: str | Path, *, base: str | Path | None = None) -> Path:
    path = path_from_text(raw_path)
    if path.is_absolute():
        return path.resolve()
    if base is None:
        return path.resolve()
    return (Path(base).resolve() / path).resolve()


def is_absolute_path_text(raw_path: str | Path) -> bool:
    text = str(raw_path).strip().strip("\"'")
    return Path(normalize_path_text(text)).is_absolute() or looks_like_windows_absolute_path(text)


def looks_like_windows_absolute_path(raw_path: str | Path) -> bool:
    text = str(raw_path).strip().strip("\"'")
    return bool(WINDOWS_DRIVE_PATH_RE.match(text) or WINDOWS_UNC_PATH_RE.match(text))


def shell_eaten_windows_path_hint(raw_path: str | Path) -> str:
    if os.name == "nt":
        return ""
    text = str(raw_path).strip().strip("\"'")
    if not text or "/" in text or "\\" in text:
        return ""
    normalized = text.removeprefix("./").removeprefix(".")
    if not any(normalized.startswith(root) for root in COMMON_PROJECT_PATH_ROOTS):
        return ""
    return (
        "这个路径看起来像是在 macOS/Linux shell 中未加引号输入了 Windows 写法，"
        "反斜杠已经被 shell 吃掉。请改用 ./plans/... 这种正斜杠路径，"
        "或把 Windows 写法放进单引号，例如 '.\\plans\\demo\\plan.json'。"
    )


def format_missing_path_message(raw_path: str | Path, resolved_path: Path, *, label: str = "文件") -> str:
    hint = shell_eaten_windows_path_hint(raw_path)
    message = f"{label}不存在：{resolved_path}"
    if hint:
        message = f"{message}；{hint}"
    return message
