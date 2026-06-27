# desktop_input

`desktop_input` 只用于 `automation_type: "desktop"`。它发送操作系统级键盘和鼠标输入，不读取浏览器 DOM，也不等同于浏览器线的 `keyboard`、`mouse`、`element.click`。

## 类型

| type | 作用 | 关键参数 | 场景 |
| --- | --- | --- | --- |
| `type_text` | 输入文本 | `value`、`method`、`delay_ms` | 向当前焦点控件输入文本 |
| `hotkey` | 发送组合键 | `keys` | 保存、全选、关闭菜单、平台快捷键 |
| `click` | 坐标级点击 | `target` 或 `x/y`、`button`、`clicks` | 控件语义点击不可用时兜底 |
| `double_click` | 坐标级左键双击 | `target` 或 `x/y`、`interval_ms` | 打开文件、选中文本、触发双击区域 |
| `right_click` | 坐标级右键点击 | `target` 或 `x/y` | 打开上下文菜单 |
| `scroll` | 坐标级滚轮 | `target` 或 `x/y`、`amount` | 滚动列表、页面或面板 |
| `drag` | 坐标级拖拽 | `target + delta_x/delta_y` 或 `start_x/start_y/end_x/end_y` | 拖动滑块、拖拽区域、移动对象 |

## type_text

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "type_text",
  "value": "hello",
  "method": "clipboard",
  "preserve_clipboard": true,
  "save_as": "typed"
}
```

字段：

- `desktop`: 必填，桌面 session 名。
- `value`: 必填，待输入文本。
- `method`: `auto`、`type`、`clipboard`，默认 `auto`。
- `delay_ms`: 逐字符输入延迟，默认 `0`。
- `preserve_clipboard`: 使用剪贴板时是否恢复原内容，默认 `true`。
- `save_as`: 可选，保存输入结果。

## hotkey

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "hotkey",
  "keys": ["ctrl", "s"]
}
```

字段：

- `keys`: 必填，非空字符串数组。

常用键名：

- Windows: `ctrl`、`alt`、`shift`、`win`、`enter`、`esc`、`tab`。
- macOS: `command`、`cmd`、`option`、`ctrl`、`shift`、`enter`、`esc`、`tab`。

plan 应按目标平台写明确快捷键；runtime 不把业务含义自动翻译成平台快捷键。

## 系统文件对话框

Open/Save 文件对话框优先按系统窗口处理，不要默认依赖文件名输入框的控件树定位。常用稳定流程：

1. 先用 `desktop_element type=click` 或 `desktop_input type=click target=element_center` 点击触发按钮。
2. 用 `desktop_wait type=window` 等待 Open/Save 对话框出现。
3. 用 `desktop_capture type=screenshot` 保存对话框证据。
4. 用 `desktop_input type=type_text method=clipboard` 输入完整文件路径。
5. 用 `desktop_input type=hotkey keys=["enter"]` 确认。
6. 用 `desktop_wait type=window state=not_exists` 等待对话框关闭。

```json
[
  {
    "action": "desktop_wait",
    "desktop": "desk",
    "type": "window",
    "title_contains": "Open",
    "state": "exists",
    "timeout_ms": 5000
  },
  {
    "action": "desktop_capture",
    "desktop": "desk",
    "type": "screenshot",
    "path": "open-dialog.png"
  },
  {
    "action": "desktop_input",
    "desktop": "desk",
    "type": "type_text",
    "value": "{{absolute_file_path}}",
    "method": "clipboard",
    "preserve_clipboard": true
  },
  {
    "action": "desktop_input",
    "desktop": "desk",
    "type": "hotkey",
    "keys": ["enter"]
  }
]
```

如果触发按钮使用 `desktop_element type=invoke` 后 plan 卡住，说明原生 invoke 正在等待模态对话框关闭；改用 `click`。

## 鼠标目标定位

`click`、`double_click`、`right_click`、`scroll` 支持 `target` 或绝对 `x/y`，二选一。`drag` 支持 `target + delta_x/delta_y` 或绝对起止坐标。

`target` 可选值：

| target | 必填字段 | 作用 | 场景 |
| --- | --- | --- | --- |
| `current_window_center` | 先聚焦/等待窗口 | 最近窗口 bounds 中心 | 临时兜底点击窗口中央 |
| `focused_window_center` | 先聚焦/等待窗口 | 同 `current_window_center` | 强调当前焦点窗口 |
| `current_window_offset` | `offset_x`、`offset_y` | 最近窗口左上角加偏移 | 固定布局工具面板 |
| `focused_window_offset` | `offset_x`、`offset_y` | 同 `current_window_offset` | 焦点窗口内固定位置 |
| `element_center` | Window Query + Element Locator | 控件 bounds 中心 | 控件可枚举但需要系统级鼠标事件 |
| `bounds_center` | `bounds` | 给定 bounds 中心 | 使用前一步 `get_state/dump` 返回的 bounds |

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "click",
  "target": "current_window_center",
  "button": "left",
  "clicks": 1
}
```

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "double_click",
  "target": "element_center",
  "title_contains": "Demo",
  "automation_id": "CanvasPanel",
  "control_type": "Pane",
  "max_depth": 5,
  "max_elements": 200
}
```

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "click",
  "target": "bounds_center",
  "bounds": "{{panel_state.element_state.bounds}}"
}
```

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "click",
  "x": 640,
  "y": 360,
  "button": "left"
}
```

