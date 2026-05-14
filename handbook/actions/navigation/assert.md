# assert

## 用途

统一处理断言。断言失败会中断当前 plan，并触发失败现场采集。

## 必填字段

- `action`: 固定写成 `assert`
- `type`: 断言类型
- `browser`: 浏览器会话名

## 类型说明

| type | 必填字段 | 默认 mode |
| --- | --- | --- |
| `selector` | `selector` | 无 |
| `text` | `selector`、`expected` | `equals` |
| `value` | `selector`、`expected` | `equals` |
| `url` | `expected` | `contains` |
| `count` | `selector`、`expected` | `equals` |
| `attribute` | `selector`、`attribute`、`expected` | `equals` |
| `css` | `selector`、`property`、`expected` | `equals` |
| `checked` | 定位字段 | 无 |
| `unchecked` | 定位字段 | 无 |
| `enabled` | 定位字段 | 无 |
| `disabled` | 定位字段 | 无 |
| `visible` | 定位字段 | 无 |
| `hidden` | 定位字段 | 无 |
| `title` | `expected` | `contains` |

## 可选字段

- `mode`: `text` / `value` / `attribute` / `css` / `title` 支持 `equals`、`contains`、`not_contains`；`url` 支持 `contains`、`equals`、`not_contains`；`count` 支持 `equals`、`gte`、`lte`
- `state`: 仅 `type: selector` 有效，默认 `visible`
- `frame_selector`: iframe 选择器
- `frame_name`: 通过 frame name 定位
- `frame_url`: 通过完整 frame URL 定位
- `frame_url_contains`: 通过 URL 片段定位
- `frame_index`: 通过 `page.frames` 顺序定位，从 `0` 开始
- `index`: 选择器匹配多个元素时选择第几个

## 示例

```json
{
  "action": "assert",
  "type": "text",
  "browser": "main",
  "selector": "#submit-btn",
  "expected": "进入控制台"
}
```

断言属性：

```json
{
  "action": "assert",
  "type": "attribute",
  "browser": "main",
  "selector": "#status",
  "attribute": "data-state",
  "expected": "ready"
}
```
