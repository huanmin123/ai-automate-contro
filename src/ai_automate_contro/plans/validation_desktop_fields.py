from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_field_helpers import (
    DESKTOP_ELEMENT_LOCATOR_FIELDS,
    DESKTOP_ELEMENT_REQUIRED_LOCATOR_FIELDS,
    DESKTOP_INPUT_TARGETS,
    DESKTOP_TARGET_CANDIDATE_SOURCE_ALIASES,
    _is_template,
    _validate_bool,
    _validate_dict,
    _validate_enum,
    _validate_int,
    _validate_list,
    _validate_nonempty_string_list,
    _validate_number,
    _validate_size,
    _validate_string,
    _validate_string_or_nonempty_string_list,
)
from ai_automate_contro.plans.validation_models import ValidationIssue


def _validate_open_desktop_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_enum(step, "platform", {"auto", "windows", "macos"}, location, issues)
    _validate_enum(
        step,
        "backend",
        {"auto", "native"},
        location,
        issues,
    )
    _validate_bool(step, "request_permissions", location, issues)
    _validate_list(step, "permissions", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)


def _validate_desktop_app_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_string(step, "app", location, issues)
    _validate_string(step, "path", location, issues)
    _validate_string(step, "command", location, issues)
    _validate_list(step, "args", location, issues)
    _validate_bool(step, "wait", location, issues)
    _validate_bool(step, "wait_for_window", location, issues)
    _validate_bool(step, "focus", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "window_timeout_ms", location, issues, minimum=1)
    _validate_int(step, "interval_ms", location, issues, minimum=1)
    _validate_window_query_fields(step, location, issues)
    if step_type != "launch":
        return
    launch_fields = [field for field in ("app", "path", "command") if field in step and step.get(field)]
    if len(launch_fields) > 1:
        issues.append(ValidationIssue(location, "desktop_app.launch 只能同时使用 app、path 或 command 之一"))
    args = step.get("args")
    if args is None or _is_template(args) or not isinstance(args, list):
        return
    for index, arg in enumerate(args):
        if not isinstance(arg, str) or not arg:
            issues.append(ValidationIssue(f"{location}.args[{index}]", "args 每一项必须是非空字符串"))


def _validate_desktop_window_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_window_query_fields(step, location, issues)
    _validate_string(step, "path", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "max_windows", location, issues, minimum=1)
    if step_type in {"list", "find"}:
        _validate_bool(step, "include_invisible", location, issues)


def _validate_desktop_element_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_window_query_fields(step, location, issues)
    _validate_desktop_element_locator_fields(step, location, issues)
    _validate_string(step, "path", location, issues)
    _validate_int(step, "max_depth", location, issues, minimum=0)
    _validate_int(step, "max_elements", location, issues, minimum=1)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "interval_ms", location, issues, minimum=1)
    _validate_bool(step, "include_tree", location, issues)
    _validate_bool(step, "include_selector_hints", location, issues)
    _validate_int(step, "text_limit", location, issues, minimum=0)
    _validate_int(step, "max_rows", location, issues, minimum=1)
    _validate_int(step, "max_columns", location, issues, minimum=1)
    _validate_int(step, "max_nodes", location, issues, minimum=1)
    _validate_bool(step, "visible_only", location, issues)
    if step_type == "wait":
        _validate_enum(step, "state", {"exists", "not_exists", "enabled", "disabled", "focused"}, location, issues)
    elif step_type in {"find", "get_text", "get_state"}:
        _validate_enum(step, "state", {"exists", "enabled", "disabled", "focused"}, location, issues)
    if step_type == "set_text":
        _validate_string(step, "value", location, issues)
        _validate_bool(step, "preserve_clipboard", location, issues)
    if step_type == "select":
        _validate_string(step, "value", location, issues)
        _validate_int(step, "option_index", location, issues, minimum=0)
    if step_type == "select_cell":
        _validate_int(step, "row", location, issues, minimum=0)
        _validate_string(step, "column", location, issues)
        _validate_int(step, "column_index", location, issues, minimum=0)
    if step_type in {"expand_tree", "collapse_tree", "select_tree"}:
        _validate_nonempty_string_list(step, "tree_path", location, issues)
    if step_type == "invoke_menu":
        _validate_nonempty_string_list(step, "menu_path", location, issues)
        _validate_bool(step, "open_context_menu", location, issues)
    if step_type == "scroll_element":
        _validate_int(step, "amount", location, issues)
        _validate_enum(step, "scroll_to", {"start", "end", "top", "bottom", "left", "right"}, location, issues)
        if "amount" in step and not _is_template(step["amount"]) and isinstance(step["amount"], int) and step["amount"] == 0:
            issues.append(ValidationIssue(location, "desktop_element.scroll_element amount 不能为 0"))


