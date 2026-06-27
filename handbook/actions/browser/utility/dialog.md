# dialog

## 用途

统一处理浏览器弹窗。

## 必填字段

- `action`: 固定写成 `dialog`
- `type`: `accept`、`dismiss`
- `browser`: 浏览器会话名

## 可选字段

- `trigger`: 触发弹窗的单个动作对象
- `prompt_text`: 仅 `type: accept` 且弹窗需要输入时使用

## 示例

```json
{
  "action": "dialog",
  "type": "accept",
  "browser": "main",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#alertBtn"
  }
}
```
