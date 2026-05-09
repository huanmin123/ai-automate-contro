# page

## 用途

统一管理同一浏览器会话下的页面。

## 必填字段

- `action`: 固定写成 `page`
- `type`: `open`、`switch`、`close`
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `open` | `page` | 新建命名页面 |
| `switch` | `page` | 切换当前活动页面 |
| `close` | 无 | 关闭页面，未传 `page` 时关闭当前页面 |

## 可选字段

- `url`: 仅 `type: open` 有效，新页面打开后立即跳转
- `switch`: 仅 `type: open` 有效，是否切换到新页面，默认 `true`
- `wait_until`: 仅打开并跳转 URL 时有效

## 示例

```json
{
  "action": "page",
  "type": "open",
  "browser": "main",
  "page": "docs",
  "url": "{{resources_file_url}}/details.html"
}
```
