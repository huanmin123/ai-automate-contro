from __future__ import annotations

import json
import os
import platform
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file


SQL_SERVICE_QUERIES = {
    "mysql": "select 1 as ok",
    "postgresql": "select 1 as ok",
    "oracle": "select 1 as ok from dual",
}
SQL_SERVICE_ALIASES = {
    "mysql": ("mysql", "mariadb"),
    "postgresql": ("postgresql", "postgres", "pg"),
    "oracle": ("oracle", "oracledb"),
}
REAL_CASE_NAMES = ("mysql", "postgresql", "redis", "oracle", "elasticsearch")


def self_check_database_components(
    project_root: str | Path,
    *,
    include_real_db: bool = False,
    allow_writes: bool = False,
    database_config: str | Path | None = None,
    only: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    selected = _requested_case_names(only)
    deterministic_cases: list[tuple[str, Callable[[Path], dict[str, Any]]]] = [
        ("sqlite-basic", _run_sqlite_basic_case),
        ("sqlite-features", _run_sqlite_features_case),
    ]
    real_cases_requested = include_real_db or any(name in selected for name in REAL_CASE_NAMES)
    explicit_database_config = bool(str(database_config or "").strip())
    config_path = _resolve_database_config_path(root, database_config)
    config_status = _empty_database_config_status(config_path)
    should_load_config = bool(config_path is not None and config_path.exists() and (real_cases_requested or explicit_database_config))
    if should_load_config:
        try:
            config, config_status = _load_database_config(config_path)
        except Exception as error:
            return {
                "ok": False,
                "check": "database_components",
                "project_root": str(root),
                "include_real_db": include_real_db,
                "database_config_path": str(config_path),
                "database_config": {
                    "path": str(config_path),
                    "path_exists": True,
                    "loaded": True,
                    "load_ok": False,
                    "error": str(error),
                    "error_type": type(error).__name__,
                },
                "cases": [],
            }
    else:
        config = {}

    available_names = [name for name, _case in deterministic_cases]
    if real_cases_requested:
        available_names.extend(REAL_CASE_NAMES)
    unknown = sorted(name for name in selected if name not in available_names)
    if unknown:
        return {
            "ok": False,
            "check": "database_components",
            "project_root": str(root),
            "include_real_db": include_real_db,
            "database_config_path": str(config_path) if config_path is not None else "",
            "database_config": config_status,
            "available_cases": available_names,
            "unknown_cases": unknown,
            "cases": [],
        }

    cases: list[dict[str, Any]] = []
    for name, runner in deterministic_cases:
        if selected and name not in selected:
            continue
        cases.append(runner(root))

    if real_cases_requested:
        for name in REAL_CASE_NAMES:
            if selected and name not in selected:
                continue
            if name == "redis":
                cases.append(_run_real_redis_case(root, config, config_status, allow_writes=allow_writes))
            elif name == "elasticsearch":
                cases.append(_run_real_elasticsearch_case(root, config, config_status))
            else:
                cases.append(_run_real_sql_case(root, config, config_status, name, allow_writes=allow_writes))

    return {
        "ok": all(case.get("ok") for case in cases),
        "check": "database_components",
        "project_root": str(root),
        "include_real_db": include_real_db,
        "database_config_path": str(config_path) if config_path is not None else "",
        "database_config": config_status,
        "cases": cases,
        "commands": {
            "default": f"python {_cplan_script_path()} self-check database-components",
            "real_db": f"python {_cplan_script_path()} self-check database-components --include-real-db --allow-writes --database-config .\\local\\database-services.json",
        },
    }


def _run_sqlite_basic_case(project_root: Path) -> dict[str, Any]:
    plan_path = project_root / "test-plans" / "database" / "sqlite-basic" / "plan.json"
    started_at = time.time()
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        return _validation_failed_case("sqlite-basic", plan_path, validation)
    try:
        plan = load_plan(plan_path)
        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name="database-components-sqlite-basic",
            run_context_handler=_disable_run_log_echo,
        )
    except Exception as error:
        return _run_failed_case("sqlite-basic", plan_path, error)

    output_root = plan_path.parent / "output"
    rows_path = output_root / "sql" / "active-items.json"
    variables_path = output_root / "variables" / "sqlite-basic-variables.json"
    evidence = [
        _expect("run_passed", result.status == "passed"),
        _expect("active_rows_fresh", _file_nonempty_after(rows_path, started_at)),
        _expect("variables_fresh", _file_nonempty_after(variables_path, started_at)),
    ]
    try:
        rows = _read_json(rows_path)
        variables = _read_json(variables_path)
        evidence.extend(
            [
                _expect("active_row_count", isinstance(rows, list) and len(rows) == 2),
                _expect("active_count_value", _nested_value(variables, ("active_count", "value")) == 3),
            ]
        )
    except Exception as error:
        evidence.append({"name": "evidence_read", "ok": False, "error": str(error), "error_type": type(error).__name__})

    return {
        "name": "sqlite-basic",
        "ok": result.status == "passed" and all(item["ok"] for item in evidence),
        "plan_path": str(plan_path),
        "output_dir": result.output_dir,
        "evidence": evidence,
    }


