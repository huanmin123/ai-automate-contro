# network

## 用途

配置浏览器上下文级网络行为：mock 响应、阻断请求、继续请求或设置额外请求头。

## 必填字段

- `action`: 固定写成 `network`
- `type`: 网络操作类型
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `route` | `url` | 拦截匹配请求 |
| `unroute` | `url` | 移除匹配请求的拦截 |
| `set_extra_http_headers` | `headers` | 设置上下文级额外请求头 |

## `route` 字段

- `mode`: `fulfill`、`abort`、`continue`；省略时，如果提供 `json`、`body` 或 `path`，默认 `fulfill`，否则默认 `continue`
- `status`: mock 响应状态码，默认 `200`
- `headers`: mock 响应头，或 continue 时覆盖请求头
- `json`: mock JSON 响应体
- `body`: mock 文本或字节响应体
- `path`: 使用本地文件作为响应体，路径相对于 plan 包解析
- `content_type`: mock 响应 Content-Type
- `error_code`: `mode: abort` 时使用，默认 `failed`
- `continue_url`、`method`、`post_data`: `mode: continue` 时改写请求

## 示例

```json
{
  "action": "network",
  "type": "route",
  "browser": "main",
  "url": "https://example.com/api/profile",
  "json": {
    "name": "Demo User"
  }
}
```

阻断图片：

```json
{
  "action": "network",
  "type": "route",
  "browser": "main",
  "url": "**/*.{png,jpg,jpeg}",
  "mode": "abort"
}
```
