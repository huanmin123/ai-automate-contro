# file-io

## 说明

这个目录是一个独立自动化需求包。`plan.json` 是唯一可直接执行的入口。

## 目录

- `plan.json`: 主计划，最小执行单元。
- `sub-plans/*-plan.json`: 同包内部子计划，只能由主计划通过 `run_sub_plan` 调用。
- `resources/`: 本需求独占资源。
- `output/`: 运行输出，由 Git 忽略。
- `docs/`: 本需求说明。

## 运行

```powershell
python .\cplan.py run --file .\test-plans\basic\file-io\plan.json
```
