# 桌面定位策略

本页给 AI 选择桌面定位方式。只适用于 `automation_type: "desktop"`。

## 优先级

| 顺序 | 方式 | 使用场景 | 后续操作 |
| --- | --- | --- | --- |
| 1 | Window Query | 找 App 主窗口、弹窗、保存对话框 | `desktop_window`、`desktop_wait`、`desktop_assert type=window` |
| 2 | Element Locator | 标准按钮、输入框、列表、表格、树、菜单项、滚动容器、可访问控件 | `desktop_element`、`desktop_assert type=element` |
| 3 | `desktop_input target=element_center` | 需要系统级鼠标事件，但控件可被定位 | `desktop_input click/double_click/right_click/scroll/drag` |
| 4 | `desktop_input target=bounds_center` | 已有可信 bounds，例如控件结果或 `desktop_vision.match.bounds` | `desktop_input` 鼠标类动作 |
| 5 | 绝对 `x/y` | 临时兜底、人工确认后的固定坐标 | 必须配截图或人工确认 |
| 6 | `desktop_vision type=locate_image` | 自绘 UI、图标按钮、画布、控件树不可见、已有截图定位 | 先输出 bounds，再用 `desktop_input` |

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

先用 `desktop_element type=dump` 或 `type=list` 取证，再写稳定 locator。

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
- 最终 plan 前先获取窗口列表、控件树、截图、定位结果或人工确认。
- 能用 `automation_id/control_type/name` 时，不用绝对坐标。
- 鼠标操作后保留截图或标注证据。
- 当前视觉定位只使用 `desktop_vision type=locate_image`。
- 定位不稳定时使用 `manual_confirm`，不要扩大点击区域赌运气。
