from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_rules import ACTION_TYPES


def validate_type_field(
    step: dict[str, Any],
    action: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    allowed_types = ACTION_TYPES.get(action)
    if not allowed_types:
        return
    step_type = step.get("type")
    if action == "wait" and (step_type is None or step_type == "time") and _has_non_time_wait_fields(step):
        issues.append(
            ValidationIssue(
                location,
                "wait with selector/url/text/expected must set an explicit non-time type: selector, url, text, or count",
            )
        )
        return
    if action in {"wait", "scroll"} and step_type is None:
        return
    if not isinstance(step_type, str) or not step_type:
        issues.append(ValidationIssue(location, f"{action}.type must be a non-empty string"))
        return
    if step_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        issues.append(ValidationIssue(location, f"unsupported {action}.type: {step_type}; expected one of: {allowed}"))


def _has_non_time_wait_fields(step: dict[str, Any]) -> bool:
    return any(field in step for field in ("selector", "url", "text", "expected"))


def validate_type_specific_required_fields(
    step: dict[str, Any],
    action: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    step_type = step.get("type")
    required: tuple[str, ...] = ()

    if action == "navigate" and step_type == "goto":
        required = ("url",)
    elif action == "page" and step_type in {"open", "switch"}:
        required = ("page",)
    elif action == "element" and step_type in {"fill", "type"}:
        required = ("value",)
    elif action == "element" and step_type == "press":
        required = ("key",)
    elif action == "element" and step_type == "set_files":
        required = ("files",)
    elif action == "wait" and step_type in {"selector", None}:
        required = ("selector",) if step_type == "selector" else ()
    elif action == "wait" and step_type == "url":
        required = ("url",)
    elif action == "wait" and step_type == "text":
        required = ("selector", "text")
    elif action == "wait" and step_type == "count":
        required = ("selector", "expected")
    elif action == "extract" and step_type in {"text", "value", "attribute", "html", "all_texts", "all_values"}:
        required = ("selector",)
    elif action == "extract" and step_type == "attribute":
        required = ("selector", "attribute")
    elif action == "extract" and step_type == "count":
        required = ("selector",)
    elif action == "extract" and step_type == "table":
        required = ("row_selector",)
    elif action == "keyboard" and step_type in {"press", "down", "up"}:
        required = ("key",)
    elif action == "keyboard" and step_type == "type":
        required = ("value",)
    elif action == "mouse" and step_type in {"move", "click"}:
        required = ("x", "y")
    elif action == "assert" and step_type == "selector":
        required = ("selector",)
    elif action == "assert" and step_type in {"text", "value"}:
        required = ("selector", "expected")
    elif action == "assert" and step_type == "url":
        required = ("expected",)
    elif action == "assert" and step_type == "count":
        required = ("selector", "expected")
    elif action == "ai" and step_type == "extract_data":
        required = ("schema",)
    elif action == "ai" and step_type == "classify_text" and "schema" not in step:
        required = ("labels",)

    for field in required:
        if field not in step:
            issues.append(ValidationIssue(location, f"missing required field for {action}.{step_type}: {field}"))
