from __future__ import annotations

import csv
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ai_automate_contro.engine.output_contract import publish_step_output
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text

from . import files


DEFAULT_MAX_ROWS = 1000
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    if isinstance(params, dict) and database_type == "sqlserver":
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
        if database_type in {"sqlite", "postgresql"}:
            return sql + f" ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
        return sql + " ON DUPLICATE KEY UPDATE " + ", ".join(f"{column}={column}" for column in conflict_columns)
    if database_type in {"sqlite", "postgresql"}:
        updates = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        return sql + f" ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {updates}"
    updates = ", ".join(f"{column}=VALUES({column})" for column in update_columns)
    return sql + f" ON DUPLICATE KEY UPDATE {updates}"


def _bulk_insert_values_sql(database_type: str, column_count: int) -> str:
    if database_type in {"sqlite", "sqlserver"}:
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
    safe_payload = _json_safe(payload)
    publish_step_output(executor, step, safe_payload, action="sql")


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