def _run_sqlite_features_case(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="database-components-sqlite-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir) / "sqlite-features"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(json.dumps(_sqlite_features_plan(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        started_at = time.time()
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return _validation_failed_case("sqlite-features", plan_path, validation)
        try:
            plan = load_plan(plan_path)
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="database-components-sqlite-features",
                run_context_handler=_disable_run_log_echo,
            )
        except Exception as error:
            return _run_failed_case("sqlite-features", plan_path, error)

        output_root = package_dir / "output"
        jsonl_path = output_root / "sql" / "accounts.jsonl"
        page_path = output_root / "sql" / "accounts-page-2.json"
        bulk_path = output_root / "sql" / "bulk-batched.json"
        copy_path = output_root / "sql" / "copy-result.json"
        copy_rows_path = output_root / "sql" / "copy-rows.jsonl"
        transaction_path = output_root / "sql" / "transaction.json"
        variables_path = output_root / "variables" / "sqlite-features-variables.json"
        evidence = [
            _expect("run_passed", result.status == "passed"),
            _expect("jsonl_fresh", _file_nonempty_after(jsonl_path, started_at)),
            _expect("page_result_fresh", _file_nonempty_after(page_path, started_at)),
            _expect("bulk_result_fresh", _file_nonempty_after(bulk_path, started_at)),
            _expect("copy_result_fresh", _file_nonempty_after(copy_path, started_at)),
            _expect("copy_rows_fresh", _file_nonempty_after(copy_rows_path, started_at)),
            _expect("transaction_result_fresh", _file_nonempty_after(transaction_path, started_at)),
            _expect("variables_fresh", _file_nonempty_after(variables_path, started_at)),
        ]
        try:
            jsonl_rows = _read_jsonl(jsonl_path)
            page_rows = _read_json(page_path)
            bulk = _read_json(bulk_path)
            copy_result = _read_json(copy_path)
            copy_rows = _read_jsonl(copy_rows_path)
            transaction = _read_json(transaction_path)
            variables = _read_json(variables_path)
            evidence.extend(
                [
                    _expect("jsonl_row_count", len(jsonl_rows) == 5),
                    _expect("page_row_count", isinstance(page_rows, list) and len(page_rows) == 2),
                    _expect("page_row_ids", isinstance(page_rows, list) and [row.get("id") for row in page_rows] == [3, 4]),
                    _expect("bulk_batch_count", bulk.get("batch_count") == 3),
                    _expect("bulk_affected_rows", bulk.get("affected_rows") == 5),
                    _expect("copy_source_row_count", copy_result.get("source_row_count") == 5),
                    _expect("copy_input_rows", copy_result.get("input_rows") == 5),
                    _expect("copy_batch_count", copy_result.get("batch_count") == 3),
                    _expect("copy_rows_row_count", len(copy_rows) == 5),
                    _expect("copy_target_count", _nested_value(variables, ("copy_target_count", "value")) == 5),
                    _expect("transaction_committed", transaction.get("committed") is True),
                    _expect("transaction_step_count", transaction.get("step_count") == 2),
                    _expect("balance_after_transaction", _nested_value(variables, ("balance_after_tx", "value")) == 37),
                ]
            )
        except Exception as error:
            evidence.append({"name": "evidence_read", "ok": False, "error": str(error), "error_type": type(error).__name__})

        return {
            "name": "sqlite-features",
            "ok": result.status == "passed" and all(item["ok"] for item in evidence),
            "plan_path": str(plan_path),
            "output_dir": result.output_dir,
            "evidence": evidence,
        }


