# mouse

## 用途

统一处理页面级鼠标操作。

## 必填字段

- `action`: 固定写成 `mouse`
- `type`: `move`、`click`、`down`、`up`、`wheel`
- `browser`: 浏览器会话名

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `move` | `x`、`y` | 移动鼠标 |
| `click` | `x`、`y` | 点击坐标 |
| `down` | 无 | 按下鼠标键 |
| `up` | 无 | 释放鼠标键 |
| `wheel` | `delta_x` / `delta_y` | 滚轮滚动 |

## 可选字段

- `button`: 鼠标键，默认 `left`
- `click_count`: 仅 `type: click` 有效，默认 `1`

## 示例

```json
{
  "action": "mouse",
  "type": "wheel",
  "browser": "main",
  "delta_y": 300
}
```
