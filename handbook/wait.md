# wait

## 用途

固定等待一段时间。

## 必填字段

- `action`: 固定写成 `wait`
- `browser`: 目标浏览器会话名称

## 可选字段

- `seconds`: 等待秒数，默认 `1`

## 示例

```json
{
  "action": "wait",
  "browser": "main",
  "seconds": 3
}
```

## 什么时候用

- 你要临时观察页面变化
- 你在调试计划流程
- 目标站点有短暂动画，不值得专门写更精细的等待

## 注意事项

- 生产化流程中，不要过度依赖它。
- 如果能用 `wait_for_selector` 或 `wait_for_url`，优先用更明确的等待方式。
