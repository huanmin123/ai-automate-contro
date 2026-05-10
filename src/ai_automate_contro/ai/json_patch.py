from __future__ import annotations

import json
from typing import Any


def normalize_json_patch_operation(operation: Any) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise ValueError("Each JSON patch operation must be an object.")
    op_name = str(operation.get("op", "")).strip().lower()
    if op_name not in {"add", "replace", "remove"}:
        raise ValueError("JSON patch operation op must be add, replace, or remove.")
    path = normalize_json_path(operation.get("path"))
    if op_name in {"add", "replace"} and "value" not in operation:
        raise ValueError(f"JSON patch operation '{op_name}' requires value.")
    normalized: dict[str, Any] = {
        "op": op_name,
        "path": path,
    }
    if "value" in operation:
        normalized["value"] = operation["value"]
    return normalized


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


def apply_json_patch_operations(document: Any, operations: list[dict[str, Any]]) -> Any:
    current_document = document
    for operation in operations:
        op_name = operation["op"]
        path = operation["path"]
        if op_name == "replace":
            current_document = _replace_json_path(current_document, path, operation["value"])
        elif op_name == "add":
            current_document = _add_json_path(current_document, path, operation["value"])
        elif op_name == "remove":
            current_document = _remove_json_path(current_document, path)
        else:
            raise ValueError(f"Unsupported JSON patch operation: {op_name}")
    return current_document


def serialize_json_patch_result(
    original_text: str,
    updated_document: Any,
    operations: list[dict[str, Any]],
) -> tuple[str, str]:
    patched_text = _try_patch_json_text_in_place(original_text, updated_document, operations)
    if patched_text is not None:
        return patched_text, "in_place"
    return json.dumps(updated_document, ensure_ascii=False, indent=2) + _detect_json_trailing_newline(original_text), "rewrite"


def _unescape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _replace_json_path(document: Any, path: list[Any], value: Any) -> Any:
    if not path:
        return value
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {_format_json_path(path)}")
        parent[key] = value
        return document
    if isinstance(parent, list):
        index = _coerce_json_list_index(segment, len(parent), allow_end=False)
        parent[index] = value
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _add_json_path(document: Any, path: list[Any], value: Any) -> Any:
    if not path:
        return value
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        parent[str(segment)] = value
        return document
    if isinstance(parent, list):
        if segment == "-":
            parent.append(value)
            return document
        index = _coerce_json_list_index(segment, len(parent), allow_end=True)
        parent.insert(index, value)
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _remove_json_path(document: Any, path: list[Any]) -> Any:
    if not path:
        raise ValueError("Removing the JSON document root is not supported.")
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {_format_json_path(path)}")
        del parent[key]
        return document
    if isinstance(parent, list):
        index = _coerce_json_list_index(segment, len(parent), allow_end=False)
        del parent[index]
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _resolve_json_parent(document: Any, path: list[Any]) -> tuple[Any, Any]:
    current = document
    for depth, segment in enumerate(path[:-1], start=1):
        if isinstance(current, dict):
            key = str(segment)
            if key not in current:
                raise KeyError(f"JSON path does not exist: {_format_json_path(path[:depth])}")
            current = current[key]
            continue
        if isinstance(current, list):
            index = _coerce_json_list_index(segment, len(current), allow_end=False)
            current = current[index]
            continue
        raise TypeError(f"JSON path segment is not reachable: {_format_json_path(path[:depth])}")
    return current, path[-1]


def _coerce_json_list_index(segment: Any, length: int, *, allow_end: bool) -> int:
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


def _format_json_path(path: list[Any]) -> str:
    if not path:
        return "<root>"
    return "/" + "/".join(str(segment).replace("~", "~0").replace("/", "~1") for segment in path)


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
        raise ValueError("JSON text is empty.")
    return _find_json_value_span_from(text, start, path)


def _find_json_value_span_from(text: str, index: int, path: list[Any]) -> tuple[int, int]:
    start = _skip_json_whitespace(text, index)
    if not path:
        return start, _scan_json_value_end(text, start)
    if start >= len(text):
        raise ValueError("Unexpected end of JSON text.")
    marker = text[start]
    if marker == "{":
        return _find_json_object_member_span(text, start, path)
    if marker == "[":
        return _find_json_array_item_span(text, start, path)
    raise TypeError(f"JSON path cannot continue through scalar at {_format_json_path(path)}")


def _find_json_object_member_span(text: str, object_start: int, path: list[Any]) -> tuple[int, int]:
    target_key = str(path[0])
    index = _skip_json_whitespace(text, object_start + 1)
    if index < len(text) and text[index] == "}":
        raise KeyError(f"JSON object key does not exist: {target_key}")
    while index < len(text):
        key, index = _parse_json_string(text, index)
        index = _skip_json_whitespace(text, index)
        if index >= len(text) or text[index] != ":":
            raise ValueError("Invalid JSON object: expected colon after key.")
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
            raise KeyError(f"JSON object key does not exist: {target_key}")
        raise ValueError("Invalid JSON object: expected comma or closing brace.")
    raise ValueError("Invalid JSON object: missing closing brace.")


def _find_json_array_item_span(text: str, array_start: int, path: list[Any]) -> tuple[int, int]:
    target_index = _coerce_json_list_index(path[0], _json_array_length(text, array_start), allow_end=False)
    index = _skip_json_whitespace(text, array_start + 1)
    current_index = 0
    if index < len(text) and text[index] == "]":
        raise IndexError(f"JSON array index out of range: {target_index}")
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
            raise IndexError(f"JSON array index out of range: {target_index}")
        raise ValueError("Invalid JSON array: expected comma or closing bracket.")
    raise ValueError("Invalid JSON array: missing closing bracket.")


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
        raise ValueError("Invalid JSON array: expected comma or closing bracket.")
    raise ValueError("Invalid JSON array: missing closing bracket.")


def _parse_json_string(text: str, index: int) -> tuple[str, int]:
    index = _skip_json_whitespace(text, index)
    if index >= len(text) or text[index] != '"':
        raise ValueError("Invalid JSON: expected string.")
    value, end = json.JSONDecoder().raw_decode(text, index)
    if not isinstance(value, str):
        raise ValueError("Invalid JSON: expected string.")
    return value, end


def _scan_json_value_end(text: str, index: int) -> int:
    _, end = json.JSONDecoder().raw_decode(text, index)
    return end


def _skip_json_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index
