# goto

## 用途

让指定浏览器会话跳转到一个 URL。

## 必填字段

- `action`: 固定写成 `goto`
- `browser`: 目标浏览器会话名称
- `url`: 要打开的网址

## 可选字段

- `wait_until`: 页面等待策略，默认 `domcontentloaded`

## 示例

```json
{
  "action": "goto",
  "browser": "main",
  "url": "https://example.com"
}
```

## 带变量示例

```json
{
  "action": "goto",
  "browser": "main",
  "url": "{{target_url}}"
}
```

## 注意事项

- `url` 支持变量替换。
- 跳转后如果页面元素还没稳定出现，建议马上接一个 `wait_for_selector`。
