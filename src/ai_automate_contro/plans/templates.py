from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_automate_contro.support.paths import path_from_text


TemplateWriter = Callable[[Path, str], None]


@dataclass(frozen=True)
class PlanTemplate:
    id: str
    title: str
    automation_type: str
    description: str
    variables: tuple[dict[str, Any], ...]
    risk_notes: tuple[str, ...]
    offline_runnable: bool
    run_by_default: bool
    expected_outputs: tuple[str, ...]
    writer: TemplateWriter


def list_plan_templates() -> list[dict[str, Any]]:
    return [_template_summary(template) for template in _templates()]


def get_plan_template(template_id: str) -> dict[str, Any]:
    return _template_summary(_require_template(template_id))


def parse_template_param_pairs(raw_params: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for raw_param in raw_params or []:
        text = str(raw_param)
        if "=" not in text:
            raise ValueError(f"模板参数格式必须是 key=value：{text}")
        raw_key, raw_value = text.split("=", 1)
        key = raw_key.strip()
        if not key:
            raise ValueError(f"模板参数名称不能为空：{text}")
        if key in params:
            raise ValueError(f"重复的模板参数：{key}")
        params[key] = _parse_template_param_value(raw_value)
    return params


def create_plan_package_from_template(
    raw_path: str | Path,
    *,
    project_root: Path,
    template_id: str,
    name: str | None = None,
    automation_type: str | None = None,
    template_params: Mapping[str, Any] | None = None,
    force: bool = False,
) -> Path:
    template = _require_template(template_id)
    if automation_type and automation_type != template.automation_type:
        raise ValueError(
            f"模板 {template.id} 的执行线是 {template.automation_type}，不能用 automation_type={automation_type} 创建。"
        )
    normalized_params = _normalize_template_params(template, template_params)
    package_dir = _prepare_package_dir(raw_path, force=force)
    _write_common_dirs(package_dir)
    plan_name = name or template.title
    template.writer(package_dir, plan_name)
    if normalized_params:
        _apply_template_params(package_dir, template, normalized_params)
    return package_dir


def _templates() -> tuple[PlanTemplate, ...]:
    return (
        PlanTemplate(
            id="browser-login-extract",
            title="Browser Login Extract",
            automation_type="browser",
            description="打开网页、填写登录表单、抽取页面表格，并写出 JSON/CSV/Excel。",
            variables=(
                {"name": "login_url", "type": "string", "description": "入口 URL；默认指向模板自带本地 HTML。"},
                {"name": "username", "type": "string", "description": "示例登录用户名；真实站点按用户授权填写。"},
                {"name": "password", "type": "string", "description": "示例登录密码；真实站点可改为 config 或人工登录。"},
            ),
            risk_notes=(
                "真实网站最终 plan 前仍必须先用 inspect_web_page 或 headed 探索 plan 取证。",
                "验证码、二次验证或权限流程用 manual_confirm 交给用户。",
            ),
            offline_runnable=True,
            run_by_default=True,
            expected_outputs=(
                "output/json/browser-login-extract/table.json",
                "output/csv/browser-login-extract/table.csv",
                "output/excel/browser-login-extract/table.xlsx",
            ),
            writer=_write_browser_login_extract_template,
        ),
        PlanTemplate(
            id="excel-cleaning-report",
            title="Excel Cleaning Report",
            automation_type="browser",
            description="读取 Excel，筛选、填空、类型转换、分组汇总，并写出报表。",
            variables=(
                {"name": "source_workbook", "type": "string", "description": "输入工作簿路径；默认使用 resources/ 下的样例。"},
                {"name": "active_status", "type": "string", "description": "要保留的状态值。"},
            ),
            risk_notes=(
                "纯文件数据处理不需要真实浏览器；这里使用 browser 执行线承载 common action。",
                "大表处理应按现有 read.excel 的 preview_rows、limit_rows 和 max_cells 控制范围。",
            ),
            offline_runnable=True,
            run_by_default=True,
            expected_outputs=(
                "output/json/excel-cleaning-report/report.json",
                "output/excel/excel-cleaning-report/report.xlsx",
            ),
            writer=_write_excel_cleaning_report_template,
        ),
        PlanTemplate(
            id="api-to-excel",
            title="API To Excel",
            automation_type="browser",
            description="请求 HTTP API，筛选 JSON 数组，并写出 JSON/CSV/Excel。",
            variables=(
                {"name": "api_base_url", "type": "string", "description": "API 根地址；默认使用模板自带本地 Python 服务端口。"},
                {"name": "order_status", "type": "string", "description": "要保留的订单状态。"},
            ),
            risk_notes=(
                "模板自带 server.py 需要在另一个 PowerShell 终端手动启动。",
                "真实 API 的认证头、分页、限流、重试和字段映射按接口文档调整。",
            ),
            offline_runnable=False,
            run_by_default=False,
            expected_outputs=(
                "output/json/api-to-excel/orders.json",
                "output/csv/api-to-excel/orders.csv",
                "output/excel/api-to-excel/orders.xlsx",
            ),
            writer=_write_api_to_excel_template,
        ),
        PlanTemplate(
            id="browser-download-process",
            title="Browser Download Process",
            automation_type="browser",
            description="触发浏览器下载 CSV，读取下载文件，筛选后写出 JSON/CSV/Excel。",
            variables=(
                {"name": "download_page_url", "type": "string", "description": "下载页 URL；默认指向模板自带本地 HTML。"},
                {"name": "target_status", "type": "string", "description": "要保留的订单状态。"},
            ),
            risk_notes=(
                "真实网站下载前仍需要先用 headed 探索或 manual_confirm 处理登录、验证码和权限。",
                "下载后的读取路径来自 wait_for_download 输出，不要手写 output/downloads 绝对路径。",
            ),
            offline_runnable=True,
            run_by_default=True,
            expected_outputs=(
                "output/downloads/browser-download-process/orders.csv",
                "output/json/browser-download-process/ready-orders.json",
                "output/csv/browser-download-process/ready-orders.csv",
                "output/excel/browser-download-process/ready-orders.xlsx",
            ),
            writer=_write_browser_download_process_template,
        ),
        PlanTemplate(
            id="sql-import-export",
            title="SQL Import Export",
            automation_type="browser",
            description="把 CSV 导入 SQLite，查询筛选结果，导出 Excel，并写出 JSON 报告。",
            variables=(
                {"name": "sqlite_connection", "type": "object", "description": "SQLite 连接对象；默认写入当前 plan 包 output/sql/。"},
                {"name": "source_csv", "type": "string", "description": "输入 CSV 路径；默认使用 resources/ 下样例。"},
                {"name": "target_status", "type": "string", "description": "要导出的客户状态。"},
                {"name": "minimum_balance", "type": "number", "description": "最低余额过滤条件。"},
            ),
            risk_notes=(
                "SQLite 是本地离线默认路径；真实 MySQL/PostgreSQL/SQL Server/Oracle 需按目标驱动配置连接。",
                "生产库写入前必须确认表名、字段映射、冲突键、事务和写入权限。",
            ),
            offline_runnable=True,
            run_by_default=True,
            expected_outputs=(
                "output/sql/sql-import-export/import-result.json",
                "output/sql/sql-import-export/active-accounts.json",
                "output/sql/sql-import-export/active-accounts.xlsx",
                "output/sql/sql-import-export/export-result.json",
                "output/json/sql-import-export/report.json",
            ),
            writer=_write_sql_import_export_template,
        ),
        PlanTemplate(
            id="desktop-file-dialog-batch",
            title="Desktop File Dialog Batch",
            automation_type="desktop",
            description="桌面文件打开/保存对话框批处理脚手架，保留观察、人工确认和截图证据。",
            variables=(
                {"name": "files", "type": "array", "item_type": "object", "description": "待处理文件和保存路径列表。"},
                {"name": "open_dialog_title", "type": "string", "description": "打开文件对话框标题片段。"},
                {"name": "save_dialog_title", "type": "string", "description": "保存文件对话框标题片段。"},
            ),
            risk_notes=(
                "默认模板不自动操作真实业务 App；用户需要先确认目标窗口和文件对话框。",
                "真实桌面 App 最终 plan 前必须先用 inspect_desktop 或 desktop_capture type=observe 取证。",
            ),
            offline_runnable=False,
            run_by_default=False,
            expected_outputs=(),
            writer=_write_desktop_file_dialog_batch_template,
        ),
    )


def _require_template(template_id: str) -> PlanTemplate:
    normalized = str(template_id or "").strip()
    for template in _templates():
        if template.id == normalized:
            return template
    supported = ", ".join(template.id for template in _templates())
    raise ValueError(f"不支持的 plan 模板：{template_id}。支持的模板：{supported}")


def _template_summary(template: PlanTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "title": template.title,
        "automation_type": template.automation_type,
        "description": template.description,
        "variables": list(template.variables),
        "parameters": list(template.variables),
        "risk_notes": list(template.risk_notes),
        "offline_runnable": template.offline_runnable,
        "run_by_default": template.run_by_default,
        "expected_outputs": list(template.expected_outputs),
    }


def _parse_template_param_value(raw_value: str) -> Any:
    text = str(raw_value).strip()
    if not text:
        return ""
    if text[:1] in {"{", "[", '"'} or text.lower() in {"true", "false", "null"}:
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"模板参数 JSON 值格式不正确：{text}") from error
    return text