字段：

- `target`: 可选，见上表。
- `x` / `y`: 可选，绝对屏幕坐标；使用坐标时必须同时提供，不能和 `target` 同时使用。
- `offset_x` / `offset_y`: `current_window_offset`、`focused_window_offset` 必填，表示相对窗口左上角的像素偏移。
- `bounds`: `bounds_center` 必填，形如 `{"x": 10, "y": 10, "width": 120, "height": 32}`；`width/height` 必须大于 `0`。
- `element_center`: 必须同时提供窗口定位字段和控件定位字段，字段同 [desktop_element](./desktop_element.md)。
- 窗口类 target 依赖最近一次 `desktop_window type=focus` 或 `desktop_wait type=window` 写入的 `session.current_window.bounds`。

## click

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "click",
  "target": "current_window_center",
  "button": "left",
  "clicks": 1,
  "interval_ms": 0,
  "save_as": "clicked"
}
```

字段：

- `button`: `left`、`right`、`middle`，默认 `left`。
- `clicks`: 点击次数，默认 `1`。
- `interval_ms`: 多次点击的间隔，默认 `0`。

## double_click

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "double_click",
  "target": "current_window_center",
  "interval_ms": 50,
  "save_as": "double_clicked"
}
```

字段：

- `interval_ms`: 双击两次点击之间的间隔，默认 `0`。
- 固定发送左键双击；需要其他按钮多次点击时使用 `click`。

## right_click

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "right_click",
  "target": "current_window_center",
  "save_as": "right_clicked"
}
```

字段：

- 固定发送右键单击。
- 如果目标是选择右键菜单项，优先用 [desktop_element](./desktop_element.md) 的 `type=invoke_menu` + `open_context_menu=true`。
- 右键后通常要用 `desktop_input type=hotkey keys=["esc"]` 关闭上下文菜单，避免遮挡后续步骤。

## scroll

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "scroll",
  "target": "current_window_center",
  "amount": -3,
  "save_as": "scrolled"
}
```

字段：

- `amount`: 必填，整数，不能为 `0`。正数向上滚动，负数向下滚动。

如果控件树可用且目标是滚动容器，优先使用 [desktop_element](./desktop_element.md) 的 `type=scroll_element`；本动作是坐标级滚轮兜底。

## drag

使用当前窗口中心作为起点，并按偏移量拖拽：

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "drag",
  "target": "current_window_center",
  "delta_x": 80,
  "delta_y": 0,
  "duration_ms": 150,
  "save_as": "dragged"
}
```

或使用绝对起止坐标：

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "drag",
  "start_x": 300,
  "start_y": 300,
  "end_x": 420,
  "end_y": 300,
  "duration_ms": 150
}
```

字段：

- `target` + `delta_x` / `delta_y`: `target` 解析为起点；`delta_x` 和 `delta_y` 至少提供一个，不能同时为 `0`。
- `start_x` / `start_y` / `end_x` / `end_y`: 绝对坐标模式，四个字段必填。
- `button`: `left`、`right`、`middle`，默认 `left`。
- `duration_ms`: 拖拽持续时间，默认 `0`；真实桌面建议给 `100-300` 提高稳定性。

## 边界

- `desktop_input` 不会自动聚焦窗口；需要先用 `desktop_window type=focus` 或让用户通过 `manual_confirm` 确认焦点。
- 坐标级鼠标输入受窗口位置、缩放、多显示器、远程桌面缩放、遮挡和当前焦点影响。
- 需要稳定操作控件时，优先使用 [desktop_element](./desktop_element.md)；控件树不可用时再考虑坐标、图像或 OCR 兜底。
- Windows/macOS 输入由 `pyautogui` 执行；macOS 需要 Accessibility 权限。

## 标注输出

`click`、`double_click`、`right_click`、`scroll`、`drag` 成功后会尽力写入标注证据：

- `output/<run>/desktop-annotations/step-xxx-<desktop>-desktop_input.<type>.png`
- `output/<run>/desktop-annotations/step-xxx-<desktop>-desktop_input.<type>.json`

JSON 包含 `schema_version`、`coordinate_space`、`target`、`points`、`bounds`、`overlays`、`warnings` 和截图路径。标注失败不会让鼠标动作失败，payload 的 `annotation.ok=false` 会记录错误原因。
