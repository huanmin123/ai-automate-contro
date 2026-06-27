# desktop_capture

`desktop_capture` 只用于 `automation_type: "desktop"`。它保存桌面截图或桌面状态快照。

## 支持类型

| type | 作用 | 输出分区 |
| --- | --- | --- |
| `screenshot` | 保存屏幕、区域、窗口或控件截图 | `output/desktop-screenshots/` |
| `snapshot` | 保存桌面状态 JSON | `output/desktop-state/` |

## type=screenshot

全屏截图：

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "screenshot",
  "target": "screen",
  "path": "screen.png",
  "save_as": "screen"
}
```

区域截图：

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "screenshot",
  "target": "region",
  "path": "region.png",
  "region": {"x": 0, "y": 0, "width": 800, "height": 600},
  "save_as": "region_screen"
}
```

窗口截图：

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "screenshot",
  "target": "window",
  "title_contains": "Demo",
  "path": "demo-window.png",
  "save_as": "window_screen"
}
```

控件截图：

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "screenshot",
  "target": "element",
  "title_contains": "Demo",
  "automation_id": "UsernameTextBox",
  "control_type": "Edit",
  "path": "username-field.png",
  "save_as": "username_screen",
  "max_depth": 5,
  "max_elements": 200
}
```

参数：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `screenshot`。
- `path`: 必填，相对于 `output/desktop-screenshots/`。
- `target`: 可选，`screen`、`region`、`window`、`element`。省略时默认全屏；省略 `target` 但提供 `region` 时按区域截图处理。
- `region`: `target=region` 时必填，格式为 `{"x": 0, "y": 0, "width": 800, "height": 600}`。`target=window/element` 不能同时使用 `region`。
- Window Query: `target=window/element` 必填至少一种窗口定位字段，例如 `title_contains`、`title_regex`、`process_name`、`class_name`、`window_id`。
- Element Locator: `target=element` 必填至少一种控件定位字段，例如 `automation_id`、`name_contains`、`text_contains`、`control_type`、`role`、`element_id`。
- `state`: 仅 `target=element` 可用，`exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `timeout_ms`、`interval_ms`: 等待窗口或控件的超时与轮询间隔。
- `max_depth`、`max_elements`: `target=element` 的控件树遍历限制。
- `include_cursor`: 可选，是否包含鼠标指针，默认 `false`。
- `save_as`: 可选，保存 payload。

输出：

- 写入 `output/desktop-screenshots/<path>`。
- payload 包含 `ok`、`path`、`width`、`height`、`target`、`source_bounds`、`coordinate_space`。
- `target=window` 时 payload 包含 `target_query` 和 `window`。
- `target=element` 时 payload 包含 `target_query`、`locator`、`window` 和 `element`。

## type=snapshot

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "snapshot",
  "path": "state.json",
  "include_windows": true,
  "include_displays": true,
  "save_as": "desktop_state"
}
```

参数：

- `desktop`: 必填。
- `type`: 必填，固定为 `snapshot`。
- `path`: 必填，相对于 `output/desktop-state/`。
- `include_windows`: 可选，是否包含窗口列表，默认 `true`。
- `include_displays`: 可选，是否包含显示器信息，默认 `true`。
- `save_as`: 可选。

输出：

- 写入 `output/desktop-state/<path>`。
- payload 顶层包含 `capability_matrix`。
- `snapshot.capability_matrix` 与顶层矩阵一致，用于判断窗口、控件、键鼠、截图、权限和依赖能力。

## 场景

- 运行前后保存桌面画面。
- 截取指定 App 窗口或控件区域，给后续 `desktop_vision`、人工检查或报告使用。
- 保存当前窗口、显示器、权限和依赖状态。
