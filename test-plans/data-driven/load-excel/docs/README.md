# load-excel

## 说明

这个目录验证 `read.type=excel` 读取 `resources/人员名单.xlsx` 后，可以通过 `table` 筛选、选列并导出 JSON 和 Excel。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\data-driven\load-excel\plan.json
python .\cplan.py run --file .\test-plans\data-driven\load-excel\plan.json --run-name load-excel
```
