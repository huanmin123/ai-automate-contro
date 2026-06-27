# foreach

## 用途

遍历一个列表，并对每个元素执行同一组步骤。

## 必填字段

- `action`: 固定写成 `foreach`
- `items`: 要遍历的数组
- `steps`: 每个元素都要执行的步骤数组

## 可选字段

- `item_var`: 当前元素变量名，默认 `item`
- `index_var`: 当前索引变量名，默认 `index`

## 示例

```json
{
  "action": "foreach",
  "items": "{{accounts}}",
  "item_var": "account",
  "index_var": "account_index",
  "steps": [
    {
      "action": "print",
      "message": "第 {{account_index}} 个邮箱是 {{account.email}}"
    }
  ]
}
```