def _validate_desktop_input_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_enum(step, "method", {"auto", "type", "clipboard"}, location, issues)
    _validate_int(step, "delay_ms", location, issues, minimum=0)
    _validate_bool(step, "preserve_clipboard", location, issues)
    if step_type == "type_text":
        _validate_string(step, "value", location, issues)
    if step_type == "hotkey":
        keys = step.get("keys")
        if keys is None or _is_template(keys):
            return
        if not isinstance(keys, list) or not keys:
            issues.append(ValidationIssue(location, "keys 必须是非空字符串数组"))
            return
        for index, key in enumerate(keys):
            if not isinstance(key, str) or not key:
                issues.append(ValidationIssue(f"{location}.keys[{index}]", "keys 每一项必须是非空字符串"))
    if step_type in {"click", "double_click", "right_click", "scroll"}:
        _validate_enum(step, "target", DESKTOP_INPUT_TARGETS, location, issues)
        _validate_bool(step, "allow_outside_window", location, issues)
        _validate_int(step, "x", location, issues)
        _validate_int(step, "y", location, issues)
        _validate_int(step, "offset_x", location, issues)
        _validate_int(step, "offset_y", location, issues)
        _validate_bounds(step, "bounds", location, issues)
        _validate_string(step, "candidate_id", location, issues)
        _validate_string(step, "target_candidate_id", location, issues)
        _validate_string(step, "min_confidence", location, issues)
        _validate_desktop_target_candidates_field(step, location, issues)
        _validate_window_query_fields(step, location, issues)
        _validate_desktop_element_locator_fields(step, location, issues)
        _validate_desktop_input_target_requirements(step, step_type, location, issues)
        if step_type == "click":
            _validate_enum(step, "button", {"left", "right", "middle"}, location, issues)
            _validate_int(step, "clicks", location, issues, minimum=1)
            _validate_int(step, "interval_ms", location, issues, minimum=0)
        if step_type == "double_click":
            _validate_int(step, "interval_ms", location, issues, minimum=0)
        if step_type == "scroll":
            _validate_int(step, "amount", location, issues)
            if "amount" in step and not _is_template(step["amount"]) and isinstance(step["amount"], int) and step["amount"] == 0:
                issues.append(ValidationIssue(location, "desktop_input.scroll amount 不能为 0"))
        if ("x" in step) != ("y" in step):
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} 使用坐标时必须同时提供 x 和 y"))
        if "target" in step and ("x" in step or "y" in step):
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} 不能同时使用 target 和 x/y"))
    if step_type == "drag":
        _validate_enum(step, "target", DESKTOP_INPUT_TARGETS, location, issues)
        _validate_bool(step, "allow_outside_window", location, issues)
        _validate_enum(step, "button", {"left", "right", "middle"}, location, issues)
        _validate_int(step, "start_x", location, issues)
        _validate_int(step, "start_y", location, issues)
        _validate_int(step, "end_x", location, issues)
        _validate_int(step, "end_y", location, issues)
        _validate_int(step, "delta_x", location, issues)
        _validate_int(step, "delta_y", location, issues)
        _validate_int(step, "offset_x", location, issues)
        _validate_int(step, "offset_y", location, issues)
        _validate_bounds(step, "bounds", location, issues)
        _validate_string(step, "candidate_id", location, issues)
        _validate_string(step, "target_candidate_id", location, issues)
        _validate_string(step, "min_confidence", location, issues)
        _validate_desktop_target_candidates_field(step, location, issues)
        _validate_window_query_fields(step, location, issues)
        _validate_desktop_element_locator_fields(step, location, issues)
        _validate_int(step, "duration_ms", location, issues, minimum=0)
        direct_fields = {"start_x", "start_y", "end_x", "end_y"}
        if "x" in step or "y" in step:
            issues.append(ValidationIssue(location, "desktop_input.drag 使用 start_x/start_y/end_x/end_y，不能使用 x/y"))
        if "target" in step:
            _validate_desktop_input_target_requirements(step, step_type, location, issues)
            if direct_fields.intersection(step):
                issues.append(ValidationIssue(location, "desktop_input.drag 不能同时使用 target 和 start/end 坐标"))
            delta_x = step.get("delta_x", 0)
            delta_y = step.get("delta_y", 0)
            has_delta = "delta_x" in step or "delta_y" in step
            if (
                has_delta
                and not _is_template(delta_x)
                and not _is_template(delta_y)
                and isinstance(delta_x, int)
                and isinstance(delta_y, int)
                and delta_x == 0
                and delta_y == 0
            ):
                issues.append(ValidationIssue(location, "desktop_input.drag delta_x 和 delta_y 不能同时为 0"))
        elif "delta_x" in step or "delta_y" in step:
            issues.append(ValidationIssue(location, "desktop_input.drag 只有 target 模式可以使用 delta_x/delta_y"))


