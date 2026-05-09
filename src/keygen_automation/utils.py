from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]+')


def make_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sanitize_name(value: str) -> str:
    cleaned = INVALID_PATH_CHARS_RE.sub("_", value).strip()
    return cleaned or "unnamed"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

