# table-cleaning

这个目录验证常见表格清洗链路：替换值、拆列、合列、日期解析、查表补充字段，并输出 JSON。

重点覆盖：

- `table.replace` 全局空值替换和指定列值映射。
- `table.split_column` 按分隔符拆出多个字段。
- `table.merge_columns` 合并多个字段生成新列。
- `table.date_parse` 将多种日期文本格式统一成 ISO 日期。
- `table.lookup` 按 key 从右表查字段并重命名输出列。

验证命令：

```powershell
python .\cplan.py validate --file .\test-plans\data-driven\table-cleaning\plan.json
python .\cplan.py run --file .\test-plans\data-driven\table-cleaning\plan.json --run-name table-cleaning
```
