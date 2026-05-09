# wait_for_url

## 用途

等待页面跳转到指定 URL。

## 必填字段

- `action`: 固定写成 `wait_for_url`
- `browser`: 目标浏览器会话名称
- `url`: 要等待的目标 URL

## 示例

```json
{
  "action": "wait_for_url",
  "browser": "main",
  "url": "https://example.com/dashboard"
}
```

## 什么时候用

- 点击登录或提交按钮后，页面会跳转
- 你需要确认当前已经进入目标页面

## 注意事项

- 这个动作只关心 URL，不保证页面上的具体元素已经可操作。
- 如果跳转完成后还要操作页面，建议继续接一个 `wait_for_selector`。
