# read

## 用途

读取当前 plan 包资源、运行产物，或用户明确指定的本机路径，并保存为变量。

`read` 是统一读文件组件。能共用 `path`、`type`、`save_as` 的读取能力都放在这里，通过 `type` 控制解析方式。

## 必填字段

- `action`: 固定写成 `read`
- `type`: 读取类型，支持 `json`、`text`、`csv`、`excel`、`storage_state`
- `path`: 输入文件路径
- `save_as`: 保存到变量池的变量名

## 类型说明

| type | 读取结果 |
| --- | --- |
| `json` | JSON 对象、数组或值 |
| `text` | 字符串 |
| `csv` | 字典数组 |
| `excel` | 字典数组、二维数组或单元格对象 |
| `storage_state` | storage state 文件的绝对路径字符串 |

## 可选字段

- `split_lines`: 仅 `type: text` 有效，设置为 `true` 时按行拆分，并过滤空行。
- `sheet`: 仅 `type: excel` 有效，工作表名称或从 0 开始的索引，默认第一个工作表。
- `sheets`: 仅 `type: excel` 有效，多工作表读取数组；每项可以是 sheet 名称、从 0 开始的索引，或包含 `sheet`、`name`、`range`、`headers`、`mode` 等读取选项的对象。
- `range`: 仅 `type: excel` 有效，A1 范围，例如 `A1:F100`。
- `header_row`: 仅 `type: excel` 且 `mode=records` 有效，表头所在行号。
- `headers`: 仅 `type: excel` 且 `mode=records` 有效，自定义表头数组。
- `mode`: 仅 `type: excel` 有效，`records`、`matrix`、`cells`，默认 `records`。
- `save_meta_as`: 仅 `type: excel` 有效，额外保存工作簿、sheet、range、表头和行列数元数据。

## 示例

读取资源 JSON：

```json
{
  "action": "read",
  "type": "json",
  "path": "resources/accounts.json",
  "save_as": "accounts"
}
```

读取输出 CSV：

```json
{
  "action": "read",
  "type": "csv",
  "path": "output/csv/accounts.csv",
  "save_as": "rows"
}
```

读取 Excel 工作表：

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

读取 Excel 区域为二维数组：

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

一次读取多个 Excel 工作表：

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
    },
    {
      "sheet": "财务流水",
      "name": "transactions"
    }
  ],
  "save_as": "workbook",
  "save_meta_as": "workbook_meta"
}
```

读取结果可以用 `{{workbook.employees}}`、`{{workbook.departments}}` 这样的别名引用。没有写 `name` 时，结果键使用实际 sheet 名。

读取文本并按行拆分：

```json
{
  "action": "read",
  "type": "text",
  "path": "resources/accounts.txt",
  "split_lines": true,
  "save_as": "lines"
}
```

读取浏览器状态文件路径：

```json
{
  "action": "read",
  "type": "storage_state",
  "path": "output/storage-states/state-demo.json",
  "save_as": "saved_state_path"
}
```

## 路径约束

- 资源输入默认放在当前 plan 包的 `resources/`。
- 需要读取运行产物时，可以读取当前 plan 包的 `output/<component>/...`。
- 不建议跨 plan 包读取文件；不同需求包之间保持独立。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- AI 创建 plan 时，用户没有指定固定本机文件路径时，推荐把文件导入当前包 `resources/`，再写 `resources/...`。
- `path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
