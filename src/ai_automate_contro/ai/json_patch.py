from __future__ import annotations

from typing import Any

from ai_automate_contro.ai.json_path import (
    coerce_json_list_index,
    format_json_path,
    normalize_json_path,
)


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


def _replace_json_path(document: Any, path: list[Any], value: Any) -> Any:
    if not path:
        return value
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {format_json_path(path)}")
        parent[key] = value
        return document
    if isinstance(parent, list):
        index = coerce_json_list_index(segment, len(parent), allow_end=False)
        parent[index] = value
        return document
    raise TypeError(f"JSON path parent is not a container: {format_json_path(path[:-1])}")


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
        index = coerce_json_list_index(segment, len(parent), allow_end=True)
        parent.insert(index, value)
        return document
    raise TypeError(f"JSON path parent is not a container: {format_json_path(path[:-1])}")


def _remove_json_path(document: Any, path: list[Any]) -> Any:
    if not path:
        raise ValueError("Removing the JSON document root is not supported.")
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {format_json_path(path)}")
        del parent[key]
        return document
    if isinstance(parent, list):
        index = coerce_json_list_index(segment, len(parent), allow_end=False)
        del parent[index]
        return document
    raise TypeError(f"JSON path parent is not a container: {format_json_path(path[:-1])}")


def _resolve_json_parent(document: Any, path: list[Any]) -> tuple[Any, Any]:
    current = document
    for depth, segment in enumerate(path[:-1], start=1):
        if isinstance(current, dict):
            key = str(segment)
            if key not in current:
                raise KeyError(f"JSON path does not exist: {format_json_path(path[:depth])}")
            current = current[key]
            continue
        if isinstance(current, list):
            index = coerce_json_list_index(segment, len(current), allow_end=False)
            current = current[index]
            continue
        raise TypeError(f"JSON path segment is not reachable: {format_json_path(path[:depth])}")
    return current, path[-1]
