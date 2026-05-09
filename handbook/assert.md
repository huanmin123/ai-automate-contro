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

## 可选字段

- `mode`: `text` / `value` 支持 `equals`、`contains`；`url` 支持 `contains`、`equals`、`not_contains`；`count` 支持 `equals`、`gte`、`lte`
- `state`: 仅 `type: selector` 有效，默认 `visible`

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
