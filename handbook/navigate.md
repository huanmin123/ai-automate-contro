# navigate

## 用途

统一处理页面导航动作。

## 必填字段

- `action`: 固定写成 `navigate`
- `type`: `goto`、`refresh`、`back`、`forward`
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `goto` | `url` | 跳转到指定 URL |
| `refresh` | 无 | 刷新当前页面 |
| `back` | 无 | 浏览器后退 |
| `forward` | 无 | 浏览器前进 |

## 可选字段

- `wait_until`: Playwright 导航等待条件，默认 `domcontentloaded`

## 示例

```json
{
  "action": "navigate",
  "type": "goto",
  "browser": "main",
  "url": "{{resources_file_url}}/basic_login.html"
}
```
