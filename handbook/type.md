# type

## 用途

像真人打字一样逐个字符输入内容。

## 必填字段

- `action`: 固定写成 `type`
- `browser`: 目标浏览器会话名称
- `selector`: 输入框选择器
- `value`: 要输入的内容

## 可选字段

- `index`: 当选择器匹配多个输入框时，指定第几个
- `delay_ms`: 每个字符之间的延迟，默认 `50`

## 示例

```json
{
  "action": "type",
  "browser": "main",
  "selector": "input.search",
  "value": "hello world",
  "delay_ms": 80
}
```

## 什么时候优先用它

- 目标页面依赖键盘输入事件
- 你想观察逐字输入过程
- 某些自动补全框只在键入时触发逻辑

## 注意事项

- `type` 一般比 `fill` 慢。
- 如果输入框里原来已经有值，`type` 不会自动清空，必要时先用 `fill` 写空字符串。
