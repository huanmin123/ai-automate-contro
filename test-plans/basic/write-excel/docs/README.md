# write-excel

## 说明

这个目录验证 `write.type=excel` 可以把变量行数组写入 `output/excel/`，并通过 `read.type=excel` 读回为字典数组。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\basic\write-excel\plan.json
python .\cplan.py run --file .\test-plans\basic\write-excel\plan.json --run-name write-excel
```
