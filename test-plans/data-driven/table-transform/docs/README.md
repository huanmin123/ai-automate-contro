# table-transform

## 说明

这个目录验证 `table` 对变量行数组执行筛选、排序、去重和选列。输入数据可以来自 JSON、CSV、Excel、SQL 或页面提取结果，本示例直接使用 plan 变量。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\data-driven\table-transform\plan.json
python .\cplan.py run --file .\test-plans\data-driven\table-transform\plan.json --run-name table-transform
```
