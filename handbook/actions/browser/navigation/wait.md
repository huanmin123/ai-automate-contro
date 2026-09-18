# wait

## 用途

统一处理等待。

## 必填字段

- `action`: 固定写成 `wait`
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `time` | 无 | 固定等待，默认类型 |
| `selector` | `selector` | 等待元素状态 |
| `url` | `url` | 等待 URL 匹配 |
| `text` | `selector`、`text` | 等待文本匹配 |
| `count` | `selector`、`expected` | 等待元素数量匹配 |
| `load_state` | `state` | 等待页面加载状态 |
| `element_state` | `state` | 等待语义定位或 selector 对应元素状态 |
| `function` | `js` | 等待页面 JS 条件返回真值 |

没有 `type: timeout`。固定等 2 秒应写 `type: time` 加 `seconds: 2`，条件等待不要用固定等待代替。

包含 `selector`、`url`、`text`、`expected`、`state` 或 `js` 的等待必须显式写非 `time` 的 `type`。这样可以避免把本来想写成条件等待的步骤静默执行成固定等待。

## 可选字段

- `seconds`: 仅 `type: time` 有效，默认 `1`
- `state`: `selector` / `text` 使用，默认 `visible`
- `mode`: `text` 支持 `contains`、`equals`；`count` 支持 `equals`、`gte`、`lte`
- `timeout_ms`: `text`、`count`、`function` 读取该字段，默认 `15000`，超时抛出断言错误；`selector`、`element_state`、`url`、`load_state` 不读取该字段，按会话默认超时执行（由 `open_browser.timeout_ms` 设置，默认 `15000`）
- `index`: `selector` / `text` / `element_state` 使用，当选择器匹配多个元素时选择第几个
- `frame_selector`: iframe 选择器
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始
- `arg`: `type: function` 的 JS 参数

超时行为细节：`text` 先等元素进入目标状态（会话默认超时），再在 `timeout_ms` 内轮询文本内容；`count` 在 `timeout_ms` 内轮询元素数量；`function` 把 `timeout_ms` 直接传给 Playwright `wait_for_function`。

## 示例

```json
{
  "action": "wait",
  "type": "selector",
  "browser": "main",
  "selector": "input[autocomplete='username']"
}
```

等待网络空闲：

```json
{
  "action": "wait",
  "type": "load_state",
  "browser": "main",
  "state": "networkidle"
}
```

等待 JS 条件：

```json
{
  "action": "wait",
  "type": "function",
  "browser": "main",
  "js": "() => window.appReady === true"
}
```

```json
{
  "action": "wait",
  "type": "text",
  "browser": "main",
  "selector": "#submit-btn",
  "text": "进入控制台",
  "mode": "equals"
}
```

## 建议

- 优先使用 `selector`、`url`、`text`、`count`、`element_state`、`function` 这类条件等待，让流程等真实页面状态，不等固定时间。
- `type: time` 只适合短动画、节流、人工观察或没有稳定条件的兜底。真实业务流程里不要用长 sleep 代替 selector、接口响应或业务状态。
- `networkidle` 只适合没有长轮询、WebSocket、SSE、持续埋点或广告请求的页面。后台系统、聊天页、实时看板和埋点多的页面优先等目标元素、URL、文本、接口响应或 JS 状态。
- 等待超时说明定位条件不满足，不要第一反应把时间加长。先检查 locator、iframe、登录态、权限页、遮罩层、接口失败和页面是否进入了不同状态。
- 优化耗时时先看 `output/<run>/events.jsonl` 或 `run.log` 的 step 用时，再判断是导航、等待条件、接口响应、下载还是数据提取慢。
