# desktop_assert

`desktop_assert` 用于在 `automation_type: "desktop"` plan 中做桌面线断言。它只读取当前桌面 session 和当前 plan 包 `output/` 产物，不创建浏览器会话。

## type=window

验证窗口状态。

```json
{
  "action": "desktop_assert",
  "type": "window",
  "desktop": "desk",
  "state": "focused",
  "title_contains": "Notepad",
  "timeout_ms": 2000,
  "interval_ms": 100,
  "save_as": "focused_window"
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `state`: `exists`、`not_exists`、`focused`，默认 `exists`。
- `title`、`title_contains`、`title_regex`、`app`、`process`、`process_name`、`class_name`、`window_id`: 至少提供一种窗口定位字段。
- `match_index`: 多个候选时的索引，默认 `0`。
- `timeout_ms`: 默认 `1000`。
- `interval_ms`: 默认 `100`。
- `save_as`: 可选，保存断言 payload。

行为：

- 复用 backend 的窗口查询和等待逻辑。
- `state=focused` 成功时会更新当前 session 的 `current_window`。
- 超时会抛出断言错误，并触发 `failure-desktop-screenshots/` 与 `failure-desktop-state/`。

## type=screenshot

验证已生成的桌面截图产物存在且不为空。

```json
{
  "action": "desktop_assert",
  "type": "screenshot",
  "desktop": "desk",
  "path": "screen.png",
  "min_bytes": 1,
  "save_as": "screen_assertion"
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `path`: 必填，相对于 `output/desktop-screenshots/`。
- `min_bytes`: 最小文件字节数，默认 `1`。
- `save_as`: 可选，保存断言 payload。

示例通常先执行：

```json
{
  "action": "desktop_capture",
  "type": "screenshot",
  "desktop": "desk",
  "path": "screen.png"
}
```

再执行 `desktop_assert type=screenshot`。

## 验证

```powershell
python .\cplan.py self-check desktop-components
```

当前自检覆盖：

- `desktop_assert.window` 缺少窗口定位字段时校验失败。
- `desktop_assert.screenshot` 缺少 `path` 时校验失败。
- 基础桌面 plan 生成截图并通过截图断言。
- Windows Notepad / macOS TextEdit 临时 App 回归覆盖聚焦、输入、保存、截图和断言。
- 不存在窗口触发失败后生成桌面失败截图和状态 JSON。
