# Excel 表格处理 Cookbook

本页收集公司里常见的 Excel/table plan 写法。Excel 文件处理属于 common action；只要不是控制本机 Excel App 窗口，通常可以用 `automation_type: "browser"` 承载 `read`、`table`、`write`。

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

完整可运行示例见 `test-plans/data-driven/enterprise-cookbook/plan.json`。
