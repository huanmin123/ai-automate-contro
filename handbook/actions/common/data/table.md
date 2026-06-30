# table

## 用途

处理变量中的表格行数组。`table` 不关心数据来自 Excel、CSV、JSON、SQL 还是页面提取结果；它只处理已经在变量池中的数组。

当前支持筛选、选列、排序、去重、分组聚合、连接、派生列、改列名、填补空值、类型转换、透视汇总、值替换、拆列、合列、日期解析、查表补字段、表头归一化、多来源合并和模糊查表。

## 必填字段

- `action`: 固定写成 `table`
- `type`: 处理类型，支持 `filter`、`select`、`sort`、`dedupe`、`group`、`join`、`add_column`、`rename`、`fill_empty`、`type_convert`、`pivot`、`replace`、`split_column`、`merge_columns`、`date_parse`、`lookup`、`normalize_headers`、`union`、`fuzzy_lookup`
- `source`: 源行数组，通常写完整变量引用，例如 `{{employees}}`
- `save_as`: 保存结果变量名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `filter` | `where` | 按字段值筛选字典行 |
| `select` | `columns` | 选列，可配合 `rename` 改名 |
| `sort` | `by` | 按一列或多列排序 |
| `dedupe` | `by` | 按一列或多列去重 |
| `group` | `by`, `aggregations` | 按一列或多列分组聚合 |
| `join` | `right`, `on` 或 `left_on` + `right_on` | 把右侧行数组连接到当前行数组 |
| `add_column` | `columns` | 增加常量、复制、格式化或求和派生列 |
| `rename` | `columns` | 批量改列名，保留未列出的列 |
| `fill_empty` | `values` | 对空字符串、空白字符串或 null 填默认值 |
| `type_convert` | `columns` | 把列转成 `string`、`number`、`integer` 或 `boolean` |
| `pivot` | `index`, `columns` | 按行维度和列维度做透视；无 `values` 时默认计数，有 `values` 时默认求和 |
| `replace` | `columns` 或 `values` | 全局或按列替换值 |
| `split_column` | `column`, `into`, `separator` | 把一列拆成多列 |
| `merge_columns` | `columns`, `into` | 把多列拼成一列 |
| `date_parse` | `columns` | 把日期文本统一成 ISO 或指定格式 |
| `lookup` | `right`, `on` 或 `left_on` + `right_on` | 按 key 查右表字段并写入当前行 |
| `normalize_headers` | 无 | 归一化或映射字典行的列名 |
| `union` | 无 | 合并多个行数组，并按统一列集合补空 |
| `fuzzy_lookup` | `right`, `on` 或 `left_on` + `right_on` | 按文本相似度查右表字段并写入当前行 |

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

分组聚合：

```json
{
  "action": "table",
  "type": "group",
  "source": "{{transactions}}",
  "by": "部门",
  "aggregations": {
    "笔数": {
      "count": "*"
    },
    "总金额": {
      "sum": "金额"
    },
    "平均金额": {
      "avg": "金额"
    }
  },
  "save_as": "department_summary"
}
```

连接部门信息：

```json
{
  "action": "table",
  "type": "join",
  "source": "{{transactions}}",
  "right": "{{departments}}",
  "on": "部门",
  "how": "left",
  "save_as": "joined_rows"
}
```

增加派生列：

```json
{
  "action": "table",
  "type": "add_column",
  "source": "{{joined_rows}}",
  "columns": {
    "标签": {
      "format": "{部门}-{单号}-{负责人}"
    },
    "含税金额": {
      "sum": ["金额", "税额"]
    }
  },
  "save_as": "labeled_rows"
}
```

批量改列名：

```json
{
  "action": "table",
  "type": "rename",
  "source": "{{employees}}",
  "columns": {
    "姓名": "员工姓名",
    "手机号": "电话"
  },
  "save_as": "renamed_employees"
}
```

