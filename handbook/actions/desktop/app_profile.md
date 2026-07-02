# desktop app profile

`profile` 是桌面线的 App/窗口定位预设。它可以给多个 step 复用同一组启动参数、Window Query 和默认等待参数，减少 plan 里重复写进程名、窗口标题和聚焦等待。

可用字段：

- `profile`: 推荐字段，profile 名称。
- `app_profile`: `profile` 的别名。

可使用 profile 的位置：

- `desktop_app type=launch`: profile 可提供 `app`、`path`、`command`、`args`、`wait`、`timeout_ms`、`wait_for_window`、`focus`、`window_timeout_ms`、Window Query。
- Window Query 场景：`desktop_window`、`desktop_wait`、`desktop_assert window/element`、`desktop_element`、`desktop_capture target=window/element`、`desktop_vision source_target=window/element`、`desktop_input target=element_center`。

内置 profile：

| profile | 平台 | 作用 |
| --- | --- | --- |
| `notepad` | Windows | 启动和定位 Notepad |
| `explorer` | Windows | 启动和定位 File Explorer |
| `powershell` | Windows | 启动和定位 PowerShell |
| `file_dialog_open` | Windows | 定位 Open 文件对话框 |
| `file_dialog_save` | Windows | 定位 Save 文件对话框 |
| `textedit` | macOS | 启动和定位 TextEdit |

显式 step 字段优先级高于 profile。需要覆盖时直接在 step 上写字段：

```json
{
  "action": "desktop_app",
  "desktop": "desk",
  "type": "launch",
  "profile": "notepad",
  "args": ["C:/tmp/demo.txt"],
  "output": {"as": "notepad_launch"}
}
```

自定义 profile 写在当前 plan 包 `config.json` 或集合级 `config.json` 的顶层 `desktop_profiles`：

```json
{
  "desktop_profiles": {
    "mock-chat": {
      "platforms": {
        "windows": {
          "launch": {
            "command": "C:/apps/mock-chat.exe"
          },
          "window_query": {
            "process_name": "mock-chat.exe",
            "title_contains": "Mock Chat"
          },
          "defaults": {
            "wait_for_window": true,
            "focus": true,
            "window_timeout_ms": 10000
          }
        }
      }
    }
  }
}
```

使用自定义 profile：

```json
[
  {
    "action": "desktop_app",
    "desktop": "desk",
    "type": "launch",
    "profile": "mock-chat",
    "output": {"as": "chat_launch"}
  },
  {
    "action": "desktop_window",
    "desktop": "desk",
    "type": "focus",
    "profile": "mock-chat",
    "output": {"as": "chat_window"}
  }
]
```

限制：

- `profile` 只能补桌面 App/窗口相关字段，不提供 Element Locator。
- `desktop_input target=candidate` 不能同时使用 `profile`；候选点击只使用 `target_candidates/candidate_source/candidate` 和 `candidate_id`。
