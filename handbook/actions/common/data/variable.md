# variable

## 用途

统一管理变量池。

## 必填字段

- `action`: 固定写成 `variable`
- `type`: `set`、`set_many`、`copy`

## 类型说明

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `set` | `name`、`value` | 设置单个变量 |
| `set_many` | `values` | 批量设置变量 |
| `copy` | `source`、`target` | 复制已有变量 |

`last` 是保留输出变量，只能由 step 级 `output` 发布器维护，不能作为 `name`、`values` key 或 `target`。

## 示例

```json
{
  "action": "variable",
  "type": "set",
  "name": "email",
  "value": "test@example.com"
}
```
