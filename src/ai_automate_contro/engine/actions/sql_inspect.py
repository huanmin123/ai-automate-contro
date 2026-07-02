from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.actions.sql_runtime import _close_cursor, _execute, _fetch_rows, _prepare_sql


DEFAULT_MAX_ROWS = 1000


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
