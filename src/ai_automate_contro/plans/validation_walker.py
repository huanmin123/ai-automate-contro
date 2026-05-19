from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.engine.actions import SUPPORTED_ACTIONS
from ai_automate_contro.plans.validation_fields import (
    validate_type_field,
    validate_type_specific_required_fields,
)
from ai_automate_contro.plans.validation_io import load_json_document
from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_paths import is_relative_to, validate_output_path
from ai_automate_contro.plans.validation_rules import OUTPUT_ACTION_CATEGORIES, REQUIRED_FIELDS
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


def validate_plan_document(
    document: dict[str, Any],
    *,
    document_path: Path,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    resolved_document_path = document_path.resolve()
    if resolved_document_path in stack:
        issues.append(ValidationIssue(str(document_path), "检测到子计划循环引用"))
        return

    steps = document.get("steps")
    if not isinstance(steps, list):
        issues.append(ValidationIssue(str(document_path), "plan 文档必须包含 steps 数组"))
        return

    next_stack = [*stack, resolved_document_path]
    for index, step in enumerate(steps):
        validate_step(
            step,
            location=f"{document_path}:steps[{index}]",
            package_root=package_root,
            issues=issues,
            stack=next_stack,
        )
    validate_manual_confirm_visible_browser_flow(
        steps,
        location_prefix=f"{document_path}:steps",
        package_root=package_root,
        issues=issues,
        stack=next_stack,
        active_sessions={},
    )


def validate_step(
    step: Any,
    *,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if not isinstance(step, dict):
        issues.append(ValidationIssue(location, "step 必须是 JSON 对象"))
        return

    action = step.get("action")
    if not isinstance(action, str) or not action:
        issues.append(ValidationIssue(location, "step.action 必须是非空字符串"))
        return
    if action not in SUPPORTED_ACTIONS:
        issues.append(ValidationIssue(location, f"不支持的 action：{action}"))
        return

    for field in REQUIRED_FIELDS.get(action, ()):
        if field not in step:
            issues.append(ValidationIssue(location, f"缺少必填字段：{field}"))

    validate_type_field(step, action, location, issues)
    validate_action_specific_fields(step, action, location, package_root, issues, stack)


def validate_action_specific_fields(
    step: dict[str, Any],
    action: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if action == "run_sub_plan":
        validate_sub_plan(step.get("path"), location, package_root, issues, stack)
        return

    if action in {"if", "foreach", "retry"}:
        validate_control_flow(step, action, location, package_root, issues, stack)
        return

    if "trigger" in step:
        validate_step(
            step["trigger"],
            location=f"{location}.trigger",
            package_root=package_root,
            issues=issues,
            stack=stack,
        )

    if action == "open_browser":
        if "record_har_path" in step:
            validate_output_path(step["record_har_path"], "har", location, package_root, issues)
        if "record_video_dir" in step:
            validate_output_path(step["record_video_dir"], "videos", location, package_root, issues)

    if action == "write" and step.get("type") != "variables" and "value" not in step:
        issues.append(ValidationIssue(location, "write 在 type 不是 variables 时必须提供 value"))

    if action in {"capture", "write", "wait_for_download", "ai", "trace", "event", "coverage"}:
        output_type = str(step.get("type", "")) if action != "wait_for_download" else ""
        category = OUTPUT_ACTION_CATEGORIES.get((action, output_type))
        if category and "path" in step:
            validate_output_path(step["path"], category, location, package_root, issues)

    validate_type_specific_required_fields(step, action, location, issues)


def validate_control_flow(
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
                issues.append(ValidationIssue(location, f"{branch} 必须是数组"))
                continue
            for index, child_step in enumerate(value):
                validate_step(
                    child_step,
                    location=f"{location}.{branch}[{index}]",
                    package_root=package_root,
                    issues=issues,
                    stack=stack,
                )
        return

    child_steps = step.get("steps")
    if not isinstance(child_steps, list):
        issues.append(ValidationIssue(location, "steps 必须是数组"))
        return
    for index, child_step in enumerate(child_steps):
        validate_step(
            child_step,
            location=f"{location}.steps[{index}]",
            package_root=package_root,
            issues=issues,
            stack=stack,
        )


def validate_sub_plan(
    raw_path: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须是非空字符串"))
        return
    if "{{" in raw_path or "}}" in raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须是静态路径，便于校验"))
        return

    path = path_from_text(raw_path)
    if is_absolute_path_text(raw_path):
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须相对于当前 plan 包"))
        return
    if not path.parts or path.parts[0] != "sub-plans":
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须以 sub-plans/ 开头"))
        return
    if path.name == "plan.json":
        issues.append(ValidationIssue(location, "run_sub_plan 不能引用主入口 plan.json"))
        return
    if not path.name.endswith("-plan.json"):
        issues.append(ValidationIssue(location, "子计划文件名必须以 -plan.json 结尾"))
        return

    sub_plans_dir = (package_root / "sub-plans").resolve()
    resolved_path = (package_root / path).resolve()
    if not is_relative_to(resolved_path, sub_plans_dir):
        issues.append(ValidationIssue(location, "run_sub_plan.path 解析后必须位于 sub-plans/ 内"))
        return
    if not resolved_path.exists():
        issues.append(ValidationIssue(location, f"子计划不存在：{raw_path}"))
        return

    document = load_json_document(resolved_path, issues)
    if document is None:
        return
    validate_plan_document(
        document,
        document_path=resolved_path,
        package_root=package_root,
        issues=issues,
        stack=stack,
    )


def validate_manual_confirm_visible_browser_flow(
    steps: list[Any],
    *,
    location_prefix: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    active_sessions: dict[str, bool],
) -> dict[str, bool]:
    sessions = dict(active_sessions)
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        location = f"{location_prefix}[{index}]"
        if isinstance(step.get("trigger"), dict):
            sessions = validate_manual_confirm_visible_browser_flow(
                [step["trigger"]],
                location_prefix=f"{location}.trigger",
                package_root=package_root,
                issues=issues,
                stack=stack,
                active_sessions=sessions,
            )

        action = step.get("action")
        if action == "open_browser":
            name = step.get("name")
            if isinstance(name, str) and name:
                sessions[name] = bool(step.get("headed", False))
        elif action == "close_browser":
            browser = step.get("browser")
            if isinstance(browser, str):
                sessions.pop(browser, None)
        elif action == "manual_confirm" and sessions and not any(sessions.values()):
            active = ", ".join(sorted(sessions))
            issues.append(
                ValidationIssue(
                    location,
                    "manual_confirm 前已有浏览器会话，但没有 headed=true 的可见浏览器。"
                    f"当前会话：{active}。需要用户在页面里操作时，请把 open_browser.headed 设为 true。",
                )
            )
        elif action == "run_sub_plan":
            sessions = _validate_manual_confirm_visible_sub_plan(step, location, package_root, issues, stack, sessions)
        elif action == "if":
            for branch in ("then", "else"):
                branch_steps = step.get(branch, [])
                if isinstance(branch_steps, list):
                    validate_manual_confirm_visible_browser_flow(
                        branch_steps,
                        location_prefix=f"{location}.{branch}",
                        package_root=package_root,
                        issues=issues,
                        stack=stack,
                        active_sessions=sessions,
                    )
        elif action in {"foreach", "retry"}:
            child_steps = step.get("steps", [])
            if isinstance(child_steps, list):
                validate_manual_confirm_visible_browser_flow(
                    child_steps,
                    location_prefix=f"{location}.steps",
                    package_root=package_root,
                    issues=issues,
                    stack=stack,
                    active_sessions=sessions,
                )
    return sessions


def _validate_manual_confirm_visible_sub_plan(
    step: dict[str, Any],
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    active_sessions: dict[str, bool],
) -> dict[str, bool]:
    raw_path = step.get("path")
    if not isinstance(raw_path, str) or not raw_path or "{{" in raw_path or "}}" in raw_path:
        return dict(active_sessions)
    if is_absolute_path_text(raw_path):
        return dict(active_sessions)
    path = path_from_text(raw_path)
    if not path.parts or path.parts[0] != "sub-plans" or path.name == "plan.json":
        return dict(active_sessions)
    resolved_path = (package_root / path).resolve()
    sub_plans_dir = (package_root / "sub-plans").resolve()
    if not is_relative_to(resolved_path, sub_plans_dir) or not resolved_path.exists():
        return dict(active_sessions)
    if resolved_path in stack:
        return dict(active_sessions)
    document = load_json_document(resolved_path, issues)
    if document is None:
        return dict(active_sessions)
    child_steps = document.get("steps", [])
    if not isinstance(child_steps, list):
        return dict(active_sessions)
    return validate_manual_confirm_visible_browser_flow(
        child_steps,
        location_prefix=f"{resolved_path}:steps",
        package_root=package_root,
        issues=issues,
        stack=[*stack, resolved_path],
        active_sessions=active_sessions,
    )
