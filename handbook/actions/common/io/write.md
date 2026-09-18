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
- `sheets`: 仅 `type: excel` 有效，多工作表写入配置数组；每项可包含 `sheet`、`value`/`rows`、`cells`、`range`、`formula_columns` 和本节 Excel 选项；顶层除 `path`、`template_path`、`sheets`、`sheet`、`value`、`rows`、`cells` 外的 Excel 选项会先合并进每一项，再被项内同名字段覆盖。
- `start_cell`: 仅 `type: excel` 有效，表格数据写入的左上角单元格，默认 `A1`。
- `range`: 仅 `type: excel` 有效，A1 写入区域，例如 `B4:H20`；会限制表格不能写出区域。
- `named_range`: 仅 `type: excel` 有效，使用模板工作簿中的命名区域作为写入区域；不能和 `range` 同时使用。
- `template_path`: 仅 `type: excel` 有效，模板工作簿输入路径。
- `write_mode`: 仅 `type: excel` 有效，`create`、`replace_sheet`、`append_rows`、`overlay_cells`。
- `cells`: 仅 `type: excel` 有效，A1 单元格到值的对象。
- `formula_columns`: 仅 `type: excel` 有效，给字典行追加公式列；公式可用 `{row}` 和 `{列名}` 引用当前行单元格。
- `include_header`: 仅 `type: excel` 有效，写表格数据时是否输出表头行，默认 `true`；详见 Excel 参数分组。
- `column_widths`: 仅 `type: excel` 有效，设置列宽对象；详见 Excel 参数分组。
- `number_format`: 仅 `type: excel` 有效，设置数据列数字格式对象；详见 Excel 参数分组。
- `table`: 仅 `type: excel` 有效，把数据区转成 Excel 表格，默认 `false`；详见 Excel 参数分组。
- `table_name`: 仅 `type: excel` 有效，Excel 表格名称，默认使用工作表名；详见 Excel 参数分组。
- `copy_row_style`: 仅 `type: excel` 有效，写模板区域时把样式源行复制到写入数据行；模板 + `range`/`named_range` 默认开启。
- `style_source_row`: 仅 `type: excel` 有效，指定复制样式的源行号，默认使用写入区域首个数据行。
- `extend_conditional_formatting`: 仅 `type: excel` 有效，写模板区域时把相交的条件格式延展到实际写入数据范围；模板 + `range`/`named_range` 默认开启。
- `freeze_header`: 仅 `type: excel` 有效，冻结首行。
- `auto_filter`: 仅 `type: excel` 有效，给首行添加筛选。

## Excel 参数分组

`type: excel` 的选项按作用分成四组；`sheets[]` 每一项可以使用同样的选项。

### 数据写入

- `value` / `rows`: 写入的数据，字典行数组或二维数组；`rows` 是 `value` 的别名，两者只能提供一个。
- `headers`: 自定义表头数组；不写时从字典行键名按首次出现顺序推断。
- `include_header`: 布尔，默认 `true`；写表格数据时是否输出表头行。仅对 `value`/`rows` 生效，`cells` 单元格写入不涉及表头。以下情况即使为 `true` 也不写表头：数据无法推断表头（纯数组行）、`write_mode: "append_rows"` 追加到非空工作表。表头写入后参与 `range` 边界检查。
- `start_cell`: 表格数据左上角单元格，默认 `A1`；提供 `range` 时以 `range` 为准，`start_cell` 被忽略。
- `range`: A1 写入区域；行列数放不下数据时报错，不会截断；写入命中合并单元格且不是左上角时报错。
- `named_range`: 模板中的命名区域，解析成 `sheet` + `range` 后按 `range` 规则写入；区域不是唯一 A1 范围、或与显式 `sheet` 不一致时报错。
- `template_path`: 模板工作簿；`.xlsm` 模板保留 VBA。
- `write_mode`: `create`、`replace_sheet`、`append_rows`、`overlay_cells`；默认值见下方组合关系。
- `formula_columns`: 公式列对象；只支持字典行数组，数组行使用时报错。
- `cells`: A1 单元格到值的对象；与 `value` 可以同时使用，先写表格数据再写单元格。

### 样式

- `freeze_header`: 布尔，默认 `false`；冻结数据区首行（通常是表头行）。
- `auto_filter`: 布尔，默认 `false`；给整个数据区加筛选。
- `column_widths`: 对象，默认不设置；key 是列名（按数据区首行表头匹配）或列字母（如 `"A"`），value 是数字列宽；作用于整列；key 既匹配不到表头也不是 1-3 位列字母时报错。
- `copy_row_style`: 布尔；复制字体、填充、边框、对齐和数字格式到每个数据行。默认值见下方组合关系。
- `style_source_row`: 正整数行号；默认使用写入区域首个数据行作为样式源行。
- `extend_conditional_formatting`: 布尔；把与写入区域相交的条件格式规则延展到实际写入的数据范围。默认值见下方组合关系。

### 表格

- `table`: 布尔，默认 `false`；把数据区（含表头行）转成 Excel 表格，使用内置中等样式并显示隔行条纹。要求数据区至少 2 行且至少 1 列，不满足时静默跳过不建表；只写 `cells` 时按整个已用区域建表。
- `table_name`: 字符串；默认使用工作表名。写入前会把非 ASCII 字母、数字和下划线字符替换成 `_`（中文表名会被替换成下划线），数字开头补 `Table_` 前缀，最长 255 字符；与工作簿内已有表格重名时自动追加数字后缀，例如 `Detail` 变 `Detail2`。

### 格式

- `number_format`: 对象，默认不设置；key 是列名（按数据区首行表头匹配）或列字母，value 是 Excel 数字格式字符串，例如 `"#,##0.00"`、`"0.00%"`、`"yyyy-mm-dd"`；应用到该列从表头行下一行到工作表已用区域末尾的所有单元格，模板中已有内容的行也会被覆盖格式。

### 模板与写入区域组合关系

- 不写 `write_mode` 时按配置推断默认值：
  - 无 `template_path`：默认 `create`。
  - 有 `template_path` 且没有 `range`/`named_range`，数据是 `value`：默认 `replace_sheet`。
  - 有 `template_path` 且提供 `range`/`named_range`，或提供 `template_path` + `cells` 且没有 `value`：默认 `overlay_cells`。没有 `template_path` 时即使只有 `cells` 也默认 `create`。
- `copy_row_style` 和 `extend_conditional_formatting` 默认在 `template_path` + `range`/`named_range` 时开启，其余情况默认关闭；可显式覆盖。
- `range` 和 `named_range` 不能同时使用；`named_range` 会定位到模板里的具体 `sheet`，显式写了不一致的 `sheet` 会报错。

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

写 Excel 并设置格式和表格：

```json
{
  "action": "write",
  "type": "excel",
  "path": "工资表.xlsx",
  "sheet": "工资",
  "value": "{{salary_rows}}",
  "include_header": true,
  "column_widths": {
    "姓名": 12,
    "A": 16
  },
  "number_format": {
    "应发工资": "#,##0.00"
  },
  "table": true,
  "table_name": "SalaryTable",
  "freeze_header": true
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

当同时提供 `template_path` 和 `range`/`named_range`，或只提供 `template_path + cells` 且没有显式写 `write_mode` 时，默认按 `overlay_cells` 写入，保留模板其它区域的样式、标题区和汇总区。写入命中合并单元格时，只允许写合并区域左上角，避免把模板结构写坏。

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
