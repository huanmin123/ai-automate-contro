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
    if action == "wait_for_network":
        _validate_enum(step, "body_type", {"text", "json", "body"}, location, issues)
        _validate_bool(step, "include_headers", location, issues)
        _validate_bool(step, "include_post_data", location, issues)
        _validate_bool(step, "include_body", location, issues)
        return
    if action == "network":
        _validate_network_fields(step, step_type, location, issues)
        return
    if action == "event":
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
    if action == "mouse":
        _validate_number(step, "x", location, issues)
        _validate_number(step, "y", location, issues)
        _validate_number(step, "delta_x", location, issues)
        _validate_number(step, "delta_y", location, issues)
        _validate_number(step, "start_x", location, issues)
        _validate_number(step, "start_y", location, issues)
        _validate_number(step, "end_x", location, issues)
        _validate_number(step, "end_y", location, issues)
        _validate_int(step, "steps", location, issues, minimum=1)
        _validate_int(step, "duration_ms", location, issues, minimum=0)
        _validate_bool(step, "touch", location, issues)
        _validate_bool(step, "fallback_to_mouse", location, issues)

