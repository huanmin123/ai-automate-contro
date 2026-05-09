# wait_for_count

## 用途

等待某个选择器的元素数量达到条件。

## 必填字段

- `action`: 固定写成 `wait_for_count`
- `browser`: 浏览器会话名
- `selector`: 目标选择器
- `expected`: 期望数量

## 可选字段

- `mode`: `equals`、`gte`、`lte`
- `timeout_ms`: 超时时间
