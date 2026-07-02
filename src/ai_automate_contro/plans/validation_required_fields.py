from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_browser_fields import _validate_frame_fields, _validate_locator_fields
from ai_automate_contro.plans.validation_desktop_fields import _validate_desktop_element_locator, _validate_window_query
from ai_automate_contro.plans.validation_field_helpers import REDIS_VALUE_TYPES
from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_optional_fields import validate_optional_field_values


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
        required = ("output",)
    elif action == "storage" and step_type in {"local_storage", "session_storage"}:
        required = ("key", "output")
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
        elif step_type == "fuzzy_lookup":
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

    validate_optional_field_values(step, action, step_type, location, issues)

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


