from __future__ import annotations

import re
from typing import Any


SENSITIVE_FIELD_TOKENS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "cookie",
    "credential",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
    "密码",
    "口令",
    "验证码",
)
SENSITIVE_CONTEXT_VALUE_KEYS = {"value", "values", "content", "default"}
SAFE_SECRET_PLACEHOLDER_VALUES = {"", "[REDACTED]", "<redacted>", "redacted", "***"}
ENV_REFERENCE_RE = re.compile(
    r"^(?:"
    r"\$env:[A-Za-z_][A-Za-z0-9_]*|"
    r"env:[A-Za-z_][A-Za-z0-9_]*|"
    r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|"
    r"%[A-Za-z_][A-Za-z0-9_]*%|"
    r"[A-Z][A-Z0-9_]{2,}"
    r")$"
)
INLINE_SECRET_PATTERNS = (
    re.compile(
        r"(?P<label>(?i:api[_ -]?key|apikey|authorization|auth[_ -]?token|token|secret|password|passwd|pwd))"
        r"(?P<sep>\s*[:：=]\s*|\s+)"
        r"(?P<value>[A-Za-z0-9@._~+/=-]{4,})"
        r"(?P<tail>[,.;!?)]*)"
    ),
    re.compile(
        r"(?P<label>密码|口令)"
        r"(?P<sep>\s*[:：=]?\s*)"
        r"(?P<value>[A-Za-z0-9@._~+/=-]{4,})"
        r"(?P<tail>[,.;!?，。；！）]*)"
    ),
    re.compile(
        r"(?P<label>验证码)"
        r"(?P<sep>\s*[:：=]?\s*)"
        r"(?P<value>\d{4,8})"
        r"(?P<tail>[,.;!?，。；！）]*)"
    ),
    re.compile(
        r"(?P<label>Bearer\s+)"
        r"(?P<value>[A-Za-z0-9._~+/=-]{8,})"
        r"(?P<tail>[,.;!?)]*)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<label>sk-)"
        r"(?P<value>[A-Za-z0-9]{8,})"
        r"(?P<tail>\b)"
    ),
)


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        sensitive_context = _dict_has_sensitive_context(value)
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key) or (
                sensitive_context and text_key.strip().lower() in SENSITIVE_CONTEXT_VALUE_KEYS
            ):
                redacted[text_key] = "[REDACTED]"
            else:
                redacted[text_key] = redact_sensitive_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    return value


def redact_sensitive_text(text: str) -> str:
    redacted = str(text or "")
    for pattern in INLINE_SECRET_PATTERNS:
        redacted = pattern.sub(_redact_inline_secret_match, redacted)
    return redacted


def collect_sensitive_literal_paths(value: Any) -> list[str]:
    """Return JSON-style paths that appear to contain secret literals.

    Template references such as ``{{password}}`` and environment variable
    references such as ``OPENAI_API_KEY`` are intentionally allowed. The goal is
    to stop AI-created plan files from persisting real credentials while still
    allowing reusable plans to refer to runtime variables.
    """

    return _collect_sensitive_literal_paths(value, path="$", sensitive_context=False)


def is_sensitive_key(key: str) -> bool:
    return _is_sensitive_key(key)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in SENSITIVE_FIELD_TOKENS)


def _dict_has_sensitive_context(value: dict[Any, Any]) -> bool:
    for key, item in value.items():
        text_key = str(key)
        if _is_sensitive_key(text_key):
            return True
        if text_key.strip().lower() in {
            "name",
            "field",
            "label",
            "placeholder",
            "selector",
            "locator",
            "css",
            "xpath",
            "test_id",
            "id",
            "autocomplete",
            "kind",
        } and _is_sensitive_key(str(item)):
            return True
    return False


def _collect_sensitive_literal_paths(value: Any, *, path: str, sensitive_context: bool) -> list[str]:
    if isinstance(value, dict):
        local_sensitive_context = sensitive_context or _dict_has_sensitive_context(value)
        findings: list[str] = []
        for key, item in value.items():
            text_key = str(key)
            item_path = f"{path}.{_path_key(text_key)}"
            if _is_secret_storage_key(text_key):
                if not _safe_secret_reference(item, key=text_key):
                    findings.append(item_path)
                continue
            if local_sensitive_context and text_key.strip().lower() in SENSITIVE_CONTEXT_VALUE_KEYS:
                if not _safe_secret_reference(item, key=text_key):
                    findings.append(item_path)
                continue
            findings.extend(
                _collect_sensitive_literal_paths(
                    item,
                    path=item_path,
                    sensitive_context=local_sensitive_context,
                )
            )
        return findings
    if isinstance(value, list):
        findings: list[str] = []
        for index, item in enumerate(value):
            findings.extend(
                _collect_sensitive_literal_paths(
                    item,
                    path=f"{path}[{index}]",
                    sensitive_context=sensitive_context,
                )
            )
        return findings
    return []


def _is_secret_storage_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.endswith("_env"):
        return False
    metadata_tokens = (
        "selector",
        "locator",
        "label",
        "placeholder",
        "field_count",
        "detected",
        "signal",
        "type",
        "autocomplete",
        "save_as",
    )
    if any(token in normalized for token in metadata_tokens):
        return False
    return _is_sensitive_key(key)


def _safe_secret_reference(value: Any, *, key: str) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        if text in SAFE_SECRET_PLACEHOLDER_VALUES:
            return True
        lowered = text.lower()
        if lowered in SAFE_SECRET_PLACEHOLDER_VALUES:
            return True
        if "{{" in text and "}}" in text:
            return True
        if ENV_REFERENCE_RE.fullmatch(text):
            return True
        normalized_key = key.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_key.endswith("_env"):
            return True
        return False
    if isinstance(value, list):
        return all(_safe_secret_reference(item, key=key) for item in value)
    if isinstance(value, tuple):
        return all(_safe_secret_reference(item, key=key) for item in value)
    if isinstance(value, dict):
        return not _collect_sensitive_literal_paths(value, path="$", sensitive_context=True)
    return False


def _path_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    return json_path_quote(key)


def json_path_quote(key: str) -> str:
    return "[" + repr(key) + "]"


def _redact_inline_secret_match(match: re.Match[str]) -> str:
    label = match.group("label")
    sep = match.groupdict().get("sep", "")
    tail = match.groupdict().get("tail", "")
    return f"{label}{sep}[REDACTED]{tail}"
