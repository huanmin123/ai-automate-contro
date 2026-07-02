from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.templates import create_plan_package_from_template, list_plan_templates
from ai_automate_contro.plans.validator import validate_plan_file


def self_check_template_components(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    templates = list_plan_templates()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="template-components-") as raw_temp_dir:
        temp_root = Path(raw_temp_dir).resolve()
        for template in templates:
            results.append(_check_template(temp_root, template))
        parameterized_result = _check_parameterized_template(temp_root, templates)
    return {
        "ok": all(result.get("ok") for result in results) and bool(parameterized_result.get("ok")),
        "check": "template_components",
        "project_root": str(root),
        "templates": [
            {
                "id": template["id"],
                "automation_type": template["automation_type"],
                "offline_runnable": template["offline_runnable"],
                "run_by_default": template["run_by_default"],
            }
            for template in templates
        ],
        "results": results,
        "parameterized_result": parameterized_result,
    }


def _check_template(project_root: Path, template: dict[str, Any]) -> dict[str, Any]:
    template_id = str(template["id"])
    package_dir = project_root / "plans" / template_id
    try:
        created_dir = create_plan_package_from_template(
            package_dir,
            project_root=project_root,
            template_id=template_id,
            force=False,
        )
    except Exception as error:
        return {
            "id": template_id,
            "ok": False,
            "stage": "create",
            "error_type": type(error).__name__,
            "error": str(error),
        }

    plan_path = created_dir / "plan.json"
    validation = validate_plan_file(plan_path, project_root)
    structure_checks = [
        *_structure_checks(created_dir, template),
        *_template_param_contract_checks(project_root, template),
    ]
    run_result: dict[str, Any] | None = None
    if validation.ok and bool(template.get("run_by_default")):
        run_result = _run_template(project_root, plan_path, template)
    if validation.ok and template_id == "api-to-excel":
        run_result = _run_api_to_excel_template(project_root, template)
    ok = validation.ok and all(check["ok"] for check in structure_checks) and (run_result is None or run_result["ok"])
    return {
        "id": template_id,
        "ok": ok,
        "package_dir": str(created_dir),
        "validation": {
            "ok": validation.ok,
            "errors": [issue.format() for issue in validation.errors],
        },
        "structure_checks": structure_checks,
        "run": run_result,
    }


def _structure_checks(package_dir: Path, template: dict[str, Any]) -> list[dict[str, Any]]:
    resources = list((package_dir / "resources").rglob("*")) if (package_dir / "resources").exists() else []
    return [
        {"name": "plan_json_exists", "ok": (package_dir / "plan.json").is_file()},
        {"name": "config_json_exists", "ok": (package_dir / "config.json").is_file()},
        {"name": "docs_readme_exists", "ok": (package_dir / "docs" / "README.md").is_file()},
        {
            "name": "resource_presence_matches_template",
            "ok": bool(resources) or str(template.get("id")) == "desktop-file-dialog-batch",
        },
    ]


def _template_param_contract_checks(project_root: Path, template: dict[str, Any]) -> list[dict[str, Any]]:
    template_id = str(template["id"])
    variables = template.get("variables") if isinstance(template.get("variables"), list) else []
    checks: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for variable in variables:
        if not isinstance(variable, dict):
            checks.append({"name": "template_param_metadata_shape", "ok": False, "parameter": variable})
            continue
        name = str(variable.get("name") or "").strip()
        parameter_type = str(variable.get("type") or "").strip()
        base_check = {
            "name": "template_param_metadata",
            "parameter": name,
            "type": parameter_type,
            "ok": bool(name) and bool(parameter_type) and name not in seen_names,
        }
        checks.append(base_check)
        if not base_check["ok"]:
            continue
        seen_names.add(name)
        invalid_value = _invalid_template_param_value(variable)
        invalid_error = ""
        try:
            create_plan_package_from_template(
                project_root / "plans" / f"{template_id}-invalid-{name}",
                project_root=project_root,
                template_id=template_id,
                template_params={name: invalid_value},
            )
        except Exception as error:
            invalid_error = str(error)
        checks.append(
            {
                "name": "template_param_type_rejects_invalid_value",
                "parameter": name,
                "type": parameter_type,
                "ok": name in invalid_error and "必须是" in invalid_error,
                "error": invalid_error,
            }
        )
    return checks