def _sqlite_features_plan() -> dict[str, Any]:
    return {
        "name": "database sqlite features",
        "automation_type": "browser",
        "variables": {
            "sqlite_connection": {"type": "sqlite", "path": "output/sql/sqlite-features.db"},
            "sqlite_target_connection": {"type": "sqlite", "path": "output/sql/sqlite-copy-target.db"},
            "seed_rows": [
                {"id": 1, "name": "alpha", "balance": 10},
                {"id": 2, "name": "beta", "balance": 20},
                {"id": 3, "name": "gamma", "balance": 30},
                {"id": 4, "name": "delta", "balance": 40},
                {"id": 5, "name": "epsilon", "balance": 50},
            ],
        },
        "steps": [
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_connection}}",
                "sql": "drop table if exists accounts",
            },
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_connection}}",
                "sql": "drop table if exists audit",
            },
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_target_connection}}",
                "sql": "drop table if exists account_export",
            },
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_connection}}",
                "sql": "create table accounts (id integer primary key, name text not null, balance integer not null)",
            },
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_connection}}",
                "sql": "create table audit (id integer primary key, account_id integer not null, note text not null)",
            },
            {
                "action": "sql",
                "type": "execute",
                "connection": "{{sqlite_target_connection}}",
                "sql": "create table account_export (account_id integer primary key, account_name text not null, balance integer not null)",
            },
            {
                "action": "sql",
                "type": "bulk_insert",
                "connection": "{{sqlite_connection}}",
                "table": "accounts",
                "rows": "{{seed_rows}}",
                "columns": ["id", "name", "balance"],
                "batch_size": 2,
                "result_path": "bulk-batched.json",
                "save_as": "bulk_result",
            },
            {
                "action": "sql",
                "type": "query",
                "connection": "{{sqlite_connection}}",
                "sql": "select id, name, balance from accounts order by id",
                "rows_path": "accounts.jsonl",
                "save_as": "account_rows",
            },
            {
                "action": "sql",
                "type": "query",
                "connection": "{{sqlite_connection}}",
                "sql": "select id, name, balance from accounts order by id",
                "page_size": 2,
                "page": 2,
                "rows_path": "accounts-page-2.json",
                "save_as": "account_page",
            },
            {
                "action": "sql",
                "type": "copy",
                "connection": "{{sqlite_connection}}",
                "target_connection": "{{sqlite_target_connection}}",
                "sql": "select id, name, balance from accounts order by id",
                "table": "account_export",
                "column_map": {
                    "account_id": "id",
                    "account_name": "name",
                    "balance": "balance"
                },
                "batch_size": 2,
                "result_path": "copy-result.json",
                "rows_path": "copy-rows.jsonl",
                "save_as": "copy_result",
            },
            {
                "action": "sql",
                "type": "scalar",
                "connection": "{{sqlite_target_connection}}",
                "sql": "select count(*) from account_export",
                "save_as": "copy_target_count",
            },
            {
                "action": "sql",
                "type": "transaction",
                "connection": "{{sqlite_connection}}",
                "steps": [
                    {
                        "type": "execute",
                        "name": "update_balance",
                        "sql": "update accounts set balance = balance + :delta where id = :id",
                        "params": {"delta": 7, "id": 3},
                        "expect_affected_rows": 1,
                    },
                    {
                        "type": "bulk_insert",
                        "name": "insert_audit",
                        "table": "audit",
                        "rows": [{"id": 1, "account_id": 3, "note": "balance adjusted"}],
                        "columns": ["id", "account_id", "note"],
                        "batch_size": 1,
                    },
                ],
                "result_path": "transaction.json",
                "save_as": "transaction_result",
            },
            {
                "action": "sql",
                "type": "scalar",
                "connection": "{{sqlite_connection}}",
                "sql": "select balance from accounts where id = :id",
                "params": {"id": 3},
                "save_as": "balance_after_tx",
            },
            {
                "action": "write",
                "type": "variables",
                "path": "sqlite-features-variables.json",
            },
        ],
    }


