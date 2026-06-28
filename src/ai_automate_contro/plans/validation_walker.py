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
from ai_automate_contro.plans.validation_rules import (
    ACTIONS_BY_AUTOMATION_TYPE,
    ALLOWED_AUTOMATION_TYPES,
    OUTPUT_ACTION_CATEGORIES,
    REQUIRED_FIELDS,
)
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


def validate_plan_document(
    document: dict[str, Any],
    *,
    document_path: Path,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None = None,
) -> None:
    resolved_document_path = document_path.resolve()
    if resolved_document_path in stack:
        issues.append(ValidationIssue(str(document_path), "检测到子计划循环引用"))
        return

    current_automation_type = validate_document_automation_type(
        document,
        document_path=document_path,
        issues=issues,
        parent_automation_type=automation_type,
    )

    steps = document.get("steps")
    if not isinstance(steps, list):
        issues.append(ValidationIssue(str(document_path), "plan 文档必须包含 steps 数组"))
        return

    next_stack = [*stack, resolved_document_path]
    if "routines" in document:
        issues.append(
            ValidationIssue(
                str(document_path),
                "顶层 routines 已移除。请把周期执行体直接写入 steps 中的 trigger.steps，或用 trigger.path 引用 sub-plans/*-plan.json。",
            )
        )
    if "triggers" in document:
        issues.append(
            ValidationIssue(
                str(document_path),
                "顶层 triggers 已移除。trigger 是父级控制流 action，必须直接写在 steps 中执行。",
            )
        )

    for index, step in enumerate(steps):
        validate_step(
            step,
            location=f"{document_path}:steps[{index}]",
            package_root=package_root,
            issues=issues,
            stack=next_stack,
            automation_type=current_automation_type,
        )
    if current_automation_type == "browser":
        validate_manual_confirm_visible_browser_flow(
            steps,
            location_prefix=f"{document_path}:steps",
            package_root=package_root,
            issues=issues,
            stack=next_stack,
            active_sessions={},
        )


def validate_document_automation_type(
    document: dict[str, Any],
    *,
    document_path: Path,
    issues: list[ValidationIssue],
    parent_automation_type: str | None,
) -> str | None:
    raw_value = document.get("automation_type")
    location = f"{document_path}:automation_type"
    if parent_automation_type is None:
        if "automation_type" not in document:
            issues.append(
                ValidationIssue(
                    str(document_path),
                    "主 plan 必须包含 automation_type，取值为 browser 或 desktop。",
                )
            )
            return None
        if not isinstance(raw_value, str) or not raw_value:
            issues.append(ValidationIssue(location, "automation_type 必须是非空字符串，取值为 browser 或 desktop。"))
            return None
        if raw_value not in ALLOWED_AUTOMATION_TYPES:
            allowed = ", ".join(sorted(ALLOWED_AUTOMATION_TYPES))
            issues.append(ValidationIssue(location, f"automation_type 不支持：{raw_value}；可选值：{allowed}"))
            return None
        return raw_value

    if "automation_type" not in document:
        return parent_automation_type
    if not isinstance(raw_value, str) or not raw_value:
        issues.append(ValidationIssue(location, "子计划 automation_type 必须是非空字符串，或省略以继承主 plan。"))
        return parent_automation_type
    if raw_value not in ALLOWED_AUTOMATION_TYPES:
        allowed = ", ".join(sorted(ALLOWED_AUTOMATION_TYPES))
        issues.append(ValidationIssue(location, f"子计划 automation_type 不支持：{raw_value}；可选值：{allowed}"))
        return parent_automation_type
    if raw_value != parent_automation_type:
        issues.append(
            ValidationIssue(
                location,
                f"子计划 automation_type 必须与主 plan 一致：主 plan={parent_automation_type}，子计划={raw_value}。",
            )
        )
    return parent_automation_type


