# press

## 用途

向某个元素发送键盘按键。

## 必填字段

- `action`: 固定写成 `press`
- `browser`: 目标浏览器会话名称
- `selector`: 目标元素选择器
- `key`: 按键名称

## 可选字段

- `index`: 当选择器匹配多个元素时，指定第几个

## 示例

```json
{
  "action": "press",
  "browser": "main",
  "selector": "input.search",
  "key": "Enter"
}
```

## 常见按键

- `Enter`
- `Tab`
- `Escape`
- `ArrowDown`

## 注意事项

- 一般先让输入框获得焦点，再发送按键。
- 某些场景会先 `fill` 或 `type`，然后用 `press` 提交。