def _run_real_sql_case(
    project_root: Path,
    config: dict[str, Any],
    config_status: dict[str, Any],
    service_name: str,
    *,
    allow_writes: bool,
) -> dict[str, Any]:
    unresolved = _unresolved_env_refs_for_service(config, config_status, service_name)
    if unresolved:
        return _skipped_case(service_name, "database config 需要先设置环境变量。", unresolved_env_refs=unresolved)
    connection = _connection_for_service(config, service_name)
    if connection is None:
        return _skipped_case(service_name, f"未在 database config 中找到 {service_name} 连接。")
    table_name = _temporary_table_name(service_name)
    with tempfile.TemporaryDirectory(prefix=f"database-components-{service_name}-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir) / service_name
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan = _real_sql_plan(service_name, connection, allow_writes=allow_writes, table_name=table_name)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return _validation_failed_case(service_name, plan_path, validation)
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name=f"database-components-{service_name}",
                run_context_handler=_disable_run_log_echo,
            )
        except Exception as error:
            if allow_writes:
                _attempt_real_sql_cleanup(project_root, service_name, connection, table_name)
            return _run_failed_case(service_name, plan_path, error)

        output_root = package_dir / "output"
        smoke_path = output_root / "sql" / f"{service_name}-smoke.json"
        evidence = [_expect("run_passed", result.status == "passed")]
        try:
            smoke = _read_json(smoke_path)
            evidence.append(_expect("smoke_value", str(smoke.get("value")) == "1"))
            if allow_writes:
                count = _read_json(output_root / "sql" / f"{service_name}-write-count.json")
                bulk = _read_json(output_root / "sql" / f"{service_name}-bulk.json")
                evidence.extend(
                    [
                        _expect("write_count", str(count.get("value")) == "2"),
                        _expect("bulk_input_rows", bulk.get("input_rows") == 2),
                    ]
                )
        except Exception as error:
            evidence.append({"name": "evidence_read", "ok": False, "error": str(error), "error_type": type(error).__name__})
        return {
            "name": service_name,
            "ok": result.status == "passed" and all(item["ok"] for item in evidence),
            "allow_writes": allow_writes,
            "plan_path": str(plan_path),
            "output_dir": result.output_dir,
            "evidence": evidence,
        }


