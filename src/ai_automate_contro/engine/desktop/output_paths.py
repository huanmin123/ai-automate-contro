from __future__ import annotations

from pathlib import Path


def output_relative_path(path: Path) -> str:
    parts = path.parts
    if "output" in parts:
        index = len(parts) - 1 - list(reversed(parts)).index("output")
        return str(Path(*parts[index + 1 :]))
    return path.name
