# write_csv

## 用途

把数组数据写入 CSV 文件。

这个组件适合导出提取结果、生成测试中间产物、或者把多轮执行结果沉淀成表格。

## 必填字段

- `action`: 固定写成 `write_csv`
- `path`: 输出文件路径
- `rows`: 要写入的行数据

## 可选字段

- `headers`: 自定义表头

## 使用说明

- 如果 `rows` 是字典数组，且没有传 `headers`，会自动使用第一行的字段名作为表头。
- 如果 `rows` 是列表数组，可以直接逐行写入。
- 文件会使用 `utf-8-sig` 编码，方便在 Windows 下直接用表格软件打开。

## 示例

```json
{
  "action": "write_csv",
  "path": "../../../output/examples/accounts.csv",
  "rows": "{{rows}}"
}
```
