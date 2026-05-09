# load_csv

## 用途

从 CSV 文件读取数据，并保存成“字典数组”变量。

## 必填字段

- `action`: 固定写成 `load_csv`
- `path`: CSV 文件路径
- `save_as`: 保存变量名

## 示例

```json
{
  "action": "load_csv",
  "path": "../data/sample_accounts.csv",
  "save_as": "rows"
}
```

如果你运行的是 `examples/scenarios/data-driven/` 下的示例，那么这里的 `../../data/` 实际会指向 `examples/data/`。