def _normalize_template_params(template: PlanTemplate, params: Mapping[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    parameters = _template_parameters_by_name(template)
    allowed_names = set(parameters)
    normalized: dict[str, Any] = {}
    for raw_key, value in params.items():
        key = str(raw_key or "").strip()
        if not key:
            raise ValueError("模板参数名称不能为空。")
        if key not in allowed_names:
            supported = ", ".join(sorted(allowed_names))
            raise ValueError(f"模板 {template.id} 不支持参数 {key}。支持的参数：{supported}")
        normalized[key] = _normalize_template_param_value(template, parameters[key], value)
    return normalized


def _template_parameters_by_name(template: PlanTemplate) -> dict[str, dict[str, Any]]:
    parameters: dict[str, dict[str, Any]] = {}
    for item in template.variables:
        name = str(item.get("name") or "").strip()
        if name:
            parameters[name] = dict(item)
    return parameters


def _normalize_template_param_value(template: PlanTemplate, parameter: dict[str, Any], value: Any) -> Any:
    name = str(parameter.get("name") or "").strip()
    expected_type = str(parameter.get("type") or "string").strip().lower()
    if expected_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"模板 {template.id} 参数 {name} 必须是 string。")
        return value
    if expected_type == "number":
        if isinstance(value, bool):
            raise ValueError(f"模板 {template.id} 参数 {name} 必须是 number。")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            text = value.strip()
            try:
                return float(text) if any(marker in text.lower() for marker in (".", "e")) else int(text)
            except ValueError as error:
                raise ValueError(f"模板 {template.id} 参数 {name} 必须是 number。") from error
        raise ValueError(f"模板 {template.id} 参数 {name} 必须是 number。")
    if expected_type == "boolean":
        if isinstance(value, bool):
            return value
        raise ValueError(f"模板 {template.id} 参数 {name} 必须是 boolean。")
    if expected_type == "object":
        if isinstance(value, dict):
            return value
        raise ValueError(f"模板 {template.id} 参数 {name} 必须是 object。")
    if expected_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"模板 {template.id} 参数 {name} 必须是 array。")
        item_type = str(parameter.get("item_type") or "").strip().lower()
        if item_type == "object" and any(not isinstance(item, dict) for item in value):
            raise ValueError(f"模板 {template.id} 参数 {name} 的每一项必须是 object。")
        return value
    if expected_type == "any":
        return value
    raise ValueError(f"模板 {template.id} 参数 {name} 声明了不支持的类型：{expected_type}")


