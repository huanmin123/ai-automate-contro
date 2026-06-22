from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_rules import ACTION_TYPES


LOCATOR_FIELDS = {
    "selector",
    "role",
    "text",
    "label",
    "placeholder",
    "alt_text",
    "title",
    "test_id",
}

FRAME_FIELDS = {
    "frame_selector",
    "frame_name",
    "frame_url",
    "frame_url_contains",
    "frame_index",
}

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
HTTP_BODY_FIELDS = ("json", "body", "body_path", "form", "multipart")


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
    if action == "wait" and step_type == "timeout":
        issues.append(
            ValidationIssue(
                location,
                "不支持的 wait.type：timeout。固定等待请写 type=time 并使用 seconds，例如 {\"action\":\"wait\",\"type\":\"time\",\"browser\":\"main\",\"seconds\":2}；条件等待请使用 selector、url、text、count、load_state、element_state 或 function。",
            )
        )
        return
    if action == "wait" and (step_type is None or step_type == "time") and _has_non_time_wait_fields(step):
        issues.append(
            ValidationIssue(
                location,
                "wait 带 selector/url/text/expected/state/js 时必须显式设置非 time 的 type。",
            )
        )
        return
    if action in {"wait", "scroll"} and step_type is None:
        return
    if not isinstance(step_type, str) or not step_type:
        issues.append(ValidationIssue(location, f"{action}.type 必须是非空字符串"))
        return
    if step_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        issues.append(ValidationIssue(location, f"不支持的 {action}.type：{step_type}；可选值：{allowed}"))


def _has_non_time_wait_fields(step: dict[str, Any]) -> bool:
    return any(field in step for field in ("selector", "url", "text", "expected", "state", "js"))


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
    elif action == "element" and step_type == "drag_to":
        required = ("target_selector",)
    elif action == "wait" and step_type in {"selector", None}:
        required = ("selector",) if step_type == "selector" else ()
    elif action == "wait" and step_type == "url":
        required = ("url",)
    elif action == "wait" and step_type == "text":
        required = ("text",)
    elif action == "wait" and step_type == "count":
        required = ("selector", "expected")
    elif action == "wait" and step_type == "load_state":
        required = ("state",)
    elif action == "wait" and step_type == "element_state":
        required = ("state",)
    elif action == "wait" and step_type == "function":
        required = ("js",)
    elif action == "extract" and step_type in {"text", "value", "html"}:
        required = ()
    elif action == "extract" and step_type in {"all_texts", "all_values"}:
        required = ("selector",)
    elif action == "extract" and step_type == "attribute":
        required = ("attribute",)
    elif action == "extract" and step_type == "count":
        required = ("selector",)
    elif action == "extract" and step_type == "table":
        required = ("row_selector",)
    elif action == "extract" and step_type == "frames":
        required = ()
    elif action == "extract" and step_type == "css":
        required = ("property",)
    elif action == "keyboard" and step_type in {"press", "down", "up"}:
        required = ("key",)
    elif action == "keyboard" and step_type == "type":
        required = ("value",)
    elif action == "mouse" and step_type in {"move", "click"}:
        required = ("x", "y")
    elif action == "mouse" and step_type == "tap":
        required = ("x", "y")
    elif action == "mouse" and step_type == "swipe":
        required = ("start_x", "start_y", "end_x", "end_y")
    elif action == "assert" and step_type == "selector":
        required = ("selector",)
    elif action == "assert" and step_type in {"text", "value"}:
        required = ("expected",)
    elif action == "assert" and step_type == "url":
        required = ("expected",)
    elif action == "assert" and step_type == "count":
        required = ("selector", "expected")
    elif action == "assert" and step_type == "attribute":
        required = ("selector", "attribute", "expected")
    elif action == "assert" and step_type == "css":
        required = ("selector", "property", "expected")
    elif action == "assert" and step_type in {"checked", "unchecked", "enabled", "disabled", "visible", "hidden"}:
        required = ()
    elif action == "assert" and step_type == "title":
        required = ("expected",)
    elif action == "network" and step_type == "route":
        required = ("url",)
    elif action == "network" and step_type == "unroute":
        required = ("url",)
    elif action == "network" and step_type == "set_extra_http_headers":
        required = ("headers",)
    elif action == "network" and step_type == "route_from_har":
        required = ("path",)
    elif action == "network" and step_type == "route_web_socket":
        required = ("url",)
    elif action == "event" and step_type == "stop":
        required = ("path",)
    elif action == "coverage" and step_type == "stop":
        required = ("path",)
    elif action == "script" and step_type in {"evaluate", "add_init_script"}:
        required = ("js",)
    elif action == "storage" and step_type in {"set_cookies"}:
        required = ("cookies",)
    elif action == "storage" and step_type == "cookies":
        required = ("save_as",)
    elif action == "storage" and step_type in {"local_storage", "session_storage"}:
        required = ("key", "save_as")
    elif action == "storage" and step_type in {"set_local_storage", "set_session_storage"}:
        required = ("key", "value")
    elif action == "storage" and step_type in {"remove_local_storage", "remove_session_storage"}:
        required = ("key",)
    elif action == "trace" and step_type == "stop":
        required = ("path",)
    elif action == "command" and step_type == "run" and not any(field in step for field in ("command", "commands", "argv")):
        issues.append(ValidationIssue(location, "command.run 需要 command、commands 或 argv 之一"))
    elif action == "ai" and step_type == "extract_data":
        required = ("schema",)
    elif action == "ai" and step_type == "classify_text" and "schema" not in step:
        required = ("labels",)

    for field in required:
        if field not in step:
            issues.append(ValidationIssue(location, f"{action}.{step_type} 缺少必填字段：{field}"))

    _validate_optional_field_values(step, action, step_type, location, issues)

    if action in {"element", "wait", "extract", "assert"} and step_type not in {
        None,
        "time",
        "url",
        "load_state",
        "function",
        "title",
        "table",
        "frames",
        "count",
    }:
        _validate_frame_fields(step, location, issues)
        _validate_locator_fields(step, action, step_type, location, issues)
    elif action in {"element", "wait", "extract", "assert"}:
        _validate_frame_fields(step, location, issues)


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


