# mouse

## 用途

统一处理页面级鼠标操作。

## 必填字段

- `action`: 固定写成 `mouse`
- `type`: `move`、`click`、`down`、`up`、`wheel`、`tap`、`swipe`
- `browser`: 浏览器会话名

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `move` | `x`、`y` | 移动鼠标 |
| `click` | `x`、`y` | 点击坐标 |
| `down` | 无 | 按下鼠标键 |
| `up` | 无 | 释放鼠标键 |
| `wheel` | `delta_x` / `delta_y` | 滚轮滚动 |
| `tap` | `x`、`y` | 触摸点击坐标 |
| `swipe` | `start_x`、`start_y`、`end_x`、`end_y` | 触控滑动手势 |

## 可选字段

- `button`: 鼠标键，默认 `left`
- `click_count`: 仅 `type: click` 有效，默认 `1`
- `steps`: `swipe` 分段数量，默认 `10`
- `duration_ms`: `swipe` 持续时间，默认 `300`
- `touch`: `swipe` 是否优先使用 Chromium CDP 触摸事件，默认 `true`
- `fallback_to_mouse`: 触摸事件不可用时是否回退为鼠标拖动，默认 `true`

## 示例

```json
{
  "action": "mouse",
  "type": "wheel",
  "browser": "main",
  "delta_y": 300
}
```

触控滑动：

```json
{
  "action": "mouse",
  "type": "swipe",
  "browser": "mobile",
  "start_x": 40,
  "start_y": 190,
  "end_x": 300,
  "end_y": 190,
  "steps": 8,
  "duration_ms": 240,
  "touch": true
}
```
