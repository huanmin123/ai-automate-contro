# desktop_element

`desktop_element` 只用于 `automation_type: "desktop"`。它在目标桌面窗口的控件树中做语义定位、读取、点击、文本写入和原生触发，和浏览器线的 `element`/Playwright selector 没有关系，也不同于 `desktop_input` 鼠标类动作的坐标级输入。

当前支持：

- `list`: 枚举目标窗口控件树。
- `dump`: 导出控件树诊断、匹配结果和 selector 建议。
- `find`: 定位一个控件并返回候选。
- `wait`: 等待控件存在、不存在、可用、不可用或聚焦。
- `get_text`: 读取控件文本。
- `get_state`: 读取控件状态和 bounds。
- `get_table`: 读取表格控件的列、行和单元格文本。
- `get_tree`: 读取树控件的节点结构。
- `click`: 点击控件 bounds 中心。
- `set_text`: 先定位控件，再优先使用原生 UIA/AX 写入文本；原生不可用时退到聚焦、全选和剪贴板粘贴。
- `select`: 选择 ComboBox、ListBox、列表项或可选项。
- `select_cell`: 选择表格中的一个单元格。
- `invoke`: 先定位控件，再优先使用 Windows InvokePattern 或 macOS AXPress 触发；原生不可用时退到控件 bounds 中心点击。
- `expand_tree`: 按 `tree_path` 展开树节点。
- `collapse_tree`: 按 `tree_path` 折叠树节点。
- `select_tree`: 按 `tree_path` 选择树节点。
- `invoke_menu`: 按 `menu_path` 触发菜单栏或上下文菜单项。
- `scroll_element`: 对滚动容器做语义滚动。

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

除 `list`/`dump`/`invoke_menu` 外，所有类型都必须提供至少一种控件定位字段。`dump` 可选 Element Locator；提供后会标记命中控件并生成 near match 诊断。`get_table` 和 `select_cell` 的 Element Locator 定位表格控件；`get_tree`、`expand_tree`、`collapse_tree` 和 `select_tree` 的 Element Locator 定位树控件；`scroll_element` 的 Element Locator 定位滚动容器。`invoke_menu` 默认使用 Window Query 和 `menu_path` 定位菜单栏；`open_context_menu=true` 时必须提供 Element Locator，先右键目标控件再触发上下文菜单项。

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
- `timeout_ms`: `find/wait/get_text/get_state/click/set_text/select/invoke/get_table/select_cell/get_tree/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 的等待超时，默认 `1000`。
- `interval_ms`: 重试间隔，默认 `100`。
- `include_tree`: `dump` 是否输出嵌套控件树，默认 `true`。
- `include_selector_hints`: `dump` 是否输出稳定 locator 建议，默认 `true`。
- `text_limit`: `dump/get_table/get_tree` 中单个文本字段最大长度，默认 `160`，`0` 表示不裁剪。
- `max_nodes`: `get_tree` 最多返回树节点数，默认 `200`。
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

`list` 是桌面识别证据。

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

`selector_hints` 中 `automation_id + control_type` 通常最稳定；`element_id` 只适合同一次会话调试，不适合长期 plan。`dump` 是桌面识别证据。

当 `find`、`wait`、`get_text`、`get_state`、`get_table`、`get_tree`、`click`、`set_text`、`select`、`select_cell`、`invoke`、`expand_tree`、`collapse_tree`、`select_tree`、`invoke_menu`、`scroll_element` 或 `desktop_assert type=element` 找不到控件时，失败现场会写入 `failure-desktop-state/`，并尽量包含 `diagnostics.window`、`diagnostics.element`、`near_matches`、`selector_hints` 和推荐 locator。窗口未命中时，AI 应优先根据候选窗口修正 Window Query。

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

## type=get_table

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "get_table",
  "title_contains": "Orders",
  "automation_id": "OrdersGrid",
  "max_rows": 50,
  "max_columns": 20,
  "path": "orders-table.json",
  "save_as": "orders_table"
}
```

字段：

- `max_rows`: 可选，最多读取多少行，默认 `50`。
- `max_columns`: 可选，最多读取多少列，默认 `20`。
- `visible_only`: 可选，只返回当前可见单元格，默认 `true`。
- `text_limit`: 可选，单元格文本最大长度，默认 `160`。

主要 payload 字段：

- `table.row_count`: 表格总行数。
- `table.column_count`: 表格总列数。
- `table.columns`: 列名数组。
- `table.rows`: 按行组织的单元格。
- `table.cells`: 扁平单元格列表，每个单元格包含 `row`、`column_index`、`text`、`value`、`name`、`bounds`。
- `table.truncated`: 行列被 `max_rows/max_columns` 截断时为 `true`。

