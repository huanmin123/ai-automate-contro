from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]+')


def make_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sanitize_name(value: str) -> str:
    cleaned = INVALID_PATH_CHARS_RE.sub("_", value).strip()
    return cleaned or "unnamed"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def dict_get(value: Any, key: str) -> Any:
    if not isinstance(value, dict):
        return None
    return value.get(key)


def first_string(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def safe_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
