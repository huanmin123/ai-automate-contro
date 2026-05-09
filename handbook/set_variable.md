# set_variable

## 用途

在执行过程中手动设置一个变量，供后续步骤使用。

## 必填字段

- `action`: 固定写成 `set_variable`
- `name`: 变量名
- `value`: 变量值

## 示例

```json
{
  "action": "set_variable",
  "name": "email",
  "value": "test@example.com"
}
```

## 什么时候用

- 你想在计划中途覆盖某个变量
- 某个值不想写在顶层 `variables` 里

## 注意事项

- 后设置的同名变量会覆盖旧值。
- 当前版本的 `value` 更适合字符串、数字、布尔值这类简单数据。
