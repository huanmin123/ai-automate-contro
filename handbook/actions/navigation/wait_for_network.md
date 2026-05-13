# wait_for_network

## 用途

统一等待并捕获网络请求或响应。

## 必填字段

- `action`: 固定写成 `wait_for_network`
- `type`: `request`、`response`
- `browser`: 浏览器会话名
- `url`: 需要匹配的 URL 或 Playwright URL matcher
- `trigger`: 触发网络事件的单个动作对象

## 可选字段

- `save_as`: 把捕获到的请求或响应摘要保存为变量
- `include_headers`: 是否把 headers 写入摘要，默认 `false`
- `include_post_data`: 仅 `type: request` 有效，是否保存请求体
- `include_body`: 仅 `type: response` 有效，是否保存响应体
- `body_type`: `include_body` 时使用，支持 `text`、`json`、`body`，默认 `text`

## 示例

```json
{
  "action": "wait_for_network",
  "type": "response",
  "browser": "main",
  "url": "https://example.com/api",
  "save_as": "response_info",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#submit"
  }
}
```

捕获 JSON 响应体：

```json
{
  "action": "wait_for_network",
  "type": "response",
  "browser": "main",
  "url": "https://example.com/api/profile",
  "include_body": true,
  "body_type": "json",
  "save_as": "profile_response",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#load-profile"
  }
}
```
