# element

## 用途

统一处理基于选择器的元素交互。

## 必填字段

- `action`: 固定写成 `element`
- `type`: 元素操作类型
- `browser`: 浏览器会话名
- `selector`: Playwright 选择器

`selector` 不是唯一定位方式。除 `selector` 外，也可以使用语义定位字段：`role` + `name`、`text`、`label`、`placeholder`、`alt_text`、`title`、`test_id`。如果元素位于 iframe 内，可使用 `frame_selector`、`frame_name`、`frame_url`、`frame_url_contains` 或 `frame_index`。

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

## 通用可选字段

- `page`: 页面名，默认当前页面
- `frame_selector`: iframe 选择器，指定后在该 iframe 内定位元素
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始
- `index`: 当选择器匹配多个元素时选择第几个，从 `0` 开始
- `delay_ms`: 仅 `type: type` 有效，默认 `50`
- `force`: 强制执行点击、悬停或拖拽
- `timeout`: 本次元素操作超时时间，单位毫秒
- `position`: 点击或悬停的位置，例如 `{"x": 10, "y": 8}`
- `modifiers`: 修饰键数组，例如 `["ControlOrMeta"]`
- `no_wait_after`: `tap` 可用，是否跳过后续等待
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