def _validate_desktop_input_target_requirements(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    target = step.get("target")
    if target in {"current_window_offset", "focused_window_offset"}:
        for field in ("offset_x", "offset_y"):
            if field not in step:
                issues.append(ValidationIssue(location, f"desktop_input.{step_type} target={target} 缺少必填字段：{field}"))
    elif target == "bounds_center":
        if "bounds" not in step:
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} target=bounds_center 缺少必填字段：bounds"))
    elif target == "element_center":
        _validate_window_query(step, "desktop_input", step_type, location, issues)
        _validate_desktop_element_locator(step, "desktop_input", step_type, location, issues)
    elif target == "candidate":
        if "target_candidates" not in step and "candidate_source" not in step and "candidate" not in step:
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} target=candidate 缺少候选来源：target_candidates、candidate_source 或 candidate"))
        if "candidate_id" not in step and "target_candidate_id" not in step:
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} target=candidate 缺少必填字段：candidate_id"))
        forbidden_fields = (
            {"bounds", "offset_x", "offset_y"}
            | DESKTOP_ELEMENT_LOCATOR_FIELDS
            | DESKTOP_ELEMENT_REQUIRED_LOCATOR_FIELDS
            | {
                "title",
                "title_contains",
                "title_regex",
                "app",
                "process",
                "process_name",
                "class_name",
                "window_id",
                "match_index",
                "profile",
                "app_profile",
            }
        )
        mixed = sorted(field for field in forbidden_fields if field in step)
        if mixed:
            issues.append(
                ValidationIssue(
                    location,
                    "desktop_input."
                    + str(step_type)
                    + " target=candidate 不能同时展开 bounds、Window Query 或 Element Locator；"
                    + "请只传 target_candidates 和 candidate_id。当前混用字段："
                    + ", ".join(mixed),
                )
            )


