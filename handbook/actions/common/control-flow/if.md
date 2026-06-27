# if

## 用途

根据条件决定执行 `then` 还是 `else` 里的步骤。

## 必填字段

- `action`: 固定写成 `if`
- `condition`: 条件对象
- `then`: 条件成立时执行的步骤数组

## 可选字段

- `else`: 条件不成立时执行的步骤数组

## 示例

```json
{
  "action": "if",
  "condition": {
    "type": "equals",
    "left": "{{mode}}",
    "right": "debug"
  },
  "then": [
    {
      "action": "print",
      "message": "当前是调试模式"
    }
  ],
  "else": [
    {
      "action": "print",
      "message": "当前不是调试模式"
    }
  ]
}
```
