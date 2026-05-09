# load_json

## 用途

从外部 JSON 文件读取数据并保存为变量。

## 必填字段

- `action`: 固定写成 `load_json`
- `path`: JSON 文件路径
- `save_as`: 保存变量名

## 示例

```json
{
  "action": "load_json",
  "path": "../data/sample_accounts.json",
  "save_as": "accounts"
}
```

## 注意事项

- 相对路径基于当前计划文件所在目录解析。
- 读取后的对象可以通过 `{{accounts}}` 或 `{{account.email}}` 这类形式引用。
- 如果你运行的是 `examples/scenarios/data-driven/` 下的示例，那么这里的 `../../data/` 实际会指向 `examples/data/`。
