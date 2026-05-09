# extract_nth_text

## 用途

从一组匹配元素中，取第 N 个元素的文本，并保存为变量。

## 必填字段

- `action`: 固定写成 `extract_nth_text`
- `browser`: 目标浏览器会话名称
- `selector`: 会匹配到多个元素的选择器
- `save_as`: 保存后的变量名

## 可选字段

- `index`: 第几个元素，默认 `0`

## 示例

```json
{
  "action": "extract_nth_text",
  "browser": "main",
  "selector": ".account-item",
  "index": 0,
  "save_as": "first_account"
}
```

## 适合场景

- 页面里有列表
- 你只想取第一个、第二个或指定位置的文本

## 注意事项

- `index` 从 `0` 开始。
- 如果你后面还要对同一批元素做更多处理，未来可以考虑扩展更强的列表组件。
