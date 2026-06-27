# desktop_wait

`desktop_wait` 只用于 `automation_type: "desktop"`。它等待桌面状态达到指定条件。当前支持窗口等待。

## type=window

```json
{
  "action": "desktop_wait",
  "desktop": "desk",
  "type": "window",
  "title_contains": "Save As",
  "state": "exists",
  "timeout_ms": 5000,
  "interval_ms": 250,
  "save_as": "save_dialog"
}
```

## 参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `desktop_wait` |
| `desktop` | 是 | `open_desktop.name` |
| `type` | 是 | 当前固定为 `window` |
| Window Query | 是 | `title`、`title_contains`、`title_regex`、`app`、`process`、`process_name`、`class_name`、`window_id` 至少一个 |
| `state` | 否 | `exists`、`not_exists`、`focused`，默认 `exists` |
| `timeout_ms` | 否 | 超时毫秒，默认 `10000` |
| `interval_ms` | 否 | 轮询间隔，默认 `250` |
| `save_as` | 否 | 保存 payload |

## 场景

- 启动 App 后等待窗口出现。
- 点击保存/关闭后等待确认框出现或窗口消失。
- 聚焦窗口后等待其变为 focused。

## 注意

- `desktop_wait type=window` 成功时会更新当前 session 的 `current_window`。
- 它是桌面状态采集证据，可用于质量门禁。
- 控件级等待使用 `desktop_element type=wait`。
