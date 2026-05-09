# set_variables

## 用途

一次性设置多个变量。

## 必填字段

- `action`: 固定写成 `set_variables`
- `values`: 变量字典

## 示例

```json
{
  "action": "set_variables",
  "values": {
    "email": "test@example.com",
    "mode": "debug"
  }
}
```
