# click

## 用途

点击页面上的某个元素。

## 必填字段

- `action`: 固定写成 `click`
- `browser`: 目标浏览器会话名称
- `selector`: 要点击的元素选择器

## 可选字段

- `index`: 当一个选择器匹配多个元素时，点击第几个，从 `0` 开始

## 示例

```json
{
  "action": "click",
  "browser": "main",
  "selector": "button[type='submit']"
}
```

## 多元素示例

```json
{
  "action": "click",
  "browser": "main",
  "selector": ".menu-item",
  "index": 1
}
```

## 注意事项

- 如果选择器匹配到多个元素，而你又没有提供 `index`，Playwright 可能报严格模式错误。
- 如果按钮需要先出现，前面最好先加一个 `wait_for_selector`。
