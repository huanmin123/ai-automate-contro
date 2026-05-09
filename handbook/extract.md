# extract

## 用途

统一从页面元素中提取数据并保存为变量。

## 必填字段

- `action`: 固定写成 `extract`
- `type`: 提取类型
- `browser`: 浏览器会话名
- `selector`: Playwright 选择器
- `save_as`: 保存变量名

## 类型说明

| type | 额外字段 | 结果 |
| --- | --- | --- |
| `text` | 无 | 元素文本 |
| `value` | 无 | 输入框值 |
| `attribute` | `attribute` | 指定属性值 |
| `html` | 无 | 元素内部 HTML |
| `count` | 无 | 匹配数量 |
| `all_texts` | 可选 `skip_empty` | 所有文本数组 |
| `all_values` | 无 | 所有输入值数组 |
| `table` | `row_selector` | 表格行数据 |

## 示例

```json
{
  "action": "extract",
  "type": "attribute",
  "browser": "main",
  "selector": "#username",
  "attribute": "placeholder",
  "save_as": "username_placeholder"
}
```

提取表格：

```json
{
  "action": "extract",
  "type": "table",
  "browser": "main",
  "row_selector": "tbody tr",
  "cell_selector": "td",
  "save_as": "rows"
}
```
