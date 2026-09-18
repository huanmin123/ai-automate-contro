# element

## 用途

统一处理基于选择器的元素交互。

## 必填字段

- `action`: 固定写成 `element`
- `type`: 元素操作类型
- `browser`: 浏览器会话名
- 元素定位：`selector` 或一种语义定位字段（见下），二选一

`selector` 不是唯一定位方式。除 `selector` 外，也可以使用语义定位字段：`role` + `name`、`text`、`label`、`placeholder`、`alt_text`、`title`、`test_id`。如果元素位于 iframe 内，可使用 `frame_selector`、`frame_name`、`frame_url`、`frame_url_contains` 或 `frame_index`。

## 定位经验

- 优先使用语义 locator：`role + name`、`label`、`placeholder`、`test_id`、稳定业务属性或短 CSS selector。真实页面里按钮、输入框、菜单项优先找可读名称，不优先写长 CSS、XPath、`nth-child` 或页面坐标。
- 页面结构不稳定时先用 `inspect_web_page`、`extract type=aria_snapshot`、`extract type=frames` 或 headed 探索确认 locator。最终 plan 不能只凭用户描述猜 selector。
- 多个元素命中时，先缩小 locator、补充容器 selector、补充 `role/name` 或进入正确 iframe；`index` 只适合同类列表有稳定排序的场景，不适合作为长期兜底。
- 输入框优先使用 `type=fill`，下拉框优先使用 `type=select`，上传文件优先使用 `type=set_files`。只有需要模拟逐字输入、组合键、滚动、拖拽或页面级鼠标时才用 [input](./input.md)。
- 点击前如果页面存在异步加载，先用 `wait type=selector/element_state/text/function` 等目标可见、可用或业务状态就绪。点击后用 `wait`、`assert` 或 `extract` 验证结果，不要只加固定等待。
- `force`、`position` 和坐标类点击是兜底手段。使用前要先确认不是遮罩、禁用态、iframe 或 locator 过宽导致的问题。

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `click` | 无 | 点击元素 |
| `dblclick` | 无 | 双击元素 |
| `right_click` | 无 | 右键点击元素 |
| `hover` | 无 | 悬停元素 |
| `tap` | 无 | 触控点击元素 |
| `fill` | `value` | 清空并填入内容 |
| `clear` | 无 | 清空输入框 |
| `type` | `value` | 模拟逐字输入 |
| `focus` | 无 | 聚焦元素 |
| `press` | `key` | 在元素上按键 |
| `check` | 无 | 勾选复选框或单选框 |
| `uncheck` | 无 | 取消勾选 |
| `select` | `value` / `label` / `index_value` | 选择下拉项 |
| `set_files` | `files` | 设置文件上传输入框 |
| `drag_to` | `target_selector` | 拖拽当前元素到目标元素 |

`set_files.files` 推荐使用当前 plan 包 `resources/...`。AI 创建 plan 时，用户没有指定固定本机上传路径时，推荐先把文件导入当前包 `resources/`，再写 `resources/...`。用户要求使用本机绝对路径、共享盘、外部工作目录或越出 plan 包的相对路径时可以直接写入；不需要审批字段。plan JSON 内部路径推荐使用 `/`。

## 通用可选字段

- `page`: 页面名，默认当前页面
- `frame_selector`: iframe 选择器，指定后在该 iframe 内定位元素
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始
- `index`: 当选择器匹配多个元素时选择第几个，从 `0` 开始
- `delay_ms`: 整数，默认不设置。`type` 表示逐字输入间隔（默认 `50`）；`click`、`dblclick`、`right_click` 表示连续点击之间的间隔
- `force`: 布尔，默认 `false`，跳过可操作性检查强制执行，适用 `click`、`dblclick`、`right_click`、`hover`、`tap`、`drag_to`
- `trial`: 布尔，默认 `false`，只做元素可操作性检查，不产生实际点击、悬停或拖拽，适用 `click`、`dblclick`、`right_click`、`hover`、`tap`、`drag_to`
- `timeout`: 整数，本次元素操作超时时间，单位毫秒，不设置时使用会话默认超时（见 `open_browser.timeout_ms`）
- `position`: 对象，点击、悬停或触控时相对元素左上角的偏移坐标，例如 `{"x": 10, "y": 8}`，适用 `click`、`dblclick`、`right_click`、`hover`、`tap`
- `button`: 字符串，鼠标键，`left`、`right`、`middle`，默认 `left`，适用 `click`、`dblclick`；`right_click` 固定为 `right`，该字段会被忽略
- `click_count`: 整数，最小 `1`，默认 `1`，点击次数，`click`、`right_click` 有效（`dblclick` 已等价于 2 次点击）；需要双击时优先用 `type: dblclick`
- `modifiers`: 修饰键数组，例如 `["ControlOrMeta"]`，适用 `click`、`dblclick`、`right_click`、`hover`、`tap`
- `no_wait_after`: 布尔，是否跳过操作后的默认等待，仅 `tap` 可用
- `source_position`: 对象，拖拽起点相对源元素左上角的偏移坐标，例如 `{"x": 10, "y": 10}`，仅 `drag_to` 有效
- `target_position`: 对象，拖拽终点相对目标元素左上角的偏移坐标，仅 `drag_to` 有效
- `target_index`: `drag_to` 目标选择器匹配多个元素时选择第几个

## 示例

```json
{
  "action": "element",
  "type": "fill",
  "browser": "main",
  "selector": "input[autocomplete='username']",
  "value": "{{email}}"
}
```

iframe 内输入：

```json
{
  "action": "element",
  "type": "fill",
  "browser": "main",
  "frame_selector": "#payment-frame",
  "label": "Card number",
  "value": "{{card_number}}"
}
```

通过 frame name 输入：

```json
{
  "action": "element",
  "type": "fill",
  "browser": "main",
  "frame_name": "details-frame",
  "label": "Frame Note",
  "value": "demo"
}
```

语义定位点击：

```json
{
  "action": "element",
  "type": "click",
  "browser": "main",
  "role": "button",
  "name": "提交"
}
```

触控点击：

```json
{
  "action": "element",
  "type": "tap",
  "browser": "mobile",
  "selector": "#primary-action"
}
```
