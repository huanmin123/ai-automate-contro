# 桌面定位策略

本页给 AI 选择桌面定位方式。只适用于 `automation_type: "desktop"`。

## 优先级

| 顺序 | 方式 | 使用场景 | 后续操作 |
| --- | --- | --- | --- |
| 1 | Window Query | 找 App 主窗口、弹窗、保存对话框 | `desktop_window`、`desktop_wait`、`desktop_assert type=window` |
| 2 | Element Locator | 标准按钮、输入框、列表、菜单项、可访问控件 | `desktop_element`、`desktop_assert type=element` |
| 3 | `desktop_input target=element_center` | 需要系统级鼠标事件，但控件可被定位 | `desktop_input click/double_click/right_click/scroll/drag` |
| 4 | `desktop_input target=bounds_center` | 已有可信 bounds，例如控件结果或未来视觉结果 | `desktop_input` 鼠标类动作 |
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

## AI 规则

- 不要凭用户文字猜坐标。
- 最终 plan 前先获取窗口列表、控件树、截图、定位结果或人工确认。
- 能用 `automation_id/control_type/name` 时，不用绝对坐标。
- 鼠标操作后保留截图或标注证据。
- 当前可写 `desktop_vision type=locate_image`；不要把 `locate_text` 写入可运行 plan。
- 定位不稳定时使用 `manual_confirm`，不要扩大点击区域赌运气。