def _validate_desktop_target_candidates_field(step: dict[str, Any], location: str, issues: list[ValidationIssue]) -> None:
    for field in ("target_candidates", "candidate_source", "candidate"):
        if field not in step or _is_template(step[field]):
            continue
        value = step[field]
        if field == "candidate" and isinstance(value, dict):
            continue
        if field in {"target_candidates", "candidate_source"} and isinstance(value, dict):
            continue
        if field == "candidate_source" and isinstance(value, str) and value in DESKTOP_TARGET_CANDIDATE_SOURCE_ALIASES:
            continue
        issues.append(ValidationIssue(location, f"{field} 必须是对象或完整模板引用。"))


def _validate_desktop_capture_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_region(step, "region", location, issues)
    _validate_enum(step, "target", {"screen", "region", "window", "element"}, location, issues)
    _validate_bool(step, "include_cursor", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "interval_ms", location, issues, minimum=1)
    _validate_int(step, "max_depth", location, issues, minimum=0)
    _validate_int(step, "max_elements", location, issues, minimum=1)
    if step_type == "screenshot" and step.get("target") == "element":
        _validate_enum(step, "state", {"exists", "enabled", "disabled", "focused"}, location, issues)
    if step_type == "screenshot" and step.get("target") in {"window", "element"} and "region" in step:
        issues.append(ValidationIssue(location, "desktop_capture.screenshot target=window/element 不能同时使用 region"))
    if step_type == "snapshot":
        _validate_bool(step, "include_windows", location, issues)
        _validate_bool(step, "include_displays", location, issues)
    if step_type == "observe":
        _validate_bool(step, "request_permissions", location, issues)
        _validate_bool(step, "include_windows", location, issues)
        _validate_bool(step, "include_invisible", location, issues)
        _validate_bool(step, "include_elements", location, issues)
        _validate_bool(step, "include_screenshot", location, issues)
        _validate_window_query_fields(step, location, issues)
        _validate_desktop_element_locator_fields(step, location, issues)
        _validate_int(step, "max_windows", location, issues, minimum=1)
        _validate_int(step, "max_depth", location, issues, minimum=0)
        _validate_int(step, "max_elements", location, issues, minimum=1)
        _validate_int(step, "text_limit", location, issues, minimum=0)
        if "target" in step:
            issues.append(ValidationIssue(location, "desktop_capture.observe 不使用 target；需要指定窗口时使用 Window Query"))
        if "region" in step:
            issues.append(ValidationIssue(location, "desktop_capture.observe 不使用 region；需要局部识别时使用 desktop_capture.screenshot 或 desktop_vision"))


def _validate_desktop_vision_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "locate_image":
        _validate_string(step, "template_path", location, issues)
    if step_type == "locate_text":
        for field in ("text", "text_contains", "text_regex", "language"):
            _validate_string(step, field, location, issues)
        _validate_enum(step, "provider", {"auto", "tesseract"}, location, issues)
        _validate_number(step, "min_confidence", location, issues)
        _validate_bool(step, "case_sensitive", location, issues)
        if "template_path" in step:
            issues.append(ValidationIssue(location, "desktop_vision.locate_text 不使用 template_path"))
    _validate_string(step, "source_path", location, issues)
    _validate_string(step, "path", location, issues)
    _validate_region(step, "region", location, issues)
    _validate_bool(step, "include_cursor", location, issues)
    _validate_enum(step, "source_target", {"screen", "window", "element"}, location, issues)
    _validate_enum(step, "state", {"exists", "enabled", "disabled", "focused"}, location, issues)
    _validate_number(step, "threshold", location, issues)
    _validate_int(step, "match_index", location, issues, minimum=0)
    _validate_int(step, "window_match_index", location, issues, minimum=0)
    _validate_int(step, "max_matches", location, issues, minimum=1)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "interval_ms", location, issues, minimum=1)
    _validate_int(step, "max_depth", location, issues, minimum=0)
    _validate_int(step, "max_elements", location, issues, minimum=1)
    if step_type in {"locate_image", "locate_text"}:
        if step.get("source_target") in {"window", "element"}:
            _validate_desktop_vision_window_query_fields(step, location, issues)
        if step.get("source_target") == "element":
            _validate_desktop_element_locator_fields(step, location, issues)
        if "source_path" in step and "source_target" in step:
            issues.append(ValidationIssue(location, f"desktop_vision.{step_type} 不能同时使用 source_path 和 source_target"))
    if step_type == "locate_image":
        threshold = step.get("threshold")
        if (
            threshold is not None
            and not _is_template(threshold)
            and isinstance(threshold, (int, float))
            and not 0 <= float(threshold) <= 1
        ):
            issues.append(ValidationIssue(location, "desktop_vision.locate_image threshold 必须在 0 到 1 之间"))
    if step_type == "locate_text":
        min_confidence = step.get("min_confidence")
        if (
            min_confidence is not None
            and not _is_template(min_confidence)
            and isinstance(min_confidence, (int, float))
            and not 0 <= float(min_confidence) <= 1
        ):
            issues.append(ValidationIssue(location, "desktop_vision.locate_text min_confidence 必须在 0 到 1 之间"))


