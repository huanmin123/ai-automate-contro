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
  "replace_existing": true,
  "preserve_clipboard": true,
  "output": {"as": "typed"}
}
```

字段：

- `desktop`: 必填，桌面 session 名。
- `value`: 必填，待输入文本。
- `method`: `auto`、`type`、`clipboard`，默认 `auto`。
- `delay_ms`: 逐字符输入延迟，默认 `0`。
- `replace_existing`: 可选，布尔值。为 `true` 时先在当前焦点控件内发送平台主快捷键全选，再输入 `value`。适合搜索框、输入框覆盖旧文本，避免把 `primary+a`、`delete` 拆成多个 plan 步骤。
- `preserve_clipboard`: 使用剪贴板时是否恢复原内容，默认 `true`。
- `output.as`: 可选，保存输入结果。

## hotkey

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "hotkey",
  "keys": ["primary", "s"]
}
```

字段：

- `keys`: 必填，非空字符串数组。

常用键名：

- 跨平台别名：`primary`、`mod`、`shortcut`、`cmd_or_ctrl` 都表示系统主快捷键；macOS 映射为 `command`，Windows/Linux 映射为 `ctrl`。
- 跨平台别名：`option_or_alt`、`alt_or_option` 在 macOS 映射为 `option`，其他平台映射为 `alt`。
- 通用键名：`enter`、`esc`、`tab`、`space`、`delete`、`backspace`、`left`、`right`、`up`、`down`。
- Windows 明确键：`ctrl`、`alt`、`shift`、`win`。
- macOS 明确键：`command`、`cmd`、`option`、`ctrl`、`shift`。

