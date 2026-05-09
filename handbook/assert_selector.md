# assert_selector

## 用途

断言某个元素在指定时间内进入目标状态，否则直接报错。

## 必填字段

- `action`: 固定写成 `assert_selector`
- `browser`: 目标浏览器会话名称
- `selector`: 要断言的元素选择器

## 可选字段

- `state`: 断言状态，默认 `visible`
- `index`: 当选择器匹配多个元素时，指定第几个

## 示例

```json
{
  "action": "assert_selector",
  "browser": "main",
  "selector": ".login-card"
}
```

## 什么时候用

- 你想把某个元素是否出现作为流程成功条件
- 你希望失败时有更明确的断言含义

## 注意事项

- 它和 `wait_for_selector` 很像，但语义更偏“验证通过/失败”。
- 断言失败后，后续步骤不会继续执行。