def _real_sql_plan(
    service_name: str,
    connection: dict[str, Any],
    *,
    allow_writes: bool,
    table_name: str,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "action": "sql",
            "type": "scalar",
            "connection": "{{db_connection}}",
            "sql": SQL_SERVICE_QUERIES[service_name],
            "result_path": f"{service_name}-smoke.json",
            "save_as": "smoke",
        }
    ]
    if allow_writes:
        create_sql, drop_sql = _table_ddl(service_name, table_name)
        steps.extend(
            [
                {"action": "sql", "type": "execute", "connection": "{{db_connection}}", "sql": create_sql},
                {
                    "action": "sql",
                    "type": "bulk_insert",
                    "connection": "{{db_connection}}",
                    "table": table_name,
                    "rows": [{"id": 1, "label": "alpha"}, {"id": 2, "label": "beta"}],
                    "columns": ["id", "label"],
                    "batch_size": 1,
                    "result_path": f"{service_name}-bulk.json",
                    "save_as": "bulk",
                },
                {
                    "action": "sql",
                    "type": "scalar",
                    "connection": "{{db_connection}}",
                    "sql": f"select count(*) from {table_name}",
                    "result_path": f"{service_name}-write-count.json",
                    "save_as": "write_count",
                },
                {"action": "sql", "type": "execute", "connection": "{{db_connection}}", "sql": drop_sql},
            ]
        )
    return {
        "name": f"database real {service_name}",
        "automation_type": "browser",
        "variables": {"db_connection": connection},
        "steps": steps,
    }


def _run_real_redis_case(
    project_root: Path,
    config: dict[str, Any],
    config_status: dict[str, Any],
    *,
    allow_writes: bool,
) -> dict[str, Any]:
    unresolved = _unresolved_env_refs_for_service(config, config_status, "redis")
    if unresolved:
        return _skipped_case("redis", "database config 需要先设置环境变量。", unresolved_env_refs=unresolved)
    connection = _connection_for_service(config, "redis")
    if connection is None:
        return _skipped_case("redis", "未在 database config 中找到 redis 连接。")
    key = f"aic:self-check:{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="database-components-redis-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir) / "redis"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan = _real_redis_plan(connection, allow_writes=allow_writes, key=key)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return _validation_failed_case("redis", plan_path, validation)
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="database-components-redis",
                run_context_handler=_disable_run_log_echo,
            )
        except Exception as error:
            if allow_writes:
                _attempt_redis_cleanup(project_root, connection, key)
            return _run_failed_case("redis", plan_path, error)

        evidence = [_expect("run_passed", result.status == "passed")]
        try:
            ping = _read_json(package_dir / "output" / "redis" / "redis-ping.json")
            ping_result = ping.get("result")
            evidence.append(_expect("ping_result", ping_result is True or str(ping_result).upper() == "PONG"))
            if allow_writes:
                pipeline = _read_json(package_dir / "output" / "redis" / "redis-pipeline.json")
                result_values = pipeline.get("result", [])
                evidence.append(_expect("pipeline_get_value", isinstance(result_values, list) and "value" in result_values))
        except Exception as error:
            evidence.append({"name": "evidence_read", "ok": False, "error": str(error), "error_type": type(error).__name__})
        return {
            "name": "redis",
            "ok": result.status == "passed" and all(item["ok"] for item in evidence),
            "allow_writes": allow_writes,
            "plan_path": str(plan_path),
            "output_dir": result.output_dir,
            "evidence": evidence,
        }


def _real_redis_plan(connection: dict[str, Any], *, allow_writes: bool, key: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "action": "redis",
            "type": "command",
            "connection": "{{redis_connection}}",
            "command": "PING",
            "result_path": "redis-ping.json",
            "save_as": "ping",
        }
    ]
    if allow_writes:
        steps.append(
            {
                "action": "redis",
                "type": "pipeline",
                "connection": "{{redis_connection}}",
                "commands": [
                    {"command": "DEL", "args": [key]},
                    {"command": "SET", "args": [key, "value", "EX", 60]},
                    {"command": "GET", "args": [key]},
                    {"command": "DEL", "args": [key]},
                ],
                "batch_size": 2,
                "result_path": "redis-pipeline.json",
                "save_as": "pipeline",
            }
        )
    return {
        "name": "database real redis",
        "automation_type": "browser",
        "variables": {"redis_connection": connection},
        "steps": steps,
    }


