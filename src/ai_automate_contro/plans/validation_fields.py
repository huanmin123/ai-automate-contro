from __future__ import annotations

import re
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

DESKTOP_ELEMENT_LOCATOR_FIELDS = {
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
    "element_match_index",
}
DESKTOP_ELEMENT_REQUIRED_LOCATOR_FIELDS = DESKTOP_ELEMENT_LOCATOR_FIELDS - {"element_match_index"}
DESKTOP_INPUT_TARGETS = {
    "current_window_center",
    "focused_window_center",
    "current_window_offset",
    "focused_window_offset",
    "element_center",
    "bounds_center",
    "candidate",
}
DESKTOP_TARGET_CANDIDATE_SOURCE_ALIASES = {"latest", "last", "session", "latest_target_candidates"}

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
HTTP_BODY_FIELDS = ("json", "body", "body_path", "form", "multipart")
SQL_CONNECTION_TYPES = {
    "sqlite",
    "sqlite3",
    "postgresql",
    "postgres",
    "pg",
    "mysql",
    "mariadb",
    "oracle",
    "oracledb",
    "duckdb",
    "mssql",
    "sqlserver",
    "sql_server",
    "sql-server",
}
SQL_ROW_MODES = {"dict", "list"}
SQL_BULK_MODES = {"insert", "replace", "upsert"}
SQL_FILE_TABLE_TYPES = {"csv", "json", "jsonl", "excel", "xlsx", "xlsm"}
SQL_TRANSACTION_STEP_TYPES = {"query", "scalar", "execute", "executemany", "bulk_insert"}
MONGO_CONNECTION_TYPES = {"mongo", "mongodb"}
REDIS_VALUE_TYPES = {"set", "lpush", "rpush"}
EXCEL_A1_RE = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]*(?::[A-Za-z]{1,3}[1-9][0-9]*)?$")
TABLE_FILTER_OPERATORS = {
    "contains",
    "empty",
    "eq",
    "equals",
    "gt",
    "gte",
    "in",
    "lt",
    "lte",
    "ne",
    "not_contains",
    "not_empty",
    "not_equals",
    "not_in",
}
TABLE_AGGREGATION_OPERATORS = {"count", "sum", "avg", "min", "max"}
TABLE_ADD_COLUMN_OPERATORS = {"value", "copy", "format", "sum"}
TABLE_TYPE_CONVERT_TYPES = {"str", "string", "text", "int", "integer", "float", "number", "bool", "boolean"}


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
    elif action == "sql":
        if step_type in {"query", "scalar", "execute"}:
            required = ("sql",)
        elif step_type == "executemany":
            required = ("sql", "params_list")
        elif step_type == "bulk_insert":
            required = ("table", "rows")
        elif step_type == "import":
            required = ("source_path", "table")
        elif step_type == "export":
            required = ("sql", "target_path")
        elif step_type == "copy":
            required = ("sql", "target_connection", "table")
        elif step_type == "transaction":
            required = ("steps",)
    elif action == "mongo":
        if step_type in {"find", "find_one"}:
            required = ("collection",)
        elif step_type == "insert_one":
            required = ("collection", "document")
        elif step_type == "insert_many":
            required = ("collection", "documents")
        elif step_type in {"update_one", "update_many"}:
            required = ("collection", "filter", "update")
        elif step_type in {"delete_one", "delete_many"}:
            required = ("collection", "filter")
        elif step_type == "aggregate":
            required = ("collection", "pipeline")
        elif step_type == "command":
            required = ("command",)
        elif step_type == "list_indexes":
            required = ("collection",)
        elif step_type == "create_index":
            required = ("collection", "keys")
        elif step_type == "drop_index":
            required = ("collection",)
    elif action == "redis":
        if step_type in {"get", "hgetall", "lrange", "smembers"}:
            required = ("key",)
        elif step_type == "set":
            required = ("key", "value")
        elif step_type == "delete" and "key" not in step and "keys" not in step:
            issues.append(ValidationIssue(location, "redis.delete 需要 key 或 keys"))
        elif step_type == "hget":
            required = ("key", "field")
        elif step_type == "hset" and "mapping" not in step:
            required = ("key", "field", "value")
        elif step_type in REDIS_VALUE_TYPES and "value" not in step and "values" not in step:
            issues.append(ValidationIssue(location, f"redis.{step_type} 需要 value 或 values"))
        elif step_type == "sadd" and "value" not in step and "members" not in step:
            issues.append(ValidationIssue(location, "redis.sadd 需要 value 或 members"))
        elif step_type == "expire":
            required = ("key", "seconds")
        elif step_type == "command":
            required = ("command",)
        elif step_type == "pipeline":
            required = ("commands",)
    elif action == "command" and step_type == "run" and not any(field in step for field in ("command", "commands", "argv")):
        issues.append(ValidationIssue(location, "command.run 需要 command、commands 或 argv 之一"))
    elif action == "table":
        if step_type == "filter":
            required = ("where",)
        elif step_type == "select":
            required = ("columns",)
        elif step_type in {"sort", "dedupe"}:
            required = ("by",)
        elif step_type == "group":
            required = ("by", "aggregations")
        elif step_type == "join":
            required = ("right",)
        elif step_type == "add_column":
            required = ("columns",)
        elif step_type == "rename":
            required = ("columns",)
        elif step_type == "fill_empty":
            required = ("values",)
        elif step_type == "type_convert":
            required = ("columns",)
        elif step_type == "pivot":
            required = ("index", "columns")
        elif step_type == "split_column":
            required = ("column", "into", "separator")
        elif step_type == "merge_columns":
            required = ("columns", "into")
        elif step_type == "date_parse":
            required = ("columns",)
        elif step_type == "lookup":
            required = ("right",)
    elif action == "desktop_app" and step_type == "launch" and not any(
        step.get(field) for field in ("app", "path", "command", "profile", "app_profile")
    ):
        issues.append(ValidationIssue(location, "desktop_app.launch 需要 app、path、command 或 profile 之一"))
    elif action == "desktop_app" and step_type == "launch" and step.get("wait_for_window") is True:
        _validate_window_query(step, action, "launch wait_for_window", location, issues)
    elif action == "desktop_window" and step_type in {"find", "focus", "close", "minimize", "maximize", "restore"}:
        _validate_window_query(step, action, step_type, location, issues)
    elif action == "desktop_element":
        _validate_window_query(step, action, step_type, location, issues)
        if step_type in {
            "find",
            "wait",
            "get_text",
            "get_state",
            "click",
            "set_text",
            "invoke",
            "select",
            "get_table",
            "select_cell",
            "get_tree",
            "expand_tree",
            "collapse_tree",
            "select_tree",
            "scroll_element",
        }:
            _validate_desktop_element_locator(step, action, step_type, location, issues)
        if step_type == "set_text":
            required = ("value",)
        if step_type == "select" and "value" not in step and "option_index" not in step:
            issues.append(ValidationIssue(location, "desktop_element.select 需要 value 或 option_index"))
        if step_type == "select_cell":
            if "row" not in step:
                issues.append(ValidationIssue(location, "desktop_element.select_cell 缺少必填字段：row"))
            if "column" not in step and "column_index" not in step:
                issues.append(ValidationIssue(location, "desktop_element.select_cell 需要 column 或 column_index"))
        if step_type in {"expand_tree", "collapse_tree", "select_tree"} and "tree_path" not in step:
            issues.append(ValidationIssue(location, f"desktop_element.{step_type} 缺少必填字段：tree_path"))
        if step_type == "invoke_menu" and "menu_path" not in step:
            issues.append(ValidationIssue(location, "desktop_element.invoke_menu 缺少必填字段：menu_path"))
        if step_type == "invoke_menu" and step.get("open_context_menu") is True:
            _validate_desktop_element_locator(step, action, step_type, location, issues)
        if step_type == "scroll_element" and "amount" not in step and "scroll_to" not in step:
            issues.append(ValidationIssue(location, "desktop_element.scroll_element 需要 amount 或 scroll_to"))
    elif action == "desktop_input" and step_type == "type_text":
        required = ("value",)
    elif action == "desktop_input" and step_type == "hotkey":
        required = ("keys",)
    elif action == "desktop_input" and step_type in {"click", "double_click", "right_click", "scroll"}:
        if "target" not in step and not ("x" in step and "y" in step):
            issues.append(ValidationIssue(location, f"desktop_input.{step_type} 需要 target 或 x/y"))
        if step_type == "scroll" and "amount" not in step:
            issues.append(ValidationIssue(location, "desktop_input.scroll 需要 amount"))
    elif action == "desktop_input" and step_type == "drag":
        if "target" in step:
            if "delta_x" not in step and "delta_y" not in step:
                issues.append(ValidationIssue(location, "desktop_input.drag 使用 target 时需要 delta_x 或 delta_y"))
        elif not all(field in step for field in ("start_x", "start_y", "end_x", "end_y")):
            issues.append(
                ValidationIssue(location, "desktop_input.drag 需要 target+delta_x/delta_y 或 start_x/start_y/end_x/end_y")
            )
    elif action == "desktop_capture" and step_type == "screenshot":
        capture_target = step.get("target")
        if capture_target == "window":
            _validate_window_query(step, action, step_type, location, issues)
        elif capture_target == "element":
            _validate_window_query(step, action, step_type, location, issues)
            _validate_desktop_element_locator(step, action, step_type, location, issues)
        elif capture_target == "region" and "region" not in step:
            issues.append(ValidationIssue(location, "desktop_capture.screenshot target=region 缺少必填字段：region"))
    elif action == "desktop_vision" and step_type in {"locate_image", "locate_text"}:
        if step_type == "locate_image":
            required = ("template_path",)
        if step_type == "locate_text" and not any(step.get(field) for field in ("text", "text_contains", "text_regex")):
            issues.append(ValidationIssue(location, "desktop_vision.locate_text 需要 text、text_contains 或 text_regex 之一"))
        source_target = step.get("source_target")
        if source_target == "window":
            _validate_window_query(step, action, step_type, location, issues)
        elif source_target == "element":
            _validate_window_query(step, action, step_type, location, issues)
            _validate_desktop_element_locator(step, action, step_type, location, issues)
    elif action == "desktop_wait" and step_type == "window":
        _validate_window_query(step, action, step_type, location, issues)
    elif action == "desktop_assert" and step_type == "window":
        _validate_window_query(step, action, step_type, location, issues)
    elif action == "desktop_assert" and step_type == "screenshot":
        required = ("path",)
    elif action == "desktop_assert" and step_type == "element":
        _validate_window_query(step, action, step_type, location, issues)
        _validate_desktop_element_locator(step, action, step_type, location, issues)
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


