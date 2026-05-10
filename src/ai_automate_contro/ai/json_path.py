from __future__ import annotations

from typing import Any


def normalize_json_path(raw_path: Any) -> list[Any]:
    if isinstance(raw_path, list):
        path: list[Any] = []
        for segment in raw_path:
            if isinstance(segment, bool) or not isinstance(segment, (str, int)):
                raise ValueError("JSON path array segments must be strings or integers.")
            path.append(segment)
        return path
    if isinstance(raw_path, str):
        if raw_path == "":
            return []
        if not raw_path.startswith("/"):
            raise ValueError("String JSON paths must be JSON Pointer values, for example /steps/0/message.")
        return [_unescape_json_pointer_segment(segment) for segment in raw_path.split("/")[1:]]
    raise ValueError("JSON patch operation path must be an array or JSON Pointer string.")


def coerce_json_list_index(segment: Any, length: int, *, allow_end: bool) -> int:
    if isinstance(segment, bool):
        raise TypeError("JSON array index cannot be a boolean.")
    if isinstance(segment, int):
        index = segment
    elif isinstance(segment, str) and segment.isdecimal():
        index = int(segment)
    else:
        raise TypeError(f"JSON array index must be an integer, got {segment!r}.")
    upper_bound = length if allow_end else length - 1
    if index < 0 or index > upper_bound:
        raise IndexError(f"JSON array index out of range: {index}")
    return index


def format_json_path(path: list[Any]) -> str:
    if not path:
        return "<root>"
    return "/" + "/".join(str(segment).replace("~", "~0").replace("/", "~1") for segment in path)


def _unescape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")
