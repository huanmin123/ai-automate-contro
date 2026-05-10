from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from keygen_automation.ai import AI_TASK_TYPES
from keygen_automation.actions import ActionExecutor
from keygen_automation.config import load_plan_config


SUPPORTED_ACTIONS = {
    name.removeprefix("_action_")
    for name in dir(ActionExecutor)
    if name.startswith("_action_")
}

ACTION_TYPES: dict[str, set[str]] = {
    "variable": {"set", "set_many", "copy"},
    "page": {"open", "switch", "close"},
    "navigate": {"goto", "refresh", "back", "forward"},
    "element": {"click", "hover", "fill", "clear", "type", "focus", "press", "check", "uncheck", "select", "set_files"},
    "wait": {"time", "selector", "url", "text", "count"},
    "extract": {"text", "value", "attribute", "html", "count", "all_texts", "all_values", "table"},
    "keyboard": {"press", "type", "down", "up"},
    "scroll": {"into_view", "by"},
    "mouse": {"move", "click", "down", "up", "wheel"},
    "capture": {"screenshot", "html", "storage_state"},
    "dialog": {"accept", "dismiss"},
    "wait_for_network": {"request", "response"},
    "write": {"json", "text", "csv", "variables"},
    "read": {"json", "text", "csv", "storage_state"},
    "assert": {"selector", "text", "value", "url", "count"},
    "ai": AI_TASK_TYPES,
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "variable": ("type",),
    "run_sub_plan": ("path",),
    "open_browser": ("name",),
    "page": ("browser", "type"),
    "close_browser": ("browser",),
    "navigate": ("browser", "type"),
    "element": ("browser", "type", "selector"),
    "wait": ("browser",),
    "detect_challenge": ("browser", "save_as"),
    "ai": ("type", "input", "save_as"),
    "extract": ("browser", "type", "save_as"),
    "keyboard": ("browser", "type"),
    "scroll": ("browser",),
    "mouse": ("browser", "type"),
    "capture": ("browser", "type", "path"),
    "manual_confirm": (),
    "print": ("message",),
    "dialog": ("type",),
    "wait_for_download": ("browser", "path", "trigger"),
    "wait_for_popup": ("browser", "popup_page", "trigger"),
    "wait_for_network": ("browser", "type", "url", "trigger"),
    "write": ("type", "path"),
    "read": ("type", "path", "save_as"),
    "assert": ("browser", "type"),
    "if": ("condition",),
    "foreach": ("items", "steps"),
    "retry": ("steps",),
    "sleep": ("seconds",),
}

OUTPUT_ACTION_CATEGORIES: dict[tuple[str, str], str] = {
    ("capture", "screenshot"): "screenshots",
    ("capture", "html"): "html",
    ("capture", "storage_state"): "storage-states",
    ("wait_for_download", ""): "downloads",
    ("write", "json"): "json",
    ("write", "text"): "text",
    ("write", "csv"): "csv",
    ("write", "variables"): "variables",
    ("ai", "connectivity"): "ai",
    ("ai", "extract_data"): "ai",
    ("ai", "classify_text"): "ai",
    ("ai", "transform_data"): "ai",
    ("ai", "summarize_text"): "ai",
}

FORBIDDEN_OUTPUT_ROOTS = {"output", "resources", "docs", "sub-plans"}


@dataclass(frozen=True)
class ValidationIssue:
    location: str
    message: str

    def format(self) -> str:
        return f"{self.location}: {self.message}"