def _validate_optional_field_values(
    step: dict[str, Any],
    action: str,
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
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
    if action == "command":
        _validate_command_fields(step, step_type, location, issues)
        return
    if action == "element":
        _validate_element_fields(step, step_type, location, issues)
        return
    if action == "extract":
        _validate_extract_fields(step, step_type, location, issues)
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


def _validate_open_browser_fields(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_enum(step, "browser_type", {"chromium", "firefox", "webkit"}, location, issues)
    if step.get("browser_type") not in {None, "chromium"} and "channel" in step and not _is_template(step["channel"]):
        issues.append(ValidationIssue(location, "open_browser.channel 仅支持 browser_type=chromium"))
    for field in (
        "headed",
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


def _validate_http_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type != "request":
        return
    method = step.get("method")
    if "method" in step and not _is_template(method):
        if not isinstance(method, str) or method.upper() not in HTTP_METHODS:
            issues.append(ValidationIssue(location, f"method 不支持的取值：{method}；可选值：{', '.join(sorted(HTTP_METHODS))}"))
    url = step.get("url")
    if "url" in step and not _is_template(url):
        if not isinstance(url, str) or not url.strip():
            issues.append(ValidationIssue(location, "url 必须是非空字符串"))
        else:
            scheme = urlsplit(url).scheme
            if scheme not in {"http", "https"}:
                issues.append(ValidationIssue(location, "url 只支持 http:// 或 https://"))
    body_fields = [field for field in HTTP_BODY_FIELDS if field in step]
    if len(body_fields) > 1:
        issues.append(ValidationIssue(location, f"http.request 只能同时使用一种 body 字段，当前包含：{', '.join(body_fields)}"))
    _validate_dict(step, "headers", location, issues)
    _validate_dict(step, "query", location, issues)
    _validate_dict(step, "form", location, issues)
    _validate_dict(step, "multipart", location, issues)
    _validate_dict(step, "auth", location, issues)
    _validate_string(step, "body_path", location, issues)
    _validate_string(step, "response_body_path", location, issues)
    _validate_string(step, "save_as", location, issues)
    _validate_string(step, "body", location, issues)
    _validate_string(step, "content_type", location, issues)
    _validate_bool(step, "allow_body", location, issues)
    _validate_bool(step, "follow_redirects", location, issues)
    _validate_bool(step, "verify_tls", location, issues)
    _validate_bool(step, "include_headers", location, issues)
    _validate_bool(step, "include_body", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "max_redirects", location, issues, minimum=0)
    _validate_int(step, "max_body_bytes", location, issues, minimum=1)
    _validate_enum(step, "body_type", {"text", "json", "bytes"}, location, issues)
    if isinstance(step.get("multipart"), dict):
        multipart = step["multipart"]
        _validate_dict(multipart, "fields", location, issues)
        _validate_list(multipart, "files", location, issues)
        files = multipart.get("files", [])
        if isinstance(files, list):
            for index, file_item in enumerate(files):
                item_location = f"{location}.multipart.files[{index}]"
                if not isinstance(file_item, dict):
                    issues.append(ValidationIssue(item_location, "multipart.files 每一项必须是对象"))
                    continue
                for field in ("field", "path"):
                    if field not in file_item:
                        issues.append(ValidationIssue(item_location, f"multipart.files 缺少必填字段：{field}"))
                    elif not isinstance(file_item[field], str) or not file_item[field]:
                        issues.append(ValidationIssue(item_location, f"{field} 必须是非空字符串"))


def _validate_command_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type != "run":
        return
    command_sources = [field for field in ("command", "commands", "argv") if field in step]
    if len(command_sources) > 1:
        issues.append(ValidationIssue(location, "command.run 只能同时提供 command、commands 或 argv 中的一种"))
    _validate_string(step, "command", location, issues)
    _validate_dict(step, "commands", location, issues)
    _validate_list(step, "argv", location, issues)
    if isinstance(step.get("argv"), list):
        for index, item in enumerate(step["argv"]):
            if not isinstance(item, str) or not item:
                issues.append(ValidationIssue(f"{location}.argv[{index}]", "argv 每一项必须是非空字符串"))
    _validate_string(step, "cwd", location, issues)
    _validate_string(step, "stdin", location, issues)
    _validate_string(step, "stdin_path", location, issues)
    if "stdin" in step and "stdin_path" in step:
        issues.append(ValidationIssue(location, "command.stdin 和 command.stdin_path 只能提供一种"))
    _validate_string(step, "stdout_path", location, issues)
    _validate_string(step, "stderr_path", location, issues)
    _validate_string(step, "save_as", location, issues)
    _validate_string(step, "encoding", location, issues)
    _validate_dict(step, "env", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "max_output_bytes", location, issues, minimum=1)
    _validate_enum(step, "stdout_type", {"text", "json"}, location, issues)
    _validate_enum(step, "shell", {"auto", "pwsh", "powershell", "cmd", "sh", "bash"}, location, issues)


def _validate_enum(
    step: dict[str, Any],
    field: str,
    allowed: set[str],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        issues.append(ValidationIssue(location, f"{field} 不支持的取值：{value}；可选值：{allowed_text}"))


def _validate_bool(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    if not isinstance(step[field], bool):
        issues.append(ValidationIssue(location, f"{field} 必须是布尔值"))


def _validate_dict(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    if not isinstance(step[field], dict):
        issues.append(ValidationIssue(location, f"{field} 必须是对象"))


def _validate_list(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    if not isinstance(step[field], list):
        issues.append(ValidationIssue(location, f"{field} 必须是数组"))


def _validate_string(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    if not isinstance(step[field], str) or not step[field]:
        issues.append(ValidationIssue(location, f"{field} 必须是非空字符串"))


def _validate_int(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
    *,
    minimum: int | None = None,
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if not isinstance(value, int):
        issues.append(ValidationIssue(location, f"{field} 必须是整数"))
        return
    if minimum is not None and value < minimum:
        issues.append(ValidationIssue(location, f"{field} 必须大于或等于 {minimum}"))


def _validate_number(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    if not isinstance(step[field], (int, float)):
        issues.append(ValidationIssue(location, f"{field} 必须是数字"))


def _validate_size(
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
    for dimension in ("width", "height"):
        if dimension not in value:
            issues.append(ValidationIssue(location, f"{field}.{dimension} 缺少必填字段"))
            continue
        dimension_value = value[dimension]
        if not isinstance(dimension_value, int) or dimension_value <= 0:
            issues.append(ValidationIssue(location, f"{field}.{dimension} 必须是正整数"))


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "}}" in value)