`get_table` 是桌面识别/读取证据。需要从桌面 App 表格提取数据时，优先使用它；如果表格是自绘或只加载可见行，先用 `desktop_capture` 或 `desktop_vision` 补截图证据。

## type=get_tree

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "get_tree",
  "title_contains": "Settings",
  "automation_id": "NavigationTree",
  "max_nodes": 100,
  "path": "navigation-tree.json",
  "save_as": "navigation_tree"
}
```

字段：

- `max_nodes`: 可选，最多返回树节点数，默认 `200`。
- `text_limit`: 可选，节点文本最大长度，默认 `160`。

主要 payload 字段：

- `tree.nodes`: 扁平树节点列表，每项包含 `name`、`text`、`path`、`expanded`、`leaf`、`selected`、`bounds`。
- `tree.count`: 返回节点数。
- `tree.truncated`: 节点数被 `max_nodes` 截断时为 `true`。

`get_tree` 是桌面识别/读取证据。需要操作树节点前，优先用它确认节点名称和 `tree_path`。

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

`click` 先定位控件，再点击控件 bounds 中心。它是操作推进步骤，不是桌面识别证据；需要确认桌面状态时，应在它前后补 `list/dump/find/get_text/get_state`、截图、等待或断言。

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

## type=select_cell

按行号和列名选择：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "select_cell",
  "title_contains": "Orders",
  "automation_id": "OrdersGrid",
  "row": 1,
  "column": "Status",
  "path": "orders-selected-cell.json",
  "save_as": "orders_selected_cell"
}
```

按行号和列序号选择：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "select_cell",
  "title_contains": "Orders",
  "automation_id": "OrdersGrid",
  "row": 1,
  "column_index": 2
}
```

字段：

- `row`: 必填，从 `0` 开始的行号。
- `column`: 可选，按列名精确或包含匹配。
- `column_index`: 可选，从 `0` 开始的列序号。
- `column` 和 `column_index` 至少提供一个；两者都有时优先使用 `column_index`。

主要 payload 字段：

- `selected_cell.row`
- `selected_cell.column_index`
- `selected_cell.text`
- `selected_cell.value`
- `selected_cell.bounds`
- `table.columns`

`select_cell` 是操作推进步骤，不是桌面识别证据。选择前可用 `get_table` 读取列名和目标单元格；选择后如需验证结果，继续使用 `get_table`、`desktop_assert type=element`、截图或业务状态控件断言。

## type=expand_tree / collapse_tree / select_tree

展开节点：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "expand_tree",
  "title_contains": "Settings",
  "automation_id": "NavigationTree",
  "tree_path": ["Settings"]
}
```

选择子节点：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "select_tree",
  "title_contains": "Settings",
  "automation_id": "NavigationTree",
  "tree_path": ["Settings", "Accounts"],
  "path": "selected-tree-node.json",
  "save_as": "selected_tree_node"
}
```

字段：

- `tree_path`: 必填，非空字符串数组，按树层级从根节点到目标节点填写。

主要 payload 字段：

- `tree_path`: 请求的路径。
- `tree_node.path`: 命中的节点路径。
- `tree_node.name`: 命中的节点名称。
- `method`: 使用的原生操作或 fallback 方法。

`expand_tree`、`collapse_tree` 和 `select_tree` 是操作推进步骤，不是桌面识别证据。操作前用 `get_tree` 确认路径；操作后用 `get_tree`、`desktop_assert type=element`、截图、状态文本或业务结果验证。

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

## type=invoke_menu

菜单栏：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "invoke_menu",
  "title_contains": "Demo",
  "menu_path": ["File", "Save"],
  "path": "menu-save.json",
  "save_as": "menu_save"
}
```

