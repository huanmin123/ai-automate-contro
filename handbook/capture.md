# capture

## 用途

统一保存页面或浏览器上下文产物。

## 必填字段

- `action`: 固定写成 `capture`
- `type`: `screenshot`、`html`、`storage_state`
- `browser`: 浏览器会话名
- `path`: 相对于对应输出分区的路径

## 类型说明

| type | 输出分区 | 说明 |
| --- | --- | --- |
| `screenshot` | `output/screenshots/` | 保存页面截图 |
| `html` | `output/html/` | 保存当前页面 HTML |
| `storage_state` | `output/storage-states/` | 保存浏览器状态 |

## 可选字段

- `full_page`: 仅 `type: screenshot` 有效，默认 `false`

## 示例

```json
{
  "action": "capture",
  "type": "screenshot",
  "browser": "main",
  "path": "login-page.png",
  "full_page": true
}
```
