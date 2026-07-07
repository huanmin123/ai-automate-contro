# event

## 用途

统一处理浏览器事件。它有两类用法：

- `type=start/stop/clear`: 采集页面运行事件并写入 JSON，用于调试前端错误、控制台输出、失败请求、WebSocket、SSE、WebRTC 和 Service Worker。
- `type=download/file_chooser/popup/request/response`: 在执行一个 `trigger` step 时等待一次浏览器事件并发布结果。

下载、文件选择器、popup、请求和响应等待只使用 `event` 的不同 `type`，避免同类能力拆成多个 action。

## 必填字段

- `action`: 固定写成 `event`
- `type`: `start`、`stop`、`clear`、`download`、`file_chooser`、`popup`、`request`、`response`
- `browser`: 浏览器会话名

`type: stop` 还必须提供：

- `path`: 相对于 `output/json/` 的 JSON 路径

触发等待类型必填字段：

- `download`: `path`、`trigger`。下载保存到 `output/downloads/`。
- `file_chooser`: `files`、`trigger`。等待文件选择器并设置本地文件。
- `popup`: `popup_page`、`trigger`。捕获新页面并注册为命名页面。
- `request`: `url`、`trigger`。捕获匹配请求。
- `response`: `url`、`trigger`。捕获匹配响应。

## 可选字段

- `page`: 页面名，默认当前页面
- `switch`: `type=popup` 捕获后是否切换到新页面，默认 `true`
- `include_headers`: `type=request/response` 是否发布 headers，默认 `false`
- `include_post_data`: `type=request` 是否发布请求体，默认 `false`
- `include_body`: `type=response` 是否发布响应体，默认 `false`
- `body_type`: `include_body` 时使用，支持 `text`、`json`、`body`，默认 `text`
- `console`: 是否采集 console，默认 `true`
- `pageerror`: 是否采集 page error，默认 `true`
- `requestfailed`: 是否采集失败请求，默认 `true`
- `websocket`: 是否采集 WebSocket 建连，默认 `true`
- `websocket_frames`: 是否采集 WebSocket 收发帧内容，默认 `false`
- `eventsource`: 是否注入 EventSource 观察脚本并在 stop 时采集 SSE 事件，默认 `false`
- `webrtc`: 是否注入 WebRTC 观察脚本，默认 `false`
- `webrtc_include_sdp`: 是否在 WebRTC 事件中包含完整 SDP，默认 `false`
- `webrtc_include_candidate`: 是否在 WebRTC 事件中包含完整 ICE candidate，默认 `false`
- `serviceworker`: 是否采集 Service Worker 创建、console、请求和页面注册事件，默认 `false`
- `output.as`: 把 `stop` 的事件数组、`download` 的文件路径、`file_chooser` 的文件列表、`popup` 的页面名、`request/response` 的捕获 payload 保存为变量

## 示例

等待下载：

```json
{
  "action": "event",
  "type": "download",
  "browser": "main",
  "path": "orders.csv",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#download"
  },
  "output": {"as": "downloaded_path"}
}
```

等待接口响应：

```json
{
  "action": "event",
  "type": "response",
  "browser": "main",
  "url": "https://example.com/api/profile",
  "include_body": true,
  "body_type": "json",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#load-profile"
  },
  "output": {"as": "profile_response"}
}
```

采集调试事件：

```json
{
  "action": "event",
  "type": "start",
  "browser": "main",
  "websocket_frames": true,
  "eventsource": true,
  "webrtc": true,
  "serviceworker": true
}
```

```json
{
  "action": "event",
  "type": "stop",
  "browser": "main",
  "path": "events.json",
  "output": {"as": "browser_events"}
}
```
