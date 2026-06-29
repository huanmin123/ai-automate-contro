# write

## 用途

把运行过程中的数据写入当前 plan 包的 `output/`。

`write` 是统一写文件组件。能共用同一组核心参数的写入能力都放在这里，通过 `type` 控制输出格式。

## 必填字段

- `action`: 固定写成 `write`
- `type`: 写入类型，支持 `json`、`text`、`csv`、`excel`、`variables`
- `path`: 相对于对应输出分区的路径

## 类型说明

| type | 输出分区 | 数据字段 | 说明 |
| --- | --- | --- | --- |
| `json` | `output/json/` | `value` | 把任意 JSON 可序列化值写成 JSON |
| `text` | `output/text/` | `value` | 把值转成文本写入；如果 `value` 是字符串数组或元组，会按一行一个写出并在末尾补换行 |
| `csv` | `output/csv/` | `value` | 把数组写成 CSV |
| `excel` | `output/excel/` | `value` 或 `cells` | 把数组写成 Excel，或向模板工作簿填充单元格 |
| `variables` | `output/variables/` | 不需要 | 导出当前变量池 |

## 可选字段

- `append`: 仅 `type: text` 有效，追加写入，默认 `false`
- `headers`: 仅 `type: csv` 和 `type: excel` 有效，自定义表头
- `indent`: 仅 `type: json` 和 `type: variables` 有效，默认 `2`
- `sheet`: 仅 `type: excel` 有效，工作表名称，默认 `Sheet1`。
- `template_path`: 仅 `type: excel` 有效，模板工作簿输入路径。
- `write_mode`: 仅 `type: excel` 有效，`create`、`replace_sheet`、`append_rows`、`overlay_cells`。
- `cells`: 仅 `type: excel` 有效，A1 单元格到值的对象。
- `freeze_header`: 仅 `type: excel` 有效，冻结首行。
- `auto_filter`: 仅 `type: excel` 有效，给首行添加筛选。

## 示例

写 JSON：

```json
{
  "action": "write",
  "type": "json",
  "path": "result.json",
  "value": {
    "status": "passed"
  }
}
```

写文本并追加：

```json
{
  "action": "write",
  "type": "text",
  "append": true,
  "path": "log.txt",
  "value": "second line\n"
}
```

把字符串数组按一行一个写入 TXT：

```json
{
  "action": "write",
  "type": "text",
  "path": "AI账户.txt",
  "value": "{{account_names}}"
}
```

写 CSV：

```json
{
  "action": "write",
  "type": "csv",
  "path": "accounts.csv",
  "value": "{{rows}}"
}
```

写 Excel：

```json
{
  "action": "write",
  "type": "excel",
  "path": "财务在职人员.xlsx",
  "sheet": "名单",
  "value": "{{finance_people}}",
  "freeze_header": true,
  "auto_filter": true
}
```

基于模板填充单元格：

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/报表模板.xlsx",
  "path": "月度报表.xlsx",
  "sheet": "封面",
  "write_mode": "overlay_cells",
  "cells": {
    "B2": "{{company_name}}",
    "B3": "{{report_month}}"
  }
}
```

导出变量：

```json
{
  "action": "write",
  "type": "variables",
  "path": "snapshot.json"
}
```

## 输出路径约束

- `path` 是相对于组件输出分区的路径，不要以 `output/` 开头。
- 不能写入绝对路径。
- 不能写入 `resources/`、`docs/`、`sub-plans/`。
- 运行产物必须留在当前 plan 包的 `output/` 下。