def _invalid_template_param_value(parameter: dict[str, Any]) -> Any:
    parameter_type = str(parameter.get("type") or "string").strip().lower()
    if parameter_type == "string":
        return {"not": "a string"}
    if parameter_type == "number":
        return "not-a-number"
    if parameter_type == "boolean":
        return "not-a-boolean"
    if parameter_type == "object":
        return "not-an-object"
    if parameter_type == "array":
        if str(parameter.get("item_type") or "").strip().lower() == "object":
            return ["not-an-object"]
        return "not-an-array"
    return object()


def _run_template(project_root: Path, plan_path: Path, template: dict[str, Any]) -> dict[str, Any]:
    template_id = str(template["id"])
    try:
        plan = load_plan(plan_path)
        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name=f"template-{template_id}",
            log_echo=False,
        )
    except Exception as error:
        return {
            "ok": False,
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
    expected_output_checks = []
    package_dir = plan_path.parent
    for raw_relative_path in template.get("expected_outputs", []):
        relative_path = Path(str(raw_relative_path))
        output_path = package_dir / relative_path
        expected_output_checks.append(
            {
                "path": str(relative_path).replace("\\", "/"),
                "ok": output_path.is_file() and output_path.stat().st_size > 0,
                "bytes": output_path.stat().st_size if output_path.exists() else 0,
            }
        )
    return {
        "ok": result.status == "passed" and all(check["ok"] for check in expected_output_checks),
        "status": result.status,
        "output_dir": str(result.output_dir),
        "expected_outputs": expected_output_checks,
    }


def _run_api_to_excel_template(project_root: Path, template: dict[str, Any]) -> dict[str, Any]:
    port = _free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    package_dir = project_root / "plans" / "api-to-excel-run"
    process: subprocess.Popen[str] | None = None
    try:
        created_dir = create_plan_package_from_template(
            package_dir,
            project_root=project_root,
            template_id="api-to-excel",
            template_params={"api_base_url": base_url},
        )
        server_path = created_dir / "resources" / "api-to-excel" / "server.py"
        env = os.environ.copy()
        env["AIC_TEMPLATE_API_PORT"] = str(port)
        process = subprocess.Popen(
            [sys.executable, str(server_path)],
            cwd=str(created_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        server_ready = _wait_for_api_server(base_url, process)
        if not server_ready["ok"]:
            return {
                "ok": False,
                "status": "failed",
                "stage": "api_server",
                "base_url": base_url,
                "server_ready": server_ready,
            }
        run_result = _run_template(project_root, created_dir / "plan.json", template)
        orders_report = _read_json(created_dir / "output" / "json" / "api-to-excel" / "orders.json")
        orders = orders_report.get("orders") if isinstance(orders_report, dict) else []
        if not isinstance(orders, list):
            orders = []
        order_ids = sorted(str(row.get("order_id") or "") for row in orders if isinstance(row, dict))
        statuses = sorted({str(row.get("status") or "") for row in orders if isinstance(row, dict)})
        return {
            "ok": run_result.get("ok") is True and order_ids == ["SO-2001", "SO-2003"] and statuses == ["ready"],
            "status": run_result.get("status"),
            "base_url": base_url,
            "server_ready": server_ready,
            "run": run_result,
            "order_ids": order_ids,
            "statuses": statuses,
        }
    except Exception as error:
        return {
            "ok": False,
            "status": "failed",
            "stage": "api_to_excel_run",
            "base_url": base_url,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_api_server(base_url: str, process: subprocess.Popen[str], *, timeout_seconds: float = 8.0) -> dict[str, Any]:
    url = f"{base_url}/orders"
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            return {
                "ok": False,
                "url": url,
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "error": "server process exited before it became ready",
            }
        try:
            request = urllib.request.Request(url, headers={"accept": "application/json"})
            with urllib.request.urlopen(request, timeout=0.5) as response:
                body = response.read()
            return {"ok": True, "url": url, "status": 200, "bytes": len(body)}
        except Exception as error:
            last_error = str(error)
            time.sleep(0.1)
    return {"ok": False, "url": url, "error": last_error or "server readiness timed out"}


def _check_parameterized_template(project_root: Path, templates: list[dict[str, Any]]) -> dict[str, Any]:
    excel_template = next((item for item in templates if item.get("id") == "excel-cleaning-report"), None)
    sql_template = next((item for item in templates if item.get("id") == "sql-import-export"), None)
    if excel_template is None:
        return {"ok": False, "stage": "lookup", "error": "缺少 excel-cleaning-report 模板。"}
    if sql_template is None:
        return {"ok": False, "stage": "lookup", "error": "缺少 sql-import-export 模板。"}
    try:
        excel_created_dir = create_plan_package_from_template(
            project_root / "plans" / "excel-cleaning-report-params",
            project_root=project_root,
            template_id="excel-cleaning-report",
            template_params={"active_status": "Inactive"},
        )
        unsupported_error = ""
        try:
            create_plan_package_from_template(
                project_root / "plans" / "excel-cleaning-report-bad-param",
                project_root=project_root,
                template_id="excel-cleaning-report",
                template_params={"unknown": "value"},
            )
        except Exception as error:
            unsupported_error = str(error)
        excel_plan_path = excel_created_dir / "plan.json"
        excel_plan = _read_json(excel_plan_path)
        excel_validation = validate_plan_file(excel_plan_path, project_root)
        excel_run_result = _run_template(project_root, excel_plan_path, excel_template)
        excel_report = _read_json(excel_created_dir / "output" / "json" / "excel-cleaning-report" / "report.json")
        active_employees = excel_report.get("active_employees") if isinstance(excel_report, dict) else []
        statuses = sorted(
            {
                str(row.get("Status") or "")
                for row in active_employees
                if isinstance(row, dict)
            }
        )
        names = sorted(
            {
                str(row.get("Name") or "")
                for row in active_employees
                if isinstance(row, dict)
            }
        )

        sql_created_dir = create_plan_package_from_template(
            project_root / "plans" / "sql-import-export-params",
            project_root=project_root,
            template_id="sql-import-export",
            template_params={"minimum_balance": "100"},
        )
        sql_plan_path = sql_created_dir / "plan.json"
        sql_plan = _read_json(sql_plan_path)
        sql_validation = validate_plan_file(sql_plan_path, project_root)
        sql_run_result = _run_template(project_root, sql_plan_path, sql_template)
        active_accounts = _read_json(sql_created_dir / "output" / "sql" / "sql-import-export" / "active-accounts.json")
        account_names = sorted(
            str(row.get("name") or "")
            for row in active_accounts
            if isinstance(row, dict)
        )
    except Exception as error:
        return {
            "ok": False,
            "stage": "parameterized_create_run",
            "error_type": type(error).__name__,
            "error": str(error),
        }
    return {
        "ok": (
            excel_validation.ok
            and excel_run_result.get("ok") is True
            and excel_plan.get("variables", {}).get("active_status") == "Inactive"
            and statuses == ["Inactive"]
            and names == ["Bob"]
            and "不支持参数 unknown" in unsupported_error
            and sql_validation.ok
            and sql_run_result.get("ok") is True
            and sql_plan.get("variables", {}).get("minimum_balance") == 100
            and account_names == ["Alice"]
        ),
        "template_id": "parameterized-templates",
        "excel": {
            "validation": {
                "ok": excel_validation.ok,
                "errors": [issue.format() for issue in excel_validation.errors],
            },
            "run": excel_run_result,
            "active_status": excel_plan.get("variables", {}).get("active_status"),
            "result_statuses": statuses,
            "result_names": names,
        },
        "sql": {
            "validation": {
                "ok": sql_validation.ok,
                "errors": [issue.format() for issue in sql_validation.errors],
            },
            "run": sql_run_result,
            "minimum_balance": sql_plan.get("variables", {}).get("minimum_balance"),
            "result_names": account_names,
        },
        "unsupported_error": unsupported_error,
    }