def validate_step(
    step: Any,
    *,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None,
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
    validate_action_partition(action, automation_type, location, issues)

    for field in REQUIRED_FIELDS.get(action, ()):
        if field not in step:
            issues.append(ValidationIssue(location, f"缺少必填字段：{field}"))

    validate_type_field(step, action, location, issues)
    validate_action_specific_fields(step, action, location, package_root, issues, stack, automation_type)


def validate_action_partition(
    action: str,
    automation_type: str | None,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if automation_type not in ACTIONS_BY_AUTOMATION_TYPE:
        return
    if action in ACTIONS_BY_AUTOMATION_TYPE[automation_type]:
        return
    issues.append(ValidationIssue(location, f"automation_type={automation_type} 不支持 action：{action}"))


def validate_action_specific_fields(
    step: dict[str, Any],
    action: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None,
) -> None:
    if action == "run_sub_plan":
        validate_sub_plan(step.get("path"), location, package_root, issues, stack, automation_type)
        return

    if action in {"if", "foreach", "retry"}:
        validate_control_flow(step, action, location, package_root, issues, stack, automation_type)
        return

    if action == "trigger":
        validate_trigger_action(step, location, package_root, issues, stack, automation_type)

    if "trigger" in step:
        validate_step(
            step["trigger"],
            location=f"{location}.trigger",
            package_root=package_root,
            issues=issues,
            stack=stack,
            automation_type=automation_type,
        )

    if action == "open_browser":
        validate_package_input_path(
            step.get("storage_state_path"),
            f"{location}.storage_state_path",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )
        if "record_har_path" in step:
            validate_output_path(step["record_har_path"], "har", location, package_root, issues)
        if "record_video_dir" in step:
            validate_output_path(step["record_video_dir"], "videos", location, package_root, issues)

    if action == "write" and step.get("type") != "variables" and "value" not in step:
        issues.append(ValidationIssue(location, "write 在 type 不是 variables 时必须提供 value"))

    if action in {
        "capture",
        "write",
        "wait_for_download",
        "ai",
        "trace",
        "event",
        "coverage",
        "desktop_capture",
        "desktop_element",
        "desktop_window",
        "desktop_vision",
        "desktop_assert",
    }:
        output_type = str(step.get("type", "")) if action != "wait_for_download" else ""
        category = OUTPUT_ACTION_CATEGORIES.get((action, output_type))
        if category and "path" in step:
            validate_output_path(step["path"], category, location, package_root, issues)

    if action == "read":
        validate_package_input_path(
            step.get("path"),
            f"{location}.path",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )

    if action == "element" and step.get("type") == "set_files":
        validate_package_input_paths(
            step.get("files"),
            f"{location}.files",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )

    if action == "wait_for_file_chooser" and step.get("type") == "set_files":
        validate_package_input_paths(
            step.get("files"),
            f"{location}.files",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )

    if action == "network":
        if step.get("type") == "route_from_har":
            validate_package_input_path(
                step.get("path"),
                f"{location}.path",
                package_root,
                issues,
                step=step,
                must_exist=False,
            )
        elif step.get("type") == "route" and "path" in step:
            validate_package_input_path(
                step.get("path"),
                f"{location}.path",
                package_root,
                issues,
                step=step,
                must_exist=False,
            )

    if action == "http":
        if "response_body_path" in step:
            validate_output_path(step["response_body_path"], "http", location, package_root, issues)
        validate_package_input_path(
            step.get("body_path"),
            f"{location}.body_path",
            package_root,
            issues,
            step=step,
        )
        multipart = step.get("multipart")
        if isinstance(multipart, dict):
            files = multipart.get("files", [])
            if isinstance(files, list):
                for index, file_item in enumerate(files):
                    if isinstance(file_item, dict):
                        validate_package_input_path(
                            file_item.get("path"),
                            f"{location}.multipart.files[{index}].path",
                            package_root,
                            issues,
                            step=step,
                        )

    if action == "command":
        for field in ("stdout_path", "stderr_path"):
            if field in step:
                validate_output_path(step[field], "commands", location, package_root, issues)
        validate_package_input_path(
            step.get("stdin_path"),
            f"{location}.stdin_path",
            package_root,
            issues,
            step=step,
        )
        validate_package_cwd(step.get("cwd"), f"{location}.cwd", package_root, issues, step=step)

    if action == "desktop_vision" and step.get("type") == "locate_image":
        validate_package_input_path(
            step.get("template_path"),
            f"{location}.template_path",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )
    if action == "desktop_vision":
        validate_package_input_path(
            step.get("source_path"),
            f"{location}.source_path",
            package_root,
            issues,
            step=step,
            must_exist=False,
        )

    validate_type_specific_required_fields(step, action, location, issues)


def validate_package_input_path(
    raw_path: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    *,
    step: dict[str, Any] | None = None,
    must_exist: bool = True,
) -> None:
    if raw_path in (None, ""):
        return
    if not isinstance(raw_path, str):
        issues.append(ValidationIssue(location, "path 必须是非空字符串"))
        return
    if "{{" in raw_path or "}}" in raw_path:
        return
    if "\\" in raw_path and not is_absolute_path_text(raw_path):
        issues.append(ValidationIssue(location, "plan JSON 内部路径必须使用 /，不要使用 Windows 反斜杠。"))
    if is_absolute_path_text(raw_path):
        resolved_path = path_from_text(raw_path).resolve()
    else:
        path = path_from_text(raw_path)
        if not path.parts:
            issues.append(ValidationIssue(location, "path 不能为空"))
            return
        resolved_path = (package_root / path).resolve()
    if must_exist and (not resolved_path.exists() or not resolved_path.is_file()):
        issues.append(ValidationIssue(location, f"文件不存在：{raw_path}"))


def validate_package_input_paths(
    raw_paths: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    *,
    step: dict[str, Any] | None = None,
    must_exist: bool = True,
) -> None:
    if raw_paths in (None, ""):
        return
    if isinstance(raw_paths, str):
        validate_package_input_path(
            raw_paths,
            location,
            package_root,
            issues,
            step=step,
            must_exist=must_exist,
        )
        return
    if isinstance(raw_paths, list):
        for index, raw_path in enumerate(raw_paths):
            validate_package_input_path(
                raw_path,
                f"{location}[{index}]",
                package_root,
                issues,
                step=step,
                must_exist=must_exist,
            )
        return
    issues.append(ValidationIssue(location, "files 必须是非空字符串或字符串数组"))


def validate_package_cwd(
    raw_path: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    *,
    step: dict[str, Any] | None = None,
) -> None:
    if raw_path in (None, ""):
        return
    if not isinstance(raw_path, str):
        issues.append(ValidationIssue(location, "cwd 必须是非空字符串"))
        return
    if "{{" in raw_path or "}}" in raw_path:
        return
    if "\\" in raw_path and not is_absolute_path_text(raw_path):
        issues.append(ValidationIssue(location, "plan JSON 内部路径必须使用 /，不要使用 Windows 反斜杠。"))
    if is_absolute_path_text(raw_path):
        resolved_path = path_from_text(raw_path).resolve()
    else:
        resolved_path = (package_root / path_from_text(raw_path)).resolve()
    if not resolved_path.exists() or not resolved_path.is_dir():
        issues.append(ValidationIssue(location, f"cwd 不存在：{raw_path}"))


def validate_control_flow(
    step: dict[str, Any],
    action: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None,
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
                    automation_type=automation_type,
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
            automation_type=automation_type,
        )


def validate_trigger_action(
    step: dict[str, Any],
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None,
) -> None:
    if "name" in step and not _is_template(step.get("name")):
        name = step.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(ValidationIssue(location, "trigger.name 必须是非空字符串"))
    if "every_seconds" in step:
        _validate_positive_number_or_template(step.get("every_seconds"), f"{location}.every_seconds", issues)
    if "max_runs" in step and step.get("max_runs") not in (None, ""):
        _validate_positive_integer_or_template(step.get("max_runs"), f"{location}.max_runs", issues)
    if "duration_seconds" in step and step.get("duration_seconds") not in (None, ""):
        _validate_positive_number_or_template(step.get("duration_seconds"), f"{location}.duration_seconds", issues)
    for field in ("run_immediately", "allow_infinite"):
        if field in step and not _is_template(step[field]) and not isinstance(step[field], bool):
            issues.append(ValidationIssue(location, f"trigger.{field} 必须是布尔值"))
    if not _has_trigger_bound(step) and not bool(step.get("allow_infinite", False)):
        issues.append(ValidationIssue(location, "无限 trigger 必须显式设置 allow_infinite=true，或提供 max_runs/duration_seconds"))
    overlap = step.get("overlap", "skip")
    if not _is_template(overlap) and overlap not in {"skip", "queue", "fail"}:
        issues.append(ValidationIssue(location, "trigger.overlap 只能是 skip、queue 或 fail"))
    on_error = step.get("on_error", "fail_plan")
    if not _is_template(on_error) and on_error not in {"fail_plan", "stop_trigger"}:
        issues.append(ValidationIssue(location, "trigger.on_error 只能是 fail_plan 或 stop_trigger"))

    has_steps_field = "steps" in step and step.get("steps") is not None
    has_steps = has_steps_field and step.get("steps") != []
    has_path = "path" in step and step.get("path") not in (None, "")
    if has_steps_field and has_path:
        issues.append(ValidationIssue(location, "trigger.steps 和 trigger.path 只能提供一种"))
    if not has_steps and not has_path:
        issues.append(ValidationIssue(location, "trigger 需要 steps 或 path 作为周期执行体"))
    if "steps" in step:
        child_steps = step.get("steps")
        if not isinstance(child_steps, list):
            issues.append(ValidationIssue(location, "trigger.steps 必须是数组"))
        else:
            for index, child_step in enumerate(child_steps):
                validate_step(
                    child_step,
                    location=f"{location}.steps[{index}]",
                    package_root=package_root,
                    issues=issues,
                    stack=stack,
                    automation_type=automation_type,
                )
    if has_path:
        validate_sub_plan(step.get("path"), f"{location}.path", package_root, issues, stack, automation_type)


def _has_trigger_bound(trigger: dict[str, Any]) -> bool:
    return trigger.get("max_runs") not in (None, "") or trigger.get("duration_seconds") not in (None, "")


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "}}" in value)


def _validate_positive_number_or_template(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, str) and ("{{" in value or "}}" in value):
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        issues.append(ValidationIssue(location, "必须是大于 0 的数字，或变量模板"))
        return
    if number <= 0:
        issues.append(ValidationIssue(location, "必须大于 0"))


def _validate_positive_integer_or_template(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, str) and ("{{" in value or "}}" in value):
        return
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(ValidationIssue(location, "必须是大于 0 的整数，或变量模板"))
        return
    if value <= 0:
        issues.append(ValidationIssue(location, "必须大于 0"))


def validate_sub_plan(
    raw_path: Any,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    automation_type: str | None,
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须是非空字符串"))
        return
    if "{{" in raw_path or "}}" in raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须是静态路径，便于校验"))
        return

    path = path_from_text(raw_path)
    if "\\" in raw_path:
        issues.append(ValidationIssue(location, "run_sub_plan.path 必须使用 /，不要使用 Windows 反斜杠。"))
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
        automation_type=automation_type,
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
    states = _validate_manual_confirm_visible_browser_flow_states(
        steps,
        location_prefix=location_prefix,
        package_root=package_root,
        issues=issues,
        stack=stack,
        active_states=[dict(active_sessions)],
    )
    return _merge_possible_session_states(states)


def _validate_manual_confirm_visible_browser_flow_states(
    steps: list[Any],
    *,
    location_prefix: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    active_states: list[dict[str, bool]],
) -> list[dict[str, bool]]:
    states = _dedupe_session_states(active_states)
    reported_manual_confirm_states: set[tuple[str, tuple[tuple[str, bool], ...]]] = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        location = f"{location_prefix}[{index}]"
        if isinstance(step.get("trigger"), dict):
            states = _validate_manual_confirm_visible_browser_flow_states(
                [step["trigger"]],
                location_prefix=f"{location}.trigger",
                package_root=package_root,
                issues=issues,
                stack=stack,
                active_states=states,
            )

        action = step.get("action")
        if action == "open_browser":
            name = step.get("name")
            if isinstance(name, str) and name:
                states = [{**state, name: bool(step.get("headed", False))} for state in states]
        elif action == "close_browser":
            browser = step.get("browser")
            if isinstance(browser, str):
                next_states: list[dict[str, bool]] = []
                for state in states:
                    next_state = dict(state)
                    next_state.pop(browser, None)
                    next_states.append(next_state)
                states = _dedupe_session_states(next_states)
        elif action == "manual_confirm":
            for state in states:
                issue_message = _manual_confirm_visible_browser_issue(step, state)
                if not issue_message:
                    continue
                state_key = (location, tuple(sorted(state.items())))
                if state_key in reported_manual_confirm_states:
                    continue
                reported_manual_confirm_states.add(state_key)
                issues.append(ValidationIssue(location, issue_message))
        elif action == "run_sub_plan":
            next_states: list[dict[str, bool]] = []
            for state in states:
                next_states.extend(
                    _validate_manual_confirm_visible_sub_plan_states(
                        step,
                        location,
                        package_root,
                        issues,
                        stack,
                        state,
                    )
                )
            states = _dedupe_session_states(next_states)
        elif action == "if":
            branch_states: list[dict[str, bool]] = []
            for branch in ("then", "else"):
                branch_steps = step.get(branch, [])
                if isinstance(branch_steps, list):
                    branch_states.extend(
                        _validate_manual_confirm_visible_browser_flow_states(
                            branch_steps,
                            location_prefix=f"{location}.{branch}",
                            package_root=package_root,
                            issues=issues,
                            stack=stack,
                            active_states=states,
                        )
                    )
            states = _dedupe_session_states(branch_states) if branch_states else states
        elif action in {"foreach", "retry"}:
            child_steps = step.get("steps", [])
            if isinstance(child_steps, list):
                child_states = _validate_manual_confirm_visible_browser_flow_states(
                    child_steps,
                    location_prefix=f"{location}.steps",
                    package_root=package_root,
                    issues=issues,
                    stack=stack,
                    active_states=states,
                )
                if action == "foreach":
                    states = _dedupe_session_states([*states, *child_states])
                else:
                    states = _dedupe_session_states(child_states)
        elif action == "trigger":
            trigger_states: list[dict[str, bool]] = []
            child_steps = step.get("steps", [])
            if isinstance(child_steps, list):
                trigger_states.extend(
                    _validate_manual_confirm_visible_browser_flow_states(
                        child_steps,
                        location_prefix=f"{location}.steps",
                        package_root=package_root,
                        issues=issues,
                        stack=stack,
                        active_states=states,
                    )
                )
            if isinstance(step.get("path"), str):
                for state in states:
                    trigger_states.extend(
                        _validate_manual_confirm_visible_sub_plan_states(
                            step,
                            location,
                            package_root,
                            issues,
                            stack,
                            state,
                        )
                    )
            if trigger_states:
                states = _dedupe_session_states([*states, *trigger_states])
    return _dedupe_session_states(states)


def _manual_confirm_visible_browser_issue(step: dict[str, Any], state: dict[str, bool]) -> str:
    target_browser = step.get("browser")
    if isinstance(target_browser, str) and target_browser.strip():
        browser_name = target_browser.strip()
        if browser_name not in state:
            active = ", ".join(sorted(state)) or "<无>"
            return f"manual_confirm 指定的浏览器会话不存在：{browser_name}。当前会话：{active}。"
        if not state.get(browser_name, False):
            return (
                "manual_confirm 需要同一个可见 Playwright 浏览器窗口。"
                f"指定浏览器 {browser_name} 不是 headed=true。需要用户在页面里操作时，请把对应 open_browser.headed 设为 true。"
            )
        return ""
    if not state:
        return ""
    active = ", ".join(sorted(state))
    if not any(state.values()):
        return (
            "manual_confirm 前已有浏览器会话，但没有 headed=true 的可见浏览器。"
            f"当前会话：{active}。需要用户在页面里操作时，请把 open_browser.headed 设为 true。"
        )
    if len(state) > 1:
        return (
            "manual_confirm 前已有多个浏览器会话，无法确定用户应操作哪一个窗口。"
            f"当前会话：{active}。请在 manual_confirm.browser 显式指定目标浏览器。"
        )
    return ""


def _validate_manual_confirm_visible_sub_plan(
    step: dict[str, Any],
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    active_sessions: dict[str, bool],
) -> dict[str, bool]:
    states = _validate_manual_confirm_visible_sub_plan_states(
        step,
        location,
        package_root,
        issues,
        stack,
        active_sessions,
    )
    return _merge_possible_session_states(states)


def _validate_manual_confirm_visible_sub_plan_states(
    step: dict[str, Any],
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
    stack: list[Path],
    active_sessions: dict[str, bool],
) -> list[dict[str, bool]]:
    raw_path = step.get("path")
    if not isinstance(raw_path, str) or not raw_path or "{{" in raw_path or "}}" in raw_path:
        return [dict(active_sessions)]
    if is_absolute_path_text(raw_path):
        return [dict(active_sessions)]
    path = path_from_text(raw_path)
    if not path.parts or path.parts[0] != "sub-plans" or path.name == "plan.json":
        return [dict(active_sessions)]
    resolved_path = (package_root / path).resolve()
    sub_plans_dir = (package_root / "sub-plans").resolve()
    if not is_relative_to(resolved_path, sub_plans_dir) or not resolved_path.exists():
        return [dict(active_sessions)]
    if resolved_path in stack:
        return [dict(active_sessions)]
    document = load_json_document(resolved_path, issues)
    if document is None:
        return [dict(active_sessions)]
    child_steps = document.get("steps", [])
    if not isinstance(child_steps, list):
        return [dict(active_sessions)]
    return _validate_manual_confirm_visible_browser_flow_states(
        child_steps,
        location_prefix=f"{resolved_path}:steps",
        package_root=package_root,
        issues=issues,
        stack=[*stack, resolved_path],
        active_states=[dict(active_sessions)],
    )


def _merge_possible_session_states(states: list[dict[str, bool]]) -> dict[str, bool]:
    merged: dict[str, bool] = {}
    for state in states:
        for name, headed in state.items():
            if name not in merged:
                merged[name] = headed
            else:
                merged[name] = merged[name] and headed
    return merged


def _dedupe_session_states(states: list[dict[str, bool]]) -> list[dict[str, bool]]:
    deduped: list[dict[str, bool]] = []
    seen: set[tuple[tuple[str, bool], ...]] = set()
    for state in states:
        key = tuple(sorted(state.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(state))
    return deduped or [{}]