def _attempt_redis_cleanup(project_root: Path, connection: dict[str, Any], key: str) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="database-components-cleanup-redis-") as raw_temp_dir:
            package_dir = Path(raw_temp_dir) / "redis"
            package_dir.mkdir(parents=True, exist_ok=True)
            plan_path = package_dir / "plan.json"
            plan = {
                "name": "database cleanup redis",
                "automation_type": "browser",
                "variables": {"redis_connection": connection},
                "steps": [
                    {
                        "action": "redis",
                        "type": "delete",
                        "connection": "{{redis_connection}}",
                        "key": key,
                    }
                ],
            }
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="database-components-cleanup-redis",
                run_context_handler=_disable_run_log_echo,
            )
    except Exception:
        return


def _run_real_elasticsearch_case(
    project_root: Path,
    config: dict[str, Any],
    config_status: dict[str, Any],
) -> dict[str, Any]:
    unresolved = _unresolved_env_refs_for_service(config, config_status, "elasticsearch")
    if unresolved:
        return _skipped_case("elasticsearch", "database config 需要先设置环境变量。", unresolved_env_refs=unresolved)
    elasticsearch = _elasticsearch_config(config)
    if elasticsearch is None:
        return _skipped_case("elasticsearch", "未在 database config 中找到 elasticsearch.url 或 elasticsearch.base_url。")
    with tempfile.TemporaryDirectory(prefix="database-components-elasticsearch-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir) / "elasticsearch"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan = _real_elasticsearch_plan(elasticsearch)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return _validation_failed_case("elasticsearch", plan_path, validation)
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="database-components-elasticsearch",
                run_context_handler=_disable_run_log_echo,
            )
        except Exception as error:
            return _run_failed_case("elasticsearch", plan_path, error)

        body_path = package_dir / "output" / "http" / "elasticsearch-root.json"
        evidence = [
            _expect("run_passed", result.status == "passed"),
            _expect("body_saved", _file_nonempty(body_path)),
        ]
        return {
            "name": "elasticsearch",
            "ok": result.status == "passed" and all(item["ok"] for item in evidence),
            "plan_path": str(plan_path),
            "output_dir": result.output_dir,
            "evidence": evidence,
        }


def _real_elasticsearch_plan(config: dict[str, Any]) -> dict[str, Any]:
    step: dict[str, Any] = {
        "action": "http",
        "type": "request",
        "method": "GET",
        "url": _join_url(str(config.get("url") or config.get("base_url") or ""), "/"),
        "expect_status": 200,
        "body_type": "json",
        "response_body_path": "elasticsearch-root.json",
        "save_as": "elasticsearch",
    }
    for field in ("headers", "auth", "verify_tls", "timeout_ms"):
        if field in config:
            step[field] = config[field]
    return {
        "name": "database real elasticsearch via http",
        "automation_type": "browser",
        "steps": [step],
    }


def _connection_for_service(config: dict[str, Any], service_name: str) -> dict[str, Any] | None:
    service_options = _service_options(config, service_name)
    raw_connection = service_options.get("connection")
    if isinstance(raw_connection, dict):
        return _with_default_type(raw_connection, service_name)
    if isinstance(raw_connection, str) and raw_connection:
        found = _named_connection(config, raw_connection)
        return _with_default_type(found, service_name) if found is not None else None
    direct = config.get(service_name)
    if isinstance(direct, dict) and any(key in direct for key in ("type", "driver", "dsn", "url", "host", "path")):
        return _with_default_type(direct, service_name)
    for alias in SQL_SERVICE_ALIASES.get(service_name, (service_name,)):
        found = _named_connection(config, alias)
        if found is not None:
            return _with_default_type(found, service_name)
    return None


def _with_default_type(connection: dict[str, Any], service_name: str) -> dict[str, Any]:
    result = dict(connection)
    if service_name in {"mysql", "postgresql", "oracle", "redis"}:
        result.setdefault("type", service_name)
    return result


