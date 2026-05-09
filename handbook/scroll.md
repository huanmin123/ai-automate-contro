# scroll

## 用途

统一处理页面滚动。

## 必填字段

- `action`: 固定写成 `scroll`
- `browser`: 浏览器会话名

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `by` | `delta_x` / `delta_y` | 按偏移量滚动，默认类型 |
| `into_view` | `selector` | 滚动到元素可见 |

## 示例

```json
{
  "action": "scroll",
  "type": "by",
  "browser": "main",
  "delta_y": 300
}
```
