# open_desktop

`open_desktop` 只用于 `automation_type: "desktop"`。它创建桌面控制 session，检测平台、backend、显示器和权限状态。

## 参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `open_desktop` |
| `name` | 是 | 桌面 session 名，后续 `desktop` 字段引用它 |
| `platform` | 否 | `auto`、`windows`、`macos`，默认 `auto` |
| `backend` | 否 | `auto`、`native`，默认 `auto` |
| `request_permissions` | 否 | 是否触发权限提示或打开设置，默认 `false` |
| `output` | 否 | 发布 probe payload，例如 `{"as":"desktop_probe"}` |

## 场景

- 桌面 plan 的第一步。
- 检测 Windows/macOS native backend 和权限。
- macOS 需要 Accessibility、Screen Recording、Automation 时触发用户授权流程。

## 示例

```json
{
  "action": "open_desktop",
  "name": "desk",
  "platform": "auto",
  "backend": "auto",
  "request_permissions": true,
  "output": {"as": "desktop_probe"}
}
```

## 输出

`output.as` 发布的 payload 包含 `ok`、`desktop`、`platform`、`backend`、`probe`、`capability_matrix`、`elapsed_ms`。

`capability_matrix` 用于 AI 判断当前桌面线可用能力：

- `schema_version`: 当前为 `1`。
- `capabilities.semantic`: 窗口/控件树/文本/状态/写值/选择/触发/表格/树/菜单/滚动容器是否可用。
- `capabilities.input`: 鼠标、键盘、快捷键、拖拽、滚轮、剪贴板是否可用。
- `capabilities.screenshot`: 全屏截图、区域截图、标注截图是否可用。
- `capabilities.vision.image_locator`: 是否可使用 `desktop_vision type=locate_image`。
- `capabilities.vision.ocr`: 是否可使用 `desktop_vision type=locate_text`。
- `permissions`: `accessibility`、`screen_recording`、`input_control`。
- `dependencies`: `Pillow.ImageGrab`、`opencv-python`、`tesseract`、`tessdata.eng`、`tessdata.chi_sim`、`pyautogui`、`pyperclip`。
- `limitations`: 当前限制，例如缺依赖、窗口列表不可用、macOS 需要用户授权。

AI 写桌面 plan 前应先看 `capability_matrix`，再决定使用 `desktop_element`、`desktop_input`、`desktop_capture`、`desktop_vision` 或人工确认。

## 注意

- `open_desktop` 不启动 App，不聚焦窗口，不做截图。
- 当前可写 `backend=auto` 或 `backend=native`；不要写 `windows-uia`、`macos-ax`、`vision` 等未开放取值。
- macOS 授权必须由用户点击；代码只能触发提示、打开系统设置并等待确认。
