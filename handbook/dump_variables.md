# dump_variables

## 用途

把当前所有变量写入一个 JSON 文件，便于排查和调试。

## 必填字段

- `action`: 固定写成 `dump_variables`
- `path`: 输出文件路径

## 示例

```json
{
  "action": "dump_variables",
  "path": "output/runtime_variables.json"
}
```

## 什么时候用

- 你想检查中途提取到的变量内容
- 你在调试复杂计划

## 注意事项

- 相对路径会基于项目根目录解析。
- 输出目录不存在时，执行器会自动创建。
