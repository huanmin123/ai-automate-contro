# desktop_capture

`desktop_capture` 只用于 `automation_type: "desktop"`。它保存桌面截图或桌面状态快照，是桌面流程的重要证据 action。

## 支持类型

| type | 作用 | 输出分区 |
| --- | --- | --- |
| `screenshot` | 保存桌面截图 | `output/desktop-screenshots/` |
| `snapshot` | 保存桌面状态 JSON | `output/desktop-state/` |

## type=screenshot

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "screenshot",
  "path": "screen.png",
  "region": {"x": 0, "y": 0, "width": 800, "height": 600},
  "include_cursor": false,
  "save_as": "screen"
}
```

参数：

- `desktop`: 必填，`open_desktop.name`。
- `type`: 必填，固定为 `screenshot`。
- `path`: 必填，相对于 `output/desktop-screenshots/`。
- `region`: 可选，截图区域对象。
- `include_cursor`: 可选，是否包含鼠标指针，默认 `false`。
- `save_as`: 可选，保存 payload。

## type=snapshot

```json
{
  "action": "desktop_capture",
  "desktop": "desk",
  "type": "snapshot",
  "path": "state.json",
  "include_windows": true,
  "include_displays": true,
  "save_as": "desktop_state"
}
```

参数：

- `desktop`: 必填。
- `type`: 必填，固定为 `snapshot`。
- `path`: 必填，相对于 `output/desktop-state/`。
- `include_windows`: 可选，是否包含窗口列表，默认 `true`。
- `include_displays`: 可选，是否包含显示器信息，默认 `true`。
- `save_as`: 可选。

输出：

- 写入 `output/desktop-state/<path>`。
- payload 顶层包含 `capability_matrix`。
- `snapshot.capability_matrix` 与顶层矩阵一致，用于判断窗口、控件、键鼠、截图、权限和依赖能力。

## 场景

- 运行前后保存桌面画面。
- 失败诊断前保存当前窗口、显示器和权限状态。
- 给 AI 终端质量门禁提供桌面证据。
