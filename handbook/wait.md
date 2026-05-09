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

## 可选字段

- `seconds`: 仅 `type: time` 有效，默认 `1`
- `state`: `selector` / `text` 使用，默认 `visible`
- `mode`: `text` 支持 `contains`、`equals`；`count` 支持 `equals`、`gte`、`lte`
- `timeout_ms`: 仅 `type: count` 有效，默认 `15000`
- `index`: `selector` / `text` 使用，当选择器匹配多个元素时选择第几个

## 示例

```json
{
  "action": "wait",
  "type": "selector",
  "browser": "main",
  "selector": "input[autocomplete='username']"
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