def _named_connection(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    connections = config.get("connections")
    if isinstance(connections, dict) and isinstance(connections.get(name), dict):
        result = dict(connections[name])
        result.setdefault("name", name)
        return result
    return None


def _service_options(config: dict[str, Any], service_name: str) -> dict[str, Any]:
    services = config.get("services")
    if isinstance(services, dict) and isinstance(services.get(service_name), dict):
        return dict(services[service_name])
    direct = config.get(service_name)
    if isinstance(direct, dict):
        return dict(direct)
    return {}


def _elasticsearch_config(config: dict[str, Any]) -> dict[str, Any] | None:
    service_options = _service_options(config, "elasticsearch")
    if isinstance(service_options.get("connection"), dict):
        service_options = dict(service_options["connection"])
    if service_options.get("url") or service_options.get("base_url"):
        return service_options
    direct = config.get("elasticsearch")
    if isinstance(direct, str) and direct:
        return {"url": direct}
    return None


def _resolve_database_config_path(root: Path, raw_path: str | Path | None) -> Path | None:
    if raw_path:
        path = Path(raw_path)
        return path.resolve() if path.is_absolute() else (root / path).resolve()
    default_path = root / "local" / "database-services.json"
    return default_path if default_path.exists() else None


def _load_database_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"database config 必须是 JSON 对象：{path}")
    env_refs: list[dict[str, Any]] = []
    resolved = _resolve_env_refs(data, path="", env_refs=env_refs)
    unresolved = [ref for ref in env_refs if ref.get("missing")]
    return resolved, {
        "path": str(path),
        "path_exists": True,
        "loaded": True,
        "load_ok": True,
        "env_ref_count": len(env_refs),
        "unresolved_env_ref_count": len(unresolved),
        "env_refs": env_refs,
        "unresolved_env_refs": unresolved,
    }


def _empty_database_config_status(path: Path | None) -> dict[str, Any]:
    return {
        "path": str(path) if path is not None else "",
        "path_exists": bool(path is not None and path.exists()),
        "loaded": False,
        "load_ok": True,
        "env_ref_count": 0,
        "unresolved_env_ref_count": 0,
        "env_refs": [],
        "unresolved_env_refs": [],
    }


