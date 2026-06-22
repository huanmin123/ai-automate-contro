from __future__ import annotations

from typing import Any


# Compatibility module. The project policy is local-debugging-first, so these
# helpers intentionally keep values unchanged.
SENSITIVE_FIELD_TOKENS: tuple[str, ...] = ()
SECRET_FIELD_TOKENS = SENSITIVE_FIELD_TOKENS
SENSITIVE_CONTEXT_VALUE_KEYS: set[str] = set()
SAFE_SECRET_PLACEHOLDER_VALUES: set[str] = set()
SECRET_VALUE_PATTERNS: tuple[Any, ...] = ()


def redact_sensitive_data(value: Any) -> Any:
    return value


def redact_sensitive_text(text: str) -> str:
    return str(text or "")


def redact_secret_text(value: Any) -> str:
    return str(value or "")


def redact_secret_value(value: Any, *, key: Any = "") -> str:
    return str(value or "")


def collect_sensitive_literal_paths(value: Any) -> list[str]:
    return []


def is_sensitive_key(key: str) -> bool:
    return False


def json_path_quote(key: str) -> str:
    return "[" + repr(key) + "]"
