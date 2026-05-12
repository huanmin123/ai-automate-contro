from __future__ import annotations

import json
from typing import Any

from ai_automate_contro.ai.json_path import coerce_json_list_index, format_json_path


def serialize_json_patch_result(
    original_text: str,
    updated_document: Any,
    operations: list[dict[str, Any]],
) -> tuple[str, str]:
    patched_text = _try_patch_json_text_in_place(original_text, updated_document, operations)
    if patched_text is not None:
        return patched_text, "in_place"
    return json.dumps(updated_document, ensure_ascii=False, indent=2) + _detect_json_trailing_newline(original_text), "rewrite"


def _try_patch_json_text_in_place(
    original_text: str,
    updated_document: Any,
    operations: list[dict[str, Any]],
) -> str | None:
    candidate = original_text
    for operation in operations:
        if operation["op"] != "replace":
            return None
        value = operation["value"]
        if isinstance(value, (dict, list)):
            return None
        try:
            start, end = _find_json_value_span(candidate, operation["path"])
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        candidate = candidate[:start] + json.dumps(value, ensure_ascii=False) + candidate[end:]
    try:
        if json.loads(candidate) != updated_document:
            return None
    except json.JSONDecodeError:
        return None
    return candidate


def _detect_json_trailing_newline(original_text: str) -> str:
    if original_text.endswith("\r\n"):
        return "\r\n"
    if original_text.endswith("\n"):
        return "\n"
    return "\n"


def _find_json_value_span(text: str, path: list[Any]) -> tuple[int, int]:
    start = _skip_json_whitespace(text, 0)
    if start >= len(text):
        raise ValueError("JSON 文本为空。")
    return _find_json_value_span_from(text, start, path)


def _find_json_value_span_from(text: str, index: int, path: list[Any]) -> tuple[int, int]:
    start = _skip_json_whitespace(text, index)
    if not path:
        return start, _scan_json_value_end(text, start)
    if start >= len(text):
        raise ValueError("JSON 文本意外结束。")
    marker = text[start]
    if marker == "{":
        return _find_json_object_member_span(text, start, path)
    if marker == "[":
        return _find_json_array_item_span(text, start, path)
    raise TypeError(f"JSON path 不能穿过标量值：{format_json_path(path)}")


def _find_json_object_member_span(text: str, object_start: int, path: list[Any]) -> tuple[int, int]:
    target_key = str(path[0])
    index = _skip_json_whitespace(text, object_start + 1)
    if index < len(text) and text[index] == "}":
        raise KeyError(f"JSON 对象 key 不存在：{target_key}")
    while index < len(text):
        key, index = _parse_json_string(text, index)
        index = _skip_json_whitespace(text, index)
        if index >= len(text) or text[index] != ":":
            raise ValueError("JSON 对象格式无效：key 后应为冒号。")
        value_start = _skip_json_whitespace(text, index + 1)
        value_end = _scan_json_value_end(text, value_start)
        if key == target_key:
            if len(path) == 1:
                return value_start, value_end
            return _find_json_value_span_from(text, value_start, path[1:])
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "}":
            raise KeyError(f"JSON 对象 key 不存在：{target_key}")
        raise ValueError("JSON 对象格式无效：应为逗号或右花括号。")
    raise ValueError("JSON 对象格式无效：缺少右花括号。")


def _find_json_array_item_span(text: str, array_start: int, path: list[Any]) -> tuple[int, int]:
    target_index = coerce_json_list_index(path[0], _json_array_length(text, array_start), allow_end=False)
    index = _skip_json_whitespace(text, array_start + 1)
    current_index = 0
    if index < len(text) and text[index] == "]":
        raise IndexError(f"JSON 数组索引越界：{target_index}")
    while index < len(text):
        value_start = _skip_json_whitespace(text, index)
        value_end = _scan_json_value_end(text, value_start)
        if current_index == target_index:
            if len(path) == 1:
                return value_start, value_end
            return _find_json_value_span_from(text, value_start, path[1:])
        current_index += 1
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "]":
            raise IndexError(f"JSON 数组索引越界：{target_index}")
        raise ValueError("JSON 数组格式无效：应为逗号或右中括号。")
    raise ValueError("JSON 数组格式无效：缺少右中括号。")


def _json_array_length(text: str, array_start: int) -> int:
    index = _skip_json_whitespace(text, array_start + 1)
    length = 0
    if index < len(text) and text[index] == "]":
        return 0
    while index < len(text):
        value_start = _skip_json_whitespace(text, index)
        value_end = _scan_json_value_end(text, value_start)
        length += 1
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "]":
            return length
        raise ValueError("JSON 数组格式无效：应为逗号或右中括号。")
    raise ValueError("JSON 数组格式无效：缺少右中括号。")


def _parse_json_string(text: str, index: int) -> tuple[str, int]:
    index = _skip_json_whitespace(text, index)
    if index >= len(text) or text[index] != '"':
        raise ValueError("JSON 格式无效：应为字符串。")
    value, end = json.JSONDecoder().raw_decode(text, index)
    if not isinstance(value, str):
        raise ValueError("JSON 格式无效：应为字符串。")
    return value, end


def _scan_json_value_end(text: str, index: int) -> int:
    _, end = json.JSONDecoder().raw_decode(text, index)
    return end


def _skip_json_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index