def _validate_desktop_wait_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_window_query_fields(step, location, issues)
    if step_type == "window":
        _validate_enum(step, "state", {"exists", "not_exists", "focused"}, location, issues)
        _validate_int(step, "timeout_ms", location, issues, minimum=1)
        _validate_int(step, "interval_ms", location, issues, minimum=1)


def _validate_desktop_assert_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "window":
        _validate_window_query_fields(step, location, issues)
        _validate_enum(step, "state", {"exists", "not_exists", "focused"}, location, issues)
        _validate_int(step, "timeout_ms", location, issues, minimum=1)
        _validate_int(step, "interval_ms", location, issues, minimum=1)
        return
    if step_type == "screenshot":
        _validate_string(step, "path", location, issues)
        _validate_int(step, "min_bytes", location, issues, minimum=0)
        return
    if step_type == "element":
        _validate_window_query_fields(step, location, issues)
        _validate_desktop_element_locator_fields(step, location, issues)
        _validate_enum(step, "state", {"exists", "not_exists", "enabled", "disabled", "focused"}, location, issues)
        _validate_string(step, "expected", location, issues)
        _validate_enum(step, "mode", {"equals", "contains", "not_contains"}, location, issues)
        _validate_enum(step, "text_source", {"auto", "text", "value", "name"}, location, issues)
        _validate_int(step, "expected_count", location, issues, minimum=0)
        _validate_int(step, "min_count", location, issues, minimum=0)
        _validate_int(step, "max_count", location, issues, minimum=0)
        _validate_string(step, "property", location, issues)
        _validate_enum(step, "property_mode", {"equals", "contains", "not_contains"}, location, issues)
        _validate_string(step, "path", location, issues)
        _validate_int(step, "timeout_ms", location, issues, minimum=1)
        _validate_int(step, "interval_ms", location, issues, minimum=1)
        _validate_int(step, "max_depth", location, issues, minimum=0)
        _validate_int(step, "max_elements", location, issues, minimum=1)
        if "property" in step and "property_expected" not in step:
            issues.append(ValidationIssue(location, "desktop_assert.element 使用 property 时必须提供 property_expected"))
        if "property_expected" in step and "property" not in step:
            issues.append(ValidationIssue(location, "desktop_assert.element 使用 property_expected 时必须提供 property"))
        if "expected_count" in step and ("min_count" in step or "max_count" in step):
            issues.append(ValidationIssue(location, "desktop_assert.element expected_count 不能和 min_count/max_count 同时使用"))
        min_count = step.get("min_count")
        max_count = step.get("max_count")
        if (
            "min_count" in step
            and "max_count" in step
            and not _is_template(min_count)
            and not _is_template(max_count)
            and isinstance(min_count, int)
            and isinstance(max_count, int)
            and min_count > max_count
        ):
            issues.append(ValidationIssue(location, "desktop_assert.element min_count 不能大于 max_count"))
        if step.get("state") == "not_exists" and "expected" in step:
            issues.append(ValidationIssue(location, "desktop_assert.element state=not_exists 不能同时使用 expected 文本断言"))
        if step.get("state") == "not_exists" and ("property" in step or "property_expected" in step):
            issues.append(ValidationIssue(location, "desktop_assert.element state=not_exists 不能同时使用 property 属性断言"))


