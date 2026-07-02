from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ai_automate_contro.plans.validation_field_helpers import (
    HTTP_BODY_FIELDS,
    HTTP_METHODS,
    MONGO_CONNECTION_TYPES,
    REDIS_VALUE_TYPES,
    SQL_BULK_MODES,
    SQL_CONNECTION_TYPES,
    SQL_FILE_TABLE_TYPES,
    SQL_ROW_MODES,
    SQL_TRANSACTION_STEP_TYPES,
    _is_template,
    _validate_bool,
    _validate_dict,
    _validate_enum,
    _validate_int,
    _validate_list,
    _validate_nonempty_string_list,
    _validate_sheet_field,
    _validate_string,
)
from ai_automate_contro.plans.validation_models import ValidationIssue


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
    _validate_list(step, "required_columns", location, issues)
    _validate_list(step, "unique_columns", location, issues)
    _validate_list(step, "steps", location, issues)
    _validate_dict(step, "column_map", location, issues)
    _validate_dict(step, "column_types", location, issues)
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
    if step_type == "import" and step.get("stream") is True:
        _validate_sql_stream_file_type(step, "source_type", "source_path", {"csv", "jsonl"}, location, issues)
    if step_type == "export" and step.get("stream") is True:
        _validate_sql_stream_file_type(step, "target_type", "target_path", {"csv", "jsonl"}, location, issues)
        if step.get("include_rows") is True:
            issues.append(ValidationIssue(location, "sql.export stream=true 不支持 include_rows"))
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
    for field in ("columns", "conflict_keys", "update_columns", "required_columns", "unique_columns"):
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
    column_types = step.get("column_types")
    if isinstance(column_types, dict):
        for key, value in column_types.items():
            if not isinstance(key, str) or not key:
                issues.append(ValidationIssue(location, "column_types 的列名必须是非空字符串"))
            if not isinstance(value, str) or not value.strip():
                issues.append(ValidationIssue(location, "column_types 的 SQL 类型必须是非空字符串"))
            elif any(token in value for token in (";", "--", "/*", "*/", "\x00")):
                issues.append(ValidationIssue(location, "column_types 的 SQL 类型不能包含 ;、注释或空字符"))


def _validate_sql_stream_file_type(
    step: dict[str, Any],
    type_field: str,
    path_field: str,
    allowed: set[str],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    raw_type = step.get(type_field)
    if isinstance(raw_type, str) and raw_type:
        normalized = {"xlsx": "excel", "xlsm": "excel"}.get(raw_type, raw_type)
        if normalized not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            issues.append(ValidationIssue(location, f"sql.{step.get('type')} stream=true 只支持 {allowed_text}"))
        return
    raw_path = step.get(path_field)
    if not isinstance(raw_path, str) or not raw_path or _is_template(raw_path):
        return
    suffix = raw_path.rsplit(".", 1)[-1].lower() if "." in raw_path else ""
    if suffix and suffix not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        issues.append(ValidationIssue(location, f"sql.{step.get('type')} stream=true 只支持 {allowed_text} 文件后缀"))


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
        forbidden = [
            field
            for field in ("action", "connection", "commit", "save_as", "output", "rows_path", "result_path")
            if field in item
        ]
        if forbidden:
            issues.append(
                ValidationIssue(
                    item_location,
                    "sql.transaction 子步骤不支持 action、connection、commit、save_as、output、rows_path 或 result_path；"
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
    _validate_string(step, "encoding", location, issues)
    _validate_dict(step, "env", location, issues)
    _validate_int(step, "timeout_ms", location, issues, minimum=1)
    _validate_int(step, "max_output_bytes", location, issues, minimum=1)
    _validate_enum(step, "stdout_type", {"text", "json"}, location, issues)
    _validate_enum(step, "shell", {"auto", "pwsh", "powershell", "cmd", "sh", "bash"}, location, issues)
