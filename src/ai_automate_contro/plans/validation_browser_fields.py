from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_field_helpers import (
    FRAME_FIELDS,
    LOCATOR_FIELDS,
    _validate_bool,
    _validate_dict,
    _validate_enum,
    _validate_int,
    _validate_list,
    _validate_number,
    _validate_size,
    _validate_string,
)
from ai_automate_contro.plans.validation_models import ValidationIssue


def _validate_locator_fields(
    step: dict[str, Any],
    action: str,
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if action == "extract" and step_type in {"count", "all_texts", "all_values"}:
        return
    if action == "assert" and step_type == "count":
        return
    if action == "wait" and step_type in {"selector", "count"}:
        return
    if action == "element" and step_type == "drag_to":
        pass
    locator_fields = [field for field in LOCATOR_FIELDS if field in step]
    if "selector" not in step and not locator_fields:
        issues.append(ValidationIssue(location, f"{action}.{step_type} 需要 selector 或一种语义定位字段"))
        return
    if len(locator_fields) > 1 and "selector" not in step:
        allowed = ", ".join(sorted(locator_fields))
        issues.append(ValidationIssue(location, f"只能同时使用一种语义定位字段，当前包含：{allowed}"))


def _validate_frame_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    frame_fields = [field for field in FRAME_FIELDS if field in step]
    if len(frame_fields) > 1:
        allowed = ", ".join(sorted(frame_fields))
        issues.append(ValidationIssue(location, f"只能同时使用一种 frame 定位字段，当前包含：{allowed}"))
    for field in ("frame_selector", "frame_name", "frame_url", "frame_url_contains"):
        _validate_string(step, field, location, issues)
    _validate_int(step, "frame_index", location, issues, minimum=0)


def _validate_open_browser_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    unsupported_profile_fields = [field for field in ("profile_dir", "profile_name", "user_data_dir") if field in step]
    if unsupported_profile_fields:
        issues.append(
            ValidationIssue(
                location,
                "open_browser 不支持自定义 profile 路径或名称；当前 plan 包只允许一套浏览器状态 profiles/browser。",
            )
        )
    if step.get("use_profile") is True and "storage_state_path" in step:
        issues.append(ValidationIssue(location, "open_browser.use_profile=true 时不能同时使用 storage_state_path。"))
    _validate_enum(step, "browser_type", {"chromium", "firefox", "webkit"}, location, issues)
    if step.get("use_profile") is True and step.get("browser_type") not in {None, "chromium"} and not _is_template(step.get("browser_type")):
        issues.append(ValidationIssue(location, "open_browser.use_profile=true 仅支持 browser_type=chromium；Chrome/Edge 请使用 channel。"))
    if step.get("browser_type") not in {None, "chromium"} and "channel" in step and not _is_template(step["channel"]):
        issues.append(ValidationIssue(location, "open_browser.channel 仅支持 browser_type=chromium"))
    for field in (
        "headed",
        "use_profile",
        "accept_downloads",
        "ignore_https_errors",
        "java_script_enabled",
        "bypass_csp",
        "is_mobile",
        "has_touch",
        "offline",
        "strict_selectors",
        "record_har_omit_content",
    ):
        _validate_bool(step, field, location, issues)
    for field in ("viewport", "screen", "record_video_size"):
        _validate_size(step, field, location, issues)
    for field in (
        "proxy",
        "geolocation",
        "extra_http_headers",
        "http_credentials",
    ):
        _validate_dict(step, field, location, issues)
    _validate_list(step, "permissions", location, issues)
    _validate_list(step, "args", location, issues)
    _validate_string(step, "device", location, issues)
    _validate_number(step, "device_scale_factor", location, issues)
    _validate_int(step, "slow_mo_ms", location, issues, minimum=0)
    _validate_int(step, "timeout_ms", location, issues, minimum=0)
    _validate_enum(step, "color_scheme", {"dark", "light", "no-preference", "null"}, location, issues)
    _validate_enum(step, "reduced_motion", {"no-preference", "reduce", "null"}, location, issues)
    _validate_enum(step, "forced_colors", {"active", "none", "null"}, location, issues)
    _validate_enum(step, "service_workers", {"allow", "block"}, location, issues)
    _validate_enum(step, "record_har_mode", {"full", "minimal"}, location, issues)
    _validate_enum(step, "record_har_content", {"attach", "embed", "omit"}, location, issues)


def _validate_network_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "route":
        _validate_enum(step, "mode", {"fulfill", "abort", "continue"}, location, issues)
        _validate_int(step, "status", location, issues, minimum=100)
        _validate_dict(step, "headers", location, issues)
        return
    if step_type == "set_extra_http_headers":
        _validate_dict(step, "headers", location, issues)
        return
    if step_type == "route_from_har":
        _validate_string(step, "path", location, issues)
        _validate_enum(step, "scope", {"context", "page"}, location, issues)
        _validate_enum(step, "not_found", {"abort", "fallback"}, location, issues)
        _validate_enum(step, "update_content", {"attach", "embed"}, location, issues)
        _validate_enum(step, "update_mode", {"full", "minimal"}, location, issues)
        _validate_bool(step, "update", location, issues)
        return
    if step_type == "route_web_socket":
        _validate_string(step, "url", location, issues)
        _validate_enum(step, "scope", {"context", "page"}, location, issues)
        _validate_bool(step, "echo", location, issues)
        _validate_bool(step, "close_after_response", location, issues)
        _validate_bool(step, "close_on_connect", location, issues)
        _validate_list(step, "server_messages", location, issues)
        _validate_int(step, "close_code", location, issues, minimum=1000)


def _validate_storage_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "set_cookies":
        _validate_list(step, "cookies", location, issues)
    if step_type in {
        "local_storage",
        "set_local_storage",
        "remove_local_storage",
        "session_storage",
        "set_session_storage",
        "remove_session_storage",
    }:
        _validate_string(step, "key", location, issues)


def _validate_element_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_bool(step, "force", location, issues)
    _validate_bool(step, "trial", location, issues)
    _validate_bool(step, "no_wait_after", location, issues)
    _validate_int(step, "timeout", location, issues, minimum=0)
    _validate_int(step, "click_count", location, issues, minimum=1)
    _validate_int(step, "delay_ms", location, issues, minimum=0)
    _validate_list(step, "modifiers", location, issues)
    _validate_dict(step, "position", location, issues)
    _validate_dict(step, "source_position", location, issues)
    _validate_dict(step, "target_position", location, issues)
    _validate_enum(step, "button", {"left", "right", "middle"}, location, issues)
    if step_type == "select" and not any(field in step for field in ("value", "label", "index_value")):
        issues.append(ValidationIssue(location, "element.select 需要 value、label 或 index_value 之一"))


def _validate_extract_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "aria_snapshot":
        _validate_int(step, "timeout", location, issues, minimum=0)
        _validate_int(step, "depth", location, issues, minimum=0)
        if step.get("mode") == "interesting":
            issues.append(
                ValidationIssue(
                    location,
                    "aria_snapshot.mode 不支持 interesting；只能使用 default 或 ai。需要模型友好的快照时请写 mode=ai，普通快照可省略或写 default。",
                )
            )
            return
        _validate_enum(step, "mode", {"ai", "default"}, location, issues)


def _validate_assert_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type in {"text", "value", "attribute", "css", "title", "url"}:
        _validate_enum(step, "mode", {"equals", "contains", "not_contains"}, location, issues)
        return
    if step_type == "count":
        _validate_enum(step, "mode", {"equals", "gte", "lte"}, location, issues)
