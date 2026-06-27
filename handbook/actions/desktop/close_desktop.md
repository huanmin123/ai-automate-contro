# close_desktop

`close_desktop` 只用于 `automation_type: "desktop"`。它关闭桌面控制 session 并释放 backend 资源。

## 参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `close_desktop` |
| `desktop` | 是 | `open_desktop.name` |

## 场景

- 桌面 plan 最后释放 session。
- 清理 backend 资源。

## 示例

```json
{
  "action": "close_desktop",
  "desktop": "desk"
}
```

## 注意

- `close_desktop` 不关闭用户 App。
- 需要关闭窗口时先使用 `desktop_window type=close`，再用 `desktop_wait state=not_exists` 验证。
