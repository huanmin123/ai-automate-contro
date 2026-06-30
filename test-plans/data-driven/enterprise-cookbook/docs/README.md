# enterprise-cookbook

这个目录验证企业 Excel/table 常见流程：一次读取多工作表、筛选在职人员、填补空奖金、转换工资数字类型、连接部门维表、按部门和级别透视薪资、汇总财务流水，并导出多工作表 Excel。

重点覆盖：

- `read.type=excel.sheets[]` 多工作表读取和 `name` 变量别名。
- `table.fill_empty`、`table.type_convert`、`table.rename`、`table.pivot`。
- `write.type=excel.sheets[].start_cell`、冻结表头、筛选、Excel Table、列宽和数字格式。
- 再次读取导出的多工作表 Excel，验证导出结果可被后续 plan 消费。

验证命令：

```powershell
python .\cplan.py validate --file .\test-plans\data-driven\enterprise-cookbook\plan.json
python .\cplan.py run --file .\test-plans\data-driven\enterprise-cookbook\plan.json --run-name enterprise-cookbook
```
