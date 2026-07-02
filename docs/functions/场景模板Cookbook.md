# 场景模板 Cookbook

场景模板用于把常见自动化需求快速展开成普通 plan 包。模板不是新 DSL；生成后仍然是 `plan.json`、`config.json`、`resources/`、`docs/README.md` 和 `output/` 这套结构。

## 查看模板

```powershell
python .\cplan.py template list
python .\cplan.py template list --verbose
python .\cplan.py template show api-to-excel
python .\cplan.py template list --json
```

`list --verbose` 和 `show` 会展示参数名、参数类型、预期产物和注意事项。脚本读取时用 `--json --compact`。

当前首批模板：

| 模板 | 执行线 | 用途 |
| --- | --- | --- |
| `browser-login-extract` | `browser` | 打开网页、登录示例页面、抽取表格并写出 JSON/CSV/Excel |
| `excel-cleaning-report` | `browser` | 读取 Excel，用 `table` 清洗和汇总，再输出报表 |
| `api-to-excel` | `browser` | 请求 HTTP API，筛选 JSON 数组，并写出 JSON/CSV/Excel |
| `browser-download-process` | `browser` | 触发浏览器下载 CSV，读取下载文件并输出报表 |
| `sql-import-export` | `browser` | CSV 导入 SQLite、查询筛选、导出 Excel 和 JSON 报告 |
| `desktop-file-dialog-batch` | `desktop` | 桌面打开/保存文件对话框批处理脚手架 |

## 创建模板 Plan

```powershell
python .\cplan.py create --template browser-login-extract --path .\plans\browser-login-extract-demo
python .\cplan.py create --template excel-cleaning-report --path .\plans\excel-cleaning-report-demo
python .\cplan.py create --template browser-download-process --path .\plans\download-process-demo
python .\cplan.py create --template sql-import-export --path .\plans\sql-import-export-demo
python .\cplan.py create --template desktop-file-dialog-batch --path .\plans\desktop-file-dialog-demo
```

模板声明自己的 `automation_type`。如果同时传 `--automation-type`，必须和模板执行线一致。

创建时可以用 `--param KEY=VALUE` 覆盖模板变量：

```powershell
python .\cplan.py create --template excel-cleaning-report --path .\plans\inactive-report --param active_status=Inactive
python .\cplan.py create --template browser-login-extract --path .\plans\orders-demo --param username=demo@example.com --param password=demo-password
python .\cplan.py create --template sql-import-export --path .\plans\high-balance-accounts --param minimum_balance=100
```

`--param` 只能覆盖模板声明过的变量名，拼错会直接失败。参数会按模板声明的 `string`、`number`、`object`、`array` 等类型校验；`number` 支持从字符串转换为数字。字符串值直接写；对象、数组、`true`、`false` 和 `null` 使用 JSON 值：

```powershell
python .\cplan.py create --template desktop-file-dialog-batch --path .\plans\desktop-batch --param 'files=[{"path":"C:/Temp/input-a.txt","save_as":"C:/Temp/output-a.txt"}]'
```

## 修改模板

生成后先读当前 plan 包的 `docs/README.md`。模板内通常需要改三类位置：

- `plan.json.variables`: URL、输入文件、输出规则、桌面文件列表等。
- `resources/`: 本需求的示例 HTML、Excel 或其它输入资源。
- `steps`: selector、表头字段、汇总规则、桌面窗口和控件定位。

真实网站或真实桌面 App 不能只按模板猜 selector、控件或坐标。仍然必须先用 `inspect_web_page`、headed 探索 plan、`inspect_desktop` 或 `desktop_capture type=observe` 获取证据。

## 验证模板

```powershell
python .\cplan.py self-check template-components
python .\cplan.py self-check release-matrix --only template_components --fail-fast
```

`template-components` 会检查模板发现、创建、校验、参数类型契约和参数化覆盖；默认会运行离线可跑的浏览器/文件数据模板。它还会为 `api-to-excel` 随机选择本地端口、启动模板自带 Python API 服务并端到端验证 JSON/CSV/Excel 产物。桌面模板默认只校验，不自动控制真实业务 App。

普通用户手动运行生成后的 `api-to-excel` plan 时，仍需要先按生成包 `docs/README.md` 启动模板自带的本地 API 服务，或把 `api_base_url` 改成真实 API 根地址。

## 后续扩展

新增模板时需要同步：

- `src/ai_automate_contro/plans/templates.py`
- `docs/functions/场景模板Cookbook.md`
- `docs/develop/测试与验证说明.md`
- 如模板代表新能力组合，还要更新 `README.md` 和相关 handbook 入口。
