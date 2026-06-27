# desktop_window

`desktop_window` 只用于 `automation_type: "desktop"`。它负责列出、聚焦和控制当前操作系统桌面会话里的真实窗口；它不接受浏览器 DOM selector，也不替代 `desktop_capture` 或 `desktop_assert` 的运行证据。

支持类型：

- `list`: 枚举窗口。
- `focus`: 聚焦匹配窗口。
- `close`: 请求关闭匹配窗口。
- `minimize`: 最小化匹配窗口。
- `maximize`: 最大化匹配窗口。
- `restore`: 还原匹配窗口。

除 `list` 外，所有类型都必须提供至少一种 Window Query 字段。

## Window Query

窗口定位字段：

- `title`: 精确匹配窗口标题。
- `title_contains`: 标题包含文本。
- `title_regex`: 标题正则匹配。
- `app`: App 或进程名包含文本。
- `process`: 进程名包含文本。
- `process_name`: 进程名包含文本。
- `class_name`: Windows 窗口类名包含文本；macOS 通常为空。
- `window_id`: 后端返回的窗口 id。
- `match_index`: 多个候选时的索引，默认 `0`。它不能单独作为定位字段。

优先使用 `title_contains` + `app/process_name` 缩小范围；只用 `window_id` 时要注意窗口重建后 id 可能变化。

## type=list

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "list",
  "include_invisible": false,
  "path": "windows.json",
  "save_as": "windows"
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `list`。
- `include_invisible`: 可选，Windows 下是否包含不可见窗口，默认 `false`。macOS 当前忽略该字段。
- `path`: 可选，相对于 `output/desktop-windows/` 写出窗口列表 JSON。
- `save_as`: 可选，保存 payload。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "list",
  "count": 1,
  "windows": [
    {
      "id": 1234,
      "title": "demo.txt - Notepad",
      "app": "notepad.exe",
      "process_name": "notepad.exe",
      "class_name": "Notepad",
      "pid": 5678,
      "bounds": {"x": 10, "y": 10, "width": 800, "height": 600},
      "visible": true,
      "focused": true
    }
  ],
  "elapsed_ms": 20,
  "path": "F:/.../output/desktop-windows/windows.json"
}
```

`list` 是桌面证据步骤。

## type=focus

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "focus",
  "title_contains": "demo.txt",
  "save_as": "focused_window"
}
```

行为：

- 选中匹配窗口并请求系统聚焦。
- 成功后更新当前 session 的 `current_window`，供 `desktop_input` 鼠标类动作的 `target=current_window_center` 使用。
- Windows 使用 Win32 前台窗口 API；macOS 使用 `osascript` 激活目标 App。

## type=close/minimize/maximize/restore

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "close",
  "title_contains": "demo.txt",
  "save_as": "closed_window"
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，`close`、`minimize`、`maximize` 或 `restore`。
- Window Query: 除 `match_index` 外至少提供一种定位字段。
- `save_as`: 可选，保存控制 payload。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "close",
  "operation": "close",
  "query": {"title_contains": "demo.txt"},
  "window": {"id": 1234, "title": "demo.txt - Notepad", "close_requested": true},
  "before": {"id": 1234, "title": "demo.txt - Notepad"},
  "elapsed_ms": 5
}
```

行为：

- `close` 请求窗口正常关闭，不强杀进程。未保存确认框、权限弹窗或 App 拒绝关闭时，窗口可能仍存在。
- `minimize` 最小化窗口；成功后 `current_window` 会记录该窗口但 `focused=false`。
- `maximize` 最大化窗口。
- `restore` 从最小化或最大化状态请求还原。
- `close` 成功发送后会清空 session 的 `current_window`；其他生命周期操作会更新 `current_window`。

建议关闭后追加验证：

```json
[
  {
    "action": "desktop_window",
    "desktop": "desk",
    "type": "close",
    "title_contains": "demo.txt",
    "save_as": "close_request"
  },
  {
    "action": "desktop_wait",
    "desktop": "desk",
    "type": "window",
    "title_contains": "demo.txt",
    "state": "not_exists",
    "timeout_ms": 4000,
    "interval_ms": 100,
    "save_as": "window_closed"
  }
]
```

## 平台行为

- Windows: `focus` 使用 Win32 前台窗口 API；`close` 使用 `WM_CLOSE`；`minimize/maximize/restore` 使用 `ShowWindow`。
- macOS: 使用 System Events/AppleScript 控制目标进程窗口；`minimize/restore` 依赖 Accessibility 的 `AXMinimized`；`maximize` 通过 zoom button 或 `AXZoomWindow` best-effort 实现。

## 权限和边界

- Windows 控制高完整性级别窗口、UAC 安全桌面或管理员窗口可能失败。
- macOS 首次控制窗口通常需要 Accessibility/Automation 权限；runtime 可以触发系统提示或打开设置，但授权必须由用户点击。
- `close` 不会绕过未保存确认框；遇到确认框时应使用 `desktop_wait`、截图和 `manual_confirm` 明确交接。
- `desktop_window close/minimize/maximize/restore` 是窗口控制步骤，不算桌面状态采集证据。需要确认桌面状态时，仍应使用 `desktop_window list`、`desktop_element list/dump/find/get_text/get_state/get_table/get_tree`、`desktop_capture`、`desktop_wait` 或 `desktop_assert`。
