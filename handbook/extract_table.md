# extract_table

## 用途

批量提取表格数据，并保存成数组变量。

如果你只要每行的单元格文本，结果会是“二维数组”。
如果你同时提供表头选择器，结果会变成“字典数组”。

## 必填字段

- `action`: 固定写成 `extract_table`
- `browser`: 浏览器会话名
- `row_selector`: 行选择器
- `save_as`: 保存变量名

## 可选字段

- `page`: 从哪个页面提取，默认当前页
- `cell_selector`: 单元格选择器，默认 `td`
- `include_header`: 是否启用表头映射，默认 `false`
- `header_selector`: 表头选择器，通常配合 `include_header: true` 使用

## 示例

```json
{
  "action": "extract_table",
  "browser": "demo",
  "row_selector": "tbody tr",
  "cell_selector": "td",
  "save_as": "table_rows"
}
```