填补空值并转换类型：

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
    "奖金": "number",
    "是否在职": "boolean"
  },
  "save_as": "employees_typed"
}
```

透视汇总：

```json
{
  "action": "table",
  "type": "pivot",
  "source": "{{employees_typed}}",
  "index": "部门",
  "columns": "级别",
  "values": "工资",
  "agg": "sum",
  "fill_value": 0,
  "save_as": "salary_pivot"
}
```

不写 `values` 时，`pivot` 默认按行数计数：

```json
{
  "action": "table",
  "type": "pivot",
  "source": "{{employees}}",
  "index": "部门",
  "columns": "状态",
  "save_as": "headcount_pivot"
}
```

替换值：

```json
{
  "action": "table",
  "type": "replace",
  "source": "{{rows}}",
  "values": {
    "": "未填写"
  },
  "columns": {
    "状态": {
      "A": "在职",
      "I": "离职"
    }
  },
  "save_as": "replaced_rows"
}
```

拆列和合列：

```json
{
  "action": "table",
  "type": "split_column",
  "source": "{{rows}}",
  "column": "员工",
  "separator": "|",
  "into": ["姓名", "部门"],
  "remove_source": true,
  "save_as": "split_rows"
}
```

```json
{
  "action": "table",
  "type": "merge_columns",
  "source": "{{split_rows}}",
  "columns": ["区号", "手机号"],
  "into": "联系电话",
  "separator": "-",
  "skip_empty": true,
  "save_as": "phone_rows"
}
```

日期解析：

```json
{
  "action": "table",
  "type": "date_parse",
  "source": "{{rows}}",
  "columns": {
    "入职日期": ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"]
  },
  "output_format": "iso",
  "save_as": "dated_rows"
}
```

查表补字段：

```json
{
  "action": "table",
  "type": "lookup",
  "source": "{{dated_rows}}",
  "right": "{{departments}}",
  "on": "部门编码",
  "values": {
    "部门名称": "部门全称"
  },
  "default": "未知",
  "save_as": "cleaned_rows"
}
```

归一化表头：

```json
{
  "action": "table",
  "type": "normalize_headers",
  "source": "{{raw_rows}}",
  "columns": {
    " 姓名 ": "姓名",
    "部门 编码": "部门编码"
  },
  "case": "keep",
  "save_as": "normalized_rows"
}
```

合并多个来源：

```json
{
  "action": "table",
  "type": "union",
  "source": "{{cleaned_rows}}",
  "sources": ["{{normalized_rows}}"],
  "columns": ["姓名", "部门编码", "状态", "入职日期"],
  "fill_missing": "",
  "save_as": "union_rows"
}
```

模糊查表：

```json
{
  "action": "table",
  "type": "fuzzy_lookup",
  "source": "{{union_rows}}",
  "right": "{{department_aliases}}",
  "left_on": "部门全称",
  "right_on": "部门名称",
  "values": {
    "部门编码标准": "部门编码"
  },
  "threshold": 0.8,
  "ignore_spaces": true,
  "score_column": "匹配分",
  "save_as": "matched_rows"
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

## `group` 聚合

`aggregations` 是输出列名到聚合说明的对象。每个聚合说明只写一个操作符：

- `count`: 统计行数；`"*"` 表示所有行，也可传列名统计非空值。
- `sum`: 数字求和。
- `avg`: 数字平均。
- `min`: 数字最小值。
- `max`: 数字最大值。

## `join` 规则

- `right` 是右侧行数组，通常写完整变量引用，例如 `{{departments}}`。
- 两边同名连接列用 `on`；左右列名不同时用 `left_on` 和 `right_on`。
- `how` 支持 `inner` 和 `left`，默认 `inner`。
- 右表非连接列与左表重名时，默认用 `right_` 前缀，可通过 `right_prefix` 修改。

## `add_column` 表达式

`columns` 是新列名到表达式的对象。表达式对象支持：

- `value`: 固定值。
- `copy`: 从已有列复制。
- `format`: 用 `{列名}` 占位拼接字符串。
- `sum`: 对一列或多列做数字求和。

## `type_convert` 类型

- `str` / `string` / `text`
- `int` / `integer`
- `float` / `number`
- `bool` / `boolean`

## `pivot` 聚合

- `index`: 行维度，可以是一列或多列。
- `columns`: 透视列维度。
- `values`: 数值列；不提供时只能计数。
- `agg`: `count`、`sum`、`avg`、`min`、`max`，不提供时按 `values` 自动选择计数或求和。
- `fill_value`: 没有数据的交叉格默认填充值，默认 `0`。

## `lookup` 规则

- `right` 是右侧查找表，通常写完整变量引用，例如 `{{departments}}`。
- 两边同名 key 用 `on`；左右 key 不同时用 `left_on` 和 `right_on`。
- `values` 不写时复制右表所有非 key 列；写字符串或数组时复制同名列；写对象时表示右表列名到输出列名的映射。
- 多条右表命中同一个 key 时使用第一条。

## `normalize_headers` 规则

- `columns` 是可选的旧列名到新列名映射，优先级高于自动归一化。
- `case` 支持 `keep`、`lower`、`upper`、`snake`，默认 `keep`。
- `separator` 默认 `_`，用于替换列名中的空白或分隔符。
- 重名列会自动追加 `_2`、`_3` 后缀。

## `union` 规则

- `source` 是第一组行数组，`sources` 是额外行数组列表。
- `columns` 不写时按首次出现顺序收集所有列；写了则按指定列顺序输出。
- 缺失列填 `fill_missing`，默认空字符串。

## `fuzzy_lookup` 规则

- `right` 是右侧查找表；两边同名 key 用 `on`，不同 key 用 `left_on` 和 `right_on`。
- `values` 规则同 `lookup`。
- `threshold` 是 0 到 1 的相似度门槛，默认 `0.9`。
- `ignore_case` 默认 `true`，`trim` 默认 `true`，`ignore_spaces` 默认 `false`。
- `score_column` 可选；提供后会写入匹配分。
- 该操作使用内置轻量相似度算法，适合小中型维表；大数据量或复杂匹配优先使用数据库或专项脚本。

## 规则

- 当前 `table` 只支持字典行数组。
- `source` 推荐使用完整变量引用，例如 `{{rows}}`，避免把数组转成字符串。
- 窗口函数、复杂多表查询或大数据量处理优先使用 `sql` + SQLite/DuckDB。