def _validate_read_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "text":
        _validate_bool(step, "split_lines", location, issues)
        return
    if step_type != "excel":
        return
    _validate_sheet_field(step, "sheet", location, issues)
    _validate_list(step, "sheets", location, issues)
    _validate_a1_range(step, "range", location, issues)
    _validate_int(step, "header_row", location, issues, minimum=1)
    _validate_nonempty_string_list(step, "headers", location, issues)
    _validate_bool(step, "skip_blank_rows", location, issues)
    _validate_int(step, "max_rows", location, issues, minimum=1)
    _validate_int(step, "max_cells", location, issues, minimum=1)
    _validate_int(step, "preview_rows", location, issues, minimum=1)
    _validate_string(step, "save_meta_as", location, issues)
    _validate_enum(step, "mode", {"records", "matrix", "cells"}, location, issues)
    _validate_enum(step, "formula_mode", {"cached", "formula"}, location, issues)
    _validate_enum(step, "date_format", {"iso", "text"}, location, issues)
    sheets = step.get("sheets")
    if isinstance(sheets, list) and not _is_template(sheets):
        if not sheets:
            issues.append(ValidationIssue(location, "sheets 必须是非空数组"))
        for index, sheet in enumerate(sheets):
            _validate_excel_read_sheet(sheet, f"{location}.sheets[{index}]", issues)


