# extract_all_values

## 用途

提取多个输入框的值，并保存成数组变量。

## 必填字段

- `action`: 固定写成 `extract_all_values`
- `browser`: 浏览器会话名
- `selector`: 输入框选择器
- `save_as`: 保存变量名

## 示例

```json
{
  "action": "extract_all_values",
  "browser": "main",
  "selector": "input.code",
  "save_as": "codes"
}
```
