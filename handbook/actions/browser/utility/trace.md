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

- `screenshots`: 是否记录截图，默认 `false`；需要 trace 内包含截图时必须显式写 `true`
- `snapshots`: 是否记录 DOM 快照，默认 `true`
- `sources`: 是否记录源码，默认 `true`

## 使用经验

- trace 是调试工具，不是默认业务步骤。只在复杂页面失败、需要复盘 Playwright 动作或定位页面状态变化时开启。
- `screenshots` 默认关闭。需要 trace 里包含画面时显式写 `true`，但不要把它当成普通流程的隐式截图。
- trace 应尽量包住最小问题片段：`start` 后执行少量关键步骤，然后立刻 `stop`。长流程 trace 会变大，也会影响运行耗时。

## 示例

```json
{
  "action": "trace",
  "type": "start",
  "browser": "main",
  "screenshots": true
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
