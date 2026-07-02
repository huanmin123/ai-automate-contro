from __future__ import annotations

import re
from typing import Any

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