def _apply_template_params(package_dir: Path, template: PlanTemplate, params: dict[str, Any]) -> None:
    plan_path = package_dir / "plan.json"
    with plan_path.open("r", encoding="utf-8") as file:
        plan = json.load(file)
    if not isinstance(plan, dict):
        raise ValueError(f"模板 {template.id} 生成的 plan.json 不是 JSON 对象。")
    variables = plan.get("variables")
    if not isinstance(variables, dict):
        variables = {}
    variables.update(params)
    plan["variables"] = variables
    _write_json(plan_path, plan)


def _prepare_package_dir(raw_path: str | Path, *, force: bool) -> Path:
    package_dir = path_from_text(raw_path).resolve()
    if package_dir.exists():
        existing_items = list(package_dir.iterdir())
        if existing_items and not force:
            raise FileExistsError(f"plan 包目录非空：{package_dir}")
    package_dir.mkdir(parents=True, exist_ok=True)
    return package_dir


def _write_common_dirs(package_dir: Path) -> None:
    (package_dir / "sub-plans").mkdir(exist_ok=True)
    (package_dir / "resources").mkdir(exist_ok=True)
    (package_dir / "output").mkdir(exist_ok=True)
    (package_dir / "docs").mkdir(exist_ok=True)


def _write_browser_login_extract_template(package_dir: Path, plan_name: str) -> None:
    resource_dir = package_dir / "resources" / "browser-login-extract"
    resource_dir.mkdir(parents=True, exist_ok=True)
    _write_text(resource_dir / "login-table.html", _browser_login_extract_html())
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "browser",
            "tags": ["template", "template:browser-login-extract"],
            "variables": {
                "login_url": "{{resources_file_url}}/browser-login-extract/login-table.html",
                "username": "demo@example.com",
                "password": "demo-password",
            },
            "steps": [
                {"action": "open_browser", "name": "web", "headed": False, "timeout_ms": 15000},
                {"action": "navigate", "type": "goto", "browser": "web", "url": "{{login_url}}"},
                {"action": "wait", "type": "selector", "browser": "web", "selector": "#email"},
                {"action": "element", "type": "fill", "browser": "web", "selector": "#email", "value": "{{username}}"},
                {"action": "element", "type": "fill", "browser": "web", "selector": "#password", "value": "{{password}}"},
                {"action": "element", "type": "click", "browser": "web", "selector": "#login-button"},
                {"action": "wait", "type": "selector", "browser": "web", "selector": "#orders-table"},
                {
                    "action": "extract",
                    "type": "table",
                    "browser": "web",
                    "row_selector": "#orders-table tbody tr",
                    "cell_selector": "td",
                    "include_header": True,
                    "header_selector": "#orders-table thead th",
                    "output": {"as": "table_rows"},
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "browser-login-extract/table.json",
                    "value": {"rows": "{{table_rows}}"},
                },
                {"action": "write", "type": "csv", "path": "browser-login-extract/table.csv", "value": "{{table_rows}}"},
                {
                    "action": "write",
                    "type": "excel",
                    "path": "browser-login-extract/table.xlsx",
                    "sheet": "orders",
                    "value": "{{table_rows}}",
                    "freeze_header": True,
                    "auto_filter": True,
                    "table": True,
                },
                {"action": "close_browser", "browser": "web"},
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for browser-login-extract."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板演示网页登录后抽取表格，并把结果写成 JSON、CSV 和 Excel。

## 修改位置

- `plan.json.variables.login_url`: 改成真实入口 URL。
- `plan.json.variables.username` / `password`: 按用户授权填写，或改成 `manual_confirm` 人工登录。
- `extract` 的表格 selector: 真实网站必须先取证后再改。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_excel_cleaning_report_template(package_dir: Path, plan_name: str) -> None:
    resource_dir = package_dir / "resources" / "excel-cleaning-report"
    resource_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = resource_dir / "sample-employees.xlsx"
    _write_sample_employee_workbook(workbook_path)
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "browser",
            "tags": ["template", "template:excel-cleaning-report"],
            "variables": {
                "source_workbook": "resources/excel-cleaning-report/sample-employees.xlsx",
                "active_status": "Active",
            },
            "steps": [
                {
                    "action": "read",
                    "type": "excel",
                    "path": "{{source_workbook}}",
                    "sheet": "Employees",
                    "output": {"as": "employees", "type": "array!"},
                },
                {
                    "action": "table",
                    "type": "filter",
                    "source": "{{employees}}",
                    "where": {"Status": "{{active_status}}"},
                    "output": {"as": "active_employees"},
                },
                {
                    "action": "table",
                    "type": "fill_empty",
                    "source": "{{active_employees}}",
                    "values": {"Bonus": 0},
                    "output": {"as": "employees_filled"},
                },
                {
                    "action": "table",
                    "type": "type_convert",
                    "source": "{{employees_filled}}",
                    "columns": {"Salary": "number", "Bonus": "number"},
                    "output": {"as": "employees_typed"},
                },
                {
                    "action": "table",
                    "type": "group",
                    "source": "{{employees_typed}}",
                    "by": "Department",
                    "aggregations": {
                        "Headcount": {"count": "*"},
                        "SalaryTotal": {"sum": "Salary"},
                        "BonusTotal": {"sum": "Bonus"},
                    },
                    "output": {"as": "department_summary"},
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "excel-cleaning-report/report.json",
                    "value": {
                        "active_employees": "{{employees_typed}}",
                        "department_summary": "{{department_summary}}",
                    },
                },
                {
                    "action": "write",
                    "type": "excel",
                    "path": "excel-cleaning-report/report.xlsx",
                    "sheets": [
                        {
                            "sheet": "Active Employees",
                            "value": "{{employees_typed}}",
                            "freeze_header": True,
                            "auto_filter": True,
                            "table": True,
                        },
                        {
                            "sheet": "Department Summary",
                            "value": "{{department_summary}}",
                            "freeze_header": True,
                            "auto_filter": True,
                            "table": True,
                        },
                    ],
                },
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for excel-cleaning-report."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板演示读取 Excel、筛选在职人员、填充空奖金、转换数字字段、按部门汇总并输出报表。

## 修改位置

- `resources/excel-cleaning-report/sample-employees.xlsx`: 替换成你的输入工作簿。
- `plan.json.variables.source_workbook`: 指向新的工作簿路径。
- `table` 步骤里的列名和汇总规则：按真实表头调整。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_api_to_excel_template(package_dir: Path, plan_name: str) -> None:
    resource_dir = package_dir / "resources" / "api-to-excel"
    resource_dir.mkdir(parents=True, exist_ok=True)
    _write_text(resource_dir / "server.py", _api_to_excel_server_py())
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "browser",
            "tags": ["template", "template:api-to-excel"],
            "variables": {
                "api_base_url": "http://127.0.0.1:43126",
                "order_status": "ready",
            },
            "steps": [
                {
                    "action": "http",
                    "type": "request",
                    "method": "GET",
                    "url": "{{api_base_url}}/orders",
                    "expect_status": 200,
                    "body_type": "json",
                    "response_body_path": "api-to-excel/orders-response.json",
                    "include_body": True,
                    "output": {"as": "orders_response"},
                },
                {
                    "action": "table",
                    "type": "filter",
                    "source": "{{orders_response.body.orders}}",
                    "where": {"status": "{{order_status}}"},
                    "output": {"as": "filtered_orders"},
                },
                {
                    "action": "table",
                    "type": "type_convert",
                    "source": "{{filtered_orders}}",
                    "columns": {"quantity": "number", "unit_price": "number", "total": "number"},
                    "output": {"as": "typed_orders"},
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "api-to-excel/orders.json",
                    "value": {"orders": "{{typed_orders}}"},
                },
                {
                    "action": "write",
                    "type": "csv",
                    "path": "api-to-excel/orders.csv",
                    "value": "{{typed_orders}}",
                },
                {
                    "action": "write",
                    "type": "excel",
                    "path": "api-to-excel/orders.xlsx",
                    "sheet": "orders",
                    "value": "{{typed_orders}}",
                    "freeze_header": True,
                    "auto_filter": True,
                    "table": True,
                },
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for api-to-excel."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板演示请求 HTTP API，筛选 JSON 数组，并输出 JSON、CSV 和 Excel。

## 本地示例服务

模板自带一个只用 Python 标准库的本地 API 服务。运行 plan 前，另开 PowerShell 7 终端并在当前 plan 包目录执行：

```powershell
python .\\resources\\api-to-excel\\server.py
```

服务默认监听 `http://127.0.0.1:43126`，和 `plan.json.variables.api_base_url` 保持一致。

## 修改位置

- `plan.json.variables.api_base_url`: 改成真实 API 根地址。
- `http` 步骤里的 headers/auth/query/body: 按真实接口认证、分页和请求参数调整。
- `table` 步骤里的 `where` 和字段名：按真实响应结构调整。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_browser_download_process_template(package_dir: Path, plan_name: str) -> None:
    resource_dir = package_dir / "resources" / "browser-download-process"
    resource_dir.mkdir(parents=True, exist_ok=True)
    _write_text(resource_dir / "download.html", _browser_download_process_html())
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "browser",
            "tags": ["template", "template:browser-download-process"],
            "variables": {
                "download_page_url": "{{resources_file_url}}/browser-download-process/download.html",
                "target_status": "Ready",
            },
            "steps": [
                {"action": "open_browser", "name": "web", "headed": False, "accept_downloads": True},
                {"action": "navigate", "type": "goto", "browser": "web", "url": "{{download_page_url}}"},
                {"action": "wait", "type": "selector", "browser": "web", "selector": "#download-orders"},
                {
                    "action": "wait_for_download",
                    "browser": "web",
                    "path": "browser-download-process/orders.csv",
                    "trigger": {
                        "action": "element",
                        "type": "click",
                        "browser": "web",
                        "selector": "#download-orders",
                    },
                    "output": {"as": "downloaded_csv_path"},
                },
                {
                    "action": "read",
                    "type": "csv",
                    "path": "{{downloaded_csv_path}}",
                    "output": {"as": "downloaded_orders", "type": "array!"},
                },
                {
                    "action": "table",
                    "type": "filter",
                    "source": "{{downloaded_orders}}",
                    "where": {"Status": "{{target_status}}"},
                    "output": {"as": "ready_orders"},
                },
                {
                    "action": "table",
                    "type": "type_convert",
                    "source": "{{ready_orders}}",
                    "columns": {"Total": "number"},
                    "output": {"as": "typed_orders"},
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "browser-download-process/ready-orders.json",
                    "value": {"orders": "{{typed_orders}}", "downloaded_csv_path": "{{downloaded_csv_path}}"},
                },
                {
                    "action": "write",
                    "type": "csv",
                    "path": "browser-download-process/ready-orders.csv",
                    "value": "{{typed_orders}}",
                },
                {
                    "action": "write",
                    "type": "excel",
                    "path": "browser-download-process/ready-orders.xlsx",
                    "sheet": "orders",
                    "value": "{{typed_orders}}",
                    "freeze_header": True,
                    "auto_filter": True,
                    "table": True,
                },
                {"action": "close_browser", "browser": "web"},
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for browser-download-process."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板演示在浏览器里触发 CSV 下载，读取下载产物，筛选目标状态，并输出 JSON、CSV 和 Excel。

## 修改位置

- `plan.json.variables.download_page_url`: 改成真实下载页。
- `wait_for_download.trigger`: 改成真实页面的下载按钮或链接操作。
- `target_status` 和后续 `table` 步骤：按真实 CSV 表头和筛选规则调整。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_sql_import_export_template(package_dir: Path, plan_name: str) -> None:
    resource_dir = package_dir / "resources" / "sql-import-export"
    resource_dir.mkdir(parents=True, exist_ok=True)
    _write_text(
        resource_dir / "accounts.csv",
        "id,name,status,balance\n"
        "101,Alice,active,120\n"
        "102,Bob,inactive,40\n"
        "103,Carol,active,85\n"
        "104,David,active,30\n",
    )
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "browser",
            "tags": ["template", "template:sql-import-export"],
            "variables": {
                "sqlite_connection": {"type": "sqlite", "path": "output/sql/sql-import-export.db"},
                "source_csv": "resources/sql-import-export/accounts.csv",
                "target_status": "active",
                "minimum_balance": 50,
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
                    "type": "import",
                    "connection": "{{sqlite_connection}}",
                    "source_path": "{{source_csv}}",
                    "source_type": "csv",
                    "table": "accounts",
                    "create_table": True,
                    "required_columns": ["id", "name", "status"],
                    "unique_columns": ["id"],
                    "column_types": {
                        "id": "INTEGER",
                        "name": "TEXT",
                        "status": "TEXT",
                        "balance": "REAL",
                    },
                    "result_path": "sql-import-export/import-result.json",
                    "output": {"as": "import_result"},
                },
                {
                    "action": "sql",
                    "type": "query",
                    "connection": "{{sqlite_connection}}",
                    "sql": "select id, name, status, balance from accounts where status = :status and balance >= :minimum_balance order by id",
                    "params": {
                        "status": "{{target_status}}",
                        "minimum_balance": "{{minimum_balance}}",
                    },
                    "rows_path": "sql-import-export/active-accounts.json",
                    "include_rows": True,
                    "output": {"as": "active_accounts"},
                },
                {
                    "action": "sql",
                    "type": "export",
                    "connection": "{{sqlite_connection}}",
                    "sql": "select id, name, status, balance from accounts where status = :status and balance >= :minimum_balance order by id",
                    "params": {
                        "status": "{{target_status}}",
                        "minimum_balance": "{{minimum_balance}}",
                    },
                    "target_path": "sql-import-export/active-accounts.xlsx",
                    "target_type": "excel",
                    "sheet": "active_accounts",
                    "result_path": "sql-import-export/export-result.json",
                    "output": {"as": "export_result"},
                },
                {
                    "action": "sql",
                    "type": "inspect",
                    "connection": "{{sqlite_connection}}",
                    "table": "accounts",
                    "include_indexes": True,
                    "result_path": "sql-import-export/schema.json",
                    "output": {"as": "schema_result"},
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "sql-import-export/report.json",
                    "value": {
                        "import": "{{import_result}}",
                        "query": "{{active_accounts}}",
                        "export": "{{export_result}}",
                        "schema": "{{schema_result}}",
                    },
                },
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for sql-import-export."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板演示把 CSV 导入 SQLite，查询目标数据，导出 Excel，并写出 JSON 报告。SQLite 不需要额外数据库服务，适合本地缓存、轻量落库和文件导入导出。

## 修改位置

- `resources/sql-import-export/accounts.csv`: 替换成真实 CSV。
- `plan.json.variables.sqlite_connection`: 改成真实 SQLite 文件或其它数据库连接。
- `sql.import` 的表名、字段类型、必填列和唯一列：按真实表结构调整。
- `sql.query` / `sql.export` 的 SQL 和参数：按真实筛选和导出规则调整。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_desktop_file_dialog_batch_template(package_dir: Path, plan_name: str) -> None:
    _write_json(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": "desktop",
            "tags": ["template", "template:desktop-file-dialog-batch"],
            "variables": {
                "files": [
                    {
                        "path": "C:/Temp/input-a.txt",
                        "save_as": "C:/Temp/output-a.txt",
                    }
                ],
                "open_dialog_title": "Open",
                "save_dialog_title": "Save",
            },
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
                {
                    "action": "desktop_capture",
                    "desktop": "desktop",
                    "type": "observe",
                    "path": "desktop-file-dialog-batch/before.json",
                    "include_windows": True,
                    "include_elements": False,
                    "include_screenshot": True,
                    "output": {"as": "initial_observation"},
                },
                {
                    "action": "foreach",
                    "items": "{{files}}",
                    "item_var": "file",
                    "index_var": "file_index",
                    "steps": [
                        {"action": "print", "message": "准备处理文件：{{file.path}}"},
                        {
                            "action": "manual_confirm",
                            "prompt": "请在目标桌面 App 中打开文件对话框，并让文件名输入框获得焦点。当前文件：{{file.path}}",
                        },
                        {
                            "action": "desktop_capture",
                            "desktop": "desktop",
                            "type": "screenshot",
                            "path": "desktop-file-dialog-batch/open-dialog-{{file_index}}.png",
                            "output": {"as": "open_dialog_screen"},
                        },
                        {
                            "action": "desktop_input",
                            "desktop": "desktop",
                            "type": "type_text",
                            "value": "{{file.path}}",
                            "method": "clipboard",
                            "preserve_clipboard": True,
                        },
                        {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["enter"]},
                        {
                            "action": "manual_confirm",
                            "prompt": "请确认文件已载入；如果需要保存，请打开保存对话框并让文件名输入框获得焦点。保存路径：{{file.save_as}}",
                        },
                        {
                            "action": "desktop_capture",
                            "desktop": "desktop",
                            "type": "screenshot",
                            "path": "desktop-file-dialog-batch/save-dialog-{{file_index}}.png",
                            "output": {"as": "save_dialog_screen"},
                        },
                        {
                            "action": "desktop_input",
                            "desktop": "desktop",
                            "type": "type_text",
                            "value": "{{file.save_as}}",
                            "method": "clipboard",
                            "preserve_clipboard": True,
                        },
                        {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["enter"]},
                        {
                            "action": "desktop_capture",
                            "desktop": "desktop",
                            "type": "observe",
                            "path": "desktop-file-dialog-batch/after-{{file_index}}.json",
                            "include_windows": True,
                            "include_elements": False,
                            "include_screenshot": True,
                        },
                    ],
                },
                {"action": "write", "type": "variables", "path": "desktop-file-dialog-batch/variables.json"},
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        },
    )
    _write_json(package_dir / "config.json", {"description": "Template config for desktop-file-dialog-batch."})
    _write_text(
        package_dir / "docs" / "README.md",
        f"""# {plan_name}

## 目标

这个模板是桌面文件打开/保存对话框批处理脚手架。默认通过 `manual_confirm` 让用户把真实 App 切到正确对话框，再由 plan 输入路径、截图和继续观察。

## 修改位置

- `plan.json.variables.files`: 改成要处理的文件和保存路径。
- `manual_confirm` 前后可替换为稳定的 `desktop_app`、`desktop_window`、`desktop_element` 和 `desktop_wait` 步骤。
- 真实 App 最终 plan 前先用 `inspect_desktop` 或 `desktop_capture type=observe` 获取窗口、控件和截图证据。

## 运行方式

```powershell
python .\\cplan.py validate --file .\\plan.json
python .\\cplan.py run --file .\\plan.json
```
""",
    )


def _write_sample_employee_workbook(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Employees"
    sheet.append(["Name", "Department", "Status", "Salary", "Bonus"])
    sheet.append(["Alice", "Finance", "Active", 12000, 1500])
    sheet.append(["Bob", "Ops", "Inactive", 9800, None])
    sheet.append(["Carol", "Finance", "Active", 13500, None])
    sheet.append(["David", "Ops", "Active", 11000, 800])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _browser_login_extract_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Template Login Extract Demo</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; }
    label { display: block; margin: 12px 0; }
    input { padding: 6px; width: 260px; }
    button { padding: 8px 14px; }
    #dashboard { display: none; margin-top: 24px; }
    table { border-collapse: collapse; margin-top: 12px; }
    th, td { border: 1px solid #aaa; padding: 6px 10px; }
  </style>
</head>
<body>
  <section id="login-card">
    <h1>Demo Login</h1>
    <label>Email <input id="email" autocomplete="username"></label>
    <label>Password <input id="password" type="password" autocomplete="current-password"></label>
    <button id="login-button" type="button">Sign in</button>
  </section>
  <section id="dashboard">
    <h2>Orders</h2>
    <table id="orders-table">
      <thead>
        <tr><th>OrderId</th><th>Customer</th><th>Status</th><th>Total</th></tr>
      </thead>
      <tbody>
        <tr><td>SO-1001</td><td>Alice</td><td>Ready</td><td>128.50</td></tr>
        <tr><td>SO-1002</td><td>Bob</td><td>Review</td><td>76.20</td></tr>
        <tr><td>SO-1003</td><td>Carol</td><td>Ready</td><td>219.00</td></tr>
      </tbody>
    </table>
  </section>
  <script>
    document.querySelector("#login-button").addEventListener("click", () => {
      document.querySelector("#login-card").style.display = "none";
      document.querySelector("#dashboard").style.display = "block";
    });
  </script>
</body>
</html>
"""


def _api_to_excel_server_py() -> str:
    return '''from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "127.0.0.1"
PORT = int(os.environ.get("AIC_TEMPLATE_API_PORT", "43126"))

ORDERS = [
    {"order_id": "SO-2001", "customer": "Alice", "status": "ready", "quantity": 2, "unit_price": 64.25, "total": 128.5},
    {"order_id": "SO-2002", "customer": "Bob", "status": "review", "quantity": 1, "unit_price": 76.2, "total": 76.2},
    {"order_id": "SO-2003", "customer": "Carol", "status": "ready", "quantity": 3, "unit_price": 73.0, "total": 219.0},
]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/orders"):
            self._send_json(200, {"orders": ORDERS})
            return
        self._send_json(404, {"error": "not found", "path": self.path})

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, value: object) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(json.dumps({"ok": True, "base_url": f"http://{HOST}:{PORT}"}, ensure_ascii=False), flush=True)
    server.serve_forever()
'''


def _browser_download_process_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Template Download Process Demo</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; }
    a { display: inline-block; padding: 8px 14px; border: 1px solid #777; color: #111; text-decoration: none; }
    table { border-collapse: collapse; margin-top: 18px; }
    th, td { border: 1px solid #aaa; padding: 6px 10px; }
  </style>
</head>
<body>
  <h1>Orders Export</h1>
  <a id="download-orders" download="orders.csv" href="data:text/csv;charset=utf-8,OrderId%2CCustomer%2CStatus%2CTotal%0ASO-3001%2CAlice%2CReady%2C128.50%0ASO-3002%2CBob%2CReview%2C76.20%0ASO-3003%2CCarol%2CReady%2C219.00%0A">Download orders CSV</a>
  <table>
    <thead><tr><th>OrderId</th><th>Customer</th><th>Status</th><th>Total</th></tr></thead>
    <tbody>
      <tr><td>SO-3001</td><td>Alice</td><td>Ready</td><td>128.50</td></tr>
      <tr><td>SO-3002</td><td>Bob</td><td>Review</td><td>76.20</td></tr>
      <tr><td>SO-3003</td><td>Carol</td><td>Ready</td><td>219.00</td></tr>
    </tbody>
  </table>
</body>
</html>
"""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
