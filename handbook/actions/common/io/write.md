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
| `excel` | `output/excel/` | `value`、`cells` 或 `sheets` | 把数组写成 Excel，或向模板工作簿填充单元格 |
| `variables` | `output/variables/` | 不需要 | 导出当前变量池 |

## 可选字段

- `append`: 仅 `type: text` 有效，追加写入，默认 `false`
- `headers`: 仅 `type: csv` 和 `type: excel` 有效，自定义表头
- `indent`: 仅 `type: json` 和 `type: variables` 有效，默认 `2`
- `sheet`: 仅 `type: excel` 有效，工作表名称，默认 `Sheet1`。
- `sheets`: 仅 `type: excel` 有效，多工作表写入配置数组；每项可包含 `sheet`、`value`/`rows`、`cells`、`range`、`formula_columns` 和本节 Excel 选项。
- `start_cell`: 仅 `type: excel` 有效，表格数据写入的左上角单元格，默认 `A1`。
- `range`: 仅 `type: excel` 有效，A1 写入区域，例如 `B4:H20`；会限制表格不能写出区域。
- `named_range`: 仅 `type: excel` 有效，使用模板工作簿中的命名区域作为写入区域；不能和 `range` 同时使用。
- `template_path`: 仅 `type: excel` 有效，模板工作簿输入路径。
- `write_mode`: 仅 `type: excel` 有效，`create`、`replace_sheet`、`append_rows`、`overlay_cells`。
- `cells`: 仅 `type: excel` 有效，A1 单元格到值的对象。
- `formula_columns`: 仅 `type: excel` 有效，给字典行追加公式列；公式可用 `{row}` 和 `{列名}` 引用当前行单元格。
- `copy_row_style`: 仅 `type: excel` 有效，写模板区域时把样式源行复制到写入数据行；模板 + `range`/`named_range` 默认开启。
- `style_source_row`: 仅 `type: excel` 有效，指定复制样式的源行号，默认使用写入区域首个数据行。
- `extend_conditional_formatting`: 仅 `type: excel` 有效，写模板区域时把相交的条件格式延展到实际写入数据范围；模板 + `range`/`named_range` 默认开启。
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
  "start_cell": "A1",
  "freeze_header": true,
  "auto_filter": true
}
```

写多工作表 Excel：

```json
{
  "action": "write",
  "type": "excel",
  "path": "财务报表.xlsx",
  "sheets": [
    {
      "sheet": "明细",
      "value": "{{detail_rows}}",
      "start_cell": "B3",
      "freeze_header": true,
      "auto_filter": true,
      "table": true
    },
    {
      "sheet": "部门汇总",
      "value": "{{summary_rows}}",
      "freeze_header": true,
      "auto_filter": true,
      "table": true
    }
  ]
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

基于模板保留样式并写入指定区域：

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/报表模板.xlsx",
  "path": "月度报表.xlsx",
  "sheet": "明细",
  "range": "B4:F20",
  "value": "{{detail_rows}}",
  "formula_columns": {
    "合计": "={金额}+{税额}"
  },
  "cells": {
    "B2": "{{report_month}}",
    "F2": "{{generated_at}}"
  }
}
```

当同时提供 `template_path` 和 `range`/`named_range` 且没有显式写 `write_mode` 时，默认按 `overlay_cells` 写入，保留模板其它区域的样式、标题区和汇总区。写入命中合并单元格时，只允许写合并区域左上角，避免把模板结构写坏。

基于模板命名区域写入：

```json
{
  "action": "write",
  "type": "excel",
  "template_path": "resources/报表模板.xlsx",
  "path": "月度报表.xlsx",
  "named_range": "DetailArea",
  "value": "{{detail_rows}}",
  "formula_columns": {
    "实发": "={基本工资}+{奖金}"
  },
  "cells": {
    "B2": "{{report_month}}",
    "F2": "{{generated_at}}"
  },
  "copy_row_style": true,
  "style_source_row": 5,
  "extend_conditional_formatting": true
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
