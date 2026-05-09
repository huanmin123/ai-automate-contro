# extract_all_texts

## 用途

提取匹配列表中所有元素的文本，并保存成数组变量。

## 必填字段

- `action`: 固定写成 `extract_all_texts`
- `browser`: 浏览器会话名
- `selector`: 列表元素选择器
- `save_as`: 保存变量名

## 可选字段

- `skip_empty`: 是否跳过空字符串，默认 `true`

## 示例

```json
{
  "action": "extract_all_texts",
  "browser": "main",
  "selector": ".account-item",
  "save_as": "accounts"
}
```
