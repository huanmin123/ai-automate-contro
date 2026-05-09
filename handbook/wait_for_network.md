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
