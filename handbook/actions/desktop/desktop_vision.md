# desktop_vision

作用：从桌面截图、窗口截图、控件截图或已有图片中做图像/OCR 定位，输出屏幕全局 `bounds/point`、source 局部 `local_bounds/local_point` 和证据文件。它只负责定位和取证，不负责点击或输入。

能用 `desktop_element` 时优先使用 `desktop_element`；控件树不可见、自绘 UI、图标按钮、图片按钮或只剩可见文本时再用 `desktop_vision`。

## 类型

| type | 作用 | 关键参数 |
| --- | --- | --- |
| `locate_image` | 模板图匹配 | `template_path`、`source_path/source_target`、`region`、`threshold` |
| `locate_text` | OCR 文本定位 | `text/text_contains/text_regex`、`language`、`min_confidence`、`source_path/source_target`、`region` |

## locate_image

```json
{
  "action": "desktop_vision",
  "type": "locate_image",
  "desktop": "desk",
  "template_path": "resources/save-button.png",
  "source_target": "window",
  "title_contains": "Demo",
  "window_match_index": 0,
  "threshold": 0.88,
  "match_index": 0,
  "max_matches": 10,
  "timeout_ms": 3000,
  "interval_ms": 250,
  "path": "save-button-match.json",
  "output": {"as": "save_button"}
}
```

## locate_text

```json
{
  "action": "desktop_vision",
  "type": "locate_text",
  "desktop": "desk",
  "source_target": "window",
  "title_contains": "Demo",
  "text_contains": "Submit",
  "language": "eng",
  "min_confidence": 0.6,
  "match_index": 0,
  "max_matches": 10,
  "timeout_ms": 3000,
  "interval_ms": 250,
  "path": "submit-text-match.json",
  "output": {"as": "submit_text"}
}
```

已有截图中 OCR：

```json
{
  "action": "desktop_vision",
  "type": "locate_text",
  "desktop": "desk",
  "source_path": "output/desktop-screenshots/screen.png",
  "text_regex": "Order\\s+Total",
  "language": "eng",
  "path": "order-total-text.json",
  "output": {"as": "order_total_text"}
}
```

## 通用参数

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，`locate_image` 或 `locate_text`。
- `source_path`: 可选，已有截图或图片；不能和 `source_target` 同时使用。
- `source_target`: 可选，`screen`、`window`、`element`。省略且没有 `source_path` 时抓取屏幕。
- Window Query: `source_target=window/element` 必填至少一种窗口定位字段，例如 `profile`、`title_contains`、`process_name`、`window_id`。profile 见 [app_profile](./app_profile.md)。
- `window_match_index`: 可选，仅 `source_target=window/element` 使用，选择第几个窗口候选，默认 `0`。
- Element Locator: `source_target=element` 必填至少一种控件定位字段。
- `region`: 可选，限制搜索区域；使用 `source_path` 时相对图片，`source_target=screen` 时相对屏幕截图，`source_target=window/element` 时相对窗口或控件截图。
- `state`: 仅 `source_target=element` 可用，`exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `match_index`: 可选，选择第几个命中，默认 `0`；它不作为窗口候选索引。
- `max_matches`: 可选，最多保存候选数量，默认 `10`。
- `timeout_ms`、`interval_ms`: 没有 `source_path` 时等待屏幕目标出现。
- `max_depth`、`max_elements`: `source_target=element` 的控件树遍历限制。
- `path`: 必填，相对于 `output/desktop-vision/`。
- `output.as`: 可选，保存 payload。

## locate_image 参数

- `template_path`: 必填，模板图路径。
- `threshold`: 可选，默认 `0.85`，取值 `0..1`。

## locate_text 参数

- `text`: 精确匹配 OCR 行文本。
- `text_contains`: 包含匹配 OCR 行文本。
- `text_regex`: 正则匹配 OCR 行文本。
- `language`: 可选，默认 `eng`。
- `provider`: 可选，`auto` 或 `tesseract`，默认 `auto`。
- `min_confidence`: 可选，默认 `0.6`，取值 `0..1`。
- `case_sensitive`: 可选，默认 `false`。

`text`、`text_contains`、`text_regex` 至少写一个，建议只写一个。

## 后续点击

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "bounds_center",
  "bounds": "{{submit_text.match.bounds}}"
}
```

也可以读取 `{{submit_text.target_candidates.best_candidate}}`。当 `strategy=visual_bounds`、`confidence` 可接受且 `screen_clickable=true` 时，优先用 `desktop_input target=candidate` 消费 `candidate_id`；紧接下一步可用 `candidate_source: "latest"`，跨多步复用时传显式 `target_candidates`。也可以使用其中的 `bounds` 作为 `bounds_center` 兜底。

## Payload

共同字段：

- `ok`
- `type`
- `desktop`
- `coordinate_space`
- `coordinate_profile`
- `coordinate_diagnostics`
- `source_target`
- `source_bounds`
- `region`
- `matches`
- `match.bounds`
- `match.local_bounds`
- `match.point`
- `match.local_point`
- `match.score`
- `target_candidates`
- `artifacts.source_path`
- `artifacts.crop_path`
- `artifacts.annotation_path`
- `diagnostics`

`coordinate_diagnostics.mapper` 包含 `source_bounds`、`display_virtual_bounds`、`screen_clickable` 和 `scale_applied`。当前 `scale_applied=false` 表示执行器没有把未校准 DPI/缩放直接乘到点击坐标。

`locate_text` 额外字段：

- `raw_text`
- `ocr_blocks`
- `match.text`
- `match.confidence`
- `language`
- `provider`

## AI 规则

- 生成 `locate_image` 前先检查 `capability_matrix.capabilities.vision.image_locator`。
- 生成 `locate_text` 前先检查 `capability_matrix.capabilities.vision.ocr`；缺 OCR 时不要写可运行 OCR plan。
- 视觉/OCR 定位只能作为控件树不可用时的兜底，或用于验证已有截图中的位置。
- `coordinate_profile.source.screen_clickable=true` 时，`match.bounds` 是可用于当前屏幕的全局坐标；`match.local_bounds` 相对 `source_bounds`，只用于诊断或局部二次处理。
- `source_path` 离线图片会返回 `screen_clickable=false`；这类结果只能作为证据，不能直接生成屏幕点击。
- `target_candidates.best_candidate.strategy=visual_bounds` 时，候选包含 `candidate_id`、`bounds`、`confidence` 和 `screen_clickable`；`screen_clickable=true` 且置信度达标时可用 `desktop_input target=candidate`。置信度低、`screen_clickable=false` 或 `manual_confirm_recommended=true` 时先人工确认。
- `threshold` 或 `min_confidence` 过低时必须人工确认。
- 多显示器、DPI、Retina、RDP 缩放场景必须确认 `coordinate_profile`、`coordinate_space` 和 `coordinate_diagnostics`；视觉命中转点击前仍要确认 `screen_clickable=true`、候选置信度和当前窗口状态。
