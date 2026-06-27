# desktop_vision

当前只支持 `locate_image`。

作用：从桌面截图、窗口截图、控件截图或已有图片中定位模板图，输出屏幕全局 `bounds`、source 局部 `local_bounds`、`point`、匹配分数和证据文件。它只负责定位，不负责点击或输入。

## 场景

- 自绘 UI、Canvas、图片按钮、图标按钮。
- 控件树不可见或没有稳定 `automation_id/name/control_type`。
- 已有截图产物，需要在图中寻找模板。

能使用 `desktop_element` 时优先使用 `desktop_element`。

## 类型

| type | 作用 | 关键参数 |
| --- | --- | --- |
| `locate_image` | 模板图匹配 | `template_path`、`source_path/source_target`、`region`、`threshold` |

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

指定窗口中定位：

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
  "path": "save-button-in-window.json",
  "save_as": "save_button"
}
```

指定控件中定位：

```json
{
  "action": "desktop_vision",
  "type": "locate_image",
  "desktop": "desk",
  "template_path": "resources/status-icon.png",
  "source_target": "element",
  "title_contains": "Demo",
  "window_match_index": 0,
  "automation_id": "StatusPanel",
  "control_type": "Pane",
  "threshold": 0.88,
  "path": "status-icon-in-panel.json",
  "save_as": "status_icon",
  "max_depth": 6,
  "max_elements": 300
}
```

参数：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `locate_image`。
- `template_path`: 必填，模板图路径。
- `source_path`: 可选，已有截图或图片；不能和 `source_target` 同时使用。
- `source_target`: 可选，`screen`、`window`、`element`。省略且没有 `source_path` 时抓取屏幕。
- Window Query: `source_target=window/element` 必填至少一种窗口定位字段。
- `window_match_index`: 可选，仅 `source_target=window/element` 使用，选择第几个窗口候选，默认 `0`。
- Element Locator: `source_target=element` 必填至少一种控件定位字段。
- `region`: 可选，限制搜索区域；使用 `source_path` 时相对图片，`source_target=screen` 时相对屏幕截图，`source_target=window/element` 时相对窗口或控件截图。
- `state`: 仅 `source_target=element` 可用，`exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `threshold`: 可选，默认 `0.85`，取值 `0..1`。
- `match_index`: 可选，选择第几个图像命中，默认 `0`；它不作为窗口候选索引。
- `max_matches`: 可选，最多保存候选数量，默认 `10`。
- `timeout_ms`、`interval_ms`: 没有 `source_path` 时等待屏幕目标出现。
- `max_depth`、`max_elements`: `source_target=element` 的控件树遍历限制。
- `path`: 必填，相对于 `output/desktop-vision/`。
- `save_as`: 可选，保存 payload。

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
- `source_target`
- `source_bounds`
- `region`
- `matches`
- `match.bounds`
- `match.local_bounds`
- `match.point`
- `match.local_point`
- `match.score`
- `artifacts.source_path`
- `artifacts.crop_path`
- `artifacts.annotation_path`
- `diagnostics`

## 输出

写入 `output/desktop-vision/`：

- 原始截图
- 命中裁剪图
- 标注图
- JSON payload

## AI 规则

- 可在可运行 plan 使用 `type=locate_image`。
- 视觉定位只能作为控件树不可用时的兜底，或用于验证已有截图中的图像位置。
- `match.bounds` 是屏幕全局坐标，可交给 `desktop_input target=bounds_center`；`match.local_bounds` 相对 `source_bounds`，只用于诊断或局部二次处理。
- 生成视觉 plan 前先检查 `capability_matrix.capabilities.vision.image_locator`。
- `threshold` 过低时必须人工确认。
- 多显示器、DPI、Retina、RDP 缩放场景必须确认坐标空间。
