# interval-trigger

验证 `trigger` 作为父级控制流 action，周期执行内联 `steps` 和 `sub-plans/*-plan.json` 子计划。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\control-flow\interval-trigger\plan.json
python .\cplan.py run --file .\test-plans\control-flow\interval-trigger\plan.json
```

## 预期

- `inline_ticker` 触发器运行 2 次。
- `sub_plan_ticker` 触发器运行 2 次，并周期执行 `sub-plans/tick-once-plan.json`。
- `output/text/ticks.txt` 包含 4 行：2 行 inline，2 行 sub-plan。
- `output/json/trigger-status.json` 中两个状态的 `status` 都是 `completed`，`run_count` 都是 `2`。
