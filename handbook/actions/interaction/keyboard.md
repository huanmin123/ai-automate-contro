# keyboard

## 用途

统一处理页面级键盘操作。

## 必填字段

- `action`: 固定写成 `keyboard`
- `type`: `press`、`type`、`down`、`up`
- `browser`: 浏览器会话名

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `press` | `key` | 按下并释放按键 |
| `type` | `value` | 输入文本 |
| `down` | `key` | 按下按键不释放 |
| `up` | `key` | 释放按键 |

## 可选字段

- `delay_ms`: 仅 `type: type` 有效，默认 `50`

## 示例

```json
{
  "action": "keyboard",
  "type": "press",
  "browser": "main",
  "key": "Tab"
}
```
