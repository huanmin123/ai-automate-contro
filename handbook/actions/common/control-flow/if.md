# if

## 用途

根据条件决定执行 `then` 还是 `else` 里的步骤。

## 必填字段

- `action`: 固定写成 `if`
- `condition`: 条件对象

## 可选字段

- `then`: 条件成立时执行的步骤数组。省略或为空数组时，条件成立不执行任何分支步骤。
- `else`: 条件不成立时执行的步骤数组。省略或为空数组时，条件不成立不执行任何分支步骤。

两个分支都省略是合法 plan：`if` 只求值 `condition` 并记录结果日志，然后继续执行后续步骤。

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
