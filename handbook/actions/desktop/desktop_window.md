# desktop_window

`desktop_window` 只用于 `automation_type: "desktop"`。它负责列出、聚焦和控制当前操作系统桌面会话里的真实窗口；它不接受浏览器 DOM selector，也不替代 `desktop_capture` 或 `desktop_assert` 的运行证据。

支持类型：

- `list`: 枚举窗口。
- `find`: 查询匹配窗口，不聚焦、不控制。
- `active`: 读取当前系统活动窗口，并更新当前桌面 session 的 `current_window`。
- `focus`: 聚焦匹配窗口。
- `normalize`: 将匹配窗口还原、移动到固定位置、调整为固定尺寸，并可聚焦。
- `close`: 请求关闭匹配窗口。
- `minimize`: 最小化匹配窗口。
- `maximize`: 最大化匹配窗口。
- `restore`: 还原匹配窗口。

`find/focus/normalize/close/minimize/maximize/restore` 必须提供至少一种 Window Query 字段。`list` 和 `active` 不要求窗口定位字段。

## Window Query

窗口定位字段：

- `title`: 精确匹配窗口标题。
- `title_contains`: 标题包含文本。
- `title_regex`: 标题正则匹配。
- `app`: App 或进程名包含文本。
- `process`: 进程名包含文本。
- `process_name`: 进程名包含文本。
- `class_name`: Windows 窗口类名包含文本；macOS 通常为空。
- `window_id`: 后端返回的窗口 id。macOS 在 Quartz 可用时通常是 `macos:<CGWindowNumber>`；缺少 Quartz 映射时会退回 App + AX 窗口序号生成的临时 id。
- `profile`: App/窗口预设，见 [app_profile](./app_profile.md)。profile 可提供 `window_query`。
- `app_profile`: `profile` 的别名。
- `match_index`: 多个候选时的索引，默认 `0`。它不能单独作为定位字段。

优先使用 `profile` 或 `title_contains` + `app/process_name` 缩小范围；只用 `window_id` 时要注意窗口重建后 id 可能变化。macOS 同一 App 多窗口操作会同时保留 `window_id` 和 AX `window_index`，用于 System Events 精确定位目标窗口。

## type=list

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "list",
  "title_contains": "demo",
  "include_invisible": false,
  "max_windows": 20,
  "path": "windows.json",
  "output": {"as": "windows"}
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `list`。
- Window Query: 可选；提供时只返回匹配窗口。
- `include_invisible`: 可选，Windows 下是否包含不可见窗口，默认 `false`。macOS 当前后端不支持不可见窗口枚举；传入 `true` 时 payload 会在 `diagnostics` 里说明该限制。
- `max_windows`: 可选，限制返回窗口数量。
- `path`: 可选，相对于 `output/desktop-windows/` 写出窗口列表 JSON。
- `output.as`: 可选，保存 payload。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "list",
  "query": {"title_contains": "demo"},
  "count": 1,
  "total_count": 1,
  "truncated": false,
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

当 `include_invisible=true` 时，payload 可额外包含：

```json
{
  "diagnostics": {
    "include_invisible_requested": true,
    "include_invisible_supported": true,
    "warnings": []
  }
}
```

`list` 是桌面证据步骤。

## type=find

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "find",
  "title_contains": "demo.txt",
  "process_name": "notepad.exe",
  "path": "matched-window.json",
  "output": {"as": "matched_window"}
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `find`。
- Window Query: 必填；除 `match_index` 外至少提供一种定位字段。
- `include_invisible`: 可选，是否包含不可见窗口；Windows 支持，macOS 当前后端会返回 `diagnostics.include_invisible_supported=false`。
- `max_windows`: 可选，限制写入和返回的匹配窗口数量。
- `path`: 可选，相对于 `output/desktop-windows/` 写出 JSON。
- `output.as`: 可选，保存 payload。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "find",
  "query": {"title_contains": "demo.txt", "process_name": "notepad.exe"},
  "match_count": 1,
  "matches": [{"title": "demo.txt - Notepad"}],
  "selected_window": {"title": "demo.txt - Notepad"},
  "truncated": false
}
```

`find` 不聚焦窗口，不修改 `current_window`，适合在操作前保留窗口定位证据。

## type=active

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "active",
  "path": "active-window.json",
  "output": {"as": "active_window"}
}
```

行为：

- 读取当前系统活动窗口。
- 找到活动窗口时更新当前 session 的 `current_window`。
- `path` 可选，相对于 `output/desktop-windows/` 写出 JSON。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "active",
  "found": true,
  "window": {"title": "demo.txt - Notepad", "focused": true}
}
```

## type=focus

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "focus",
  "profile": "notepad",
  "title_contains": "demo.txt",
  "output": {"as": "focused_window"}
}
```

行为：

