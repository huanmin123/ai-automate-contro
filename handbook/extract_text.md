# extract_text

## 用途

读取元素的可见文本，并保存为变量。

## 必填字段

- `action`: 固定写成 `extract_text`
- `browser`: 目标浏览器会话名称
- `selector`: 目标元素选择器
- `save_as`: 保存后的变量名

## 可选字段

- `index`: 当选择器匹配多个元素时，指定第几个

## 示例

```json
{
  "action": "extract_text",
  "browser": "main",
  "selector": ".account-name",
  "save_as": "current_account"
}
```

## 后续引用示例

```json
{
  "action": "print",
  "message": "当前账号是 {{current_account}}"
}
```

## 注意事项

- 它读取的是文本，不是输入框的值。
- 如果目标是 `<input>`，通常更适合用 `extract_value`。
