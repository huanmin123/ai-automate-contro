# Excel 表格处理 Cookbook

本页收集公司里常见的 Excel/table plan 写法。Excel 文件处理属于 common action；只要不是控制本机 Excel App 窗口，通常可以用 `automation_type: "browser"` 承载 `read`、`table`、`write`。

Cookbook 是组合方式参考，不是按业务词硬套的模板。“人员名单、财务流水、台账、报表模板”等词只说明数据可能长什么样；真正的筛选、汇总、连接、公式和输出区域必须来自用户明确规则或 workbook 预览结构。

## 先预览结构

当用户只给了 Excel 文件但没有说明规则，先读少量行和 meta：

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/原始数据.xlsx",
  "sheet": "Sheet1",
  "range": "A1:Z200000",
  "preview_rows": 20,
  "max_cells": 2000,
  "save_as": "preview_rows",
  "save_meta_as": "preview_meta"
}
```

如果预览后仍不能确定筛选条件、汇总维度、连接 key 或输出格式，先问用户，不要因为文件名里有“财务”“名单”“台账”就生成固定报表逻辑。

## 多工作表读取

当一本工作簿同时包含人员、部门、流水等多个 sheet，使用 `read.type=excel.sheets[]` 一次读入，并用 `name` 给变量键取 ASCII 别名：

```json
{
  "action": "read",
  "type": "excel",
  "path": "resources/企业数据.xlsx",
  "sheets": [
    {"sheet": "人员名单", "name": "employees"},
    {"sheet": "部门", "name": "departments"},
    {"sheet": "财务流水", "name": "transactions"}
  ],
  "save_as": "workbook",
  "save_meta_as": "workbook_meta"
}
```

后续通过 `{{workbook.employees}}`、`{{workbook.departments}}`、`{{workbook.transactions}}` 引用。中文 sheet 名保留在 Excel 里，变量路径用稳定英文名，避免模板路径解析歧义。

## 人员名单清洗

```json
{
  "action": "table",
  "type": "filter",
  "source": "{{workbook.employees}}",
  "where": {"状态": "在职"},
  "save_as": "active_employees"
}
```

```json
{
  "action": "table",
  "type": "fill_empty",
  "source": "{{active_employees}}",
  "values": {"奖金": 0},
  "save_as": "employees_filled"
}
```

```json
{
  "action": "table",
  "type": "type_convert",
  "source": "{{employees_filled}}",
  "columns": {"工资": "number", "奖金": "number"},
  "save_as": "employees_typed"
}
```

## 连接维表并改列名

```json
{
  "action": "table",
  "type": "join",
  "source": "{{employees_typed}}",
  "right": "{{workbook.departments}}",
  "left_on": "部门编码",
  "right_on": "部门编码",
  "how": "left",
  "save_as": "employee_joined"
}
```

```json
{
  "action": "table",
  "type": "rename",
  "source": "{{employee_joined}}",
  "columns": {"姓名": "员工姓名", "手机号": "电话"},
  "save_as": "employee_renamed"
}
```

## 透视薪资

```json
{
  "action": "table",
  "type": "pivot",
  "source": "{{employee_renamed}}",
  "index": "部门名称",
  "columns": "级别",
  "values": "工资",
  "agg": "sum",
  "fill_value": 0,
  "save_as": "salary_pivot"
}
```

不提供 `values` 时，`pivot` 默认统计数量；提供 `values` 时，默认对该列求和。

## 财务流水汇总

```json
{
  "action": "table",
  "type": "group",
  "source": "{{workbook.transactions}}",
  "by": "部门编码",
  "aggregations": {
    "流水笔数": {"count": "*"},
    "流水金额": {"sum": "金额"},
    "税额合计": {"sum": "税额"}
  },
  "save_as": "finance_grouped"
}
```

## 常见清洗链路

```json
{
  "action": "table",
  "type": "replace",
  "source": "{{rows}}",
  "values": {"": "未填写"},
  "columns": {"状态": {"A": "在职", "I": "离职"}},
  "save_as": "replaced_rows"
}
```

```json
{
  "action": "table",
  "type": "split_column",
  "source": "{{replaced_rows}}",
  "column": "员工",
  "separator": "|",
  "into": ["姓名", "部门短名"],
  "remove_source": true,
  "save_as": "split_rows"
}
```

```json
{
  "action": "table",
  "type": "date_parse",
  "source": "{{split_rows}}",
  "columns": {"入职日期": ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"]},
  "output_format": "iso",
  "save_as": "dated_rows"
}
```

```json
{
  "action": "table",
  "type": "lookup",
  "source": "{{dated_rows}}",
  "right": "{{workbook.departments}}",
  "on": "部门编码",
  "values": {"部门名称": "部门全称"},
  "default": "未知",
  "save_as": "cleaned_rows"
}
```

完整清洗示例见 `test-plans/data-driven/table-cleaning/plan.json`。

## 多 sheet 导出

`start_cell` 可以把表格写到指定左上角，冻结、筛选、Excel Table、列宽和数字格式都会跟随实际表格范围。

```json
{
  "action": "write",
  "type": "excel",
  "path": "企业数据处理结果.xlsx",
  "sheets": [
    {
      "sheet": "在职员工",
      "value": "{{employee_renamed}}",
      "start_cell": "B3",
      "freeze_header": true,
      "auto_filter": true,
      "table": true,
      "number_format": {"工资": "#,##0", "奖金": "#,##0"}
    },
    {
      "sheet": "薪资透视",
      "value": "{{salary_pivot}}",
      "start_cell": "A2",
      "freeze_header": true,
      "auto_filter": true,
      "table": true
    }
  ]
}
```

## 模板区域写入

`range` 写表格主体，`cells` 写标题区、参数区或汇总区；提供 `template_path + range` 时默认保留模板其它区域。

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/报表模板.xlsx",
  "path": "月度报表.xlsx",
  "sheet": "明细",
  "range": "B4:F20",
  "value": "{{cleaned_rows}}",
  "formula_columns": {
    "合计": "={金额}+{税额}"
  },
  "cells": {
    "B2": "{{report_month}}",
    "F2": "{{generated_at}}"
  }
}
```

完整可运行示例见 `test-plans/data-driven/enterprise-cookbook/plan.json`。
