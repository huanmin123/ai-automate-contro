# Excel 文件与表格处理 Action 设计

## 背景

公司内常见数据源大量存在于 Excel：财务流水、人员名单、排班、客户清单、报表模板、审批台账等。当前通用文件 IO 只覆盖 `json`、`text`、`csv` 和 `storage_state`，无法直接处理 `.xlsx` 文件。

Excel 能力需要满足两个目标：

- 读写语法足够简单，和现有 `read` / `write` 风格一致。
- 表格处理不要绑定 Excel 文件格式；读出来后应变成普通 JSON 行数组，后续可以和 CSV、JSON、SQL、AI、浏览器和桌面 action 组合。

## 定位

Excel 文件能力属于 common action，`automation_type: "browser"` 和 `automation_type: "desktop"` 都可以使用。它不依赖浏览器 DOM，也不依赖桌面控件树。

第一阶段不新增独立 `excel` action，优先扩展现有统一 IO：

- `read.type=excel`: 从 `.xlsx` / `.xlsm` 读取一个工作表，保存为行数组变量。
- `write.type=excel`: 把行数组、矩阵或模板填充值写成 `.xlsx`，输出到 `output/excel/`。

表格清洗、筛选、排序、去重、选列等能力建议新增独立 `table` common action。`table` 处理的是内存中的行数组，不关心来源是 Excel、CSV、JSON 还是 SQL 查询结果。这样 Excel action 保持“文件格式桥接”，表格 action 负责“数据处理”。

## 非目标

- 第一版不支持旧二进制 `.xls` 和 `.xlsb`。
- 不做 Excel 宏执行、VBA 编辑、外部链接刷新或公式计算引擎。
- 不把复杂数据清洗逻辑塞进 `read.type=excel` / `write.type=excel`。
- 不引入 pandas 作为默认依赖；第一版优先使用 `openpyxl`，便于读取/写入 `.xlsx` 并保留模板工作簿。
- 不自动脱敏 Excel 内容、公式、文件路径、财务数据或人员信息。

## 依赖策略

Excel 是高频本地能力，建议把 `openpyxl>=3.1,<4.0` 放入默认依赖，而不是可选 extra。原因：

- 安装成本小，用户无需为了最常见的 `.xlsx` 文件额外安装插件。
- `openpyxl` 支持 `.xlsx` / `.xlsm` 读写、工作表、单元格、样式模板和公式文本。
- 不强依赖本机安装 Excel、WPS 或 LibreOffice。

如果后续要支持 `.xls`、`.xlsb` 或大文件流式读取，再按格式增加可选 extra，例如 `excel-xls`、`excel-xlsb`。

## `read.type=excel`

### 最小示例

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/人员名单.xlsx",
  "sheet": "名单",
  "save_as": "employees"
}
```

默认行为：

- 读取第一个非空行为表头。
- 后续非空行转成字典数组。
- 空白行跳过。
- 日期转 ISO 字符串。
- 公式读取缓存值；如果工作簿没有缓存值，则返回空值或公式文本，取决于 `formula_mode`。

保存后的变量形态：

```json
[
  {
    "姓名": "张三",
    "部门": "财务",
    "状态": "在职"
  },
  {
    "姓名": "李四",
    "部门": "人事",
    "状态": "离职"
  }
]
```

### 读取固定范围

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/财务流水.xlsx",
  "sheet": "2026-06",
  "range": "A3:H2000",
  "header_row": 3,
  "save_as": "transactions"
}
```

### 自定义表头

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/raw.xlsx",
  "sheet": 0,
  "range": "A2:D100",
  "headers": ["工号", "姓名", "部门", "手机号"],
  "save_as": "people"
}
```

提供 `headers` 时，范围内每一行都按数据行处理，不再把第一行当表头。

### 读取矩阵

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/预算.xlsx",
  "sheet": "汇总",
  "range": "B2:F20",
  "mode": "matrix",
  "save_as": "budget_matrix"
}
```