- 选中匹配窗口并请求系统聚焦。
- 成功后更新当前 session 的 `current_window`，供 `desktop_input` 鼠标类动作的 `target=current_window_center` 使用。
- Windows 使用 Win32 前台窗口 API；macOS 使用 `osascript`/System Events 将目标进程置前，并尽量按 AX `window_index` 对目标窗口执行 `AXRaise`。

## type=normalize

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "normalize",
  "title_contains": "微信",
  "process_name": "WeChat",
  "x": 0,
  "y": 33,
  "width": 1728,
  "height": 1084,
  "focus": true,
  "tolerance_px": 2,
  "path": "wechat-normalized.json",
  "output": {"as": "wechat_window"}
}
```

行为：

- 选中匹配窗口。
- 尽量从最小化或特殊状态还原窗口。
- 将窗口移动到 `x/y`，并调整到 `width/height`。
- `focus=true` 时聚焦目标窗口。
- 操作后重新读取窗口 bounds；实际 bounds 和目标 bounds 的差异超过 `tolerance_px` 时失败。
- 成功后更新 `session.current_window`，后续 `desktop_input target=current_window_offset` 可基于归一化窗口写相对坐标。

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `normalize`。
- Window Query: 必填；除 `match_index` 外至少提供一种定位字段。
- `x`、`y`: 必填，目标窗口左上角屏幕坐标。多显示器场景可以为负。
- `width`、`height`: 必填，目标窗口尺寸，必须大于 `0`。
- `focus`: 可选，是否归一化后聚焦窗口，默认 `true`。
- `tolerance_px`: 可选，实际 bounds 和目标 bounds 的允许误差，默认 `2`。
- `path`: 可选，相对于 `output/desktop-windows/` 写出 JSON。
- `output.as`: 可选，保存 payload。

payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "normalize",
  "operation": "normalize",
  "target_bounds": {"x": 0, "y": 33, "width": 1728, "height": 1084},
  "tolerance_px": 2,
  "focus": true,
  "before": {"bounds": {"x": 20, "y": 60, "width": 1200, "height": 800}},
  "after": {"bounds": {"x": 0, "y": 33, "width": 1728, "height": 1084}},
  "window": {"bounds": {"x": 0, "y": 33, "width": 1728, "height": 1084}},
  "bounds_delta": {"x": 0, "y": 0, "width": 0, "height": 0}
}
```

`normalize` 是桌面布局归一化步骤，适合在微信、QQ、系统客户端或游戏窗口这类坐标兜底流程前执行。它仍然不是业务状态识别证据；需要证明当前页面、聊天对象、弹窗状态或操作结果时，继续使用 `desktop_window list/find/active`、`desktop_capture`、`desktop_wait`、`desktop_assert` 或可用的 `desktop_element` 读取类动作。

## type=close/minimize/maximize/restore

```json
{
  "action": "desktop_window",
  "desktop": "desk",
  "type": "close",
  "title_contains": "demo.txt",
  "output": {"as": "closed_window"}
}
```

字段：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，`close`、`minimize`、`maximize` 或 `restore`。
- Window Query: 除 `match_index` 外至少提供一种定位字段。
- `output.as`: 可选，保存控制 payload。

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
    "output": {"as": "close_request"}
  },
  {
    "action": "desktop_wait",
    "desktop": "desk",
    "type": "window",
    "title_contains": "demo.txt",
    "state": "not_exists",
    "timeout_ms": 4000,
    "interval_ms": 100,
    "output": {"as": "window_closed"}
  }
]
```

## 平台行为

- Windows: `focus` 使用 Win32 前台窗口 API；`normalize` 使用 `ShowWindow(SW_RESTORE)` + `SetWindowPos`；`close` 使用 `WM_CLOSE`；`minimize/maximize/restore` 使用 `ShowWindow`。
- macOS: 使用 System Events/AppleScript 控制目标进程窗口；`normalize` 设置窗口 `position` 和 `size`；`minimize/restore` 依赖 Accessibility 的 `AXMinimized`；`maximize` 通过 zoom button 或 `AXZoomWindow` best-effort 实现。

## 权限和边界

- Windows 控制高完整性级别窗口、UAC 安全桌面或管理员窗口可能失败。
- macOS 首次控制窗口通常需要 Accessibility/Automation 权限；runtime 可以触发系统提示或打开设置，但授权必须由用户点击。
- `close` 不会绕过未保存确认框；遇到确认框时应使用 `desktop_wait`、截图和 `manual_confirm` 明确交接。
- `desktop_window normalize/close/minimize/maximize/restore` 是窗口控制步骤，不算桌面状态采集证据。需要确认桌面状态时，仍应使用 `desktop_window list/find/active`、`desktop_element list/dump/find/get_text/get_state/get_table/get_tree`、`desktop_capture`、`desktop_wait` 或 `desktop_assert`。
