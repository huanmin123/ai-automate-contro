# 桌面定位策略

本页给 AI 选择桌面定位方式。只适用于 `automation_type: "desktop"`。

## 优先级

先用 `desktop_capture type=observe` 汇总 `capability_matrix`、窗口、可选控件摘要、截图和 `target_candidates`，再按下表选择具体定位方式。

如果 observe 或 `inspect_desktop` 返回 `target_candidates.best_candidate`，先看候选：

- 先记录 `candidate_id`、`strategy`、`confidence`、`screen_clickable`、`locator`、`bounds`。
- `strategy=semantic_locator`: 优先使用候选 `locator` 写 `desktop_element`；需要真实鼠标事件时用 `desktop_input target=candidate`，让执行器重新查找控件。
- `strategy=window_context`: 先用候选 Window Query 聚焦、截图或枚举控件。
- `strategy=visual_bounds`: `screen_clickable=true` 且置信度达标时可用 `desktop_input target=candidate` 或 `bounds_center` 兜底；低置信度、`screen_clickable=false` 或 `manual_confirm_recommended=true` 时先人工确认。
- `strategy=visual_evidence`: 只有截图证据，继续用 `desktop_vision` 或 `manual_confirm`。

| 顺序 | 方式 | 使用场景 | 后续操作 |
| --- | --- | --- | --- |
| 1 | Window Query | 找 App 主窗口、弹窗、保存对话框 | `desktop_window`、`desktop_wait`、`desktop_assert type=window` |
| 2 | Element Locator | 标准按钮、输入框、列表、表格、树、菜单项、滚动容器、可访问控件 | `desktop_element`、`desktop_assert type=element` |
| 3 | `desktop_input target=candidate` | 已有同一次 observe/vision 的候选，且需要真实鼠标事件 | 执行器校验 candidate 后点击 |
| 4 | `desktop_input target=element_center` | 需要系统级鼠标事件，但控件可被定位 | `desktop_input click/double_click/right_click/scroll/drag` |
| 5 | `desktop_vision type=locate_image/locate_text` | 自绘 UI、图标按钮、画布、控件树不可见、已有截图或可见短文本定位 | 先输出 candidate/bounds，再用 `desktop_input` |
| 6 | `desktop_input target=bounds_center` | 已有可信 bounds，例如控件结果或 `desktop_vision.match.bounds` | `desktop_input` 鼠标类动作 |
| 7 | 绝对 `x/y` | 临时兜底、人工确认后的固定坐标 | 必须配 `coordinate_profile`、截图或人工确认 |

## Window Query

常用字段：

- `title`
- `title_contains`
- `class_name`
- `process_name`
- `pid`
- `handle`

示例：

```json
{
  "action": "desktop_wait",
  "type": "window",
  "desktop": "desk",
  "state": "exists",
  "title_contains": "Notepad",
  "timeout_ms": 5000
}
```

## Element Locator

常用字段：

- `automation_id`
- `name`
- `name_contains`
- `control_type`
- `class_name`
- `index`

先用 `desktop_capture type=observe include_elements=true`、`desktop_element type=dump` 或 `type=list` 取证，再写稳定 locator。

表格、树、菜单和滚动容器优先使用 `desktop_element get_table/select_cell/get_tree/select_tree/invoke_menu/scroll_element`；上下文菜单项优先用 `desktop_element type=invoke_menu open_context_menu=true`。坐标级滚轮、右键和点击只作为控件树不可用、只需要打开菜单不选择菜单项，或需要系统级鼠标事件时的兜底。

```json
{
  "action": "desktop_element",
  "type": "dump",
  "desktop": "desk",
  "title_contains": "Calculator",
  "path": "calculator-elements.json",
  "save_as": "calculator_elements"
}
```

```json
{
  "action": "desktop_element",
  "type": "click",
  "desktop": "desk",
  "title_contains": "Calculator",
  "automation_id": "num5Button",
  "control_type": "Button"
}
```

## Candidate 输入

当上一步保存了 `target_candidates`，并且确实需要真实鼠标事件时，优先用候选引用，不要手动复制 bounds：

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "candidate",
  "target_candidates": "{{obs.target_candidates}}",
  "candidate_id": "{{obs.target_candidates.best_candidate.candidate_id}}",
  "min_confidence": "medium"
}
```

紧接 `desktop_capture type=observe` 或 `desktop_vision` 后使用同一个 desktop session 的最近候选时，可用 `candidate_source: "latest"`：

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "candidate",
  "candidate_source": "latest",
  "candidate_id": "{{obs.target_candidates.best_candidate.candidate_id}}",
  "min_confidence": "medium"
}
```

如果中间又执行了新的 observe/vision，`latest` 会变成新的候选；跨多步复用时传显式 `target_candidates` 更清楚。

`semantic_locator` 会重新查找控件；`visual_bounds` 必须 `screen_clickable=true`。离线图片、截图证据、低置信和 `screen_clickable=false` 不可直接执行。

## Bounds 输入

当已有可信 bounds 时，使用 `bounds_center`：

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "bounds_center",
  "bounds": "{{some_result.match.bounds}}"
}
```

`bounds` 必须包含 `x`、`y`、`width`、`height`，坐标空间必须和当前屏幕逻辑像素一致。

`desktop_vision.match.bounds` 是屏幕全局坐标，可以传给 `desktop_input target=bounds_center`；`desktop_vision.match.local_bounds` 只相对截图 source，不能直接用于屏幕点击。

## AI 规则

- 不要凭用户文字猜坐标。
- 最终 plan 前先获取 `desktop_capture type=observe`、窗口列表、控件树、截图、定位结果或人工确认。
- 能用 `automation_id/control_type/name` 时，不用绝对坐标。
- 鼠标操作后保留截图或标注证据。
- `desktop_vision type=locate_image` 适合稳定图标、图片按钮和模板图；`desktop_vision type=locate_text` 适合可见短文本稳定、控件树不可读且没有模板图的界面。
- 使用 `locate_text` 前必须确认 `capability_matrix.capabilities.vision.ocr=true`。
- 定位不稳定时使用 `manual_confirm`，不要扩大点击区域赌运气。