WINDOW_QUERY_FIELDS = {
    "title",
    "title_contains",
    "title_regex",
    "app",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "profile",
    "app_profile",
}


def _validate_window_query(
    step: dict[str, Any],
    action: str,
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if not any(field in step and step.get(field) not in (None, "") for field in WINDOW_QUERY_FIELDS):
        issues.append(ValidationIssue(location, f"{action}.{step_type} 需要至少一种窗口定位字段"))


def _validate_window_query_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    for field in (
        "title",
        "title_contains",
        "title_regex",
        "app",
        "process",
        "process_name",
        "class_name",
        "profile",
        "app_profile",
    ):
        _validate_string(step, field, location, issues)
    if "window_id" in step and not _is_template(step["window_id"]):
        value = step["window_id"]
        if not isinstance(value, (str, int)) or value == "":
            issues.append(ValidationIssue(location, "window_id 必须是非空字符串或整数"))
    _validate_int(step, "match_index", location, issues, minimum=0)


def _validate_desktop_vision_window_query_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    for field in (
        "title",
        "title_contains",
        "title_regex",
        "app",
        "process",
        "process_name",
        "class_name",
        "profile",
        "app_profile",
    ):
        _validate_string(step, field, location, issues)
    if "window_id" in step and not _is_template(step["window_id"]):
        value = step["window_id"]
        if not isinstance(value, (str, int)) or value == "":
            issues.append(ValidationIssue(location, "window_id 必须是非空字符串或整数"))


def _validate_desktop_element_locator(
    step: dict[str, Any],
    action: str,
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if not any(field in step and step.get(field) not in (None, "") for field in DESKTOP_ELEMENT_REQUIRED_LOCATOR_FIELDS):
        issues.append(ValidationIssue(location, f"{action}.{step_type} 需要至少一种控件定位字段"))


def _validate_desktop_element_locator_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    for field in (
        "element_id",
        "automation_id",
        "name",
        "name_contains",
        "name_regex",
        "text",
        "text_contains",
        "text_regex",
        "control_type",
        "role",
        "element_class_name",
    ):
        _validate_string(step, field, location, issues)
    _validate_int(step, "element_match_index", location, issues, minimum=0)


def _validate_region(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, f"{field} 必须是对象"))
        return
    for required_field in ("x", "y", "width", "height"):
        if required_field not in value:
            issues.append(ValidationIssue(location, f"{field}.{required_field} 缺少必填字段"))
            continue
        dimension = value[required_field]
        if not isinstance(dimension, int):
            issues.append(ValidationIssue(location, f"{field}.{required_field} 必须是整数"))
            continue
        if required_field in {"width", "height"} and dimension <= 0:
            issues.append(ValidationIssue(location, f"{field}.{required_field} 必须大于 0"))


def _validate_bounds(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, f"{field} 必须是对象"))
        return
    for required_field in ("x", "y", "width", "height"):
        if required_field not in value:
            issues.append(ValidationIssue(location, f"{field}.{required_field} 缺少必填字段"))
            continue
        dimension = value[required_field]
        if not isinstance(dimension, int):
            issues.append(ValidationIssue(location, f"{field}.{required_field} 必须是整数"))
            continue
        if required_field in {"width", "height"} and dimension <= 0:
            issues.append(ValidationIssue(location, f"{field}.{required_field} 必须大于 0"))
