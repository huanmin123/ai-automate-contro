# extract

## 用途

统一从页面元素中提取数据并保存为变量。

## 必填字段

- `action`: 固定写成 `extract`
- `type`: 提取类型
- `browser`: 浏览器会话名
- `output.as`: 保存变量名

`selector` 不是全类型必填。定位要求按 `type` 划分：

| type 分组 | 定位要求 | 其他必填字段 |
| --- | --- | --- |
| `text`、`value`、`html`、`bounding_box`、`aria_snapshot` | `selector` 或一种语义定位字段 | 无 |
| `attribute` | `selector` 或一种语义定位字段 | `attribute` |
| `css` | `selector` 或一种语义定位字段 | `property` |
| `count`、`all_texts`、`all_values` | 必须使用 `selector`，不支持语义定位字段 | 无 |
| `table` | 行定位必须使用 `row_selector`，不支持语义定位字段 | 无 |
| `frames`、`url`、`title` | 页面级提取，不需要元素定位字段 | 无 |

`frames`、`url`、`title` 直接读取当前页面信息，不定位元素；其余类型是元素级提取。元素级提取都支持 frame 定位；`selector` 定位对所有元素级 type 可用，语义定位字段（`role` + `name`、`text`、`label`、`placeholder`、`alt_text`、`title`、`test_id`）只对第一组的单元素 type 生效，`count`、`all_texts`、`all_values`、`table` 只认 `selector` 字符串。

命中多个元素时选择第几个的字段各不相同：元素型 type 用 `index`，`count` 用 `count_index`，`all_texts` 用 `all_texts_index`，`all_values` 用 `all_values_index`，`table` 的行用 `row_index`，都从 `0` 开始。

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
| `count` | `selector`（必填） | 匹配数量 |
| `all_texts` | `selector`（必填），可选 `skip_empty` | 所有文本数组 |
| `all_values` | `selector`（必填） | 所有输入值数组 |
| `table` | `row_selector`（必填），可选 `cell_selector`、`include_header`、`header_selector` | 表格行数据 |
| `frames` | 可选 frame 过滤字段 | 当前页面 frame 列表 |
| `url` | 无 | 当前页面 URL |
| `title` | 无 | 当前页面标题 |
| `bounding_box` | 无 | 元素位置和尺寸 |
| `css` | `property` | 元素计算样式属性值 |
| `aria_snapshot` | 可选 `depth`、`mode`、`timeout` | 元素的 Playwright ARIA snapshot |

`table` 参数说明：

- `row_selector`: 行选择器，必填，匹配的每个元素作为一行
- `cell_selector`: 单元格选择器，默认 `td`
- `include_header`: 是否提取表头并把每行组装成 `{表头: 值}` 字典，默认 `false`；为 `false` 时每行输出文本数组
- `header_selector`: 表头单元格选择器，仅在 `include_header: true` 时读取；启用表头但未提供时按无表头处理，每行输出数组

`all_texts.skip_empty` 默认 `true`，过滤空文本；设为 `false` 时保留空字符串项。`frames` 的过滤字段：`frame_name`（精确 name）、`frame_url`（精确 URL）、`frame_url_contains`（URL 片段）、`frame_index`（`page.frames` 顺序，从 `0` 开始），建议只使用其中一个（同时提供多个时按全部条件求交集过滤，不会报错），全部缺省返回所有 frame。

`aria_snapshot.mode` 只能写 `default` 或 `ai`。需要更适合模型阅读的快照时用 `ai`，不要写旧示例或其他库里可能出现的 `interesting`。

如果目标数据已经是页面里的可见列表、表格、文本块或一组同类元素，优先使用 `extract.table`、`extract.all_texts`、`extract.text` 或配合 `script.evaluate` 做确定性提取，不要先把整页文本扔给 `ai` action 重新猜一遍。

## 示例

```json
{
  "action": "extract",
  "type": "attribute",
  "browser": "main",
  "selector": "#username",
  "attribute": "placeholder",
  "output": {"as": "username_placeholder"}
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
  "output": {"as": "frame_result"}
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
  "output": {"as": "frame_result"}
}
```

提取 frame 列表：

```json
{
  "action": "extract",
  "type": "frames",
  "browser": "main",
  "output": {"as": "frames"}
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
  "output": {"as": "rows"}
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
  "output": {"as": "aria_snapshot"}
}
```