@dataclass(frozen=True)
class ValidationResult:
    plan_path: Path
    errors: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_plan_file(plan_path: str | Path, project_root: str | Path) -> ValidationResult:
    resolved_plan_path = Path(plan_path).resolve()
    resolved_project_root = Path(project_root).resolve()
    issues: list[ValidationIssue] = []

    if not resolved_plan_path.exists():
        return ValidationResult(
            plan_path=resolved_plan_path,
            errors=(ValidationIssue(str(resolved_plan_path), "plan file does not exist"),),
        )
    if resolved_plan_path.name != "plan.json":
        issues.append(
            ValidationIssue(
                str(resolved_plan_path),
                "directly executable plan files must be named plan.json",
            )
        )

    document = _load_json_document(resolved_plan_path, issues)
    if document is None:
        return ValidationResult(resolved_plan_path, tuple(issues))

    plan_dir = resolved_plan_path.parent
    _validate_config(resolved_project_root, plan_dir, issues)
    _validate_plan_document(
        document,
        document_path=resolved_plan_path,
        package_root=plan_dir,
        issues=issues,
        stack=[],
    )
    return ValidationResult(resolved_plan_path, tuple(issues))


def _load_json_document(path: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as file:
            document = json.load(file)
    except JSONDecodeError as error:
        issues.append(ValidationIssue(str(path), f"invalid JSON: {error.msg}"))
        return None
    except OSError as error:
        issues.append(ValidationIssue(str(path), str(error)))
        return None
    if not isinstance(document, dict):
        issues.append(ValidationIssue(str(path), "plan document must be a JSON object"))
        return None
    return document


def _validate_config(project_root: Path, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        load_plan_config(project_root, plan_dir)
    except Exception as error:
        issues.append(ValidationIssue(str(plan_dir / "config.json"), f"invalid merged config: {error}"))


def _validate_plan_document(
    document: dict[str, Any],
    *,
    document_path: Path,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    resolved_document_path = document_path.resolve()
    if resolved_document_path in stack:
        issues.append(ValidationIssue(str(document_path), "sub-plan cycle detected"))
        return

    steps = document.get("steps")
    if not isinstance(steps, list):
        issues.append(ValidationIssue(str(document_path), "plan document must contain a steps array"))
        return

    next_stack = [*stack, resolved_document_path]
    for index, step in enumerate(steps):
        _validate_step(
            step,
            location=f"{document_path}:steps[{index}]",
            package_root=package_root,
            issues=issues,
            stack=next_stack,
        )


def _validate_step(
    step: Any,
    *,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if not isinstance(step, dict):
        issues.append(ValidationIssue(location, "step must be a JSON object"))
        return

    action = step.get("action")
    if not isinstance(action, str) or not action:
        issues.append(ValidationIssue(location, "step.action must be a non-empty string"))
        return
    if action not in SUPPORTED_ACTIONS:
        issues.append(ValidationIssue(location, f"unsupported action: {action}"))
        return

    for field in REQUIRED_FIELDS.get(action, ()):
        if field not in step:
            issues.append(ValidationIssue(location, f"missing required field: {field}"))

    _validate_type_field(step, action, location, issues)
    _validate_action_specific_fields(step, action, location, package_root, issues, stack)


def _validate_type_field(
    step: dict[str, Any],
    action: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    allowed_types = ACTION_TYPES.get(action)
    if not allowed_types:
        return
    step_type = step.get("type")
    if action in {"wait", "scroll"} and step_type is None:
        return
    if not isinstance(step_type, str) or not step_type:
        issues.append(ValidationIssue(location, f"{action}.type must be a non-empty string"))
        return
    if step_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        issues.append(ValidationIssue(location, f"unsupported {action}.type: {step_type}; expected one of: {allowed}"))


def _validate_action_specific_fields(
    step: dict[str, Any],
    action: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if action == "run_sub_plan":
        _validate_sub_plan(step.get("path"), location, package_root, issues, stack)
        return

    if action in {"if", "foreach", "retry"}:
        _validate_control_flow(step, action, location, package_root, issues, stack)
        return

    if "trigger" in step:
        _validate_step(
            step["trigger"],
            location=f"{location}.trigger",
            package_root=package_root,
            issues=issues,
            stack=stack,
        )

    if action == "write" and step.get("type") != "variables" and "value" not in step:
        issues.append(ValidationIssue(location, "write requires value except when type is variables"))

    if action == "capture" or action == "write" or action == "wait_for_download" or action == "ai":
        output_type = str(step.get("type", "")) if action != "wait_for_download" else ""
        category = OUTPUT_ACTION_CATEGORIES.get((action, output_type))
        if category and "path" in step:
            _validate_output_path(step["path"], category, location, package_root, issues)

    _validate_type_specific_required_fields(step, action, location, issues)


def _validate_control_flow(
    step: dict[str, Any],
    action: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if action == "if":
        for branch in ("then", "else"):
            value = step.get(branch, [])
            if not isinstance(value, list):
                issues.append(ValidationIssue(location, f"{branch} must be an array"))
                continue
            for index, child_step in enumerate(value):
                _validate_step(
                    child_step,
                    location=f"{location}.{branch}[{index}]",
                    package_root=package_root,
                    issues=issues,
                    stack=stack,
                )
        return

    child_steps = step.get("steps")
    if not isinstance(child_steps, list):
        issues.append(ValidationIssue(location, "steps must be an array"))
        return
    for index, child_step in enumerate(child_steps):
        _validate_step(
            child_step,
            location=f"{location}.steps[{index}]",
            package_root=package_root,
            issues=issues,
            stack=stack,
        )


def _validate_sub_plan(
    raw_path: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path must be a non-empty string"))
        return
    if "{{" in raw_path or "}}" in raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path must be static so it can be validated"))
        return

    path = Path(raw_path)
    if path.is_absolute():
        issues.append(ValidationIssue(location, "run_sub_plan.path must be relative to the current plan package"))
        return
    if not path.parts or path.parts[0] != "sub-plans":
        issues.append(ValidationIssue(location, "run_sub_plan.path must start with sub-plans/"))
        return
    if path.name == "plan.json":
        issues.append(ValidationIssue(location, "run_sub_plan cannot reference a main plan.json"))
        return
    if not path.name.endswith("-plan.json"):
        issues.append(ValidationIssue(location, "sub-plan filenames must end with -plan.json"))
        return

    sub_plans_dir = (package_root / "sub-plans").resolve()
    resolved_path = (package_root / path).resolve()
    if not _is_relative_to(resolved_path, sub_plans_dir):
        issues.append(ValidationIssue(location, "run_sub_plan.path must resolve inside sub-plans/"))
        return
    if not resolved_path.exists():
        issues.append(ValidationIssue(location, f"sub-plan not found: {raw_path}"))
        return

    document = _load_json_document(resolved_path, issues)
    if document is None:
        return
    _validate_plan_document(
        document,
        document_path=resolved_path,
        package_root=package_root,
        issues=issues,
        stack=stack,
    )


def _validate_output_path(
    raw_path: Any,
    category: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "output path must be a non-empty string"))
        return

    path = Path(raw_path)
    if path.is_absolute():
        issues.append(ValidationIssue(location, f"output path must be relative to output/{category}/"))
        return
    if not path.parts:
        issues.append(ValidationIssue(location, "output path cannot be empty"))
        return
    if path.parts[0] in FORBIDDEN_OUTPUT_ROOTS:
        issues.append(
            ValidationIssue(
                location,
                f"output path is already relative to output/{category}/; do not start with {path.parts[0]}/",
            )
        )
        return
    if "{{" in raw_path or "}}" in raw_path:
        return

    output_root = (package_root / "output").resolve()
    category_root = (output_root / category).resolve()
    resolved_path = (category_root / path).resolve() if path.parts[0] != category else (output_root / path).resolve()
    if not _is_relative_to(resolved_path, output_root):
        issues.append(ValidationIssue(location, "output path must stay inside the current plan output directory"))
    if not _is_relative_to(resolved_path, category_root):
        issues.append(ValidationIssue(location, f"output path for this action must stay inside output/{category}/"))


def _validate_type_specific_required_fields(
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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
