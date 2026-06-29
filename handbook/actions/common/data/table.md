# table

## 用途

处理变量中的表格行数组。`table` 不关心数据来自 Excel、CSV、JSON、SQL 还是页面提取结果；它只处理已经在变量池中的数组。

第一版支持筛选、选列、排序和去重。

## 必填字段

- `action`: 固定写成 `table`
- `type`: 处理类型，支持 `filter`、`select`、`sort`、`dedupe`
- `source`: 源行数组，通常写完整变量引用，例如 `{{employees}}`
- `save_as`: 保存结果变量名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `filter` | `where` | 按字段值筛选字典行 |
| `select` | `columns` | 选列，可配合 `rename` 改名 |
| `sort` | `by` | 按一列或多列排序 |
| `dedupe` | `by` | 按一列或多列去重 |

## 示例

筛选财务在职人员：

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

使用条件操作符：

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

选列和改名：

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

排序：

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

去重：

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

## `filter` 操作符

`where` 的字段值可以直接写期望值，表示相等；也可以写对象：

- `eq` / `equals`
- `ne` / `not_equals`
- `contains`
- `not_contains`
- `in`
- `not_in`
- `gt`
- `gte`
- `lt`
- `lte`
- `empty`
- `not_empty`

## 规则

- 当前 `table` 只支持字典行数组。
- `source` 推荐使用完整变量引用，例如 `{{rows}}`，避免把数组转成字符串。
- 复杂分组、join、窗口函数或大数据量处理优先使用 `sql` + SQLite/DuckDB。
