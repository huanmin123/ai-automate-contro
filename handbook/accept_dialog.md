# accept_dialog

## 用途

接受当前捕获到的浏览器弹窗。

## 必填字段

- `action`: 固定写成 `accept_dialog`

## 可选字段

- `prompt_text`: 如果是 prompt 弹窗，可顺便输入文本
- `trigger`: 触发弹窗的单个动作对象。对于 `alert/confirm/prompt`，推荐优先用这个方式。
