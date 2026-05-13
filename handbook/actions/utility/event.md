# event

## 用途

采集页面运行事件并写入 JSON，用于调试真实网站的前端错误、控制台输出、失败请求和 WebSocket 建连。

## 必填字段

- `action`: 固定写成 `event`
- `type`: `start`、`stop` 或 `clear`
- `browser`: 浏览器会话名

`type: stop` 还必须提供：

- `path`: 相对于 `output/json/` 的 JSON 路径

## 可选字段

- `page`: 页面名，默认当前页面
- `console`: 是否采集 console，默认 `true`
- `pageerror`: 是否采集 page error，默认 `true`
- `requestfailed`: 是否采集失败请求，默认 `true`
- `websocket`: 是否采集 WebSocket 建连，默认 `true`
- `save_as`: `type: stop` 时把事件数组保存为变量

## 示例

```json
{
  "action": "event",
  "type": "start",
  "browser": "main"
}
```

```json
{
  "action": "event",
  "type": "stop",
  "browser": "main",
  "path": "events.json",
  "save_as": "browser_events"
}
```