跨平台 plan 优先使用 `primary`，例如搜索写 `["primary", "f"]`，全选写 `["primary", "a"]`，粘贴写 `["primary", "v"]`。确实只有某个平台不同的快捷键，再用 step 级 `platform_overrides` 覆盖 `keys`。

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
| `candidate` | `target_candidates` 或 `candidate_source`、`candidate_id` | 消费 observe/vision 返回的候选 | AI 已有 `target_candidates.best_candidate`，需要真实鼠标事件 |
| `element_center` | Window Query + Element Locator | 控件 bounds 中心 | 控件可枚举但需要系统级鼠标事件；Window Query 可用 `profile` |
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
  "target": "candidate",
  "target_candidates": "{{form_observation.target_candidates}}",
  "candidate_id": "{{form_observation.target_candidates.best_candidate.candidate_id}}",
  "min_confidence": "medium",
  "output": {"as": "candidate_click"}
}
```

```json
{
  "action": "desktop_input",
  "desktop": "desk",
  "type": "click",
  "target": "candidate",
  "candidate_source": "latest",
  "candidate_id": "{{form_observation.target_candidates.best_candidate.candidate_id}}",
  "min_confidence": "medium"
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
- `target_candidates`: `candidate` 可用，传入 `desktop_capture type=observe`、`desktop_vision` 或 `inspect_desktop` 的 `target_candidates` 对象；推荐用完整模板引用，例如 `{{obs.target_candidates}}`。
- `candidate_source`: `candidate` 可用。写 `latest`、`last`、`session` 或 `latest_target_candidates` 时，使用当前 desktop session 最近一次 `desktop_capture type=observe` 或 `desktop_vision` 保存的候选；适合紧接上一步使用，避免复制大对象。
- `candidate_id`: `candidate` 必填，候选 ID；推荐用 `{{obs.target_candidates.best_candidate.candidate_id}}` 或显式候选 ID。兼容别名 `target_candidate_id`：两者都写时 `candidate_id` 优先，只有 `candidate_id` 缺失时才读取 `target_candidate_id`；新 plan 统一写 `candidate_id`。
- `min_confidence`: `candidate` 可选，默认 `medium`。低于该置信度会失败。
- `bounds`: `bounds_center` 必填，形如 `{"x": 10, "y": 10, "width": 120, "height": 32}`；`width/height` 必须大于 `0`。
- `element_center`: 必须同时提供窗口定位字段和控件定位字段，字段同 [desktop_element](./desktop_element.md)。窗口定位可用 [app_profile](./app_profile.md) 的 `profile`。
- 窗口类 target 依赖最近一次 `desktop_window type=focus` 或 `desktop_wait type=window` 写入的 `session.current_window.bounds`。
- `allow_outside_window`: 可选布尔值，默认 `false`。坐标落点必须在激活后的目标窗口 bounds 内，并且在支持的平台上必须命中目标窗口或其子控件；确实需要点窗口外弹层、跨窗口拖拽或系统区域时才显式设为 `true`。

经验规则：

- `current_window_offset` 和 `focused_window_offset` 适合窗口已经被 `desktop_window normalize/focus` 或 `desktop_wait window` 确认后的固定布局兜底。先归一化窗口，再使用窗口内偏移，比直接写绝对 `x/y` 稳定。
- 不要在每个 `desktop_input` 前手写一个额外 `desktop_window focus`。真实输入前 runtime 会按 Window Query、候选窗口或当前 session 窗口做前台保护；连续同窗口输入时通过 `desktop.foreground_protection.cache_ttl_ms` 复用校验。
- 如果同一桌面流程中连续多次键盘/鼠标操作都指向同一窗口，并且中途没有人工切换焦点，可以把 `cache_ttl_ms` 调到 `8000` 到 `10000`。如果会跨窗口、跨弹层或执行高风险点击，保持默认值或关闭缓存。
- 看耗时时优先查 `events.jsonl` 中 `desktop input sent` 的 `elapsed_ms` 和 `guard_mode`。`restore_focus_verify` 表示执行了完整前台保护，`cached_restore_focus_verify` 表示命中缓存。

`target=candidate` 只执行两类候选：

- `strategy=semantic_locator`: 执行器重新用候选 `window_query + locator` 查找控件，再点击实时 bounds 中心。
- `strategy=visual_bounds`: 只有 `screen_clickable=true` 且置信度达标时才点击候选全局 `bounds`。

`visual_evidence`、`window_context`、`window_query_repair`、`source_path` 离线图、`screen_clickable=false` 或低置信候选不能直接执行，先继续 `desktop_capture type=observe`、`desktop_vision` 或 `manual_confirm`。

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
  "output": {"as": "clicked"}
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
  "output": {"as": "double_clicked"}
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
  "output": {"as": "right_clicked"}
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
  "output": {"as": "scrolled"}
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
  "output": {"as": "dragged"}
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

- plan 应保持简单：描述目标窗口、目标控件/候选和要执行的输入，不要为普通焦点抢占、窗口遮挡、最小化恢复或短暂前台失败手写重试循环。
- `desktop_input` 发送真实键盘或鼠标输入前会自动执行窗口激活保护：按当前 action 的 Window Query、候选里的 `window_query` 或 `session.current_window` 执行有上限的 `restore/focus`，并验证系统前台窗口仍是目标窗口。
- 如果没有 Window Query，也没有前序 `desktop_window focus` / `desktop_wait window` 写入的 `session.current_window`，运行时会失败并提示先提供目标窗口上下文。
- 成功 payload 会包含 `interaction_guard`，记录激活使用的窗口查询、目标窗口、激活后的前台窗口和有限复查次数。
- 坐标级鼠标动作默认要求 point 落在激活后的目标窗口 bounds 内；支持命中检测的平台还会确认该屏幕点真实属于目标窗口或其子控件。失败 payload 前会抛出诊断。确需窗口外坐标时写 `allow_outside_window=true`。
- 坐标级动作成功 payload 会包含 `input_resolution`、`safety_check` 和 `window_safety_check`；`window_safety_check.points[].ownership` 记录点命中的窗口归属；`target=candidate` 会记录 `candidate_id`、`strategy`、`confidence`、解析后的 point/bounds 和安全检查结果。
- `safety_check` 使用当前坐标 profile 的 mapper 做屏幕边界检查；`scale_applied=false` 表示未把未校准 DPI/缩放直接应用到点击坐标。
- 坐标级鼠标输入仍受窗口位置、缩放、多显示器、远程桌面缩放和遮挡影响；使用 `bounds_center` 或绝对坐标前先确认来源 payload 的 `coordinate_profile.source.screen_clickable=true`。
- 需要稳定操作控件时，优先使用 [desktop_element](./desktop_element.md)；控件树不可用时再考虑坐标、图像模板或人工确认兜底。
- plan 不应为普通键盘/鼠标动作手写 `command` 或 Python 脚本；使用 `desktop_input type=hotkey/type_text/click/...`。macOS `hotkey` 和 `type_text method=clipboard` 由 System Events 发送按键，鼠标坐标动作仍使用系统级输入兜底；macOS 需要 Accessibility 权限。

## 截图边界

`desktop_input` 不会自动截图，也不会隐式写入标注 PNG。需要截图证据时，显式调用 `desktop_capture type=screenshot/observe`；需要图像定位证据时，显式调用 `desktop_vision type=locate_image`。
