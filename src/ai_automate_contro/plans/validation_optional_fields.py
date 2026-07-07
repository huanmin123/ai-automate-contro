from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_browser_fields import (
    _validate_assert_fields,
    _validate_element_fields,
    _validate_extract_fields,
    _validate_network_fields,
    _validate_open_browser_fields,
    _validate_storage_fields,
)
from ai_automate_contro.plans.validation_data_fields import (
    _validate_read_fields,
    _validate_table_fields,
    _validate_write_fields,
)
from ai_automate_contro.plans.validation_database_fields import (
    _validate_command_fields,
    _validate_http_fields,
    _validate_mongo_fields,
    _validate_redis_fields,
    _validate_sql_fields,
)
from ai_automate_contro.plans.validation_desktop_fields import (
    _validate_desktop_app_fields,
    _validate_desktop_assert_fields,
    _validate_desktop_capture_fields,
    _validate_desktop_element_fields,
    _validate_desktop_input_fields,
    _validate_desktop_vision_fields,
    _validate_desktop_wait_fields,
    _validate_desktop_window_fields,
    _validate_open_desktop_fields,
)
from ai_automate_contro.plans.validation_field_helpers import (
    _validate_bool,
    _validate_enum,
    _validate_int,
    _validate_number,
    _validate_size,
    _validate_string,
)
from ai_automate_contro.plans.validation_models import ValidationIssue


def validate_optional_field_values(
    step: dict[str, Any],
    action: str,
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if action == "read":
        _validate_read_fields(step, step_type, location, issues)
        return
    if action == "write":
        _validate_write_fields(step, step_type, location, issues)
        return
    if action == "table":
        _validate_table_fields(step, step_type, location, issues)
        return
    if action == "open_browser":
        _validate_open_browser_fields(step, location, issues)
        return
    if action == "wait":
        if step_type in {"selector", "element_state"}:
            _validate_enum(step, "state", {"attached", "detached", "visible", "hidden"}, location, issues)
        if step_type == "load_state":
            _validate_enum(step, "state", {"load", "domcontentloaded", "networkidle"}, location, issues)
        if step_type == "function":
            _validate_string(step, "js", location, issues)
        _validate_int(step, "timeout_ms", location, issues, minimum=0)
        return
    if action == "network":
        _validate_network_fields(step, step_type, location, issues)
        return
    if action == "event":
        if step_type in {"request", "response"}:
            _validate_enum(step, "body_type", {"text", "json", "body"}, location, issues)
            _validate_bool(step, "include_headers", location, issues)
            _validate_bool(step, "include_post_data", location, issues)
            _validate_bool(step, "include_body", location, issues)
        _validate_bool(step, "switch", location, issues)
        for field in (
            "console",
            "pageerror",
            "requestfailed",
            "websocket",
            "websocket_frames",
            "eventsource",
            "webrtc",
            "webrtc_include_sdp",
            "webrtc_include_candidate",
            "serviceworker",
        ):
            _validate_bool(step, field, location, issues)
        return
    if action == "coverage":
        _validate_bool(step, "js", location, issues)
        _validate_bool(step, "css", location, issues)
        if step_type == "start" and step.get("js") is False and step.get("css") is False:
            issues.append(ValidationIssue(location, "coverage.start 至少需要启用 js 或 css 之一"))
        return
    if action == "trace":
        for field in ("screenshots", "snapshots", "sources"):
            _validate_bool(step, field, location, issues)
        return
    if action == "script":
        _validate_string(step, "js", location, issues)
        return
    if action == "storage":
        _validate_storage_fields(step, step_type, location, issues)
        return
    if action == "http":
        _validate_http_fields(step, step_type, location, issues)
        return
    if action == "sql":
        _validate_sql_fields(step, step_type, location, issues)
        return
    if action == "mongo":
        _validate_mongo_fields(step, step_type, location, issues)
        return
    if action == "redis":
        _validate_redis_fields(step, step_type, location, issues)
        return
    if action == "command":
        _validate_command_fields(step, step_type, location, issues)
        return
    if action == "open_desktop":
        _validate_open_desktop_fields(step, location, issues)
        return
    if action == "desktop_app":
        _validate_desktop_app_fields(step, step_type, location, issues)
        return
    if action == "desktop_window":
        _validate_desktop_window_fields(step, step_type, location, issues)
        return
    if action == "desktop_element":
        _validate_desktop_element_fields(step, step_type, location, issues)
        return
    if action == "desktop_input":
        _validate_desktop_input_fields(step, step_type, location, issues)
        return
    if action == "desktop_capture":
        _validate_desktop_capture_fields(step, step_type, location, issues)
        return
    if action == "desktop_vision":
        _validate_desktop_vision_fields(step, step_type, location, issues)
        return
    if action == "desktop_wait":
        _validate_desktop_wait_fields(step, step_type, location, issues)
        return
    if action == "desktop_assert":
        _validate_desktop_assert_fields(step, step_type, location, issues)
        return
    if action == "element":
        _validate_element_fields(step, step_type, location, issues)
        return
    if action == "extract":
        _validate_extract_fields(step, step_type, location, issues)
        return
    if action == "ai":
        _validate_string(step, "service", location, issues)
        _validate_string(step, "path", location, issues)
        return
    if action == "assert":
        _validate_assert_fields(step, step_type, location, issues)
        return
    if action == "input":
        _validate_browser_input_fields(step, step_type, location, issues)
        return


def _validate_browser_input_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_enum(step, "device", {"keyboard", "mouse", "scroll"}, location, issues)
    _validate_int(step, "delay_ms", location, issues, minimum=0)
    for field in ("x", "y", "delta_x", "delta_y", "start_x", "start_y", "end_x", "end_y"):
        _validate_number(step, field, location, issues)
    _validate_int(step, "steps", location, issues, minimum=1)
    _validate_int(step, "duration_ms", location, issues, minimum=0)
    _validate_bool(step, "touch", location, issues)
    _validate_bool(step, "fallback_to_mouse", location, issues)

    raw_device = step.get("device")
    if raw_device not in (None, "") and raw_device not in {"keyboard", "mouse", "scroll"}:
        return
    device = raw_device or _infer_browser_input_device(step_type)
    if device == "keyboard" and step_type not in {"press", "type", "down", "up"}:
        issues.append(ValidationIssue(location, f"input.device=keyboard 不支持 type={step_type}"))
    elif device == "mouse" and step_type not in {"move", "click", "down", "up", "wheel", "tap", "swipe"}:
        issues.append(ValidationIssue(location, f"input.device=mouse 不支持 type={step_type}"))
    elif device == "scroll" and step_type not in {"into_view", "by"}:
        issues.append(ValidationIssue(location, f"input.device=scroll 不支持 type={step_type}"))


def _infer_browser_input_device(step_type: Any) -> str | None:
    if step_type in {"press", "type"}:
        return "keyboard"
    if step_type in {"move", "click", "wheel", "tap", "swipe"}:
        return "mouse"
    if step_type in {"into_view", "by"}:
        return "scroll"
    return None
