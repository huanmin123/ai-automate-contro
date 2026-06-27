# trace

## 用途

开启和保存 Playwright trace，用于失败复盘和复杂页面调试。

## 必填字段

- `action`: 固定写成 `trace`
- `type`: `start` 或 `stop`
- `browser`: 浏览器会话名

`type: stop` 还必须提供：

- `path`: 相对于 `output/traces/` 的 zip 路径

## 可选字段

`type: start` 支持：

- `screenshots`: 是否记录截图，默认 `true`
- `snapshots`: 是否记录 DOM 快照，默认 `true`
- `sources`: 是否记录源码，默认 `true`

## 示例

```json
{
  "action": "trace",
  "type": "start",
  "browser": "main"
}
```

```json
{
  "action": "trace",
  "type": "stop",
  "browser": "main",
  "path": "debug-session.zip"
}
```
