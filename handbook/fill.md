# fill

## 用途

向输入框直接写入完整内容。

`fill` 会先清空原内容，再一次性填入新值，适合表单输入、账号密码填写这类场景。

## 必填字段

- `action`: 固定写成 `fill`
- `browser`: 目标浏览器会话名称
- `selector`: 输入框选择器
- `value`: 要填入的内容

## 可选字段

- `index`: 当选择器匹配多个输入框时，指定第几个

## 示例

```json
{
  "action": "fill",
  "browser": "main",
  "selector": "input[autocomplete='username']",
  "value": "{{email}}"
}
```

## 什么时候优先用它

- 你只关心最终输入结果
- 你不需要模拟真人逐字输入
- 你想快速稳定地填表单

## 注意事项

- `value` 支持变量替换。
- 有些前端页面对逐字输入有特殊监听，这种情况可以换成 `type`。
