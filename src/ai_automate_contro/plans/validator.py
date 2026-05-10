from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.actions import SUPPORTED_ACTIONS
from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.plans.validation_fields import (
    validate_type_field,
    validate_type_specific_required_fields,
)
from ai_automate_contro.plans.validation_models import ValidationIssue, ValidationResult
from ai_automate_contro.plans.validation_paths import is_relative_to, validate_output_path
from ai_automate_contro.plans.validation_rules import OUTPUT_ACTION_CATEGORIES, REQUIRED_FIELDS


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

    validate_type_field(step, action, location, issues)
    _validate_action_specific_fields(step, action, location, package_root, issues, stack)


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
            validate_output_path(step["path"], category, location, package_root, issues)

    validate_type_specific_required_fields(step, action, location, issues)


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
    if not is_relative_to(resolved_path, sub_plans_dir):
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
