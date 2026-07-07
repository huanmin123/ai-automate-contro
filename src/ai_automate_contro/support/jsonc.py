from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def strip_json_line_comments(text: str) -> str:
    """Remove // line comments outside JSON strings while preserving line/column offsets."""
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            result.extend((" ", " "))
            index += 2
            while index < length and text[index] not in "\r\n":
                result.append(" ")
                index += 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


def loads_jsonc(text: str) -> Any:
    return json.loads(strip_json_line_comments(text))


def load_jsonc(path: str | Path) -> Any:
    return loads_jsonc(Path(path).read_text(encoding="utf-8"))