`mode=matrix` 返回二维数组，适合没有稳定表头的报表区域。

### 元数据

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/人员名单.xlsx",
  "sheet": "名单",
  "save_as": "employees",
  "save_meta_as": "employees_meta"
}
```

`save_meta_as` 保存结构摘要：

```json
{
  "type": "excel",
  "path": "resources/人员名单.xlsx",
  "sheets": ["名单", "部门"],
  "sheet": "名单",
  "range": "A1:C3",
  "headers": ["姓名", "部门", "状态"],
  "row_count": 2,
  "column_count": 3
}
```

### 读取多个工作表

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/企业数据.xlsx",
  "sheets": [
    {
      "sheet": "人员名单",
      "name": "employees"
    },
    {
      "sheet": "部门",
      "name": "departments"
    }
  ],
  "save_as": "workbook",
  "save_meta_as": "workbook_meta"
}
```

`sheets[]` 每项可以是 sheet 名称、从 0 开始的索引，或读取配置对象。配置对象里的 `name` 是保存到结果对象里的别名，便于后续写 `{{workbook.employees}}`。不提供 `name` 时使用实际 sheet 名。

多工作表读取的元数据额外包含：

```json
{
  "selected_sheets": ["人员名单", "部门"],
  "value_names": ["employees", "departments"],
  "sheet_meta": {
    "employees": {"sheet": "人员名单", "row_count": 4},
    "departments": {"sheet": "部门", "row_count": 3}
  }
}
```

### 字段

必填字段：

- `action`: 固定为 `read`
- `type`: 固定为 `excel`
- `path`: 输入文件路径
- `save_as`: 行数组、矩阵或单元格值保存变量名

常用可选字段：

- `sheet`: 工作表名称或从 0 开始的索引，默认第一个工作表。
- `sheets`: 多工作表读取数组；每项可包含 `sheet`、`name`、`range`、`header_row`、`headers`、`mode`、`skip_blank_rows`、`max_rows`、`formula_mode` 和 `date_format`。
- `range`: A1 范围，例如 `A1:F100`。
- `header_row`: 表头所在行号，默认范围首行或第一个非空行。
- `headers`: 自定义表头数组。
- `mode`: `records`、`matrix`、`cells`，默认 `records`。
- `skip_blank_rows`: 是否跳过空白行，默认 `true`。
- `formula_mode`: `cached` 或 `formula`，默认 `cached`。
- `date_format`: `iso` 或 `text`，默认 `iso`。
- `max_rows`: 最大读取行数，防止误读巨大表，默认可设为 `10000`。
- `save_meta_as`: 额外保存工作簿和读取范围元数据。

## `write.type=excel`

### 写新工作簿

```json
{
  "action": "write",
  "type": "excel",
  "path": "财务人员.xlsx",
  "sheet": "名单",
  "value": "{{finance_people}}",
  "start_cell": "A1",
  "headers": ["姓名", "部门", "状态"],
  "freeze_header": true,
  "auto_filter": true
}
```

输出到：

```text
output/excel/财务人员.xlsx
```

### 使用模板并替换工作表

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/报表模板.xlsx",
  "path": "月度报表.xlsx",
  "sheet": "明细",
  "write_mode": "replace_sheet",
  "value": "{{transactions}}"
}
```

`template_path` 是输入文件，按普通输入路径规则解析；`path` 是输出文件，必须写入当前 plan 包 `output/excel/`。

### 追加行

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/客户台账.xlsx",
  "path": "客户台账-更新.xlsx",
  "sheet": "客户",
  "write_mode": "append_rows",
  "value": "{{new_customers}}"
}
```