def _validate_write_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "json":
        _validate_int(step, "indent", location, issues, minimum=0)
        return
    if step_type == "variables":
        _validate_int(step, "indent", location, issues, minimum=0)
        return
    if step_type == "text":
        _validate_bool(step, "append", location, issues)
        return
    if step_type == "csv":
        _validate_nonempty_string_list(step, "headers", location, issues)
        return
    if step_type != "excel":
        return
    _validate_sheet_field(step, "sheet", location, issues)
    _validate_a1_cell(step, "start_cell", location, issues)
    _validate_a1_write_range(step, "range", location, issues)
    _validate_string(step, "template_path", location, issues)
    _validate_string(step, "table_name", location, issues)
    _validate_nonempty_string_list(step, "headers", location, issues)
    _validate_dict(step, "formula_columns", location, issues)
    _validate_dict(step, "cells", location, issues)
    _validate_list(step, "sheets", location, issues)
    _validate_dict(step, "number_format", location, issues)
    _validate_dict(step, "column_widths", location, issues)
    _validate_bool(step, "include_header", location, issues)
    _validate_bool(step, "freeze_header", location, issues)
    _validate_bool(step, "auto_filter", location, issues)
    _validate_bool(step, "table", location, issues)
    _validate_enum(step, "write_mode", {"create", "replace_sheet", "append_rows", "overlay_cells"}, location, issues)
    _validate_string(step, "date_format", location, issues)
    _validate_excel_cells(step.get("cells"), location, "cells", issues)
    _validate_excel_formula_columns(step.get("formula_columns"), location, "formula_columns", issues)
    sheets = step.get("sheets")
    if isinstance(sheets, list) and not _is_template(sheets):
        if not sheets:
            issues.append(ValidationIssue(location, "sheets 必须是非空数组"))
        for index, sheet in enumerate(sheets):
            _validate_excel_write_sheet(sheet, f"{location}.sheets[{index}]", issues)


def _validate_excel_write_sheet(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "sheets 每一项必须是对象"))
        return
    _validate_sheet_field(value, "sheet", location, issues)
    _validate_a1_cell(value, "start_cell", location, issues)
    _validate_a1_write_range(value, "range", location, issues)
    _validate_nonempty_string_list(value, "headers", location, issues)
    _validate_dict(value, "formula_columns", location, issues)
    _validate_dict(value, "cells", location, issues)
    _validate_dict(value, "number_format", location, issues)
    _validate_dict(value, "column_widths", location, issues)
    _validate_bool(value, "include_header", location, issues)
    _validate_bool(value, "freeze_header", location, issues)
    _validate_bool(value, "auto_filter", location, issues)
    _validate_bool(value, "table", location, issues)
    _validate_string(value, "table_name", location, issues)
    _validate_enum(value, "write_mode", {"create", "replace_sheet", "append_rows", "overlay_cells"}, location, issues)
    _validate_excel_cells(value.get("cells"), location, "cells", issues)
    _validate_excel_formula_columns(value.get("formula_columns"), location, "formula_columns", issues)
    if not any(field in value for field in ("value", "rows", "cells")):
        issues.append(ValidationIssue(location, "sheets 每一项需要 value、rows 或 cells 之一"))


def _validate_excel_read_sheet(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, (str, int)):
        temp_step = {"sheet": value}
        _validate_sheet_field(temp_step, "sheet", location, issues)
        return
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "sheets 每一项必须是 sheet 名称、索引或读取配置对象"))
        return
    if "sheet" not in value:
        issues.append(ValidationIssue(location, "sheets 配置对象缺少必填字段：sheet"))
    _validate_string(value, "name", location, issues)
    _validate_sheet_field(value, "sheet", location, issues)
    _validate_a1_range(value, "range", location, issues)
    _validate_int(value, "header_row", location, issues, minimum=1)
    _validate_nonempty_string_list(value, "headers", location, issues)
    _validate_bool(value, "skip_blank_rows", location, issues)
    _validate_int(value, "max_rows", location, issues, minimum=1)
    _validate_int(value, "max_cells", location, issues, minimum=1)
    _validate_int(value, "preview_rows", location, issues, minimum=1)
    _validate_enum(value, "mode", {"records", "matrix", "cells"}, location, issues)
    _validate_enum(value, "formula_mode", {"cached", "formula"}, location, issues)
    _validate_enum(value, "date_format", {"iso", "text"}, location, issues)


