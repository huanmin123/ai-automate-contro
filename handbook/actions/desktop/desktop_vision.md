# desktop_vision

状态：`locate_image` 已支持；`locate_text` 仍规划中，当前不可写入可运行 plan。

作用：从桌面截图或已有图片中定位模板图，输出 `bounds`、`point`、匹配分数和证据文件。它只负责定位，不负责点击或输入。

## 场景

- 自绘 UI、Canvas、图片按钮、图标按钮。
- 控件树不可见或没有稳定 `automation_id/name/control_type`。
- 已有截图产物，需要在图中寻找模板。
- OCR 识别屏幕文字位置当前不可写入可运行 plan。

能使用 `desktop_element` 时优先使用 `desktop_element`。

## 类型

| type | 作用 | 关键参数 |
| --- | --- | --- |
| `locate_image` | 模板图匹配 | `template_path`、`region`、`threshold` |
| `locate_text` | 规划中 OCR 文字定位 | `text_contains`、`language`、`confidence` |

## locate_image

```json
{
  "action": "desktop_vision",
  "type": "locate_image",
  "desktop": "desk",
  "template_path": "resources/save-button.png",
  "region": {"x": 0, "y": 0, "width": 1200, "height": 800},
  "threshold": 0.88,
  "match_index": 0,
  "max_matches": 10,
  "timeout_ms": 3000,
  "interval_ms": 250,
  "path": "save-button-match.json",
  "save_as": "save_button"
}
```

已有截图中定位：

```json
{
  "action": "desktop_vision",
  "type": "locate_image",
  "desktop": "desk",
  "template_path": "resources/save-button.png",
  "source_path": "output/desktop-screenshots/screen.png",
  "threshold": 0.88,
  "path": "save-button-match.json",
  "save_as": "save_button"
}
```

## locate_text 草案

```json
{
  "action": "desktop_vision",
  "type": "locate_text",
  "desktop": "desk",
  "text_contains": "保存",
  "region": {"x": 0, "y": 0, "width": 1200, "height": 800},
  "language": "chi_sim+eng",
  "confidence": 0.7,
  "path": "save-text-ocr.json",
  "save_as": "save_text"
}
```

## 后续点击

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "bounds_center",
  "bounds": "{{save_button.match.bounds}}"
}
```

## Payload

最小字段：

- `ok`
- `type`
- `desktop`
- `coordinate_space`
- `region`
- `matches`
- `match.bounds`
- `match.point`
- `match.score` 或 `match.confidence`
- `artifacts.source_path`
- `artifacts.crop_path`
- `artifacts.annotation_path`
- `raw_text` / `ocr_blocks`，仅 OCR
- `diagnostics`

## 输出

写入 `output/desktop-vision/`：

- 原始截图
- 命中裁剪图
- 标注图
- JSON payload
- OCR 原文和 blocks

## AI 规则

- 可在可运行 plan 使用 `type=locate_image`；不要使用 `type=locate_text`。
- 视觉定位只能作为控件树不可用时的兜底，或用于验证已有截图中的图像位置。
- 生成视觉 plan 前先检查 `capability_matrix.capabilities.vision.image_locator`。
- `threshold` 或 `confidence` 过低时必须人工确认。
- 多显示器、DPI、Retina、RDP 缩放场景必须确认坐标空间。