def _resolve_env_refs(value: Any, *, path: str, env_refs: list[dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if _is_env_ref_object(value):
            env_name = str(value.get("env") or value.get("env_var") or "")
            env_value = os.environ.get(env_name)
            has_default = "default" in value
            missing = env_value is None and not has_default
            env_refs.append(
                {
                    "path": path,
                    "env": env_name,
                    "resolved": env_value is not None,
                    "used_default": env_value is None and has_default,
                    "missing": missing,
                }
            )
            if env_value is not None:
                return env_value
            if has_default:
                return value["default"]
            return ""
        return {key: _resolve_env_refs(item, path=_join_config_path(path, str(key)), env_refs=env_refs) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_refs(item, path=f"{path}[{index}]", env_refs=env_refs) for index, item in enumerate(value)]
    if isinstance(value, str):
        env_name = _string_env_ref_name(value)
        if env_name:
            env_value = os.environ.get(env_name)
            missing = env_value is None
            env_refs.append(
                {
                    "path": path,
                    "env": env_name,
                    "resolved": env_value is not None,
                    "used_default": False,
                    "missing": missing,
                }
            )
            return env_value if env_value is not None else ""
    return value


def _is_env_ref_object(value: dict[str, Any]) -> bool:
    keys = set(value)
    return bool(keys & {"env", "env_var"}) and keys <= {"env", "env_var", "default"}


def _string_env_ref_name(value: str) -> str | None:
    text = value.strip()
    if text.startswith("env:") and len(text) > 4:
        return text[4:]
    if text.startswith("$env:") and len(text) > 5:
        return text[5:]
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        return text[2:-1]
    return None


def _join_config_path(parent: str, child: str) -> str:
    return f"{parent}.{child}" if parent else child


def _unresolved_env_refs_for_service(config: dict[str, Any], config_status: dict[str, Any], service_name: str) -> list[dict[str, Any]]:
    unresolved = config_status.get("unresolved_env_refs")
    if not isinstance(unresolved, list) or not unresolved:
        return []
    aliases = set(SQL_SERVICE_ALIASES.get(service_name, (service_name,)))
    aliases.add(service_name)
    connection_names = set(aliases)
    service_options = _service_options(config, service_name)
    raw_connection = service_options.get("connection")
    if isinstance(raw_connection, str) and raw_connection:
        connection_names.add(raw_connection)
    prefixes: list[str] = []
    for alias in aliases:
        prefixes.extend([f"{alias}.", f"services.{alias}."])
    for name in connection_names:
        prefixes.append(f"connections.{name}.")
    if service_name == "elasticsearch":
        prefixes.extend(["elasticsearch.", "services.elasticsearch."])
    return [ref for ref in unresolved if any(str(ref.get("path", "")).startswith(prefix) for prefix in prefixes)]


def _temporary_table_name(service_name: str) -> str:
    suffix = uuid.uuid4().hex[:12]
    if service_name == "oracle":
        return f"AIC_DB_CHECK_{suffix}".upper()
    return f"aic_db_check_{suffix}"


def _table_ddl(service_name: str, table_name: str) -> tuple[str, str]:
    if service_name == "oracle":
        return (
            f"create table {table_name} (id number primary key, label varchar2(64))",
            f"drop table {table_name} purge",
        )
    return (
        f"create table {table_name} (id integer primary key, label varchar(64))",
        f"drop table {table_name}",
    )


def _attempt_real_sql_cleanup(project_root: Path, service_name: str, connection: dict[str, Any], table_name: str) -> None:
    _create_sql, drop_sql = _table_ddl(service_name, table_name)
    try:
        with tempfile.TemporaryDirectory(prefix=f"database-components-cleanup-{service_name}-") as raw_temp_dir:
            package_dir = Path(raw_temp_dir) / service_name
            package_dir.mkdir(parents=True, exist_ok=True)
            plan_path = package_dir / "plan.json"
            plan = {
                "name": f"database cleanup {service_name}",
                "automation_type": "browser",
                "variables": {"db_connection": connection},
                "steps": [{"action": "sql", "type": "execute", "connection": "{{db_connection}}", "sql": drop_sql}],
            }
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name=f"database-components-cleanup-{service_name}",
                run_context_handler=_disable_run_log_echo,
            )
    except Exception:
        return


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _validation_failed_case(name: str, plan_path: Path, validation: Any) -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "plan_path": str(plan_path),
        "validation_ok": False,
        "errors": [error.format() for error in validation.errors],
    }


def _run_failed_case(name: str, plan_path: Path, error: Exception) -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "plan_path": str(plan_path),
        "validation_ok": True,
        "run_ok": False,
        "error": str(error),
        "error_type": type(error).__name__,
    }


def _skipped_case(name: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "ok": True, "skipped": True, "reason": reason, **extra}


def _disable_run_log_echo(_output_dir: Path, logger: Any) -> None:
    logger.echo = False


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_jsonl(path: Path) -> list[Any]:
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _nested_value(data: Any, path: tuple[str, ...]) -> Any:
    value = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _file_nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _file_nonempty_after(path: Path, started_at: float) -> bool:
    return _file_nonempty(path) and path.stat().st_mtime >= started_at - 1.0


def _expect(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok)}


def _requested_case_names(only: list[str] | None) -> list[str]:
    names: list[str] = []
    for raw_item in only or []:
        for raw_name in str(raw_item or "").split(","):
            name = raw_name.strip()
            if name and name not in names:
                names.append(name)
    return names


def _cplan_script_path() -> str:
    return ".\\cplan.py" if platform.system() == "Windows" else "./cplan.py"