def _validate_excel_cells(value: Any, location: str, field: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        return
    for address in value:
        if not isinstance(address, str) or not EXCEL_A1_RE.match(address):
            issues.append(ValidationIssue(location, f"{field} 的 key 必须是 A1 单元格地址：{address}"))


def _validate_excel_formula_columns(value: Any, location: str, field: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or value in (None, ""):
        return
    if not isinstance(value, dict):
        return
    if not value:
        issues.append(ValidationIssue(location, f"{field} 必须是非空对象"))
        return
    for column, spec in value.items():
        if not isinstance(column, str) or not column:
            issues.append(ValidationIssue(location, f"{field} 的列名必须是非空字符串"))
            continue
        if isinstance(spec, str) and spec:
            continue
        if isinstance(spec, dict) and isinstance(spec.get("formula"), str) and spec["formula"]:
            continue
        issues.append(ValidationIssue(location, f"{field}.{column} 必须是公式字符串或包含 formula 的对象"))


def _validate_table_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_string(step, "save_as", location, issues)
    if step_type == "filter":
        _validate_dict(step, "where", location, issues)
        where = step.get("where")
        if isinstance(where, dict):
            for field, condition in where.items():
                if not isinstance(field, str) or not field:
                    issues.append(ValidationIssue(location, "table.filter.where 的字段名必须是非空字符串"))
                if isinstance(condition, dict):
                    for operator in condition:
                        if operator not in TABLE_FILTER_OPERATORS:
                            allowed = ", ".join(sorted(TABLE_FILTER_OPERATORS))
                            issues.append(ValidationIssue(location, f"table.filter 操作符不支持：{operator}；可选值：{allowed}"))
        return
    if step_type == "select":
        _validate_nonempty_string_list(step, "columns", location, issues)
        _validate_dict(step, "rename", location, issues)
        rename = step.get("rename")
        if isinstance(rename, dict):
            for key, value in rename.items():
                if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
                    issues.append(ValidationIssue(location, "table.select.rename 必须是源列名到目标列名的非空字符串对象"))
        return
    if step_type in {"sort", "dedupe"}:
        _validate_string_or_nonempty_string_list(step, "by", location, issues)
    if step_type == "sort":
        value = step.get("descending")
        if value is not None and not _is_template(value):
            if isinstance(value, bool):
                return
            if isinstance(value, list) and all(isinstance(item, bool) for item in value):
                by = step.get("by")
                if isinstance(by, list) and len(value) != len(by):
                    issues.append(ValidationIssue(location, "table.sort.descending 数组长度必须与 by 一致"))
                return
            issues.append(ValidationIssue(location, "table.sort.descending 必须是布尔值或布尔数组"))
        return
    if step_type == "dedupe":
        _validate_enum(step, "keep", {"first", "last"}, location, issues)
        return
    if step_type == "group":
        _validate_string_or_nonempty_string_list(step, "by", location, issues)
        _validate_dict(step, "aggregations", location, issues)
        aggregations = step.get("aggregations")
        if isinstance(aggregations, dict):
            if not aggregations:
                issues.append(ValidationIssue(location, "table.group.aggregations 必须是非空对象"))
            for output_column, spec in aggregations.items():
                if not isinstance(output_column, str) or not output_column:
                    issues.append(ValidationIssue(location, "table.group.aggregations 的输出列名必须是非空字符串"))
                _validate_table_aggregation_spec(spec, location, issues)
        return
    if step_type == "join":
        _validate_list(step, "right", location, issues)
        _validate_string_or_nonempty_string_list(step, "on", location, issues)
        _validate_string_or_nonempty_string_list(step, "left_on", location, issues)
        _validate_string_or_nonempty_string_list(step, "right_on", location, issues)
        _validate_enum(step, "how", {"inner", "left"}, location, issues)
        _validate_string(step, "right_prefix", location, issues)
        if "on" not in step and not ("left_on" in step and "right_on" in step):
            issues.append(ValidationIssue(location, "table.join 需要 on，或同时提供 left_on 和 right_on"))
        if "on" in step and ("left_on" in step or "right_on" in step):
            issues.append(ValidationIssue(location, "table.join 不能同时使用 on 和 left_on/right_on"))
        left_on = step.get("left_on")
        right_on = step.get("right_on")
        if isinstance(left_on, list) and isinstance(right_on, list) and len(left_on) != len(right_on):
            issues.append(ValidationIssue(location, "table.join.left_on 和 right_on 长度必须一致"))
        return
    if step_type == "add_column":
        _validate_dict(step, "columns", location, issues)
        columns = step.get("columns")
        if isinstance(columns, dict):
            if not columns:
                issues.append(ValidationIssue(location, "table.add_column.columns 必须是非空对象"))
            for output_column, spec in columns.items():
                if not isinstance(output_column, str) or not output_column:
                    issues.append(ValidationIssue(location, "table.add_column.columns 的列名必须是非空字符串"))
                _validate_table_add_column_spec(spec, location, issues)
        return
    if step_type == "rename":
        _validate_dict(step, "columns", location, issues)
        _validate_string_mapping(step.get("columns"), location, "table.rename.columns", issues)
        return
    if step_type == "fill_empty":
        _validate_dict(step, "values", location, issues)
        values = step.get("values")
        if isinstance(values, dict):
            if not values:
                issues.append(ValidationIssue(location, "table.fill_empty.values 必须是非空对象"))
            for column in values:
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.fill_empty.values 的列名必须是非空字符串"))
        return
    if step_type == "type_convert":
        _validate_dict(step, "columns", location, issues)
        columns = step.get("columns")
        if isinstance(columns, dict):
            if not columns:
                issues.append(ValidationIssue(location, "table.type_convert.columns 必须是非空对象"))
            for column, target_type in columns.items():
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.type_convert.columns 的列名必须是非空字符串"))
                if not isinstance(target_type, str) or target_type not in TABLE_TYPE_CONVERT_TYPES:
                    allowed = ", ".join(sorted(TABLE_TYPE_CONVERT_TYPES))
                    issues.append(ValidationIssue(location, f"table.type_convert 目标类型不支持：{target_type}；可选值：{allowed}"))
        return
    if step_type == "pivot":
        _validate_string_or_nonempty_string_list(step, "index", location, issues)
        _validate_string(step, "columns", location, issues)
        _validate_string(step, "values", location, issues)
        _validate_enum(step, "agg", TABLE_AGGREGATION_OPERATORS, location, issues)
        agg = step.get("agg", "sum" if step.get("values") else "count")
        if agg != "count" and not step.get("values"):
            issues.append(ValidationIssue(location, "table.pivot 使用 sum、avg、min 或 max 时必须提供 values"))
        return
    if step_type == "replace":
        _validate_dict(step, "columns", location, issues)
        _validate_dict(step, "values", location, issues)
        columns = step.get("columns")
        values = step.get("values")
        if not columns and not values:
            issues.append(ValidationIssue(location, "table.replace 需要 columns 或 values 至少一个非空对象"))
        if isinstance(columns, dict):
            for column, replacements in columns.items():
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.replace.columns 的列名必须是非空字符串"))
                if not isinstance(replacements, dict) or not replacements:
                    issues.append(ValidationIssue(location, "table.replace.columns 每列替换规则必须是非空对象"))
        return
    if step_type == "split_column":
        _validate_string(step, "column", location, issues)
        _validate_string_or_nonempty_string_list(step, "into", location, issues)
        _validate_string(step, "separator", location, issues)
        _validate_bool(step, "regex", location, issues)
        _validate_int(step, "maxsplit", location, issues, minimum=0)
        _validate_bool(step, "remove_source", location, issues)
        return
    if step_type == "merge_columns":
        _validate_string_or_nonempty_string_list(step, "columns", location, issues)
        _validate_string(step, "into", location, issues)
        if "separator" in step and not _is_template(step["separator"]) and not isinstance(step["separator"], str):
            issues.append(ValidationIssue(location, "table.merge_columns.separator 必须是字符串"))
        _validate_bool(step, "skip_empty", location, issues)
        _validate_bool(step, "remove_sources", location, issues)
        return
    if step_type == "date_parse":
        _validate_table_date_parse_columns(step.get("columns"), location, issues)
        _validate_string(step, "output_format", location, issues)
        return
    if step_type == "lookup":
        _validate_list(step, "right", location, issues)
        _validate_string_or_nonempty_string_list(step, "on", location, issues)
        _validate_string_or_nonempty_string_list(step, "left_on", location, issues)
        _validate_string_or_nonempty_string_list(step, "right_on", location, issues)
        _validate_table_lookup_values(step.get("values"), location, issues)
        if "on" not in step and not ("left_on" in step and "right_on" in step):
            issues.append(ValidationIssue(location, "table.lookup 需要 on，或同时提供 left_on 和 right_on"))
        if "on" in step and ("left_on" in step or "right_on" in step):
            issues.append(ValidationIssue(location, "table.lookup 不能同时使用 on 和 left_on/right_on"))
        left_on = step.get("left_on")
        right_on = step.get("right_on")
        if isinstance(left_on, list) and isinstance(right_on, list) and len(left_on) != len(right_on):
            issues.append(ValidationIssue(location, "table.lookup.left_on 和 right_on 长度必须一致"))


def _validate_table_aggregation_spec(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value):
        return
    if not isinstance(value, dict) or len(value) != 1:
        issues.append(ValidationIssue(location, "table.group.aggregations 每个值必须是只包含一个操作符的对象"))
        return
    operator, source_column = next(iter(value.items()))
    if operator not in TABLE_AGGREGATION_OPERATORS:
        allowed = ", ".join(sorted(TABLE_AGGREGATION_OPERATORS))
        issues.append(ValidationIssue(location, f"table.group 聚合操作符不支持：{operator}；可选值：{allowed}"))
    if source_column == "*" and operator == "count":
        return
    if not isinstance(source_column, str) or not source_column:
        issues.append(ValidationIssue(location, "table.group 聚合源列必须是非空字符串，count 可使用 *"))


def _validate_table_date_parse_columns(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value):
        return
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return
    if isinstance(value, dict) and value:
        for column, formats in value.items():
            if not isinstance(column, str) or not column:
                issues.append(ValidationIssue(location, "table.date_parse.columns 的列名必须是非空字符串"))
            if isinstance(formats, str) and formats:
                continue
            if isinstance(formats, list) and all(isinstance(item, str) and item for item in formats):
                continue
            if formats in (None, ""):
                continue
            issues.append(ValidationIssue(location, "table.date_parse.columns 的格式必须是字符串或字符串数组"))
        return
    issues.append(ValidationIssue(location, "table.date_parse.columns 必须是非空字符串、字符串数组或对象"))


def _validate_table_lookup_values(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or value in (None, ""):
        return
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return
    if isinstance(value, dict) and value:
        _validate_string_mapping(value, location, "table.lookup.values", issues)
        return
    issues.append(ValidationIssue(location, "table.lookup.values 必须是非空字符串、字符串数组或对象"))


def _validate_string_mapping(value: Any, location: str, field_name: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        return
    if not value:
        issues.append(ValidationIssue(location, f"{field_name} 必须是非空对象"))
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
            issues.append(ValidationIssue(location, f"{field_name} 必须是非空字符串到非空字符串的对象"))


def _validate_table_add_column_spec(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or not isinstance(value, dict):
        return
    operators = [operator for operator in TABLE_ADD_COLUMN_OPERATORS if operator in value]
    if len(operators) != 1:
        allowed = ", ".join(sorted(TABLE_ADD_COLUMN_OPERATORS))
        issues.append(ValidationIssue(location, f"table.add_column.columns 每个对象必须且只能包含一个操作符：{allowed}"))
        return
    operator = operators[0]
    if operator in {"copy", "format"} and (not isinstance(value[operator], str) or not value[operator]):
        issues.append(ValidationIssue(location, f"table.add_column.{operator} 必须是非空字符串"))
    if operator == "sum":
        temp_step = {"sum": value[operator]}
        _validate_string_or_nonempty_string_list(temp_step, "sum", location, issues)


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


def _validate_sql_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_connection_reference(step, "connection", location, issues, SQL_CONNECTION_TYPES)
    _validate_connection_reference(step, "target_connection", location, issues, SQL_CONNECTION_TYPES)
    _validate_string(step, "sql", location, issues)
    _validate_string(step, "schema", location, issues)
    _validate_string(step, "source_path", location, issues)
    _validate_string(step, "target_path", location, issues)
    _validate_string(step, "record_path", location, issues)
    _validate_sheet_field(step, "sheet", location, issues)
    if "params" in step and not _is_template(step["params"]) and not isinstance(step["params"], (dict, list)):
        issues.append(ValidationIssue(location, "params 必须是对象或数组"))
    _validate_list(step, "params_list", location, issues)
    _validate_string(step, "table", location, issues)
    _validate_list(step, "rows", location, issues)
    _validate_list(step, "columns", location, issues)
    _validate_list(step, "conflict_keys", location, issues)
    _validate_list(step, "update_columns", location, issues)
    _validate_list(step, "steps", location, issues)
    _validate_dict(step, "column_map", location, issues)
    _validate_string(step, "save_as", location, issues)
    _validate_string(step, "rows_path", location, issues)
    _validate_string(step, "result_path", location, issues)
    _validate_bool(step, "include_rows", location, issues)
    _validate_bool(step, "include_columns", location, issues)
    _validate_bool(step, "include_indexes", location, issues)
    _validate_bool(step, "commit", location, issues)
    _validate_bool(step, "stream", location, issues)
    _validate_bool(step, "create_table", location, issues)
    _validate_int(step, "max_rows", location, issues, minimum=1)
    _validate_int(step, "limit", location, issues, minimum=1)
    _validate_int(step, "offset", location, issues, minimum=0)
    _validate_int(step, "page_size", location, issues, minimum=1)
    _validate_int(step, "page", location, issues, minimum=1)
    _validate_int(step, "batch_size", location, issues, minimum=1)
    _validate_int(step, "fetch_size", location, issues, minimum=1)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_enum(step, "row_mode", SQL_ROW_MODES, location, issues)
    _validate_enum(step, "mode", SQL_BULK_MODES, location, issues)
    _validate_enum(step, "source_type", SQL_FILE_TABLE_TYPES, location, issues)
    _validate_enum(step, "target_type", SQL_FILE_TABLE_TYPES, location, issues)
    if step_type in {"query", "scalar", "copy", "export"}:
        if "limit" in step and "page_size" in step:
            issues.append(ValidationIssue(location, f"sql.{step_type} 不能同时使用 limit 和 page_size"))
        if "page" in step and "page_size" not in step:
            issues.append(ValidationIssue(location, f"sql.{step_type}.page 需要和 page_size 一起使用"))
    if "expect_affected_rows" in step and not _is_template(step["expect_affected_rows"]):
        expected = step["expect_affected_rows"]
        if isinstance(expected, int):
            pass
        elif isinstance(expected, list) and all(isinstance(item, int) for item in expected):
            pass
        else:
            issues.append(ValidationIssue(location, "expect_affected_rows 必须是整数或整数数组"))
    if step_type in {"bulk_insert", "copy", "import"} and step.get("mode") == "upsert" and "conflict_keys" not in step:
        issues.append(ValidationIssue(location, f"sql.{step_type} mode=upsert 需要 conflict_keys"))
    if step_type in {"import", "export"} and step.get("stream") is True:
        issues.append(ValidationIssue(location, f"sql.{step_type} 暂不支持 stream=true"))
    if step_type == "copy" and step.get("stream") is True:
        if step.get("include_rows") is True:
            issues.append(ValidationIssue(location, "sql.copy stream=true 不支持 include_rows；请使用 rows_path=.jsonl 分批落盘"))
        rows_path = step.get("rows_path")
        if isinstance(rows_path, str) and rows_path and not rows_path.lower().endswith(".jsonl"):
            issues.append(ValidationIssue(location, "sql.copy stream=true 的 rows_path 只支持 .jsonl"))
    if step_type == "transaction":
        if "rows_path" in step:
            issues.append(ValidationIssue(location, "sql.transaction 不支持 rows_path；请使用 result_path 保存事务摘要"))
        if "commit" in step:
            issues.append(ValidationIssue(location, "sql.transaction 不支持 commit 字段；成功自动提交，失败自动回滚"))
        _validate_sql_transaction_steps(step, location, issues)
    for field in ("columns", "conflict_keys", "update_columns"):
        value = step.get(field)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if not isinstance(item, str) or not item:
                    issues.append(ValidationIssue(f"{location}.{field}[{index}]", f"{field} 每一项必须是非空字符串"))
    column_map = step.get("column_map")
    if isinstance(column_map, dict):
        for key, value in column_map.items():
            if not isinstance(key, str) or not key:
                issues.append(ValidationIssue(location, "column_map 的目标列名必须是非空字符串"))
            if not isinstance(value, str) or not value:
                issues.append(ValidationIssue(location, "column_map 的源列名必须是非空字符串"))


def _validate_sql_transaction_steps(
    step: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    steps = step.get("steps")
    if not isinstance(steps, list):
        return
    if not steps:
        issues.append(ValidationIssue(location, "sql.transaction.steps 必须是非空数组"))
        return
    for index, item in enumerate(steps):
        item_location = f"{location}.steps[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue(item_location, "sql.transaction.steps 每一项必须是对象"))
            continue
        forbidden = [field for field in ("action", "connection", "commit", "save_as", "rows_path", "result_path") if field in item]
        if forbidden:
            issues.append(
                ValidationIssue(
                    item_location,
                    "sql.transaction 子步骤不支持 action、connection、commit、save_as、rows_path 或 result_path；"
                    f"当前包含：{', '.join(forbidden)}",
                )
            )
        child_type = item.get("type")
        if not isinstance(child_type, str) or not child_type:
            issues.append(ValidationIssue(item_location, "sql.transaction 子步骤 type 必须是非空字符串"))
            continue
        if child_type not in SQL_TRANSACTION_STEP_TYPES:
            allowed = ", ".join(sorted(SQL_TRANSACTION_STEP_TYPES))
            issues.append(ValidationIssue(item_location, f"sql.transaction 子步骤 type 不支持：{child_type}；可选值：{allowed}"))
            continue
        if child_type in {"query", "scalar", "execute"} and "sql" not in item:
            issues.append(ValidationIssue(item_location, f"sql.transaction {child_type} 缺少必填字段：sql"))
        elif child_type == "executemany":
            for field in ("sql", "params_list"):
                if field not in item:
                    issues.append(ValidationIssue(item_location, f"sql.transaction executemany 缺少必填字段：{field}"))
        elif child_type == "bulk_insert":
            for field in ("table", "rows"):
                if field not in item:
                    issues.append(ValidationIssue(item_location, f"sql.transaction bulk_insert 缺少必填字段：{field}"))
        _validate_sql_fields(item, child_type, item_location, issues)


def _validate_mongo_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_connection_reference(step, "connection", location, issues, MONGO_CONNECTION_TYPES)
    _validate_string(step, "database", location, issues)
    _validate_string(step, "collection", location, issues)
    _validate_string(step, "name", location, issues)
    _validate_string(step, "index", location, issues)
    _validate_string(step, "save_as", location, issues)
    _validate_string(step, "result_path", location, issues)
    _validate_dict(step, "filter", location, issues)
    _validate_dict(step, "document", location, issues)
    _validate_dict(step, "update", location, issues)
    _validate_dict(step, "partial_filter_expression", location, issues)
    _validate_dict(step, "partialFilterExpression", location, issues)
    _validate_dict(step, "collation", location, issues)
    _validate_dict(step, "weights", location, issues)
    _validate_list(step, "documents", location, issues)
    _validate_list(step, "pipeline", location, issues)
    _validate_list(step, "args", location, issues)
    _validate_bool(step, "upsert", location, issues)
    _validate_bool(step, "ordered", location, issues)
    _validate_bool(step, "unique", location, issues)
    _validate_bool(step, "sparse", location, issues)
    _validate_bool(step, "background", location, issues)
    _validate_int(step, "limit", location, issues, minimum=1)
    _validate_int(step, "max_docs", location, issues, minimum=1)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "expire_after_seconds", location, issues, minimum=0)
    _validate_int(step, "expireAfterSeconds", location, issues, minimum=0)
    if "command" in step and not _is_template(step["command"]) and not isinstance(step["command"], (str, dict)):
        issues.append(ValidationIssue(location, "command 必须是字符串或对象"))
    if "projection" in step and not _is_template(step["projection"]) and not isinstance(step["projection"], (dict, list)):
        issues.append(ValidationIssue(location, "projection 必须是对象或数组"))
    if "sort" in step and not _is_template(step["sort"]) and not isinstance(step["sort"], (dict, list)):
        issues.append(ValidationIssue(location, "sort 必须是对象或数组"))
    if "keys" in step and not _is_template(step["keys"]) and not isinstance(step["keys"], (str, dict, list)):
        issues.append(ValidationIssue(location, "keys 必须是字段名、对象或数组"))
    if step_type == "insert_many" and isinstance(step.get("documents"), list) and not step["documents"]:
        issues.append(ValidationIssue(location, "mongo.insert_many.documents 必须是非空数组"))
    if step_type == "aggregate" and isinstance(step.get("pipeline"), list) and not step["pipeline"]:
        issues.append(ValidationIssue(location, "mongo.aggregate.pipeline 必须是非空数组"))
    if step_type == "create_index":
        _validate_mongo_index_keys(step.get("keys"), f"{location}.keys", issues)
    if step_type == "drop_index" and "name" not in step and "index" not in step:
        issues.append(ValidationIssue(location, "mongo.drop_index 需要 name 或 index"))


def _validate_mongo_index_keys(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if value is None or _is_template(value):
        return
    if isinstance(value, str):
        if not value:
            issues.append(ValidationIssue(location, "keys 字段名不能为空"))
        return
    if isinstance(value, dict):
        if not value:
            issues.append(ValidationIssue(location, "keys 对象不能为空"))
            return
        for key, direction in value.items():
            if not isinstance(key, str) or not key:
                issues.append(ValidationIssue(location, "keys 对象的字段名必须是非空字符串"))
            _validate_mongo_index_direction(direction, location, issues)
        return
    if isinstance(value, list):
        if not value:
            issues.append(ValidationIssue(location, "keys 数组不能为空"))
            return
        for index, item in enumerate(value):
            item_location = f"{location}[{index}]"
            if isinstance(item, str):
                if not item:
                    issues.append(ValidationIssue(item_location, "keys 字段名不能为空"))
                continue
            if isinstance(item, dict):
                field = item.get("field") or item.get("key") or item.get("name")
                if not isinstance(field, str) or not field:
                    issues.append(ValidationIssue(item_location, "keys 项需要非空 field/key/name"))
                _validate_mongo_index_direction(item.get("direction", item.get("order", 1)), item_location, issues)
                continue
            if isinstance(item, list) and len(item) == 2:
                if not isinstance(item[0], str) or not item[0]:
                    issues.append(ValidationIssue(item_location, "keys 二元组第一项必须是非空字段名"))
                _validate_mongo_index_direction(item[1], item_location, issues)
                continue
            issues.append(ValidationIssue(item_location, "keys 项必须是字段名、{field, direction} 或 [field, direction]"))
        return
    issues.append(ValidationIssue(location, "keys 必须是字段名、对象或数组"))


def _validate_mongo_index_direction(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if value in {-1, 1}:
            return
    if isinstance(value, str) and value.lower() in {"asc", "ascending", "desc", "descending", "text", "hashed", "2d", "2dsphere"}:
        return
    issues.append(ValidationIssue(location, "索引 direction 只支持 1、-1、asc、desc、text、hashed、2d 或 2dsphere"))


def _validate_redis_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_connection_reference(step, "connection", location, issues, {"redis"})
    _validate_string(step, "key", location, issues)
    _validate_string(step, "field", location, issues)
    _validate_string(step, "command", location, issues)
    _validate_string(step, "save_as", location, issues)
    _validate_string(step, "result_path", location, issues)
    _validate_dict(step, "mapping", location, issues)
    _validate_list(step, "keys", location, issues)
    _validate_list(step, "values", location, issues)
    _validate_list(step, "members", location, issues)
    _validate_list(step, "args", location, issues)
    _validate_list(step, "commands", location, issues)
    _validate_int(step, "ttl_seconds", location, issues, minimum=1)
    _validate_int(step, "seconds", location, issues, minimum=1)
    _validate_int(step, "start", location, issues)
    _validate_int(step, "stop", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "batch_size", location, issues, minimum=1)
    if step_type == "pipeline" and isinstance(step.get("commands"), list):
        for index, item in enumerate(step["commands"]):
            item_location = f"{location}.commands[{index}]"
            if not isinstance(item, dict):
                issues.append(ValidationIssue(item_location, "commands 每一项必须是对象"))
                continue
            _validate_string(item, "command", item_location, issues)
            _validate_list(item, "args", item_location, issues)


def _validate_connection_reference(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
    allowed_types: set[str],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str):
        if not value:
            issues.append(ValidationIssue(location, f"{field} 必须是非空字符串或连接对象"))
        return
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, f"{field} 必须是连接名字符串或连接对象"))
        return
    raw_type = value.get("type") or value.get("driver")
    if raw_type is not None and not _is_template(raw_type):
        if not isinstance(raw_type, str) or raw_type.lower() not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            issues.append(ValidationIssue(location, f"{field}.type 不支持：{raw_type}；可选值：{allowed}"))
    for item_field in (
        "type",
        "driver",
        "dsn",
        "uri",
        "url",
        "path",
        "database",
        "host",
        "server",
        "username",
        "user",
        "password",
        "connection_string",
        "odbc_connect",
        "odbc_driver",
        "driver_name",
        "odbc_driver_name",
        "service_name",
        "sid",
        "auth_source",
        "authSource",
    ):
        if item_field in value and not _is_template(value[item_field]) and not isinstance(value[item_field], str):
            issues.append(ValidationIssue(location, f"{field}.{item_field} 必须是字符串"))
    for item_field in ("port", "db"):
        if item_field in value and not _is_template(value[item_field]) and not isinstance(value[item_field], int):
            issues.append(ValidationIssue(location, f"{field}.{item_field} 必须是整数"))
    _validate_bool(value, "decode_responses", location, issues)
    _validate_bool(value, "read_only", location, issues)
    _validate_bool(value, "autocommit", location, issues)
    _validate_bool(value, "trusted_connection", location, issues)
    _validate_bool(value, "trust_server_certificate", location, issues)


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
    _validate_string(step, "save_as", location, issues)


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
    _validate_string(step, "save_as", location, issues)
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
    _validate_string(step, "save_as", location, issues)
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
    _validate_string(step, "save_as", location, issues)
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
    _validate_string(step, "save_as", location, issues)
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
    _validate_string(step, "save_as", location, issues)
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
        _validate_string(step, "save_as", location, issues)


def _validate_desktop_assert_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    _validate_string(step, "save_as", location, issues)
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


def _validate_nonempty_string_list(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if not isinstance(value, list) or not value:
        issues.append(ValidationIssue(location, f"{field} 必须是非空字符串数组"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            issues.append(ValidationIssue(f"{location}.{field}[{index}]", f"{field} 每一项必须是非空字符串"))


def _validate_string_or_nonempty_string_list(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return
    issues.append(ValidationIssue(location, f"{field} 必须是非空字符串或非空字符串数组"))


def _validate_sheet_field(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str) and value:
        return
    if isinstance(value, int) and value >= 0:
        return
    issues.append(ValidationIssue(location, f"{field} 必须是非空字符串或非负整数"))


def _validate_a1_range(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str) and EXCEL_A1_RE.match(value):
        return
    issues.append(ValidationIssue(location, f"{field} 必须是 A1 风格单元格或范围，例如 A1 或 A1:D20"))


def _validate_a1_cell(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str) and ":" not in value and EXCEL_A1_RE.match(value):
        return
    issues.append(ValidationIssue(location, f"{field} 必须是 A1 风格单元格地址，例如 B3"))


def _validate_a1_write_range(
    step: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if field not in step or _is_template(step[field]):
        return
    value = step[field]
    if isinstance(value, str) and ":" in value and EXCEL_A1_RE.match(value):
        return
    issues.append(ValidationIssue(location, f"{field} 必须是 A1 风格范围，例如 B3:H20"))


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
