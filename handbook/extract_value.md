# extract_value

## 用途

读取输入框的当前值，并保存为变量。

## 必填字段

- `action`: 固定写成 `extract_value`
- `browser`: 目标浏览器会话名称
- `selector`: 输入框选择器
- `save_as`: 保存后的变量名

## 可选字段

- `index`: 当选择器匹配多个输入框时，指定第几个

## 示例

```json
{
  "action": "extract_value",
  "browser": "main",
  "selector": "input[autocomplete='username']",
  "save_as": "filled_email"
}
```

## 什么时候用

- 你想确认输入框里到底写进去了什么
- 你要把一个输入框的值复制到另一个页面

## 注意事项

- 这个动作适合 `<input>` 和 `<textarea>`。
- 对普通文本节点使用它通常没有意义。
