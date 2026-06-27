# desktop_app

`desktop_app` 只用于 `automation_type: "desktop"`。它负责在当前操作系统桌面会话里启动本机 App 或命令；它不负责等待窗口出现，也不做窗口定位。启动后应继续使用 `desktop_wait`、`desktop_window`、`desktop_capture` 或 `desktop_assert` 获取桌面证据。

支持类型：

- `launch`: 启动 App、可执行文件路径或命令。

## launch

```json
{
  "action": "desktop_app",
  "desktop": "desk",
  "type": "launch",
  "app": "notepad.exe",
  "args": ["C:/tmp/demo.txt"],
  "wait": false,
  "timeout_ms": 10000,
  "save_as": "app_launch"
}
```

字段：

- `desktop`: 必填，桌面 session 名。
- `type`: 必填，固定为 `launch`。
- `app` / `path` / `command`: 三选一，必须提供一个且不能同时提供多个。
- `args`: 可选，非空字符串数组，作为启动参数传给目标。
- `wait`: 可选，默认 `false`。为 `true` 时等待进程退出。
- `timeout_ms`: 可选，`wait=true` 时的等待超时，默认 `10000`。
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
  "desktop": "desk",
  "type": "launch",
  "elapsed_ms": 10
}
```

`wait=true` 时还会返回：

- `exit_code`
- `stdout`
- `stderr`

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
    "app": "TextEdit",
    "args": ["/tmp/demo.txt"],
    "save_as": "app_launch"
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

## 边界

- `desktop_app` 不做浏览器导航，不打开 Playwright page，不接受 DOM selector。
- `pid` 是启动进程的 pid。macOS 使用 `open` 时，pid 可能是 `open` 命令本身，不一定是最终 App 进程。
- GUI App 通常不要设置 `wait=true`，否则会等待到窗口关闭或超时。短生命周期命令才适合 `wait=true`。
- macOS 首次控制 App 可能涉及 Accessibility、Screen Recording 或 Automation 权限；runtime 可以触发系统提示或打开设置，但授权必须由用户点击。
