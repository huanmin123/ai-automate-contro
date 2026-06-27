# desktop_element

`desktop_element` 只用于 `automation_type: "desktop"`。它在目标桌面窗口的控件树中做语义定位、读取、点击、文本写入和原生触发，和浏览器线的 `element`/Playwright selector 没有关系，也不同于 `desktop_input` 鼠标类动作的坐标级输入。

当前支持：

- `list`: 枚举目标窗口控件树。
- `dump`: 导出控件树诊断、匹配结果和 selector 建议。
- `find`: 定位一个控件并返回候选。
- `wait`: 等待控件存在、不存在、可用、不可用或聚焦。
- `get_text`: 读取控件文本。
- `get_state`: 读取控件状态和 bounds。
- `click`: 点击控件 bounds 中心。
- `set_text`: 先定位控件，再优先使用原生 UIA/AX 写入文本；原生不可用时退到聚焦、全选和剪贴板粘贴。
- `select`: 选择 ComboBox、ListBox、列表项或可选项。
- `invoke`: 先定位控件，再优先使用 Windows InvokePattern 或 macOS AXPress 触发；原生不可用时退到控件 bounds 中心点击。

## Window Query

所有 `desktop_element` 类型都必须先用 Window Query 限定目标窗口：

- `title`
- `title_contains`
- `title_regex`
- `app`
- `process`
- `process_name`
- `class_name`
- `window_id`
- `match_index`

`match_index` 只能在多个窗口候选时选择索引，不能单独作为定位字段。

## Element Locator

除 `list`/`dump` 外，所有类型都必须提供至少一种控件定位字段。`dump` 可选 Element Locator；提供后会标记命中控件并生成 near match 诊断。

- `element_id`: backend 返回的控件 id/runtime id。
- `automation_id`: Windows UI Automation AutomationId；macOS 通常为空。
- `name`: 控件名称精确匹配。
- `name_contains`: 控件名称包含文本。
- `name_regex`: 控件名称正则匹配。
- `text`: 控件文本精确匹配。
- `text_contains`: 控件文本包含文本。
- `text_regex`: 控件文本正则匹配。
- `control_type`: 控件类型，例如 `Button`、`Edit`、`Window`。
- `role`: 平台角色；Windows 映射自 control type，macOS 映射 AX role。
- `element_class_name`: Windows class name 包含匹配；macOS 通常为空。
- `element_match_index`: 多个控件候选时选择索引，默认 `0`，不能单独作为定位字段。

通用字段：

- `max_depth`: 控件树最大深度，默认 `6`。
- `max_elements`: 最多返回控件数，默认 `200`。
- `timeout_ms`: `find/wait/get_text/get_state/click/set_text/select/invoke` 的等待超时，默认 `1000`。
- `interval_ms`: 重试间隔，默认 `100`。
- `include_tree`: `dump` 是否输出嵌套控件树，默认 `true`。
- `include_selector_hints`: `dump` 是否输出稳定 locator 建议，默认 `true`。
- `text_limit`: `dump` 中单个文本字段最大长度，默认 `160`，`0` 表示不裁剪。
- `path`: 可选，写入 `output/desktop-elements/`。
- `save_as`: 可选，保存 payload。

## type=list

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "list",
  "title_contains": "Notepad",
  "path": "notepad-elements.json",
  "save_as": "elements",
  "max_depth": 4,
  "max_elements": 250
}
```

`list` 可以不写 Element Locator；如果写了 `name_contains`、`control_type` 等字段，会在枚举后过滤结果。

`list` 是桌面识别证据，可用于 AI 终端质量门禁。

## type=dump

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "dump",
  "title_contains": "Demo",
  "automation_id": "DesktopElementTextBox",
  "control_type": "Edit",
  "path": "demo-elements-dump.json",
  "save_as": "element_dump",
  "max_depth": 6,
  "max_elements": 300
}
```

