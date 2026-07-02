from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text

from . import files
from ai_automate_contro.engine.actions.sql_runtime import (
    _close_cursor,
    _execute,
    _json_safe,
    _safe_identifier,
    _write_csv,
    _write_jsonl,
)


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


def _iter_csv_import_batches(path: Path, *, batch_size: int) -> tuple[list[str], Any]:
    file = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.DictReader(file)
    source_columns = [str(field) for field in (reader.fieldnames or [])]

    def iterator() -> Any:
        try:
            batch: list[dict[str, Any]] = []
            for index, row in enumerate(reader):
                if None in row:
                    raise ValueError(f"sql.import CSV 第 {index + 2} 行列数超过表头。")
                batch.append({str(key): value for key, value in row.items()})
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch
        finally:
            file.close()

    return source_columns, iterator()


def _iter_jsonl_import_batches(path: Path, step: dict[str, Any], *, batch_size: int) -> Any:
    def iterator() -> Any:
        with path.open("r", encoding="utf-8") as file:
            batch: list[dict[str, Any]] = []
            for line_number, line in enumerate(file, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as error:
                    raise ValueError(f"sql.import JSONL 第 {line_number} 行无效：{error.msg}") from error
                for record in _stream_jsonl_records(value, record_path=step.get("record_path"), line_number=line_number):
                    if not isinstance(record, dict):
                        raise ValueError(f"sql.import JSONL 第 {line_number} 行必须解析为对象行。")
                    batch.append({str(key): item for key, item in record.items()})
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
            if batch:
                yield batch

    return iterator()


def _stream_jsonl_records(value: Any, *, record_path: Any, line_number: int) -> list[Any]:
    if isinstance(record_path, str) and record_path.strip():
        for part in record_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                raise ValueError(f"sql.import JSONL 第 {line_number} 行 record_path 无法在非对象上继续解析：{record_path}")
    if isinstance(value, list):
        return value
    return [value]


def _extend_columns(columns: list[str], rows: list[dict[str, Any]]) -> None:
    seen = set(columns)
    for row in rows:
        for key in row:
            if key not in seen:
                columns.append(key)
                seen.add(key)


def _validate_import_column_config(step: dict[str, Any], columns: list[str]) -> None:
    for column in _import_checked_columns(step, "required_columns", columns):
        _safe_identifier(column, field_name="required_columns")
    for column in _import_checked_columns(step, "unique_columns", columns):
        _safe_identifier(column, field_name="unique_columns")
    column_types = _column_type_overrides(step)
    for column in column_types:
        _safe_identifier(column, field_name="column_types")
        if column not in columns:
            raise ValueError(f"sql.import.column_types 包含目标列中不存在的列：{column}")


def _validate_import_rows(
    step: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    unique_seen: set[tuple[Any, ...]] | None = None,
    start_index: int = 0,
) -> set[tuple[Any, ...]]:
    _validate_import_column_config(step, columns)
    required_columns = _import_checked_columns(step, "required_columns", columns)
    unique_columns = _import_checked_columns(step, "unique_columns", columns)
    seen = unique_seen if unique_seen is not None else set()
    for offset, row in enumerate(rows):
        row_number = start_index + offset + 1
        for column in required_columns:
            if row.get(column) in (None, ""):
                raise ValueError(f"sql.import 第 {row_number} 行缺少必填列 {column} 的值。")
        if unique_columns:
            unique_key = tuple(row.get(column) for column in unique_columns)
            if unique_key in seen:
                joined = ", ".join(unique_columns)
                raise ValueError(f"sql.import 第 {row_number} 行违反 unique_columns 唯一约束：{joined}")
            seen.add(unique_key)
    return seen


def _import_checked_columns(step: dict[str, Any], field: str, columns: list[str]) -> list[str]:
    raw_value = step.get(field, [])
    if raw_value in (None, ""):
        return []
    if not isinstance(raw_value, list):
        raise ValueError(f"sql.import.{field} 必须是字符串数组。")
    result: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"sql.import.{field}[{index}] 必须是非空字符串。")
        if item not in columns:
            raise ValueError(f"sql.import.{field} 包含目标列中不存在的列：{item}")
        result.append(item)
    return result


def _column_type_overrides(step: dict[str, Any]) -> dict[str, str]:
    raw_value = step.get("column_types")
    if raw_value in (None, ""):
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError("sql.import.column_types 必须是对象，格式为 {列名: SQL类型}。")
    result: dict[str, str] = {}
    for column, column_type in raw_value.items():
        if not isinstance(column, str) or not column:
            raise ValueError("sql.import.column_types 的列名必须是非空字符串。")
        if not isinstance(column_type, str) or not column_type.strip():
            raise ValueError(f"sql.import.column_types.{column} 必须是非空 SQL 类型字符串。")
        result[column] = _safe_column_type(column_type)
    return result


def _safe_column_type(value: str) -> str:
    text = value.strip()
    forbidden_tokens = (";", "--", "/*", "*/", "\x00")
    if any(token in text for token in forbidden_tokens):
        raise ValueError(f"sql.import.column_types 包含不安全的 SQL 类型片段：{value}")
    return text


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
    _validate_import_column_config(step, columns)
    column_types = _column_type_overrides(step)
    column_defs = ", ".join(f"{column} {_import_column_type(opened.database_type, rows, column, column_types)}" for column in columns)
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


def _import_column_type(database_type: str, rows: list[dict[str, Any]], column: str, column_types: dict[str, str]) -> str:
    _safe_identifier(column, field_name="columns")
    if column in column_types:
        return column_types[column]
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


@contextmanager
def _open_export_stream(path: Path, *, target_type: str, columns: list[str]) -> Any:
    if target_type == "csv":
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()

            def write_rows(rows: list[dict[str, Any]]) -> None:
                writer.writerows(_json_safe(rows))

            yield write_rows
        return
    with path.open("w", encoding="utf-8", newline="\n") as file:

        def write_rows(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                file.write(json.dumps(_json_safe(row), ensure_ascii=False, separators=(",", ":")) + "\n")

        yield write_rows


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
    optional_fields = (
        ("conflict_keys", "update_columns", "expect_affected_rows")
        if include_expect
        else ("conflict_keys", "update_columns")
    )
    for field in optional_fields:
        if field in step:
            bulk_step[field] = step[field]
    return bulk_step
