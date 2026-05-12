from __future__ import annotations

from typing import Any


def normalize_json_path(raw_path: Any) -> list[Any]:
    if isinstance(raw_path, list):
        path: list[Any] = []
        for segment in raw_path:
            if isinstance(segment, bool) or not isinstance(segment, (str, int)):
                raise ValueError("JSON path 数组片段必须是字符串或整数。")
            path.append(segment)
        return path
    if isinstance(raw_path, str):
        if raw_path == "":
            return []
        if not raw_path.startswith("/"):
            raise ValueError("字符串 JSON path 必须是 JSON Pointer，例如 /steps/0/message。")
        return [_unescape_json_pointer_segment(segment) for segment in raw_path.split("/")[1:]]
    raise ValueError("JSON patch 操作的 path 必须是数组或 JSON Pointer 字符串。")


def coerce_json_list_index(segment: Any, length: int, *, allow_end: bool) -> int:
    if isinstance(segment, bool):
        raise TypeError("JSON 数组索引不能是布尔值。")
    if isinstance(segment, int):
        index = segment
    elif isinstance(segment, str) and segment.isdecimal():
        index = int(segment)
    else:
        raise TypeError(f"JSON 数组索引必须是整数，实际收到：{segment!r}。")
    upper_bound = length if allow_end else length - 1
    if index < 0 or index > upper_bound:
        raise IndexError(f"JSON 数组索引越界：{index}")
    return index


def format_json_path(path: list[Any]) -> str:
    if not path:
        return "<root>"
    return "/" + "/".join(str(segment).replace("~", "~0").replace("/", "~1") for segment in path)


def _unescape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")
