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
- `timeout_ms`: 仅 `type: count` 有效，默认 `15000`
- `index`: `selector` / `text` 使用，当选择器匹配多个元素时选择第几个
- `frame_selector`: iframe 选择器
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始
- `arg`: `type: function` 的 JS 参数

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

- 优先使用 `selector`、`url`、`text`、`count` 这类显式等待。
- `type: time` 只适合作为观察页面或兜底等待。