`dump` 用于调试和生成稳定 Element Locator。它可以不写 Element Locator，此时导出目标窗口控件树；也可以写 `automation_id`、`name_contains`、`control_type` 等定位字段，此时 payload 会额外标记匹配和近似匹配。

主要 payload 字段：

- `elements`: 扁平控件列表，每项包含 `id`、`parent_id`、`depth`、`name`、`text`、`automation_id`、`control_type`、`role`、`class_name`、`bounds`、`matched`。
- `tree`: 由 `parent_id` 组装的嵌套控件树。
- `matches`: 当前 Element Locator 的精确命中。
- `selected_element`: 第一个精确命中。
- `near_matches`: 当前 Element Locator 没有精确命中或命中过宽时的近似候选。
- `selector_hints`: 面向匹配控件的 locator 建议，包含 `stability`、`match_count`、`unique`。
- `diagnostics`: 是否歧义、backend 限制、推荐修正方式和枚举深度信息。

`selector_hints` 中 `automation_id + control_type` 通常最稳定；`element_id` 只适合同一次会话调试，不适合长期 plan。`dump` 是桌面识别证据，可用于 AI 终端质量门禁。

当 `find`、`wait`、`get_text`、`get_state`、`click`、`set_text`、`select`、`invoke` 或 `desktop_assert type=element` 找不到控件时，失败现场会写入 `failure-desktop-state/`，并尽量包含 `diagnostics.window`、`diagnostics.element`、`near_matches`、`selector_hints` 和推荐 locator。窗口未命中时，AI 应优先根据候选窗口修正 Window Query。

## type=find

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "find",
  "title_contains": "Calculator",
  "name": "Five",
  "control_type": "Button",
  "save_as": "five_button"
}
```

返回 `element`、`matches`、`candidates_count`、`window` 和 `locator`。`find` 是桌面识别证据。

## type=wait

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "wait",
  "title_contains": "Demo",
  "name_contains": "Saved",
  "state": "exists",
  "timeout_ms": 5000,
  "interval_ms": 100
}
```

`state` 可选：

- `exists`
- `not_exists`
- `enabled`
- `disabled`
- `focused`

`wait` 是桌面识别证据。

## type=get_text

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "get_text",
  "title_contains": "Demo",
  "automation_id": "statusText",
  "save_as": "status_text"
}
```

返回字段包含 `text`。文本来源优先级为控件 `text`、`value`、`name`。`get_text` 是桌面识别证据。

## type=get_state

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "get_state",
  "title_contains": "Demo",
  "name_contains": "Submit",
  "control_type": "Button",
  "save_as": "submit_state"
}
```

返回 `element_state`：

```json
{
  "enabled": true,
  "visible": true,
  "focused": false,
  "bounds": {"x": 10, "y": 10, "width": 120, "height": 32}
}
```

`get_state` 是桌面识别证据。

## type=click

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "click",
  "title_contains": "Demo",
  "name_contains": "Login",
  "control_type": "Button",
  "save_as": "login_click"
}
```

`click` 先定位控件，再点击控件 bounds 中心。它是操作推进步骤，不是桌面识别证据；需要质量门禁通过时，应在它前后补 `list/dump/find/get_text/get_state`、截图、等待或断言。

## type=set_text

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "set_text",
  "title_contains": "Demo",
  "automation_id": "username",
  "value": "alice@example.com",
  "save_as": "username_set"
}
```

字段：

- `value`: 必填，要写入控件的文本。
- `preserve_clipboard`: 可选，fallback 使用剪贴板时是否恢复原剪贴板，默认 `true`。

行为：

- Windows 环境使用 UIAutomation `ValuePattern.SetValue`。
- macOS 优先使用 Accessibility 的 value 写入。
- 原生写入不可用或控件只读时，fallback 会点击控件中心、发送全选快捷键，再通过剪贴板粘贴。
- payload 会包含 `method`、`fallback_used`、`fallback_error`、`length` 等字段。

