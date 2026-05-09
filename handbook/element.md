# element

## 用途

统一处理基于选择器的元素交互。

## 必填字段

- `action`: 固定写成 `element`
- `type`: 元素操作类型
- `browser`: 浏览器会话名
- `selector`: Playwright 选择器

## 类型说明

| type | 额外字段 | 说明 |
| --- | --- | --- |
| `click` | 无 | 点击元素 |
| `hover` | 无 | 悬停元素 |
| `fill` | `value` | 清空并填入内容 |
| `clear` | 无 | 清空输入框 |
| `type` | `value` | 模拟逐字输入 |
| `focus` | 无 | 聚焦元素 |
| `press` | `key` | 在元素上按键 |
| `check` | 无 | 勾选复选框或单选框 |
| `uncheck` | 无 | 取消勾选 |
| `select` | `value` / `label` / `index_value` | 选择下拉项 |
| `set_files` | `files` | 设置文件上传输入框 |

## 通用可选字段

- `page`: 页面名，默认当前页面
- `index`: 当选择器匹配多个元素时选择第几个，从 `0` 开始
- `delay_ms`: 仅 `type: type` 有效，默认 `50`

## 示例

```json
{
  "action": "element",
  "type": "fill",
  "browser": "main",
  "selector": "input[autocomplete='username']",
  "value": "{{email}}"
}
```
