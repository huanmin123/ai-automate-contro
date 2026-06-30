# desktop_app

`desktop_app` 只用于 `automation_type: "desktop"`。它负责在当前操作系统桌面会话里启动本机 App 或命令；启动后可选等待并聚焦匹配窗口。窗口状态仍应继续使用 `desktop_wait`、`desktop_window`、`desktop_capture` 或 `desktop_assert` 获取桌面证据。

支持类型：

- `launch`: 启动 App、可执行文件路径或命令。

## launch

```json
{
  "action": "desktop_app",
  "desktop": "desk",
  "type": "launch",
  "profile": "notepad",
  "args": ["C:/tmp/demo.txt"],
  "wait": false,
  "timeout_ms": 10000,
  "wait_for_window": true,
  "title_contains": "demo.txt",
  "focus": true,
  "window_timeout_ms": 10000,
  "interval_ms": 250,
  "save_as": "app_launch"
}
```

字段：

- `desktop`: 必填，桌面 session 名。
- `type`: 必填，固定为 `launch`。
- `profile`: 可选，App/窗口预设，见 [app_profile](./app_profile.md)。可以提供启动目标、Window Query 和默认等待参数。
- `app` / `path` / `command`: 三选一；没有 `profile` 时必须提供一个且不能同时提供多个。显式字段会覆盖 profile 提供的启动目标。
- `args`: 可选，非空字符串数组，作为启动参数传给目标。
- `wait`: 可选，默认 `false`。为 `true` 时等待进程退出。
- `timeout_ms`: 可选，`wait=true` 时的等待超时，默认 `10000`。
- `wait_for_window`: 可选，默认 `false`。为 `true` 时，启动后等待匹配窗口出现。
- Window Query: `wait_for_window=true` 时必填；可用 `profile`、`title_contains`、`process_name`、`app`、`window_id` 等字段。
- `focus`: 可选，默认 `false`。为 `true` 且 `wait_for_window=true` 时，等待窗口后聚焦该窗口。
- `window_timeout_ms`: 可选，等待窗口超时，默认沿用 `timeout_ms` 或 `10000`。
- `interval_ms`: 可选，等待窗口轮询间隔，默认 `250`。
- `save_as`: 可选，保存启动 payload。

`save_as` payload 主要字段：

```json
{
  "ok": true,
  "platform": "windows",
  "backend": "native",
  "app": "notepad.exe",
  "path": "",
  "command": "",
  "args": ["C:/tmp/demo.txt"],
  "command_line": ["notepad.exe", "C:/tmp/demo.txt"],
  "pid": 1234,
  "wait": false,
  "wait_for_window": true,
  "focus": true,
  "window_query": {"app": "notepad.exe", "title_contains": "demo.txt"},
  "window": {"title": "demo.txt - Notepad"},
  "window_wait": {"state": "exists"},
  "window_focus": {"title": "demo.txt - Notepad"},
  "desktop": "desk",
  "type": "launch",
  "elapsed_ms": 10
}
```

`wait=true` 时还会返回：

- `exit_code`
- `stdout`
- `stderr`

使用 `profile` 时，payload 会包含 `profile.id`、`profile.requested`、`profile.platform`、`profile.source` 和已应用的 `launch/window_query/defaults` 摘要。

## 平台行为

- Windows: `app`、`path`、`command` 都作为进程启动目标传给系统。`args` 作为参数数组传入。
- macOS: `app` 会转换为 `open -a <app>`；`path` 会转换为 `open <path>`；`command` 直接作为命令启动目标。

## 推荐组合

启动 App 后必须用桌面证据 action 等待或验证状态：

```json
[
  {
    "action": "desktop_app",
    "desktop": "desk",
    "type": "launch",
    "profile": "textedit",
    "args": ["/tmp/demo.txt"],
    "title_contains": "demo.txt",
    "wait_for_window": true,
    "focus": true,
    "save_as": "app_launch"
  },
  {
    "action": "desktop_window",
    "desktop": "desk",
    "type": "active",
    "save_as": "active_window"
  },
  {
    "action": "desktop_wait",
    "desktop": "desk",
    "type": "window",
    "title_contains": "demo.txt",
    "state": "exists",
    "timeout_ms": 10000,
    "save_as": "app_window"
  },
  {
    "action": "desktop_window",
    "desktop": "desk",
    "type": "focus",
    "title_contains": "demo.txt"
  }
]
```

内置或自定义 profile 可减少重复字段：

```json
{
  "action": "desktop_app",
  "desktop": "desk",
  "type": "launch",
  "profile": "notepad",
  "args": ["C:/tmp/demo.txt"],
  "save_as": "notepad_launch"
}
```

## 边界

- `desktop_app` 不做浏览器导航，不打开 Playwright page，不接受 DOM selector。
- `pid` 是启动进程的 pid。macOS 使用 `open` 时，pid 可能是 `open` 命令本身，不一定是最终 App 进程。
- GUI App 通常不要设置 `wait=true`，否则会等待到窗口关闭或超时。短生命周期命令才适合 `wait=true`。
- macOS 首次控制 App 可能涉及 Accessibility、Screen Recording 或 Automation 权限；runtime 可以触发系统提示或打开设置，但授权必须由用户点击。
