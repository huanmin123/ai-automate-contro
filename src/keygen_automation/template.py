from __future__ import annotations

import re
from typing import Any


PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}")
FULL_PLACEHOLDER_RE = re.compile(r"^\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}$")


def render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, variables)
    if isinstance(value, list):
        return [render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, variables) for key, item in value.items()}
    return value


def _render_string(template: str, variables: dict[str, Any]) -> str:
    full_match = FULL_PLACEHOLDER_RE.match(template)
    if full_match:
        return _resolve_path(full_match.group(1), variables)

    def replace(match: re.Match[str]) -> str:
        return str(_resolve_path(match.group(1), variables))

    return PLACEHOLDER_RE.sub(replace, template)


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
