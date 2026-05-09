# wait_for_selector

## 用途

等待某个选择器对应的元素进入指定状态。

这是最推荐的同步方式，比纯 `wait` 更稳。

## 必填字段

- `action`: 固定写成 `wait_for_selector`
- `browser`: 目标浏览器会话名称
- `selector`: 要等待的元素选择器

## 可选字段

- `state`: 等待状态，默认 `visible`
- `index`: 当选择器匹配多个元素时，等待第几个

## 示例

```json
{
  "action": "wait_for_selector",
  "browser": "main",
  "selector": "input[autocomplete='username']"
}
```

## 指定状态示例

```json
{
  "action": "wait_for_selector",
  "browser": "main",
  "selector": ".loading-mask",
  "state": "hidden"
}
```

## 注意事项

- 如果不写 `index`，这个动作允许选择器匹配多个元素。
- 如果你后面要点击或输入，建议先等待对应元素 `visible`。
