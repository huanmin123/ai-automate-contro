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

## type=element

验证目标窗口内的桌面控件状态，必要时同时验证控件文本。

```json
{
  "action": "desktop_assert",
  "type": "element",
  "desktop": "desk",
  "title_contains": "Demo",
  "name": "Status",
  "state": "exists",
  "expected": "Saved",
  "mode": "contains",
  "path": "status-assertion.json",
  "save_as": "status_assertion"
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- Window Query: `title`、`title_contains`、`title_regex`、`app`、`process`、`process_name`、`class_name`、`window_id` 至少一种。
- Element Locator: `element_id`、`automation_id`、`name`、`name_contains`、`name_regex`、`text`、`text_contains`、`text_regex`、`control_type`、`role`、`element_class_name` 至少一种。
- `state`: `exists`、`not_exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `expected`: 可选，控件文本期望值。
- `mode`: `equals`、`contains`、`not_contains`，默认 `equals`。
- `text_source`: `auto`、`text`、`value`、`name`，默认 `auto`。
- `path`: 可选，写入 `output/desktop-elements/`。
- `timeout_ms`、`interval_ms`、`max_depth`、`max_elements`: 控件定位参数。

行为：

- 先用 Window Query 命中窗口，再用 Element Locator 命中控件。
- `state=not_exists` 成功时 `element` 为 `null`，不能同时使用 `expected`。
- 带 `expected` 时，断言会读取命中控件的文本并按 `mode` 比较。
- 成功 payload 包含 `element`、`matches`、`candidates_count`、`state` 和可选 `text_assertion`。

`desktop_assert type=element` 是桌面识别和验证证据。

- 不存在窗口触发失败后生成桌面失败截图和状态 JSON。
