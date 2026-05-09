# open_browser

## 用途

创建一个新的浏览器会话，供后续步骤使用。

这是大多数计划里的第一步。后面的 `goto`、`click`、`fill` 等动作，都需要先绑定到一个已经打开的浏览器会话。

## 必填字段

- `action`: 固定写成 `open_browser`
- `name`: 浏览器会话名称，自定义即可，后续通过 `browser` 字段引用

## 可选字段

- `headed`: 是否显示浏览器窗口，默认 `false`
- `slow_mo_ms`: 每个 Playwright 动作之间增加的延迟，默认 `0`
- `timeout_ms`: 当前浏览器会话的默认超时时间，默认 `15000`

## 示例

```json
{
  "action": "open_browser",
  "name": "main",
  "headed": true,
  "slow_mo_ms": 200,
  "timeout_ms": 20000
}
```

## 什么时候用

- 你需要启动第一个浏览器窗口
- 你需要多个浏览器并行工作
- 你要给不同站点分配不同的会话

## 注意事项

- `name` 不能重复。
- 如果你后面要写 `browser: "main"`，这里的 `name` 就必须叫 `main`。
- 当前版本默认新建一个空白上下文，不继承其他浏览器状态。