### 填充模板单元格

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/封面模板.xlsx",
  "path": "封面.xlsx",
  "sheet": "封面",
  "cells": {
    "B2": "{{company_name}}",
    "B3": "{{report_month}}",
    "E12": "=SUM(E5:E11)"
  }
}
```

`write.type=excel` 校验应允许 `value`、`cells` 或 `sheets` 至少提供一个。`cells` 只负责单元格赋值，不负责公式计算。

### 多工作表

```json
{
  "action": "write",
  "type": "excel",
  "path": "统计结果.xlsx",
  "sheets": [
    {
      "sheet": "财务",
      "rows": "{{finance_people}}"
    },
    {
      "sheet": "人事",
      "rows": "{{hr_people}}"
    }
  ]
}
```

多工作表由 `sheets[]` 支持。顶层 Excel 选项会作为默认值传给每个 sheet，sheet 内字段可以覆盖顶层配置。

### 字段

必填字段：

- `action`: 固定为 `write`
- `type`: 固定为 `excel`
- `path`: 输出路径，相对于 `output/excel/`
- `value`、`cells` 或 `sheets`: 至少提供一个

常用可选字段：

- `template_path`: 模板工作簿输入路径。
- `sheet`: 工作表名，默认 `Sheet1`。
- `write_mode`: `create`、`replace_sheet`、`append_rows`、`overlay_cells`，默认 `create` 或有模板时 `replace_sheet`。
- `start_cell`: 表格写入左上角单元格，默认 `A1`。`freeze_header`、`auto_filter`、`table`、`number_format` 和 `column_widths` 会按实际表格范围应用。
- `headers`: 输出表头，未提供时从第一行字典 key 推断。
- `include_header`: 是否写表头，默认 `true`。
- `freeze_header`: 冻结表头行，默认 `false`。
- `auto_filter`: 给表头添加筛选，默认 `false`。
- `table`: 是否创建 Excel Table，默认 `false`。
- `date_format`: 日期写入格式，默认 `yyyy-mm-dd`。
- `number_format`: 列级数字格式对象。
- `column_widths`: 列宽对象，例如 `{ "姓名": 12, "金额": 14 }`。
- `sheets`: 多工作表写入配置，每项可包含 `sheet`、`value`/`rows`、`cells`、`headers`、`start_cell`、`write_mode`、`freeze_header`、`auto_filter`、`table`、`number_format` 和 `column_widths`。

## `table` Action

Excel 读出来以后应尽量变成普通行数组。常见表格处理用 `table` action 表达，避免用户为简单筛选、汇总、连接和派生列写 SQL。

### 筛选

```json
{
  "action": "table",
  "type": "filter",
  "source": "{{employees}}",
  "where": {
    "部门": "财务",
    "状态": "在职"
  },
  "save_as": "finance_people"
}
```

### 条件对象

```json
{
  "action": "table",
  "type": "filter",
  "source": "{{transactions}}",
  "where": {
    "金额": {
      "gte": 1000
    },
    "摘要": {
      "contains": "差旅"
    }
  },
  "save_as": "travel_transactions"
}
```

### 选列和改名

```json
{
  "action": "table",
  "type": "select",
  "source": "{{finance_people}}",
  "columns": ["姓名", "部门", "手机号"],
  "rename": {
    "手机号": "电话"
  },
  "save_as": "contact_rows"
}
```

### 排序和去重

```json
{
  "action": "table",
  "type": "sort",
  "source": "{{transactions}}",
  "by": ["日期", "金额"],
  "descending": [false, true],
  "save_as": "sorted_transactions"
}
```

```json
{
  "action": "table",
  "type": "dedupe",
  "source": "{{employees}}",
  "by": ["工号"],
  "keep": "first",
  "save_as": "unique_employees"
}
```

### 分组汇总

```json
{
  "action": "table",
  "type": "group",
  "source": "{{transactions}}",
  "by": ["部门"],
  "aggregations": {
    "总金额": {
      "sum": "金额"
    },
    "笔数": {
      "count": "*"
    }
  },
  "save_as": "department_summary"
}
```

### 清洗、改名和透视

```json
{
  "action": "table",
  "type": "fill_empty",
  "source": "{{employees}}",
  "values": {
    "奖金": 0
  },
  "save_as": "employees_filled"
}
```

```json
{
  "action": "table",
  "type": "type_convert",
  "source": "{{employees_filled}}",
  "columns": {
    "工资": "number",
    "奖金": "number"
  },
  "save_as": "employees_typed"
}
```

```json
{
  "action": "table",
  "type": "rename",
  "source": "{{employees_typed}}",
  "columns": {
    "姓名": "员工姓名",
    "手机号": "电话"
  },
  "save_as": "employees_renamed"
}
```

```json
{
  "action": "table",
  "type": "pivot",
  "source": "{{employees_renamed}}",
  "index": "部门",
  "columns": "级别",
  "values": "工资",
  "agg": "sum",
  "fill_value": 0,
  "save_as": "salary_pivot"
}
```

当前 `table` 已落地 `filter`、`select`、`sort`、`dedupe`、`group`、`join`、`add_column`、`rename`、`fill_empty`、`type_convert` 和 `pivot`。窗口函数、复杂多表查询或大数据量处理仍优先通过 `sql` + SQLite/DuckDB 完成。

## 推荐组合

### 人员名单筛选并导出 Excel

```json
{
  "steps": [
    {
      "action": "read",
      "type": "excel",
      "path": "resources/人员名单.xlsx",
      "sheet": "名单",
      "save_as": "employees"
    },
    {
      "action": "table",
      "type": "filter",
      "source": "{{employees}}",
      "where": {
        "部门": "财务",
        "状态": "在职"
      },
      "save_as": "finance_people"
    },
    {
      "action": "write",
      "type": "excel",
      "path": "财务在职人员.xlsx",
      "sheet": "名单",
      "value": "{{finance_people}}",
      "freeze_header": true,
      "auto_filter": true
    }
  ]
}
```

### 财务流水读入 SQLite 汇总

```json
{
  "steps": [
    {
      "action": "read",
      "type": "excel",
      "path": "resources/财务流水.xlsx",
      "sheet": "明细",
      "save_as": "transactions"
    },
    {
      "action": "sql",
      "type": "bulk_insert",
      "connection": {
        "type": "sqlite",
        "path": "output/sql/finance.db"
      },
      "table": "transactions",
      "rows": "{{transactions}}"
    },
    {
      "action": "sql",
      "type": "query",
      "connection": {
        "type": "sqlite",
        "path": "output/sql/finance.db"
      },
      "sql": "select department, sum(amount) as total_amount from transactions group by department",
      "save_as": "summary"
    },
    {
      "action": "write",
      "type": "excel",
      "path": "部门汇总.xlsx",
      "sheet": "汇总",
      "value": "{{summary.rows}}"
    }
  ]
}
```

## 路径与输出

- `read.type=excel.path` 使用普通输入路径规则，推荐 `resources/...`，也允许用户明确指定绝对路径、共享盘或外部相对路径。
- `write.type=excel.path` 写入 `output/excel/`，不能以 `output/` 开头，不能写绝对路径。
- `template_path` 是输入路径，推荐 `resources/...`。
- AI 创建 plan 时，用户给出 Excel 文件但没有要求固定依赖本机路径，应导入当前 plan 包 `resources/` 后引用。
- 运行产物保留 Excel 原始内容，不自动脱敏。

## 实现边界

### Excel 读取

- 使用 `openpyxl.load_workbook(path, data_only=...)`。
- `formula_mode=cached` 时使用 `data_only=True`。
- `formula_mode=formula` 时使用 `data_only=False`。
- 日期、时间、Decimal 等值要转成 JSON 可序列化值。
- 表头重复时自动加后缀，或校验报错；第一版建议报错，避免静默覆盖列。
- 空表返回空数组，不报错。

### Excel 写入

- 没有 `template_path` 时创建新 workbook。
- 有 `template_path` 时复制模板到输出 workbook 后再改指定 sheet/cells。
- `append_rows` 需要定位最后一个非空行。
- 字典数组按 headers 写列；二维数组直接按矩阵写。
- 公式以 `=` 开头写入单元格，但不计算公式结果。
- `auto_filter`、冻结首行、基础列宽可以第一版一起做，样式高级能力后续增强。

### `table` 处理

- 用纯 Python 实现，当前运行时只处理字典行数组。
- 条件只支持明确操作符，不设计通用表达式语言。
- 返回值默认是行数组，便于直接接 `write.type=excel` 或 `write.type=csv`。
- 大数据量、复杂多表查询和窗口函数推荐继续使用 `sql` action。

## 校验规则

需要更新：

- `validation_rules.ACTION_TYPES` 增加 `read: excel`、`write: excel` 和 `table` action。
- `OUTPUT_ACTION_CATEGORIES` 增加 `("write", "excel"): "excel"`。
- `write.type=excel` 特判 `value`、`cells` 或 `sheets` 至少一个。
- `sheet` 允许字符串或非负整数。
- `range` 必须是 A1 风格字符串。
- `mode` 只允许 `records`、`matrix`、`cells`。
- `formula_mode` 只允许 `cached`、`formula`。
- `write_mode` 只允许 `create`、`replace_sheet`、`append_rows`、`overlay_cells`。
- `headers`、`columns`、`by` 等字段必须是字符串数组。
- `template_path` 走输入路径校验。
- `path` 走 `output/excel/` 输出路径校验。

## 测试策略

新增 `test-plans/data-driven/load-excel/`：

- `resources/人员名单.xlsx`：包含中文表头、日期、数字、空白行。
- plan 读取 Excel，筛选财务在职人员，写出 JSON 和 Excel。
- 校验 `output/json/loaded-rows.json` 和 `output/excel/财务在职人员.xlsx` 存在。

新增 `test-plans/basic/write-excel/`：

- 从变量写新工作簿。
- 再读回工作簿。
- 写 JSON 对比读回结果。

`table` action 回归使用 `test-plans/data-driven/table-transform/`：

- 覆盖筛选、排序、去重、选列、连接、派生列、分组汇总和多工作表 Excel 输出。
- 输入同时使用 JSON、CSV 和 Excel 读入结果，证明 table 与文件格式解耦。

企业常用 Excel/table cookbook 使用 `test-plans/data-driven/enterprise-cookbook/`：

- 覆盖多工作表读取、sheet 别名、空值填补、类型转换、列改名、透视汇总、`start_cell` 和多工作表导出。
- 输入 fixture 为人员名单、部门维表和财务流水，贴近公司内部常见 Excel 数据处理。

验证命令：

```powershell
python .\cplan.py validate --file .\test-plans\basic\write-excel\plan.json
python .\cplan.py run --file .\test-plans\basic\write-excel\plan.json --run-name write-excel
python .\cplan.py validate --file .\test-plans\data-driven\load-excel\plan.json
python .\cplan.py run --file .\test-plans\data-driven\load-excel\plan.json --run-name load-excel
python .\cplan.py validate --file .\test-plans\data-driven\enterprise-cookbook\plan.json
python .\cplan.py run --file .\test-plans\data-driven\enterprise-cookbook\plan.json --run-name enterprise-cookbook
python .\cplan.py self-check handbook
```

## 文档同步

落地时需要同步更新：

- `pyproject.toml` 默认依赖。
- `src/ai_automate_contro/engine/actions/files.py`。
- `src/ai_automate_contro/engine/actions/basic.py`。
- `src/ai_automate_contro/plans/validation_rules.py`。
- `src/ai_automate_contro/plans/validation_fields.py`。
- `handbook/actions/common/io/read.md`。
- `handbook/actions/common/io/write.md`。
- `handbook/actions/common/README.md`。
- `docs/functions/核心功能设计.md` 当前能力列表。
- `docs/develop/测试与验证说明.md` 数据驱动回归说明。
- 对应 `test-plans/` 示例和 README。
