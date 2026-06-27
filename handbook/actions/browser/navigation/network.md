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
| `route_from_har` | `path` | 使用 HAR 文件回放匹配请求 |
| `route_web_socket` | `url` | mock WebSocket 连接和消息 |

## `route` 字段

- `mode`: `fulfill`、`abort`、`continue`；省略时，如果提供 `json`、`body` 或 `path`，默认 `fulfill`，否则默认 `continue`
- `status`: mock 响应状态码，默认 `200`
- `headers`: mock 响应头，或 continue 时覆盖请求头
- `json`: mock JSON 响应体
- `body`: mock 文本或字节响应体
- `path`: 使用本地文件作为响应体，默认使用当前 plan 包 `resources/...`
- `content_type`: mock 响应 Content-Type
- `error_code`: `mode: abort` 时使用，默认 `failed`
- `continue_url`、`method`、`post_data`: `mode: continue` 时改写请求

## `route_from_har` 字段

- `path`: HAR 文件路径，默认放在当前 plan 包 `resources/` 下
- `url`: 只对匹配 URL 启用 HAR 回放；建议显式提供，避免影响其他请求
- `not_found`: HAR 未命中时的行为，`abort` 或 `fallback`
- `update`: 是否更新 HAR 文件
- `update_content`: `attach` 或 `embed`
- `update_mode`: `full` 或 `minimal`
- `scope`: `context` 或 `page`，默认 `context`

## `route_web_socket` 字段

- `url`: WebSocket URL 匹配规则
- `server_messages`: 建连后由 mock server 主动发送的消息数组
- `response`: 收到客户端消息后返回的固定消息
- `echo`: 是否把客户端消息原样发回
- `close_after_response`: 回复后是否关闭连接
- `close_on_connect`: 建连后是否立即关闭
- `close_code`、`close_reason`: 关闭连接时使用
- `scope`: `context` 或 `page`，默认 `context`

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

使用 HAR 回放接口：

```json
{
  "action": "network",
  "type": "route_from_har",
  "browser": "main",
  "path": "resources/replay.har",
  "url": "https://example.com/api/profile",
  "not_found": "fallback"
}
```

## 路径约束

- `route.path` 和 `route_from_har.path` 默认放在当前 plan 包 `resources/`。
- AI 创建 plan 时，用户没有指定固定本机响应体文件或 HAR 文件时，推荐先把文件导入当前包 `resources/`，再写 `resources/...`。
- 本机响应体文件或 HAR 文件支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。

mock WebSocket：

```json
{
  "action": "network",
  "type": "route_web_socket",
  "browser": "main",
  "url": "wss://example.com/ws",
  "server_messages": ["ready"],
  "response": "ok"
}
```
