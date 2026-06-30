from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text

from . import files

SQL_ACTION_TYPES = {"query", "scalar", "execute", "executemany", "bulk_insert", "copy", "transaction", "inspect", "import", "export"}
DEFAULT_MAX_ROWS = 1000
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def run(executor: Any, step: dict[str, Any]) -> None:
    step_type = str(step["type"])
    if step_type not in SQL_ACTION_TYPES:
        raise ValueError(f"sql.type 不支持：{step_type}")
    if step_type == "query":
        _run_query(executor, step, scalar=False)
        return
    if step_type == "scalar":
        _run_query(executor, step, scalar=True)
        return
    if step_type == "execute":
        _run_execute(executor, step)
        return
    if step_type == "executemany":
        _run_executemany(executor, step)
        return
    if step_type == "bulk_insert":
        _run_bulk_insert(executor, step)
        return
    if step_type == "import":
        _run_import(executor, step)
        return
    if step_type == "export":
        _run_export(executor, step)
        return
    if step_type == "copy":
        _run_copy(executor, step)
        return
    if step_type == "transaction":
        _run_transaction(executor, step)
        return
    if step_type == "inspect":
        _run_inspect(executor, step)
        return


def _run_query(executor: Any, step: dict[str, Any], *, scalar: bool) -> None:
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    pagination = _query_pagination(step, max_rows, action_label="sql.query")
    row_mode = str(step.get("row_mode", "dict")).lower()
    if row_mode not in {"dict", "list"}:
        raise ValueError("sql.row_mode 只支持 dict 或 list。")

    with _open_connection(executor, config, step) as opened:
        sql, params = _prepare_sql(str(step["sql"]), step.get("params"), opened.database_type)
        sql = _apply_query_pagination(sql, opened.database_type, pagination)
        cursor = opened.connection.cursor()
        try:
            _execute(cursor, sql, params)
            columns = [str(item[0]) for item in (cursor.description or [])]
            rows = _fetch_rows(cursor, columns, row_mode=row_mode, max_rows=max_rows)
        finally:
            _close_cursor(cursor)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    value = rows[0][0] if scalar and rows and isinstance(rows[0], list) else None
    if scalar and rows and isinstance(rows[0], dict):
        value = next(iter(rows[0].values()), None)
    payload: dict[str, Any] = {
        "type": "scalar" if scalar else "query",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "columns": columns,
        "row_count": len(rows),
        "first_row": rows[0] if rows else None,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(_query_pagination_payload(pagination))
    if scalar:
        payload["value"] = _json_safe(value)
    if bool(step.get("include_rows", "rows_path" not in step)):
        payload["rows"] = _json_safe(rows)
    _write_optional_rows(executor, step, rows)
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql query finished",
        type=payload["type"],
        connection=opened.connection_name,
        database_type=opened.database_type,
        row_count=payload["row_count"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_execute(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    commit = bool(step.get("commit", True))
    with _open_connection(executor, config, step) as opened:
        affected_rows, lastrowid = _execute_operation(opened, step, commit=commit)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "type": "execute",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "affected_rows": affected_rows,
        "lastrowid": lastrowid,
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql execute finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        affected_rows=affected_rows,
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_executemany(executor: Any, step: dict[str, Any]) -> None:
    params_list = step.get("params_list")
    if not isinstance(params_list, list):
        raise ValueError("sql.executemany.params_list 必须是数组。")
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    commit = bool(step.get("commit", True))
    with _open_connection(executor, config, step) as opened:
        affected_rows = _executemany_operation(opened, step, commit=commit)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "type": "executemany",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "affected_rows": affected_rows,
        "batch_count": len(params_list),
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql executemany finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        affected_rows=affected_rows,
        batch_count=len(params_list),
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_bulk_insert(executor: Any, step: dict[str, Any]) -> None:
    rows = step.get("rows")
    if not isinstance(rows, list):
        raise ValueError("sql.bulk_insert.rows 必须是数组。")
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    commit = bool(step.get("commit", True))
    with _open_connection(executor, config, step) as opened:
        payload = _bulk_insert_operation(opened, step, commit=commit)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload["elapsed_ms"] = elapsed_ms
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql bulk insert finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        table=payload["table"],
        mode=payload["mode"],
        input_rows=payload["input_rows"],
        affected_rows=payload["affected_rows"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_import(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    source_path = _resolve_input_path(executor, str(step["source_path"]))
    source_type = _file_table_type(step.get("source_type"), source_path, field_name="source_type")
    source_rows = _read_table_rows(executor, step, source_path=source_path, source_type=source_type)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS * 100)))
    if len(source_rows) > max_rows:
        raise ValueError(f"sql.import 源数据超过 max_rows={max_rows}；请清洗输入、分批导入或提高 max_rows。")
    source_columns = _rows_columns(source_rows)
    target_rows, target_columns, column_map = _copy_target_rows(step, source_rows, source_columns)
    config = _connection_config(executor, step)
    commit = bool(step.get("commit", True))
    with _open_connection(executor, config, step) as opened:
        if bool(step.get("create_table", False)):
            _create_import_table(opened, step, target_rows, target_columns, commit=commit)
        bulk_step = _copy_bulk_step(step, target_rows, target_columns)
        payload = _bulk_insert_operation(opened, bulk_step, commit=commit)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload.update(
        {
            "type": "import",
            "connection": opened.connection_name,
            "database_type": opened.database_type,
            "source_path": str(source_path),
            "source_type": source_type,
            "source_columns": source_columns,
            "column_map": column_map,
            "create_table": bool(step.get("create_table", False)),
            "elapsed_ms": elapsed_ms,
        }
    )
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql import finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        source_type=source_type,
        table=payload["table"],
        input_rows=payload["input_rows"],
        affected_rows=payload["affected_rows"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_export(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    pagination = _query_pagination(step, max_rows, action_label="sql.export")
    target_path = _resolve_sql_output_path(executor, str(step["target_path"]))
    target_type = _file_table_type(step.get("target_type"), target_path, field_name="target_type")
    with _open_connection(executor, config, step) as opened:
        sql, params = _prepare_sql(str(step["sql"]), step.get("params"), opened.database_type)
        sql = _apply_query_pagination(sql, opened.database_type, pagination)
        cursor = opened.connection.cursor()
        try:
            _execute(cursor, sql, params)
            columns = [str(item[0]) for item in (cursor.description or [])]
            rows = _fetch_rows(cursor, columns, row_mode="dict", max_rows=max_rows)
        finally:
            _close_cursor(cursor)

    _write_export_rows(target_path, target_type=target_type, rows=rows, columns=columns, sheet=step.get("sheet"))
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "export",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "target_path": str(target_path),
        "target_type": target_type,
        "columns": columns,
        "row_count": len(rows),
        "first_row": rows[0] if rows else None,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(_query_pagination_payload(pagination))
    if bool(step.get("include_rows", False)):
        payload["rows"] = _json_safe(rows)
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql export finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        target_type=target_type,
        row_count=len(rows),
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_copy(executor: Any, step: dict[str, Any]) -> None:
    if bool(step.get("stream", False)):
        _run_copy_stream(executor, step)
        return
    _run_copy_buffered(executor, step)


def _run_copy_buffered(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    source_config = _connection_config(executor, step)
    target_step = dict(step)
    target_step["connection"] = step["target_connection"]
    target_config = _connection_config(executor, target_step)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    pagination = _query_pagination(step, max_rows, action_label="sql.copy")
    commit = bool(step.get("commit", True))

    with _open_connection(executor, source_config, step) as source_opened, _open_connection(executor, target_config, step) as target_opened:
        sql, params = _prepare_sql(str(step["sql"]), step.get("params"), source_opened.database_type)
        sql = _apply_query_pagination(sql, source_opened.database_type, pagination)
        cursor = source_opened.connection.cursor()
        try:
            _execute(cursor, sql, params)
            source_columns = [str(item[0]) for item in (cursor.description or [])]
            source_rows = _fetch_rows(cursor, source_columns, row_mode="dict", max_rows=max_rows)
        finally:
            _close_cursor(cursor)
        target_rows, target_columns, column_map = _copy_target_rows(step, source_rows, source_columns)
        bulk_step = _copy_bulk_step(step, target_rows, target_columns)
        bulk_payload = _bulk_insert_operation(target_opened, bulk_step, commit=commit)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "copy",
        "source_connection": source_opened.connection_name,
        "source_database_type": source_opened.database_type,
        "target_connection": target_opened.connection_name,
        "target_database_type": target_opened.database_type,
        "source_columns": source_columns,
        "source_row_count": len(source_rows),
        "first_row": target_rows[0] if target_rows else None,
        "column_map": column_map,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(_query_pagination_payload(pagination))
    payload.update(
        {
            "table": bulk_payload["table"],
            "columns": bulk_payload["columns"],
            "mode": bulk_payload["mode"],
            "input_rows": bulk_payload["input_rows"],
            "affected_rows": bulk_payload["affected_rows"],
            "batch_size": bulk_payload["batch_size"],
            "batch_count": bulk_payload["batch_count"],
        }
    )
    if bool(step.get("include_rows", False)):
        payload["rows"] = _json_safe(target_rows)
    _write_optional_rows(executor, step, target_rows)
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql copy finished",
        source_connection=source_opened.connection_name,
        source_database_type=source_opened.database_type,
        target_connection=target_opened.connection_name,
        target_database_type=target_opened.database_type,
        table=bulk_payload["table"],
        input_rows=bulk_payload["input_rows"],
        affected_rows=bulk_payload["affected_rows"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_copy_stream(executor: Any, step: dict[str, Any]) -> None:
    if bool(step.get("include_rows", False)):
        raise ValueError("sql.copy stream=true 不支持 include_rows；请使用 rows_path=.jsonl 分批落盘。")
    rows_output_path = _stream_rows_output_path(executor, step)
    started_at = time.perf_counter()
    source_config = _connection_config(executor, step)
    target_step = dict(step)
    target_step["connection"] = step["target_connection"]
    target_config = _connection_config(executor, target_step)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    fetch_size = max(1, int(step.get("fetch_size", step.get("batch_size", 1000))))
    pagination = _query_pagination(step, max_rows, action_label="sql.copy")
    commit = bool(step.get("commit", True))
    source_columns: list[str] = []
    target_columns: list[str] = []
    column_map: dict[str, str] = {}
    first_row: dict[str, Any] | None = None
    source_row_count = 0
    input_rows = 0
    affected_rows = 0
    unknown_rowcount = False
    batch_count = 0
    mode = str(step.get("mode", "insert")).lower()

    try:
        with _open_connection(executor, source_config, step) as source_opened, _open_connection(executor, target_config, step) as target_opened:
            sql, params = _prepare_sql(str(step["sql"]), step.get("params"), source_opened.database_type)
            sql = _apply_query_pagination(sql, source_opened.database_type, pagination)
            cursor = source_opened.connection.cursor()
            try:
                _execute(cursor, sql, params)
                source_columns = [str(item[0]) for item in (cursor.description or [])]
                _empty_target_rows, target_columns, column_map = _copy_target_rows(step, [], source_columns)
                while True:
                    remaining = max_rows - source_row_count
                    if remaining <= 0:
                        if cursor.fetchmany(1):
                            raise ValueError(f"sql.copy 查询结果超过 max_rows={max_rows}；请收窄条件、分页复制或提高 max_rows。")
                        break
                    fetched = cursor.fetchmany(min(fetch_size, remaining + 1))
                    if len(fetched) > remaining:
                        raise ValueError(f"sql.copy 查询结果超过 max_rows={max_rows}；请收窄条件、分页复制或提高 max_rows。")
                    if not fetched:
                        break
                    source_batch = [dict(zip(source_columns, row)) for row in fetched]
                    target_batch, target_columns, column_map = _copy_target_rows(step, source_batch, source_columns)
                    if target_batch and first_row is None:
                        first_row = target_batch[0]
                    bulk_step = _copy_bulk_step(step, target_batch, target_columns, include_expect=False)
                    bulk_payload = _bulk_insert_operation(target_opened, bulk_step, commit=False)
                    source_row_count += len(source_batch)
                    input_rows += int(bulk_payload["input_rows"])
                    batch_count += int(bulk_payload["batch_count"])
                    rowcount = int(bulk_payload["affected_rows"])
                    if rowcount < 0:
                        unknown_rowcount = True
                    elif not unknown_rowcount:
                        affected_rows += rowcount
                    _append_optional_jsonl_rows(rows_output_path, target_batch)
            except BaseException:
                _rollback_if_possible(target_opened.connection)
                raise
            finally:
                _close_cursor(cursor)
            if unknown_rowcount:
                affected_rows = -1
            _assert_affected_rows(step, affected_rows)
            if commit:
                target_opened.connection.commit()
    except BaseException:
        _remove_partial_file(rows_output_path)
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "copy",
        "stream": True,
        "source_connection": source_opened.connection_name,
        "source_database_type": source_opened.database_type,
        "target_connection": target_opened.connection_name,
        "target_database_type": target_opened.database_type,
        "source_columns": source_columns,
        "source_row_count": source_row_count,
        "first_row": first_row,
        "column_map": column_map,
        "table": step["table"],
        "columns": target_columns,
        "mode": mode,
        "input_rows": input_rows,
        "affected_rows": affected_rows,
        "fetch_size": fetch_size,
        "batch_size": max(1, int(step.get("batch_size", fetch_size))),
        "batch_count": batch_count,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(_query_pagination_payload(pagination))
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql copy stream finished",
        source_connection=source_opened.connection_name,
        source_database_type=source_opened.database_type,
        target_connection=target_opened.connection_name,
        target_database_type=target_opened.database_type,
        table=step["table"],
        input_rows=input_rows,
        affected_rows=affected_rows,
        fetch_size=fetch_size,
        batch_count=batch_count,
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_inspect(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    with _open_connection(executor, config, step) as opened:
        schema_info = _inspect_schema(opened, step)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "inspect",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "schema": step.get("schema"),
        "table": step.get("table"),
        "tables": schema_info["tables"],
        "columns": schema_info["columns"],
        "indexes": schema_info["indexes"],
        "table_count": len(schema_info["tables"]),
        "column_count": len(schema_info["columns"]),
        "index_count": len(schema_info["indexes"]),
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql inspect finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        table_count=payload["table_count"],
        column_count=payload["column_count"],
        index_count=payload["index_count"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_transaction(executor: Any, step: dict[str, Any]) -> None:
    if "rows_path" in step:
        raise ValueError("sql.transaction 不支持 rows_path；请使用 result_path 保存事务摘要。")
    if "commit" in step:
        raise ValueError("sql.transaction 不支持 commit 字段；事务成功自动提交，失败自动回滚。")
    operations = step.get("steps")
    if not isinstance(operations, list) or not operations:
        raise ValueError("sql.transaction.steps 必须是非空数组。")
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    results: list[dict[str, Any]] = []
    with _open_connection(executor, config, step) as opened:
        try:
            for index, operation in enumerate(operations):
                results.append(_run_transaction_operation(opened, operation, index))
            opened.connection.commit()
        except BaseException:
            _rollback_if_possible(opened.connection)
            raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "type": "transaction",
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "step_count": len(operations),
        "committed": True,
        "results": _json_safe(results),
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql transaction finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        step_count=len(operations),
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
    )


def _run_transaction_operation(opened: "_OpenedConnection", operation: Any, index: int) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise ValueError(f"sql.transaction.steps[{index}] 必须是对象。")
    forbidden_fields = [field for field in ("action", "connection", "commit", "save_as", "rows_path", "result_path") if field in operation]
    if forbidden_fields:
        raise ValueError(
            f"sql.transaction.steps[{index}] 不支持字段：{', '.join(forbidden_fields)}。"
            "事务子步骤使用父级 connection/commit，只在父级 transaction 写 result_path/save_as。"
        )
    operation_type = str(operation.get("type") or "").lower()
    operation_started_at = time.perf_counter()
    if operation_type == "query":
        payload, _rows = _query_operation(opened, operation, scalar=False)
    elif operation_type == "scalar":
        payload, _rows = _query_operation(opened, operation, scalar=True)
    elif operation_type == "execute":
        affected_rows, lastrowid = _execute_operation(opened, operation, commit=False)
        payload = _operation_payload(opened, "execute", operation_started_at)
        payload.update({"affected_rows": affected_rows, "lastrowid": lastrowid})
    elif operation_type == "executemany":
        affected_rows = _executemany_operation(opened, operation, commit=False)
        payload = _operation_payload(opened, "executemany", operation_started_at)
        payload.update({"affected_rows": affected_rows, "batch_count": len(operation.get("params_list", []))})
    elif operation_type == "bulk_insert":
        payload = _bulk_insert_operation(opened, operation, commit=False)
        payload["elapsed_ms"] = int((time.perf_counter() - operation_started_at) * 1000)
    else:
        raise ValueError(
            f"sql.transaction.steps[{index}].type 不支持：{operation_type}；"
            "可选值：query、scalar、execute、executemany、bulk_insert。"
        )
    payload["index"] = index
    if "name" in operation:
        payload["name"] = operation["name"]
    return payload


def _query_operation(opened: "_OpenedConnection", step: dict[str, Any], *, scalar: bool) -> tuple[dict[str, Any], list[Any]]:
    operation_started_at = time.perf_counter()
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    pagination = _query_pagination(step, max_rows, action_label="sql.query")
    row_mode = str(step.get("row_mode", "dict")).lower()
    if row_mode not in {"dict", "list"}:
        raise ValueError("sql.row_mode 只支持 dict 或 list。")
    sql, params = _prepare_sql(str(step["sql"]), step.get("params"), opened.database_type)
    sql = _apply_query_pagination(sql, opened.database_type, pagination)
    cursor = opened.connection.cursor()
    try:
        _execute(cursor, sql, params)
        columns = [str(item[0]) for item in (cursor.description or [])]
        rows = _fetch_rows(cursor, columns, row_mode=row_mode, max_rows=max_rows)
    finally:
        _close_cursor(cursor)
    value = rows[0][0] if scalar and rows and isinstance(rows[0], list) else None
    if scalar and rows and isinstance(rows[0], dict):
        value = next(iter(rows[0].values()), None)
    payload: dict[str, Any] = _operation_payload(opened, "scalar" if scalar else "query", operation_started_at)
    payload.update(
        {
            "columns": columns,
            "row_count": len(rows),
            "first_row": rows[0] if rows else None,
        }
    )
    payload.update(_query_pagination_payload(pagination))
    if scalar:
        payload["value"] = _json_safe(value)
    if bool(step.get("include_rows", "rows_path" not in step)):
        payload["rows"] = _json_safe(rows)
    return payload, rows


def _execute_operation(opened: "_OpenedConnection", step: dict[str, Any], *, commit: bool) -> tuple[int, Any]:
    sql, params = _prepare_sql(str(step["sql"]), step.get("params"), opened.database_type)
    cursor = opened.connection.cursor()
    try:
        _execute(cursor, sql, params)
        affected_rows = int(cursor.rowcount if cursor.rowcount is not None else -1)
        lastrowid = getattr(cursor, "lastrowid", None)
        if commit:
            opened.connection.commit()
    except BaseException:
        _rollback_if_possible(opened.connection)
        raise
    finally:
        _close_cursor(cursor)
    _assert_affected_rows(step, affected_rows)
    return affected_rows, lastrowid


def _executemany_operation(opened: "_OpenedConnection", step: dict[str, Any], *, commit: bool) -> int:
    params_list = step.get("params_list")
    if not isinstance(params_list, list):
        raise ValueError("sql.executemany.params_list 必须是数组。")
    sql, _ = _prepare_sql(str(step["sql"]), params_list[0] if params_list else None, opened.database_type)
    cursor = opened.connection.cursor()
    try:
        cursor.executemany(sql, params_list)
        affected_rows = int(cursor.rowcount if cursor.rowcount is not None else -1)
        if commit:
            opened.connection.commit()
    except BaseException:
        _rollback_if_possible(opened.connection)
        raise
    finally:
        _close_cursor(cursor)
    _assert_affected_rows(step, affected_rows)
    return affected_rows


def _bulk_insert_operation(opened: "_OpenedConnection", step: dict[str, Any], *, commit: bool) -> dict[str, Any]:
    operation_started_at = time.perf_counter()
    rows = step.get("rows")
    if not isinstance(rows, list):
        raise ValueError("sql.bulk_insert.rows 必须是数组。")
    columns = _bulk_columns(step, rows)
    mode = str(step.get("mode", "insert")).lower()
    if mode not in {"insert", "replace", "upsert"}:
        raise ValueError("sql.bulk_insert.mode 只支持 insert、replace 或 upsert。")
    batch_size = max(1, int(step.get("batch_size", len(rows) or 1)))
    if not rows:
        affected_rows = 0
        batch_count = 0
    else:
        sql = _bulk_insert_sql(step, columns, opened.database_type, mode)
        values = [_bulk_row_values(row, columns) for row in rows]
        affected_rows = 0
        unknown_rowcount = False
        batch_count = 0
        cursor = opened.connection.cursor()
        try:
            for batch in _chunks(values, batch_size):
                cursor.executemany(sql, batch)
                batch_count += 1
                rowcount = int(cursor.rowcount if cursor.rowcount is not None else -1)
                if rowcount < 0:
                    unknown_rowcount = True
                elif not unknown_rowcount:
                    affected_rows += rowcount
            if unknown_rowcount:
                affected_rows = -1
            if commit:
                opened.connection.commit()
        except BaseException:
            _rollback_if_possible(opened.connection)
            raise
        finally:
            _close_cursor(cursor)
    _assert_affected_rows(step, affected_rows)
    payload = _operation_payload(opened, "bulk_insert", operation_started_at)
    payload.update(
        {
            "table": step["table"],
            "columns": columns,
            "mode": mode,
            "input_rows": len(rows),
            "affected_rows": affected_rows,
            "batch_size": batch_size,
            "batch_count": batch_count,
        }
    )
    return payload


def _operation_payload(opened: "_OpenedConnection", operation_type: str, started_at: float) -> dict[str, Any]:
    return {
        "type": operation_type,
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
    }


def _chunks(values: list[Any], batch_size: int) -> list[list[Any]]:
    return [values[index : index + batch_size] for index in range(0, len(values), batch_size)]


def _resolve_input_path(executor: Any, raw_path: str) -> Path:
    path = executor._resolve_path(raw_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"sql.import.source_path 文件不存在：{raw_path}")
    return path


def _resolve_sql_output_path(executor: Any, raw_path: str) -> Path:
    path = executor._resolve_output_path(raw_path, category="sql")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _file_table_type(raw_type: Any, path: Path, *, field_name: str) -> str:
    if raw_type is not None and str(raw_type).strip():
        value = str(raw_type).lower()
    else:
        suffix = path.suffix.lower()
        aliases = {".csv": "csv", ".json": "json", ".jsonl": "jsonl", ".xlsx": "excel", ".xlsm": "excel"}
        value = aliases.get(suffix, "")
    aliases = {"xlsx": "excel", "xlsm": "excel"}
    value = aliases.get(value, value)
    if value not in {"csv", "json", "jsonl", "excel"}:
        raise ValueError(f"sql.{field_name} 只支持 csv、json、jsonl、excel，或使用 .csv/.json/.jsonl/.xlsx 文件后缀。")
    return value


def _read_table_rows(executor: Any, step: dict[str, Any], *, source_path: Path, source_type: str) -> list[dict[str, Any]]:
    if source_type == "jsonl":
        rows = _read_jsonl_rows(source_path)
    else:
        read_step = dict(step)
        read_step["type"] = "excel" if source_type == "excel" else source_type
        read_step["path"] = str(source_path)
        if source_type == "excel":
            read_step.setdefault("mode", "records")
        rows = files.read_file(executor, read_step)
    rows = _extract_record_rows(rows, record_path=step.get("record_path"))
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"sql.import 源数据第 {index} 行必须是对象；数组行请先用 read/table 转换为对象行。")
        result.append({str(key): value for key, value in row.items()})
    return result


def _read_jsonl_rows(path: Path) -> list[Any]:
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as error:
                raise ValueError(f"sql.import JSONL 第 {line_number} 行无效：{error.msg}") from error
    return rows


def _extract_record_rows(value: Any, *, record_path: Any) -> list[Any]:
    if isinstance(record_path, str) and record_path.strip():
        for part in record_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                raise ValueError(f"sql.import.record_path 无法在非对象上继续解析：{record_path}")
    elif isinstance(value, dict):
        for key in ("rows", "data", "items"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
    if not isinstance(value, list):
        raise ValueError("sql.import 源数据必须是行对象数组，或 JSON 对象中的 rows/data/items 数组。")
    return value


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                columns.append(key)
                seen.add(key)
    return columns


def _create_import_table(
    opened: "_OpenedConnection",
    step: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    commit: bool,
) -> None:
    if not columns:
        raise ValueError("sql.import create_table=true 需要至少一列。")
    table = _safe_identifier(str(step["table"]), field_name="table")
    column_defs = ", ".join(f"{column} {_import_column_type(opened.database_type, rows, column)}" for column in columns)
    if opened.database_type == "oracle":
        raise ValueError("Oracle 暂不支持 sql.import.create_table=true；请先用 execute 建表。")
    if opened.database_type == "sqlserver":
        sql = f"IF OBJECT_ID(N'{table}', N'U') IS NULL CREATE TABLE {table} ({column_defs})"
    else:
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({column_defs})"
    cursor = opened.connection.cursor()
    try:
        _execute(cursor, sql, None)
        if commit:
            opened.connection.commit()
    except BaseException:
        _rollback_if_possible(opened.connection)
        raise
    finally:
        _close_cursor(cursor)


def _import_column_type(database_type: str, rows: list[dict[str, Any]], column: str) -> str:
    _safe_identifier(column, field_name="columns")
    values = [row.get(column) for row in rows if row.get(column) is not None and row.get(column) != ""]
    if not values:
        return _text_column_type(database_type)
    if all(isinstance(value, bool) for value in values):
        return "INTEGER" if database_type == "sqlite" else "BOOLEAN"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        if database_type == "oracle":
            return "NUMBER"
        if database_type == "mysql":
            return "BIGINT"
        return "INTEGER"
    if all(isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) for value in values):
        if database_type == "postgresql":
            return "DOUBLE PRECISION"
        if database_type == "oracle":
            return "NUMBER"
        return "REAL"
    return _text_column_type(database_type)


def _text_column_type(database_type: str) -> str:
    if database_type == "oracle":
        return "CLOB"
    if database_type == "mysql":
        return "TEXT"
    if database_type == "sqlserver":
        return "NVARCHAR(MAX)"
    return "TEXT"


def _write_export_rows(path: Path, *, target_type: str, rows: list[dict[str, Any]], columns: list[str], sheet: Any) -> None:
    safe_rows = _json_safe(rows)
    if target_type == "csv":
        _write_csv(path, safe_rows)
        return
    if target_type == "jsonl":
        _write_jsonl(path, safe_rows)
        return
    if target_type == "json":
        path.write_text(json.dumps(safe_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    _write_export_excel(path, safe_rows, columns=columns, sheet=sheet)


def _write_export_excel(path: Path, rows: list[dict[str, Any]], *, columns: list[str], sheet: Any) -> None:
    excel = files._load_openpyxl()
    workbook = excel["Workbook"]()
    worksheet = workbook.active
    worksheet.title = str(sheet or "Sheet1")
    headers = columns or _rows_columns(rows)
    for column_number, header in enumerate(headers, start=1):
        worksheet.cell(row=1, column=column_number).value = header
    for row_number, row in enumerate(rows, start=2):
        for column_number, header in enumerate(headers, start=1):
            worksheet.cell(row=row_number, column=column_number).value = _excel_export_cell_value(row.get(header))
    workbook.save(path)


def _excel_export_cell_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _copy_target_rows(step: dict[str, Any], source_rows: list[dict[str, Any]], source_columns: list[str]) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    raw_column_map = step.get("column_map")
    if raw_column_map is not None and not isinstance(raw_column_map, dict):
        raise ValueError("sql.copy.column_map 必须是对象，格式为 {目标列: 源查询列}。")
    column_map = {str(key): str(value) for key, value in (raw_column_map or {}).items()}
    if column_map:
        target_columns = [str(column) for column in step.get("columns", list(column_map.keys()))]
    else:
        target_columns = [str(column) for column in step.get("columns", source_columns)]
        column_map = {column: column for column in target_columns}
    if not target_columns:
        raise ValueError("sql.copy 需要 columns 或可从查询结果推断出的列。")
    for column in target_columns:
        _safe_identifier(column, field_name="columns")
    source_column_set = set(source_columns)
    for target_column in target_columns:
        source_column = column_map.get(target_column, target_column)
        if source_column not in source_column_set:
            raise ValueError(f"sql.copy.column_map 目标列 {target_column} 引用的源查询列不存在：{source_column}")
    target_rows = [
        {target_column: row.get(column_map.get(target_column, target_column)) for target_column in target_columns}
        for row in source_rows
    ]
    return target_rows, target_columns, {target_column: column_map.get(target_column, target_column) for target_column in target_columns}


def _copy_bulk_step(
    step: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    include_expect: bool = True,
) -> dict[str, Any]:
    bulk_step: dict[str, Any] = {
        "table": step["table"],
        "rows": rows,
        "columns": columns,
        "mode": step.get("mode", "insert"),
        "batch_size": step.get("batch_size", len(rows) or 1),
    }
    optional_fields = ("conflict_keys", "update_columns", "expect_affected_rows") if include_expect else ("conflict_keys", "update_columns")
    for field in optional_fields:
        if field in step:
            bulk_step[field] = step[field]
    return bulk_step


def _inspect_schema(opened: "_OpenedConnection", step: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    schema = str(step["schema"]) if "schema" in step else None
    table = str(step["table"]) if "table" in step else None
    include_columns = bool(step.get("include_columns", True))
    include_indexes = bool(step.get("include_indexes", False))
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS * 5)))
    if opened.database_type == "sqlite":
        return _inspect_sqlite(opened, table=table, include_columns=include_columns, include_indexes=include_indexes)
    if opened.database_type == "oracle":
        return _inspect_oracle(opened, schema=schema, table=table, include_columns=include_columns, max_rows=max_rows)
    return _inspect_information_schema(
        opened,
        schema=schema,
        table=table,
        include_columns=include_columns,
        max_rows=max_rows,
    )


def _inspect_sqlite(
    opened: "_OpenedConnection",
    *,
    table: str | None,
    include_columns: bool,
    include_indexes: bool,
) -> dict[str, list[dict[str, Any]]]:
    sql = "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
    params: list[Any] = []
    if table:
        sql += " AND name = ?"
        params.append(table)
    sql += " ORDER BY name"
    tables = [
        {"schema": "main", "name": row["name"], "type": row["type"]}
        for row in _select_dicts(opened, sql, params, max_rows=DEFAULT_MAX_ROWS * 5)
    ]
    columns: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    for table_info in tables:
        table_name = str(table_info["name"])
        quoted_table = _quote_sqlite_identifier(table_name)
        if include_columns:
            column_rows = _select_dicts(opened, f"PRAGMA table_info({quoted_table})", None, max_rows=DEFAULT_MAX_ROWS * 5)
            for row in column_rows:
                columns.append(
                    {
                        "schema": "main",
                        "table": table_name,
                        "name": row.get("name"),
                        "ordinal": row.get("cid"),
                        "data_type": row.get("type"),
                        "nullable": not bool(row.get("notnull")),
                        "default": row.get("dflt_value"),
                        "primary_key_position": row.get("pk"),
                    }
                )
        if include_indexes:
            index_rows = _select_dicts(opened, f"PRAGMA index_list({quoted_table})", None, max_rows=DEFAULT_MAX_ROWS * 5)
            for row in index_rows:
                index_name = str(row.get("name") or "")
                if not index_name:
                    continue
                index_columns = _select_dicts(
                    opened,
                    f"PRAGMA index_info({_quote_sqlite_identifier(index_name)})",
                    None,
                    max_rows=DEFAULT_MAX_ROWS * 5,
                )
                indexes.append(
                    {
                        "schema": "main",
                        "table": table_name,
                        "name": index_name,
                        "unique": bool(row.get("unique")),
                        "columns": [item.get("name") for item in index_columns],
                        "origin": row.get("origin"),
                        "partial": bool(row.get("partial")),
                    }
                )
    return {"tables": tables, "columns": columns, "indexes": indexes}


def _inspect_information_schema(
    opened: "_OpenedConnection",
    *,
    schema: str | None,
    table: str | None,
    include_columns: bool,
    max_rows: int,
) -> dict[str, list[dict[str, Any]]]:
    table_sql = """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE (:schema IS NULL OR table_schema = :schema)
          AND (:table IS NULL OR table_name = :table)
    """
    column_sql = """
        SELECT table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE (:schema IS NULL OR table_schema = :schema)
          AND (:table IS NULL OR table_name = :table)
    """
    if opened.database_type == "postgresql":
        exclude = " AND table_schema NOT IN ('pg_catalog', 'information_schema')"
    elif opened.database_type == "mysql":
        exclude = " AND table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
    elif opened.database_type == "sqlserver":
        exclude = " AND table_schema NOT IN ('INFORMATION_SCHEMA', 'sys')"
    elif opened.database_type == "duckdb":
        exclude = " AND table_schema NOT IN ('information_schema', 'pg_catalog')"
    else:
        exclude = ""
    params = {"schema": schema, "table": table}
    table_rows = _select_dicts(opened, table_sql + exclude + " ORDER BY table_schema, table_name", params, max_rows=max_rows)
    tables = [
        {"schema": row.get("table_schema"), "name": row.get("table_name"), "type": row.get("table_type")}
        for row in table_rows
    ]
    columns: list[dict[str, Any]] = []
    if include_columns:
        column_rows = _select_dicts(
            opened,
            column_sql + exclude + " ORDER BY table_schema, table_name, ordinal_position",
            params,
            max_rows=max_rows,
        )
        columns = [
            {
                "schema": row.get("table_schema"),
                "table": row.get("table_name"),
                "name": row.get("column_name"),
                "ordinal": row.get("ordinal_position"),
                "data_type": row.get("data_type"),
                "nullable": _nullable_value(row.get("is_nullable")),
                "default": row.get("column_default"),
            }
            for row in column_rows
        ]
    return {"tables": tables, "columns": columns, "indexes": []}


def _inspect_oracle(
    opened: "_OpenedConnection",
    *,
    schema: str | None,
    table: str | None,
    include_columns: bool,
    max_rows: int,
) -> dict[str, list[dict[str, Any]]]:
    params = {"schema": schema.upper() if schema else None, "table": table.upper() if table else None}
    table_sql = """
        SELECT owner, table_name, 'TABLE' AS table_type
        FROM all_tables
        WHERE owner = COALESCE(:schema, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA'))
          AND (:table IS NULL OR table_name = :table)
        ORDER BY owner, table_name
    """
    table_rows = _select_dicts(opened, table_sql, params, max_rows=max_rows)
    tables = [
        {"schema": row.get("owner"), "name": row.get("table_name"), "type": row.get("table_type")}
        for row in table_rows
    ]
    columns: list[dict[str, Any]] = []
    if include_columns:
        column_sql = """
            SELECT owner, table_name, column_name, column_id, data_type, nullable, data_default
            FROM all_tab_columns
            WHERE owner = COALESCE(:schema, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA'))
              AND (:table IS NULL OR table_name = :table)
            ORDER BY owner, table_name, column_id
        """
        column_rows = _select_dicts(opened, column_sql, params, max_rows=max_rows)
        columns = [
            {
                "schema": row.get("owner"),
                "table": row.get("table_name"),
                "name": row.get("column_name"),
                "ordinal": row.get("column_id"),
                "data_type": row.get("data_type"),
                "nullable": _nullable_value(row.get("nullable")),
                "default": row.get("data_default"),
            }
            for row in column_rows
        ]
    return {"tables": tables, "columns": columns, "indexes": []}


def _select_dicts(opened: "_OpenedConnection", sql: str, params: Any, *, max_rows: int) -> list[dict[str, Any]]:
    prepared_sql, prepared_params = _prepare_sql(sql, params, opened.database_type)
    cursor = opened.connection.cursor()
    try:
        _execute(cursor, prepared_sql, prepared_params)
        columns = [str(item[0]).lower() for item in (cursor.description or [])]
        return _fetch_rows(cursor, columns, row_mode="dict", max_rows=max_rows)
    finally:
        _close_cursor(cursor)


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _nullable_value(value: Any) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    return None


class _OpenedConnection:
    def __init__(self, connection: Any, database_type: str, connection_name: str) -> None:
        self.connection = connection
        self.database_type = database_type
        self.connection_name = connection_name

    def __enter__(self) -> "_OpenedConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.connection.close()


def _connection_config(executor: Any, step: dict[str, Any]) -> dict[str, Any]:
    raw_connection = step["connection"]
    if isinstance(raw_connection, dict):
        config = dict(raw_connection)
        config.setdefault("name", "inline")
        return config
    if not isinstance(raw_connection, str) or not raw_connection.strip():
        raise ValueError("sql.connection 必须是连接名或连接对象。")
    name = raw_connection.strip()
    variables = getattr(executor.state, "variables", {})
    connections = variables.get("connections")
    config_connections = variables.get("config", {}).get("connections") if isinstance(variables.get("config"), dict) else None
    for source in (config_connections, connections):
        if isinstance(source, dict) and isinstance(source.get(name), dict):
            config = dict(source[name])
            config.setdefault("name", name)
            return config
    raise KeyError(f"未找到数据库连接配置：{name}")


def _open_connection(executor: Any, config: dict[str, Any], step: dict[str, Any]) -> _OpenedConnection:
    database_type = _database_type(config)
    connection_name = str(config.get("name", "inline"))
    timeout_seconds = max(0.001, float(step.get("timeout_ms", 30_000)) / 1000)
    if database_type == "sqlite":
        path = _sqlite_path(executor, config)
        connection = sqlite3.connect(str(path), timeout=timeout_seconds)
        connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        return _OpenedConnection(connection, database_type, connection_name)
    if database_type == "duckdb":
        try:
            import duckdb
        except ImportError as error:
            raise RuntimeError(_driver_install_message("DuckDB", "db-duckdb", "duckdb")) from error
        path = _duckdb_path(executor, config)
        connection = duckdb.connect(database=str(path), read_only=bool(config.get("read_only", False)))
        return _OpenedConnection(connection, database_type, connection_name)
    if database_type == "postgresql":
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError(_driver_install_message("PostgreSQL", "db-postgresql", "psycopg[binary]")) from error
        kwargs = _sql_kwargs(config, aliases={"database": "dbname", "username": "user"})
        kwargs.setdefault("connect_timeout", max(1, int(timeout_seconds)))
        dsn = config.get("dsn") or config.get("url")
        connection = psycopg.connect(str(dsn), **kwargs) if dsn else psycopg.connect(**kwargs)
        return _OpenedConnection(connection, database_type, connection_name)
    if database_type == "mysql":
        try:
            import pymysql
        except ImportError as error:
            raise RuntimeError(_driver_install_message("MySQL/MariaDB", "db-mysql", "PyMySQL")) from error
        kwargs = _sql_kwargs(config, aliases={"username": "user", "dbname": "database"})
        kwargs.setdefault("connect_timeout", max(1, int(timeout_seconds)))
        dsn = config.get("dsn") or config.get("url")
        if dsn:
            kwargs.update(_mysql_dsn_kwargs(str(dsn)))
        connection = pymysql.connect(**kwargs)
        return _OpenedConnection(connection, database_type, connection_name)
    if database_type == "oracle":
        try:
            import oracledb
        except ImportError as error:
            raise RuntimeError(_driver_install_message("Oracle", "db-oracle", "oracledb")) from error
        kwargs = _oracle_connect_kwargs(config)
        connection = oracledb.connect(**kwargs)
        return _OpenedConnection(connection, database_type, connection_name)
    if database_type == "sqlserver":
        try:
            import pyodbc
        except ImportError as error:
            raise RuntimeError(_driver_install_message("SQL Server", "db-sqlserver", "pyodbc")) from error
        connect_string = _sqlserver_connect_string(config)
        connection = pyodbc.connect(
            connect_string,
            timeout=max(1, int(timeout_seconds)),
            autocommit=bool(config.get("autocommit", False)),
        )
        return _OpenedConnection(connection, database_type, connection_name)
    raise ValueError(f"sql.connection.type 不支持：{database_type}")


def _driver_install_message(database_label: str, extra_name: str, package_name: str) -> str:
    return (
        f"sql {database_label} 连接需要按需安装数据库驱动："
        f"pip install -e '.[{extra_name}]'；也可以直接安装 {package_name}。"
        "默认安装不会包含该驱动。"
    )


def _database_type(config: dict[str, Any]) -> str:
    raw_type = str(config.get("type") or config.get("driver") or "").lower()
    if not raw_type:
        dsn = str(config.get("dsn") or config.get("url") or "")
        raw_type = urlsplit(dsn).scheme.lower()
    aliases = {
        "pg": "postgresql",
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "mysql": "mysql",
        "mariadb": "mysql",
        "oracle": "oracle",
        "oracledb": "oracle",
        "sqlite": "sqlite",
        "sqlite3": "sqlite",
        "duckdb": "duckdb",
        "mssql": "sqlserver",
        "sqlserver": "sqlserver",
        "sql_server": "sqlserver",
        "sql-server": "sqlserver",
    }
    if raw_type in aliases:
        return aliases[raw_type]
    raise ValueError("sql.connection 需要 type/driver，或带协议的 dsn/url。")


def _sqlite_path(executor: Any, config: dict[str, Any]) -> Path | str:
    raw_path = str(config.get("path") or config.get("database") or config.get("dsn") or config.get("url") or "")
    if raw_path.startswith("sqlite:///"):
        raw_path = unquote(raw_path[len("sqlite:///") :])
    elif raw_path.startswith("sqlite://"):
        raw_path = unquote(raw_path[len("sqlite://") :])
    if raw_path in {"", ":memory:"}:
        return ":memory:"
    if is_absolute_path_text(raw_path):
        path = path_from_text(raw_path).resolve()
    else:
        path = (executor._package_root().resolve() / path_from_text(raw_path)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _duckdb_path(executor: Any, config: dict[str, Any]) -> Path | str:
    raw_path = str(config.get("path") or config.get("database") or config.get("dsn") or config.get("url") or "")
    if raw_path.startswith("duckdb:///"):
        raw_path = unquote(raw_path[len("duckdb:///") :])
    elif raw_path.startswith("duckdb://"):
        raw_path = unquote(raw_path[len("duckdb://") :])
    if raw_path in {"", ":memory:"}:
        return ":memory:"
    if is_absolute_path_text(raw_path):
        path = path_from_text(raw_path).resolve()
    else:
        path = (executor._package_root().resolve() / path_from_text(raw_path)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _sql_kwargs(config: dict[str, Any], *, aliases: dict[str, str]) -> dict[str, Any]:
    skip = {"name", "type", "driver", "dsn", "url", "path"}
    kwargs: dict[str, Any] = {}
    for key, value in config.items():
        if key in skip:
            continue
        kwargs[aliases.get(key, key)] = value
    return kwargs


def _mysql_dsn_kwargs(dsn: str) -> dict[str, Any]:
    parts = urlsplit(dsn)
    kwargs: dict[str, Any] = {}
    if parts.hostname:
        kwargs["host"] = parts.hostname
    if parts.port:
        kwargs["port"] = parts.port
    if parts.username:
        kwargs["user"] = unquote(parts.username)
    if parts.password:
        kwargs["password"] = unquote(parts.password)
    if parts.path and parts.path != "/":
        kwargs["database"] = unquote(parts.path.lstrip("/"))
    return kwargs


def _oracle_connect_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    dsn = str(config.get("dsn") or config.get("url") or "")
    kwargs = _sql_kwargs(config, aliases={"username": "user"})
    if dsn:
        kwargs.update(_oracle_dsn_kwargs(dsn))
    elif "service_name" in config:
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 1521))
        service_name = str(config["service_name"])
        kwargs["dsn"] = f"{host}:{port}/{service_name}"
    elif "sid" in config:
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 1521))
        sid = str(config["sid"])
        kwargs["dsn"] = f"{host}:{port}:{sid}"
    return kwargs


def _oracle_dsn_kwargs(dsn: str) -> dict[str, Any]:
    parts = urlsplit(dsn)
    if parts.scheme not in {"oracle", "oracledb"}:
        return {"dsn": dsn}
    kwargs: dict[str, Any] = {}
    if parts.username:
        kwargs["user"] = unquote(parts.username)
    if parts.password:
        kwargs["password"] = unquote(parts.password)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 1521
    service = unquote(parts.path.lstrip("/"))
    kwargs["dsn"] = f"{host}:{port}/{service}" if service else f"{host}:{port}"
    return kwargs


def _sqlserver_connect_string(config: dict[str, Any]) -> str:
    raw = config.get("connection_string") or config.get("odbc_connect")
    if raw:
        return str(raw)
    dsn = str(config.get("dsn") or config.get("url") or "")
    if dsn:
        parts = urlsplit(dsn)
        if parts.scheme not in {"mssql", "sqlserver", "sql-server"}:
            return dsn
        config = dict(config)
        if parts.hostname:
            config["host"] = parts.hostname
        if parts.port:
            config["port"] = parts.port
        if parts.username:
            config["user"] = unquote(parts.username)
        if parts.password:
            config["password"] = unquote(parts.password)
        if parts.path and parts.path != "/":
            config["database"] = unquote(parts.path.lstrip("/"))
    if config.get("dsn") and not dsn.lower().startswith(("mssql://", "sqlserver://", "sql-server://")):
        parts = [f"DSN={config['dsn']}"]
    else:
        raw_driver = str(config.get("driver") or "")
        driver_aliases = {"mssql", "sqlserver", "sql_server", "sql-server"}
        driver = str(
            config.get("odbc_driver")
            or config.get("driver_name")
            or config.get("odbc_driver_name")
            or (raw_driver if raw_driver.lower() not in driver_aliases else "")
            or "ODBC Driver 18 for SQL Server"
        )
        host = str(config.get("host") or config.get("server") or "127.0.0.1")
        server = host
        if config.get("port"):
            server = f"{host},{int(config['port'])}"
        parts = [f"DRIVER={{{driver}}}", f"SERVER={server}"]
    if config.get("database"):
        parts.append(f"DATABASE={config['database']}")
    user = config.get("user") or config.get("username")
    password = config.get("password")
    if user:
        parts.append(f"UID={user}")
    if password:
        parts.append(f"PWD={password}")
    if config.get("trusted_connection") is not None:
        parts.append(f"Trusted_Connection={_odbc_bool(config['trusted_connection'])}")
    if config.get("encrypt") is not None:
        parts.append(f"Encrypt={_odbc_bool(config['encrypt'])}")
    if config.get("trust_server_certificate") is not None:
        parts.append(f"TrustServerCertificate={_odbc_bool(config['trust_server_certificate'])}")
    return ";".join(str(part) for part in parts)


def _odbc_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _prepare_sql(sql: str, params: Any, database_type: str) -> tuple[str, Any]:
    if params is None:
        return sql, None
    if isinstance(params, dict) and database_type in {"postgresql", "mysql"}:
        return _convert_named_params(sql), params
    if isinstance(params, dict) and database_type in {"sqlserver", "duckdb"}:
        return _convert_named_params_to_qmark(sql, params)
    if isinstance(params, (dict, list, tuple)):
        return sql, params
    raise ValueError("sql.params 必须是对象、数组或省略。")


def _convert_named_params(sql: str) -> str:
    result: list[str] = []
    index = 0
    in_single = False
    in_double = False
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            index += 1
            continue
        if not in_single and not in_double and char == ":":
            if index + 1 < len(sql) and sql[index + 1] == ":":
                result.append("::")
                index += 2
                continue
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[index:])
            if match:
                name = match.group(1)
                result.append(f"%({name})s")
                index += len(name) + 1
                continue
        result.append(char)
        index += 1
    return "".join(result)


def _convert_named_params_to_qmark(sql: str, params: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    result: list[str] = []
    ordered: list[Any] = []
    index = 0
    in_single = False
    in_double = False
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            index += 1
            continue
        if not in_single and not in_double and char == ":":
            if index + 1 < len(sql) and sql[index + 1] == ":":
                result.append("::")
                index += 2
                continue
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[index:])
            if match:
                name = match.group(1)
                if name not in params:
                    raise ValueError(f"sql.params 缺少命名参数：{name}")
                result.append("?")
                ordered.append(params[name])
                index += len(name) + 1
                continue
        result.append(char)
        index += 1
    if ordered:
        return "".join(result), tuple(ordered)
    return sql, tuple(params.values())


def _execute(cursor: Any, sql: str, params: Any) -> None:
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)


def _query_pagination(step: dict[str, Any], max_rows: int, *, action_label: str) -> dict[str, Any]:
    if "limit" in step and "page_size" in step:
        raise ValueError(f"{action_label} 不能同时使用 limit 和 page_size。")
    if "page" in step and "page_size" not in step:
        raise ValueError(f"{action_label}.page 需要和 page_size 一起使用。")

    has_offset = "offset" in step
    offset = int(step["offset"]) if has_offset else None
    if offset is not None and offset < 0:
        raise ValueError(f"{action_label}.offset 必须大于等于 0。")

    page_size = None
    page = None
    limit = None
    if "page_size" in step:
        page_size = int(step["page_size"])
        if page_size < 1:
            raise ValueError(f"{action_label}.page_size 必须大于等于 1。")
        page = int(step.get("page", 1))
        if page < 1:
            raise ValueError(f"{action_label}.page 必须大于等于 1。")
        limit = page_size
        if offset is None:
            offset = (page - 1) * page_size
    elif "limit" in step:
        limit = int(step["limit"])
        if limit < 1:
            raise ValueError(f"{action_label}.limit 必须大于等于 1。")
    elif offset is not None:
        limit = max_rows

    if limit is not None and limit > max_rows:
        raise ValueError(f"{action_label}.limit/page_size={limit} 超过 max_rows={max_rows}；请提高 max_rows 或缩小分页大小。")
    return {
        "limit": limit,
        "offset": offset,
        "page_size": page_size,
        "page": page,
        "has_pagination": limit is not None or offset not in {None, 0} or page_size is not None,
        "has_offset": has_offset,
    }


def _apply_query_pagination(sql: str, database_type: str, pagination: dict[str, Any]) -> str:
    limit = pagination.get("limit")
    offset = pagination.get("offset")
    if limit is None and offset in {None, 0}:
        return sql
    base_sql = sql.strip().rstrip(";").rstrip()
    if database_type == "oracle":
        clauses: list[str] = []
        if offset not in {None, 0}:
            clauses.append(f"OFFSET {int(offset)} ROWS")
        if limit is not None:
            if offset in {None, 0}:
                clauses.append(f"FETCH FIRST {int(limit)} ROWS ONLY")
            else:
                clauses.append(f"FETCH NEXT {int(limit)} ROWS ONLY")
        return f"{base_sql} {' '.join(clauses)}"
    if database_type == "sqlserver":
        if not re.search(r"\border\s+by\b", base_sql, flags=re.IGNORECASE):
            raise ValueError("SQL Server 使用 limit/offset/page_size 时查询必须包含 ORDER BY。")
        clauses = [f"OFFSET {int(offset or 0)} ROWS"]
        if limit is not None:
            clauses.append(f"FETCH NEXT {int(limit)} ROWS ONLY")
        return f"{base_sql} {' '.join(clauses)}"
    clauses = []
    if limit is not None:
        clauses.append(f"LIMIT {int(limit)}")
    if offset not in {None, 0}:
        clauses.append(f"OFFSET {int(offset)}")
    return f"{base_sql} {' '.join(clauses)}"


def _query_pagination_payload(pagination: dict[str, Any]) -> dict[str, Any]:
    if not pagination.get("has_pagination"):
        return {}
    payload: dict[str, Any] = {}
    if pagination.get("limit") is not None:
        payload["limit"] = int(pagination["limit"])
    if pagination.get("offset") is not None:
        payload["offset"] = int(pagination["offset"])
    if pagination.get("page_size") is not None:
        payload["page_size"] = int(pagination["page_size"])
        payload["page"] = int(pagination["page"])
    return payload


def _fetch_rows(cursor: Any, columns: list[str], *, row_mode: str, max_rows: int) -> list[Any]:
    fetched = cursor.fetchmany(max_rows + 1)
    if len(fetched) > max_rows:
        raise ValueError(f"sql 查询结果超过 max_rows={max_rows}；请收窄条件或提高 max_rows。")
    if row_mode == "list":
        return [list(row) for row in fetched]
    return [dict(zip(columns, row)) for row in fetched]


def _bulk_columns(step: dict[str, Any], rows: list[Any]) -> list[str]:
    raw_columns = step.get("columns")
    if raw_columns is None:
        if rows and isinstance(rows[0], dict):
            raw_columns = list(rows[0].keys())
        else:
            raise ValueError("sql.bulk_insert 使用数组行时必须提供 columns。")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("sql.bulk_insert.columns 必须是非空数组。")
    columns = [str(column) for column in raw_columns]
    for column in columns:
        _safe_identifier(column, field_name="columns")
    return columns


def _bulk_insert_sql(step: dict[str, Any], columns: list[str], database_type: str, mode: str) -> str:
    table = _safe_identifier(str(step["table"]), field_name="table")
    column_sql = ", ".join(columns)
    if database_type == "oracle" and mode in {"replace", "upsert"}:
        raise ValueError("Oracle 暂不支持 sql.bulk_insert.mode=replace/upsert；请使用 insert 或 execute MERGE。")
    if database_type == "sqlserver" and mode in {"replace", "upsert"}:
        raise ValueError("SQL Server 暂不支持 sql.bulk_insert.mode=replace/upsert；请使用 insert 或 execute MERGE。")
    if database_type == "duckdb" and mode == "replace":
        raise ValueError("DuckDB 暂不支持 sql.bulk_insert.mode=replace；请使用 insert 或 upsert。")
    values_sql = _bulk_insert_values_sql(database_type, len(columns))
    verb = "REPLACE INTO" if mode == "replace" and database_type in {"sqlite", "mysql"} else "INSERT INTO"
    if mode == "replace" and database_type == "postgresql":
        raise ValueError("PostgreSQL 不支持 sql.bulk_insert.mode=replace；请使用 upsert。")
    sql = f"{verb} {table} ({column_sql}) VALUES ({values_sql})"
    if mode != "upsert":
        return sql
    conflict_keys = step.get("conflict_keys")
    if not isinstance(conflict_keys, list) or not conflict_keys:
        raise ValueError("sql.bulk_insert.mode=upsert 需要 conflict_keys。")
    conflict_columns = [str(column) for column in conflict_keys]
    for column in conflict_columns:
        _safe_identifier(column, field_name="conflict_keys")
    update_columns = [str(column) for column in step.get("update_columns", columns) if str(column) not in conflict_columns]
    for column in update_columns:
        _safe_identifier(column, field_name="update_columns")
    if not update_columns:
        if database_type in {"sqlite", "postgresql", "duckdb"}:
            return sql + f" ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
        return sql + " ON DUPLICATE KEY UPDATE " + ", ".join(f"{column}={column}" for column in conflict_columns)
    if database_type in {"sqlite", "postgresql", "duckdb"}:
        updates = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        return sql + f" ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {updates}"
    updates = ", ".join(f"{column}=VALUES({column})" for column in update_columns)
    return sql + f" ON DUPLICATE KEY UPDATE {updates}"


def _bulk_insert_values_sql(database_type: str, column_count: int) -> str:
    if database_type in {"sqlite", "duckdb", "sqlserver"}:
        return ", ".join(["?"] * column_count)
    if database_type == "oracle":
        return ", ".join(f":{index}" for index in range(1, column_count + 1))
    return ", ".join(["%s"] * column_count)


def _bulk_row_values(row: Any, columns: list[str]) -> tuple[Any, ...]:
    if isinstance(row, dict):
        return tuple(row.get(column) for column in columns)
    if isinstance(row, list):
        if len(row) != len(columns):
            raise ValueError("sql.bulk_insert 行长度必须和 columns 一致。")
        return tuple(row)
    raise ValueError("sql.bulk_insert.rows 每一项必须是对象或数组。")


def _safe_identifier(value: str, *, field_name: str) -> str:
    parts = value.split(".")
    if not parts or any(not IDENTIFIER_RE.match(part) for part in parts):
        raise ValueError(f"sql.bulk_insert.{field_name} 只能使用简单标识符或 schema.table：{value}")
    return value


def _assert_affected_rows(step: dict[str, Any], actual: int) -> None:
    if "expect_affected_rows" not in step:
        return
    expected = step["expect_affected_rows"]
    expected_values = {expected} if isinstance(expected, int) else set(expected if isinstance(expected, list) else [int(expected)])
    if actual not in {int(value) for value in expected_values}:
        raise AssertionError(f"SQL affected rows assertion failed. expected={sorted(expected_values)}, actual={actual}")


def _write_optional_rows(executor: Any, step: dict[str, Any], rows: list[Any]) -> None:
    if "rows_path" not in step:
        return
    path = executor._resolve_output_path(str(step["rows_path"]), category="sql")
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = _json_safe(rows)
    if path.suffix.lower() == ".csv":
        _write_csv(path, safe_rows)
    elif path.suffix.lower() == ".jsonl":
        _write_jsonl(path, safe_rows)
    else:
        path.write_text(json.dumps(safe_rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_optional_result(executor: Any, step: dict[str, Any], payload: dict[str, Any]) -> None:
    if "result_path" not in step:
        return
    path = executor._resolve_output_path(str(step["result_path"]), category="sql")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: Any) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        if not rows:
            return
        if isinstance(rows[0], dict):
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            return
        writer = csv.writer(file)
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stream_rows_output_path(executor: Any, step: dict[str, Any]) -> Path | None:
    if "rows_path" not in step:
        return None
    path = executor._resolve_output_path(str(step["rows_path"]), category="sql")
    if path.suffix.lower() != ".jsonl":
        raise ValueError("sql.copy stream=true 的 rows_path 只支持 .jsonl。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def _append_optional_jsonl_rows(path: Path | None, rows: list[Any]) -> None:
    if path is None or not rows:
        return
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(_json_safe(row), ensure_ascii=False, separators=(",", ":")) + "\n")


def _remove_partial_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return


def _save_optional(executor: Any, step: dict[str, Any], payload: dict[str, Any]) -> None:
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = _json_safe(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _rollback_if_possible(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        return


def _close_cursor(cursor: Any) -> None:
    try:
        cursor.close()
    except Exception:
        return


ACTION_HANDLERS = {
    "sql": run,
}
