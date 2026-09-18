# open_desktop

`open_desktop` 只用于 `automation_type: "desktop"`。它创建桌面控制 session，检测平台、backend、显示器和权限状态。

## 参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `open_desktop` |
| `name` | 是 | 桌面 session 名，后续 `desktop` 字段引用它 |
| `platform` | 否 | `auto`、`windows`、`macos`，默认 `auto` |
| `backend` | 否 | `auto`、`native`，默认 `auto` |
| `request_permissions` | 否 | 布尔值，默认 `false`。为 `true` 时探测会额外执行一次最小截图（1×1 像素）来推断 Screen Recording 授权状态，并立即返回当前各权限状态（如 macOS Accessibility、Screen Recording）；探测不会打开系统设置、不触发系统授权弹窗、不等待用户完成授权。授权需用户在系统设置中手动完成，未授权时后续桌面动作会失败 |
| `output` | 否 | 发布 probe payload，例如 `{"as":"desktop_probe"}` |

## 场景

- 桌面 plan 的第一步。
- 检测 Windows/macOS native backend 和权限。
- macOS 需要 Accessibility、Screen Recording、Automation 权限时，探测只报告当前授权状态；授权本身需用户在系统设置中手动完成后再重新探测。

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
- `capabilities.screenshot`: 全屏截图、区域截图是否可用。
- `capabilities.vision.image_locator`: 是否可使用 `desktop_vision type=locate_image`。
- `permissions`: `accessibility`、`screen_recording`、`input_control`。
- `dependencies`: `Pillow.ImageGrab`、`opencv-python`、`pyautogui`、`pyperclip`。
- `limitations`: 当前限制，例如缺依赖、窗口列表不可用、macOS 需要用户授权。

AI 写桌面 plan 前应先看 `capability_matrix`，再决定使用 `desktop_element`、`desktop_input`、`desktop_capture`、`desktop_vision` 或人工确认。

## 注意

- `open_desktop` 不启动 App，不聚焦窗口，不做截图。
- 当前可写 `backend=auto` 或 `backend=native`；不要写 `windows-uia`、`macos-ax`、`vision` 等未开放取值。
- macOS 授权必须由用户在系统设置中手动完成；`open_desktop` 的探测不会打开系统设置、不会触发授权弹窗，只报告当前授权状态。授权完成后重新运行探测即可拿到新状态。
