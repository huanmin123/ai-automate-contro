# copy_variable

## 用途

把一个已有变量复制成另一个变量名。

## 必填字段

- `action`: 固定写成 `copy_variable`
- `source`: 原变量名
- `target`: 新变量名

## 示例

```json
{
  "action": "copy_variable",
  "source": "email",
  "target": "backup_email"
}
```