上下文菜单：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "invoke_menu",
  "title_contains": "Demo",
  "automation_id": "OrderList",
  "control_type": "List",
  "open_context_menu": true,
  "menu_path": ["Open"],
  "path": "context-open.json",
  "save_as": "context_open"
}
```

字段：

- `menu_path`: 必填，非空字符串数组，按菜单层级填写，例如 `["File", "Save As"]`。
- `open_context_menu`: 可选布尔值，默认 `false`。为 `true` 时先右键 Element Locator 命中的控件，再在弹出的上下文菜单中按 `menu_path` 找菜单项。
- Element Locator: 仅 `open_context_menu=true` 时必填，用来定位要右键打开上下文菜单的控件。

主要 payload 字段：

- `menu_path`: 请求的菜单路径。
- `open_context_menu`: 是否使用上下文菜单模式。
- `menu_item.name`: 命中的菜单项名称。
- `context_target`: 上下文菜单模式下被右键的控件。
- `context_open`: 上下文菜单模式下的右键触发点。
- `method`: 使用的触发方法。

`invoke_menu` 是操作推进步骤，不是桌面识别证据。触发菜单后继续用窗口等待、控件断言、截图或业务状态验证结果。只需要打开菜单但不点菜单项时，用 `desktop_input type=right_click`。

## type=scroll_element

滚动到底部：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "scroll_element",
  "title_contains": "Demo",
  "automation_id": "ResultsPanel",
  "scroll_to": "end",
  "path": "results-panel-scroll.json"
}
```

按偏移滚动：

```json
{
  "action": "desktop_element",
  "desktop": "desk",
  "type": "scroll_element",
  "title_contains": "Demo",
  "automation_id": "ResultsPanel",
  "amount": -5
}
```

字段：

- `amount`: 可选，整数，不能为 `0`。
- `scroll_to`: 可选，取值 `start`、`end`、`top`、`bottom`、`left`、`right`。
- `amount` 和 `scroll_to` 至少提供一个。

`scroll_element` 是滚动容器的语义滚动步骤。需要系统级坐标滚轮时使用 [desktop_input](./desktop_input.md) 的 `type=scroll`。滚动后用 `get_state`、`desktop_assert type=element`、截图或业务状态验证目标是否可见。

## 标注输出

`click`、`set_text`、`select`、`select_cell`、`invoke`、`expand_tree`、`collapse_tree`、`select_tree`、`invoke_menu`、`scroll_element` 成功后会尽力写入控件位置标注。读取 action payload 的 `annotation` 字段可获得标注截图和 JSON 路径。

标注 JSON 包含 `schema_version`、`coordinate_space`、`target.query`、`target.locator`、`points`、`bounds`、`overlays` 和截图路径。原生控件操作不一定需要坐标，但标注会使用控件 `bounds` 中心作为诊断点。标注失败不会让控件操作失败，payload 的 `annotation.ok=false` 会记录错误原因。

## 平台行为

- Windows: 使用系统 UIAutomationClient 枚举控件树；`set_text` 优先 ValuePattern，`select` 优先 SelectionItemPattern，`invoke` 优先 InvokePattern；表格、树、菜单和滚动容器优先使用对应 UIA pattern；坐标 fallback 通过 `pyautogui` 发送鼠标输入。
- macOS: 使用 System Events/Accessibility 做有限深度控件枚举；`set_text` 优先 AX value，`select` 优先 AX 可选项或 System Events，`invoke` 优先 AXPress；坐标/键盘 fallback 通常需要 Accessibility 权限。高级控件能力先看 `capability_matrix.capabilities.semantic`，缺能力时用截图、图像定位或人工确认兜底。

## 边界

- 控件树可能因 App 框架、自绘 UI、权限、完整性级别或系统隐私授权而缺失。
- `element_id`/`runtime_id` 不是跨运行稳定句柄。长期 plan 应优先使用 `automation_id`、`name`、`text`、`control_type`、`role` 等语义定位。
- plan 应优先表达语义操作，例如点击按钮、设置文本、选择项、选择表格单元格、展开树节点、执行菜单项或滚动容器；不要为普通焦点抢占、窗口遮挡、最小化恢复或短暂前台失败手写重试循环。
- `click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 这类会改变桌面状态的动作会在执行前自动激活目标窗口，payload 的 `interaction_guard` 会记录 `restore/focus`、前台窗口验证结果和有限复查次数。
- `set_text` fallback 会短暂改变焦点和剪贴板；需要强一致验证时，写入后继续做 `desktop_assert type=element` 或 `get_text`。
- `select/invoke` fallback 仍受窗口位置、多显示器和权限影响；运行时会先激活目标窗口，但自绘 UI 或系统禁止抢焦点时会失败并返回诊断。
- 大表格、大树、虚拟滚动表格或懒加载列表可能只返回当前已加载或可见内容；需要翻页或滚动时，先保留截图/表格/树读取证据，再用滚动或业务控件推进。
- 菜单和滚动容器容易受焦点、短生命周期弹出层、窗口遮挡和自绘 UI 影响；必要时配合 `desktop_wait`、`desktop_capture`、`desktop_vision` 或 `manual_confirm`。
- 浏览器网页控件继续使用浏览器线 `element`。不要在 desktop plan 里写 Playwright selector。
