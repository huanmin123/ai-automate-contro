# storage

## 用途

读取或修改浏览器 cookies、localStorage 和 sessionStorage。

## 必填字段

- `action`: 固定写成 `storage`
- `type`: 存储操作类型
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `cookies` | `output` | 读取 cookies |
| `set_cookies` | `cookies` | 写入 cookies |
| `clear_cookies` | 无 | 清空 cookies |
| `local_storage` | `key`、`output.as` | 读取 localStorage |
| `set_local_storage` | `key`、`value` | 写入 localStorage |
| `remove_local_storage` | `key` | 删除 localStorage 键 |
| `clear_local_storage` | 无 | 清空 localStorage |
| `session_storage` | `key`、`output.as` | 读取 sessionStorage |
| `set_session_storage` | `key`、`value` | 写入 sessionStorage |
| `remove_session_storage` | `key` | 删除 sessionStorage 键 |
| `clear_session_storage` | 无 | 清空 sessionStorage |

## 可选字段

- `page`: 页面名，默认当前页面
- `urls`: `type: cookies` 时按 URL 过滤 cookies

## 示例

```json
{
  "action": "storage",
  "type": "set_local_storage",
  "browser": "main",
  "key": "demo-token",
  "value": "{{token}}"
}
```

```json
{
  "action": "storage",
  "type": "local_storage",
  "browser": "main",
  "key": "demo-token",
  "output": {"as": "stored_token"}
}
```
