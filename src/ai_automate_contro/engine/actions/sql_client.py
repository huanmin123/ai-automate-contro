from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ai_automate_contro.engine.output_contract import publish_step_output
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text

from . import files

from ai_automate_contro.engine.actions.sql_runtime import (
    _OpenedConnection,
    _append_optional_jsonl_rows,
    _apply_query_pagination,
    _assert_affected_rows,
    _bulk_columns,
    _bulk_insert_sql,
    _bulk_insert_values_sql,
    _bulk_row_values,
    _close_cursor,
    _connection_config,
    _database_type,
    _execute,
    _fetch_rows,
    _json_safe,
    _open_connection,
    _prepare_sql,
    _query_pagination,
    _query_pagination_payload,
    _remove_partial_file,
    _rollback_if_possible,
    _safe_identifier,
    _save_optional,
    _stream_rows_output_path,
    _write_csv,
    _write_jsonl,
    _write_optional_result,
    _write_optional_rows,
)
from ai_automate_contro.engine.actions.sql_inspect import _inspect_schema
from ai_automate_contro.engine.actions.sql_table_io import (
    _chunks,
    _column_type_overrides,
    _copy_bulk_step,
    _copy_target_rows,
    _create_import_table,
    _excel_export_cell_value,
    _extract_record_rows,
    _file_table_type,
    _import_column_type,
    _iter_csv_import_batches,
    _iter_jsonl_import_batches,
    _open_export_stream,
    _read_jsonl_rows,
    _read_table_rows,
    _resolve_input_path,
    _resolve_sql_output_path,
    _rows_columns,
    _stream_jsonl_records,
    _text_column_type,
    _validate_import_column_config,
    _validate_import_rows,
    _write_export_rows,
)

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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _run_import(executor: Any, step: dict[str, Any]) -> None:
    if bool(step.get("stream", False)):
        _run_import_stream(executor, step)
        return
    started_at = time.perf_counter()
    source_path = _resolve_input_path(executor, str(step["source_path"]))
    source_type = _file_table_type(step.get("source_type"), source_path, field_name="source_type")
    source_rows = _read_table_rows(executor, step, source_path=source_path, source_type=source_type)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS * 100)))
    if len(source_rows) > max_rows:
        raise ValueError(f"sql.import 源数据超过 max_rows={max_rows}；请清洗输入、分批导入或提高 max_rows。")
    source_columns = _rows_columns(source_rows)
    target_rows, target_columns, column_map = _copy_target_rows(step, source_rows, source_columns)
    _validate_import_rows(step, target_rows, target_columns)
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _run_export(executor: Any, step: dict[str, Any]) -> None:
    if bool(step.get("stream", False)):
        _run_export_stream(executor, step)
        return
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _run_import_stream(executor: Any, step: dict[str, Any]) -> None:
    started_at = time.perf_counter()
    source_path = _resolve_input_path(executor, str(step["source_path"]))
    source_type = _file_table_type(step.get("source_type"), source_path, field_name="source_type")
    if source_type not in {"csv", "jsonl"}:
        raise ValueError("sql.import stream=true 只支持 csv 或 jsonl。")
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS * 100)))
    batch_size = max(1, int(step.get("batch_size", step.get("fetch_size", 1000))))
    config = _connection_config(executor, step)
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
    if mode not in {"insert", "replace", "upsert"}:
        raise ValueError("sql.import.mode 只支持 insert、replace 或 upsert。")
    unique_seen: set[tuple[Any, ...]] = set()
    fixed_copy_step: dict[str, Any] | None = None

    try:
        with _open_connection(executor, config, step) as opened:
            if source_type == "csv":
                source_columns, batch_iterator = _iter_csv_import_batches(source_path, batch_size=batch_size)
            else:
                batch_iterator = _iter_jsonl_import_batches(source_path, step, batch_size=batch_size)
            try:
                try:
                    for source_batch in batch_iterator:
                        if not source_batch:
                            continue
                        source_row_count += len(source_batch)
                        if source_row_count > max_rows:
                            raise ValueError(f"sql.import 源数据超过 max_rows={max_rows}；请清洗输入、分批导入或提高 max_rows。")
                        if source_type == "jsonl":
                            _extend_columns(source_columns, source_batch)
                        if fixed_copy_step is None:
                            target_batch, target_columns, column_map = _copy_target_rows(step, source_batch, source_columns)
                            fixed_copy_step = dict(step)
                            fixed_copy_step["columns"] = target_columns
                            fixed_copy_step["column_map"] = column_map
                        else:
                            target_batch, _ignored_columns, _ignored_map = _copy_target_rows(fixed_copy_step, source_batch, source_columns)
                        if input_rows == 0:
                            _validate_import_column_config(step, target_columns)
                            if bool(step.get("create_table", False)):
                                _create_import_table(opened, step, target_batch, target_columns, commit=False)
                        unique_seen = _validate_import_rows(
                            step,
                            target_batch,
                            target_columns,
                            unique_seen=unique_seen,
                            start_index=input_rows,
                        )
                        if target_batch and first_row is None:
                            first_row = target_batch[0]
                        bulk_step = _copy_bulk_step(step, target_batch, target_columns, include_expect=False)
                        bulk_payload = _bulk_insert_operation(opened, bulk_step, commit=False)
                        input_rows += int(bulk_payload["input_rows"])
                        batch_count += int(bulk_payload["batch_count"])
                        rowcount = int(bulk_payload["affected_rows"])
                        if rowcount < 0:
                            unknown_rowcount = True
                        elif not unknown_rowcount:
                            affected_rows += rowcount
                finally:
                    close_iterator = getattr(batch_iterator, "close", None)
                    if callable(close_iterator):
                        close_iterator()

                if input_rows == 0:
                    target_rows, target_columns, column_map = _copy_target_rows(step, [], source_columns)
                    _validate_import_column_config(step, target_columns)
                    if bool(step.get("create_table", False)):
                        _create_import_table(opened, step, target_rows, target_columns, commit=False)
                if unknown_rowcount:
                    affected_rows = -1
                _assert_affected_rows(step, affected_rows)
                if commit:
                    opened.connection.commit()
            except BaseException:
                _rollback_if_possible(opened.connection)
                raise
    except BaseException:
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "import",
        "stream": True,
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "source_path": str(source_path),
        "source_type": source_type,
        "source_columns": source_columns,
        "column_map": column_map,
        "create_table": bool(step.get("create_table", False)),
        "table": step["table"],
        "columns": target_columns,
        "mode": mode,
        "input_rows": input_rows,
        "affected_rows": affected_rows,
        "batch_size": batch_size,
        "batch_count": batch_count,
        "first_row": first_row,
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql import stream finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        source_type=source_type,
        table=payload["table"],
        input_rows=input_rows,
        affected_rows=affected_rows,
        elapsed_ms=elapsed_ms,
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _run_export_stream(executor: Any, step: dict[str, Any]) -> None:
    if bool(step.get("include_rows", False)):
        raise ValueError("sql.export stream=true 不支持 include_rows。")
    started_at = time.perf_counter()
    config = _connection_config(executor, step)
    max_rows = max(1, int(step.get("max_rows", DEFAULT_MAX_ROWS)))
    fetch_size = max(1, int(step.get("fetch_size", step.get("batch_size", 1000))))
    pagination = _query_pagination(step, max_rows, action_label="sql.export")
    target_path = _resolve_sql_output_path(executor, str(step["target_path"]))
    target_type = _file_table_type(step.get("target_type"), target_path, field_name="target_type")
    if target_type not in {"csv", "jsonl"}:
        raise ValueError("sql.export stream=true 只支持 csv 或 jsonl。")
    columns: list[str] = []
    first_row: dict[str, Any] | None = None
    row_count = 0

    try:
        with _open_connection(executor, config, step) as opened:
            sql, params = _prepare_sql(str(step["sql"]), step.get("params"), opened.database_type)
            sql = _apply_query_pagination(sql, opened.database_type, pagination)
            cursor = opened.connection.cursor()
            try:
                _execute(cursor, sql, params)
                columns = [str(item[0]) for item in (cursor.description or [])]
                with _open_export_stream(target_path, target_type=target_type, columns=columns) as writer:
                    while True:
                        remaining = max_rows - row_count
                        if remaining <= 0:
                            if cursor.fetchmany(1):
                                raise ValueError(f"sql.export 查询结果超过 max_rows={max_rows}；请收窄条件、分页导出或提高 max_rows。")
                            break
                        fetched = cursor.fetchmany(min(fetch_size, remaining + 1))
                        if len(fetched) > remaining:
                            raise ValueError(f"sql.export 查询结果超过 max_rows={max_rows}；请收窄条件、分页导出或提高 max_rows。")
                        if not fetched:
                            break
                        rows = [dict(zip(columns, row)) for row in fetched]
                        if rows and first_row is None:
                            first_row = rows[0]
                        writer(rows)
                        row_count += len(rows)
            finally:
                _close_cursor(cursor)
    except BaseException:
        _remove_partial_file(target_path)
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload: dict[str, Any] = {
        "type": "export",
        "stream": True,
        "connection": opened.connection_name,
        "database_type": opened.database_type,
        "target_path": str(target_path),
        "target_type": target_type,
        "columns": columns,
        "row_count": row_count,
        "first_row": first_row,
        "fetch_size": fetch_size,
        "elapsed_ms": elapsed_ms,
    }
    payload.update(_query_pagination_payload(pagination))
    _write_optional_result(executor, step, payload)
    _save_optional(executor, step, payload)
    executor.state.logger.log(
        "info",
        "sql export stream finished",
        connection=opened.connection_name,
        database_type=opened.database_type,
        target_type=target_type,
        row_count=row_count,
        elapsed_ms=elapsed_ms,
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
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
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _run_transaction_operation(opened: "_OpenedConnection", operation: Any, index: int) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise ValueError(f"sql.transaction.steps[{index}] 必须是对象。")
    forbidden_fields = [
        field
        for field in ("action", "connection", "commit", "save_as", "output", "rows_path", "result_path")
        if field in operation
    ]
    if forbidden_fields:
        raise ValueError(
            f"sql.transaction.steps[{index}] 不支持字段：{', '.join(forbidden_fields)}。"
            "事务子步骤使用父级 connection/commit，只在父级 transaction 写 result_path 或 output。"
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


ACTION_HANDLERS = {
    "sql": run,
}
