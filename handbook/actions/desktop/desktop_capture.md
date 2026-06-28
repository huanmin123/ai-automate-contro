# desktop_capture

`desktop_capture` 只用于 `automation_type: "desktop"`。它保存桌面截图、桌面状态快照或 AI 可读的统一观察结果。

## 支持类型

| type | 作用 | 输出分区 |
| --- | --- | --- |
| `screenshot` | 保存屏幕、区域、窗口或控件截图 | `output/desktop-screenshots/` |
| `snapshot` | 保存桌面状态 JSON | `output/desktop-state/` |
| `observe` | 保存统一桌面观察 JSON，可合并能力矩阵、窗口、控件摘要和截图 | `output/desktop-state/` |

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
- `region`: `target=region` 时必填，格式为 `{"x": 0, "y": 0, "width": 800, "height": 600}`。`x/y` 可以为负，用于副屏位于主屏左侧或上方的虚拟屏幕坐标；`width/height` 必须大于 `0`。`target=window/element` 不能同时使用 `region`。
- Window Query: `target=window/element` 必填至少一种窗口定位字段，例如 `title_contains`、`title_regex`、`process_name`、`class_name`、`window_id`。
- Element Locator: `target=element` 必填至少一种控件定位字段，例如 `automation_id`、`name_contains`、`text_contains`、`control_type`、`role`、`element_id`。
- `state`: 仅 `target=element` 可用，`exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `timeout_ms`、`interval_ms`: 等待窗口或控件的超时与轮询间隔。
- `max_depth`、`max_elements`: `target=element` 的控件树遍历限制。
- `include_cursor`: 可选，请求截图包含鼠标指针，默认 `false`。是否实际包含由 backend 返回的 `cursor_included` 判断。
- `save_as`: 可选，保存 payload。

输出：

- 写入 `output/desktop-screenshots/<path>`。
- payload 包含 `ok`、`path`、`width`、`height`、`target`、`source_bounds`、`coordinate_space`、`coordinate_profile`、`coordinate_diagnostics`。
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
- payload 顶层包含 `capability_matrix` 和 `coordinate_profile`。
- `snapshot.capability_matrix` 与顶层矩阵一致，用于判断窗口、控件、键鼠、截图、权限和依赖能力。

## type=observe

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "observe",
  "path": "observe.json",
  "title_contains": "Demo",
  "include_windows": true,
  "include_elements": true,
  "include_screenshot": true,
  "max_windows": 20,
  "max_depth": 4,
  "max_elements": 120,
  "text_limit": 120,
  "save_as": "desktop_observation"
}
```

参数：

- `desktop`: 必填。
- `type`: 必填，固定为 `observe`。
- `path`: 必填，相对于 `output/desktop-state/`。
- `request_permissions`: 可选，是否触发可探测的系统权限检查，默认 `false`。
- `include_windows`: 可选，是否返回窗口列表，默认 `true`。
- `include_invisible`: 可选，窗口列表是否包含不可见窗口，默认 `false`。
- `include_elements`: 可选，是否返回选中窗口的控件摘要，默认 `false`。
- `include_screenshot`: 可选，是否额外保存全屏截图；截图文件与 JSON 同名、扩展名为 `.png`，默认 `false`。
- Window Query: 可选，用于选择目标窗口，例如 `title_contains`、`process_name`、`window_id`。省略时使用当前窗口、聚焦窗口或第一个可见窗口。
- Element Locator: 可选，`include_elements=true` 时过滤控件，例如 `automation_id`、`name_contains`、`text_contains`、`control_type`。
- `max_windows`、`max_depth`、`max_elements`、`text_limit`: 可选，限制返回窗口数、控件树深度、控件数和文本长度。
- `save_as`: 可选。

输出：

- 写入 `output/desktop-state/<path>`。
- `kind`: 固定为 `desktop_observation`。
- `schema_version`: 当前为 `1`。
- `capability_matrix`: 当前桌面能力矩阵。
- `coordinate_profile`: 当前坐标事实。包含 `space`、`display`、`source.bounds`、`source.screen_clickable`、`transforms.local_to_screen` 和 `warnings`。
- `summary`: 窗口数、聚焦窗口、选中窗口、控件数量、截图路径和主要能力状态。
- `windows`: 精简窗口列表。
- `selected_window`: Window Query 或当前/聚焦窗口选中的窗口。
- `elements`: `include_elements=true` 时返回精简控件列表、匹配控件、`selector_hints` 和诊断。
- `screenshot`: `include_screenshot=true` 时返回截图路径、尺寸、`coordinate_profile` 和 `coordinate_diagnostics`。
- `target_candidates`: AI 可直接读取的定位候选。优先看 `best_candidate.candidate_id`、`strategy`、`confidence`、`locator`、`bounds`、`screen_clickable` 和 `action_templates`。

`target_candidates` 常见策略：

- `semantic_locator`: 控件树候选，优先用于 `desktop_element`；需要真实鼠标事件时可用 `desktop_input target=candidate`，传入同一个 `target_candidates` 和候选 `candidate_id`。
- `window_context`: 当前/选中窗口候选，用于后续 `desktop_window`、控件枚举或窗口截图。
- `visual_evidence`: 只有截图证据，先继续用 `desktop_vision`、更窄窗口查询或 `manual_confirm`。

使用场景：

- 运行前保存“当前电脑上有什么”的统一证据。
- 让 AI 基于同一个 payload 选择 `desktop_window`、`desktop_element`、`desktop_input` 或 `desktop_vision`；有 `target_candidates.best_candidate` 时先读候选。
- 控件树可用时从 `elements.selector_hints` 写稳定 locator；控件树不可用时再改用截图或视觉定位。

## 场景

- 运行前后保存桌面画面。
- 截取指定 App 窗口或控件区域，给后续 `desktop_vision`、人工检查或报告使用。
- 保存当前窗口、显示器、权限和依赖状态。
- 用 `observe` 汇总能力矩阵、窗口、控件摘要和截图，作为 AI 写后续桌面步骤的依据。
