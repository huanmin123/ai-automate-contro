from __future__ import annotations

import re
from typing import Any


PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}")
FULL_PLACEHOLDER_RE = re.compile(r"\A\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}\Z")


def render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, variables, set())
    if isinstance(value, list):
        return [render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, variables) for key, item in value.items()}
    return value


def _render_string(template: str, variables: dict[str, Any], resolving: set[str]) -> str:
    full_match = FULL_PLACEHOLDER_RE.match(template)
    if full_match:
        key = full_match.group(1)
        resolved = _resolve_path(key, variables)
        if isinstance(resolved, str) and PLACEHOLDER_RE.search(resolved):
            return _render_nested_string(key, resolved, variables, resolving)
        return resolved

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        resolved = _resolve_path(key, variables)
        if isinstance(resolved, str) and PLACEHOLDER_RE.search(resolved):
            resolved = _render_nested_string(key, resolved, variables, resolving)
        return str(resolved)

    return PLACEHOLDER_RE.sub(replace, template)


def _render_nested_string(
    key: str,
    value: str,
    variables: dict[str, Any],
    resolving: set[str],
) -> str:
    if key in resolving:
        raise ValueError(f"Circular variable reference detected for '{key}'.")
    resolving.add(key)
    try:
        return _render_string(value, variables, resolving)
    finally:
        resolving.remove(key)


def _resolve_path(path: str, variables: dict[str, Any]) -> Any:
    current: Any = variables
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Variable '{path}' is not defined.")
            current = current[part]
            continue
        raise KeyError(f"Variable '{path}' is not defined.")
    return current