`set_text` 是输入/操作推进步骤，不是桌面识别证据。需要验证写入结果时，继续使用 `desktop_assert type=element`、`get_text` 或截图。

## type=select

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "select",
  "title_contains": "Demo",
  "automation_id": "modeCombo",
  "control_type": "ComboBox",
  "option_index": 2,
  "save_as": "mode_selected"
}
```

按可见文本选择：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "select",
  "title_contains": "Demo",
  "automation_id": "colorList",
  "control_type": "List",
  "value": "Green"
}
```

字段：

- `value`: 可选，按选项的 `name`、`text` 或 `value` 精确/包含匹配。
- `option_index`: 可选，从 `0` 开始的选项序号。
- `value` 和 `option_index` 至少提供一个；两者都有时优先使用明确选项匹配，必要时再按序号兜底。

行为：

- Windows 环境使用 UI Automation `SelectionItemPattern.Select`，ComboBox 会先尝试展开再查找选项；模式不可用时退到控件中心点击、`Home`、方向键和 `Enter`。
- macOS 优先使用 Accessibility/System Events 选择或点击匹配项；失败时退到坐标点击。
- payload 会包含 `method`、`fallback_used`、`fallback_error`、`value`、`option_index` 等字段。

`select` 是操作推进步骤，不是桌面识别证据。需要验证选中结果时，继续使用 `desktop_assert type=element`、`get_text/get_state` 或截图。

## type=invoke

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "invoke",
  "title_contains": "Demo",
  "name": "Save",
  "control_type": "Button",
  "save_as": "save_invoked"
}
```

行为：

- Windows 环境使用 UIAutomation `InvokePattern.Invoke`。
- macOS 优先使用 Accessibility `AXPress`，失败后尝试 System Events `click`。
- 原生触发不可用时 fallback 到控件 bounds 中心点击。
- payload 会包含 `method`、`fallback_used`、`fallback_error` 等字段。

`invoke` 和 `click/select` 一样是操作推进步骤，不是桌面识别证据。

## 标注输出

`click`、`set_text`、`select`、`invoke` 成功后会尽力写入控件位置标注：

- `output/<run>/desktop-annotations/step-xxx-<desktop>-desktop_element.<type>.png`
- `output/<run>/desktop-annotations/step-xxx-<desktop>-desktop_element.<type>.json`

JSON 包含 `schema_version`、`coordinate_space`、`target.query`、`target.locator`、`points`、`bounds`、`overlays` 和截图路径。原生控件操作不一定需要坐标，但标注会使用控件 `bounds` 中心作为诊断点。标注失败不会让控件操作失败，payload 的 `annotation.ok=false` 会记录错误原因。

## 平台行为

- Windows: 使用系统 UIAutomationClient 枚举控件树；`set_text` 优先 ValuePattern，`select` 优先 SelectionItemPattern，`invoke` 优先 InvokePattern；坐标 fallback 通过 `pyautogui` 发送鼠标输入。
- macOS: 使用 System Events/Accessibility 做有限深度控件枚举；`set_text` 优先 AX value，`select` 优先 AX 可选项或 System Events，`invoke` 优先 AXPress；坐标/键盘 fallback 通常需要 Accessibility 权限。

## 边界

- 控件树可能因 App 框架、自绘 UI、权限、完整性级别或系统隐私授权而缺失。
- `element_id`/`runtime_id` 不是跨运行稳定句柄。长期 plan 应优先使用 `automation_id`、`name`、`text`、`control_type`、`role` 等语义定位。
- `set_text` fallback 会短暂改变焦点和剪贴板；需要强一致验证时，写入后继续做 `desktop_assert type=element` 或 `get_text`。
- `select/invoke` fallback 仍受遮挡、窗口位置、多显示器和权限影响；可先用 `desktop_window focus`。
- 浏览器网页控件继续使用浏览器线 `element`。不要在 desktop plan 里写 Playwright selector。
