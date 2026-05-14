# extract

## 用途

统一从页面元素中提取数据并保存为变量。

## 必填字段

- `action`: 固定写成 `extract`
- `type`: 提取类型
- `browser`: 浏览器会话名
- `selector`: Playwright 选择器
- `save_as`: 保存变量名

除表格行提取外，元素定位支持 `selector`、frame 定位和语义定位字段：`role` + `name`、`text`、`label`、`placeholder`、`alt_text`、`title`、`test_id`。

frame 定位支持：

- `frame_selector`: 通过 iframe 元素 selector 进入 frame
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始

## 类型说明

| type | 额外字段 | 结果 |
| --- | --- | --- |
| `text` | 无 | 元素文本 |
| `value` | 无 | 输入框值 |
| `attribute` | `attribute` | 指定属性值 |
| `html` | 无 | 元素内部 HTML |
| `count` | 无 | 匹配数量 |
| `all_texts` | 可选 `skip_empty` | 所有文本数组 |
| `all_values` | 无 | 所有输入值数组 |
| `table` | `row_selector` | 表格行数据 |
| `frames` | 可选 frame 过滤字段 | 当前页面 frame 列表 |
| `url` | 无 | 当前页面 URL |
| `title` | 无 | 当前页面标题 |
| `bounding_box` | 无 | 元素位置和尺寸 |
| `css` | `property` | 元素计算样式属性值 |
| `aria_snapshot` | 可选 `depth`、`mode`、`timeout` | 元素的 Playwright ARIA snapshot |

## 示例

```json
{
  "action": "extract",
  "type": "attribute",
  "browser": "main",
  "selector": "#username",
  "attribute": "placeholder",
  "save_as": "username_placeholder"
}
```

提取 iframe 内元素文本：

```json
{
  "action": "extract",
  "type": "text",
  "browser": "main",
  "frame_selector": "#content-frame",
  "selector": "#result",
  "save_as": "frame_result"
}
```

通过 frame name 定位：

```json
{
  "action": "extract",
  "type": "text",
  "browser": "main",
  "frame_name": "details-frame",
  "selector": "#result",
  "save_as": "frame_result"
}
```

提取 frame 列表：

```json
{
  "action": "extract",
  "type": "frames",
  "browser": "main",
  "save_as": "frames"
}
```

提取表格：

```json
{
  "action": "extract",
  "type": "table",
  "browser": "main",
  "row_selector": "tbody tr",
  "cell_selector": "td",
  "save_as": "rows"
}
```

提取无障碍快照：

```json
{
  "action": "extract",
  "type": "aria_snapshot",
  "browser": "main",
  "selector": "body",
  "depth": 4,
  "save_as": "aria_snapshot"
}
```
