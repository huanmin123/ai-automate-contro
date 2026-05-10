# manual-command-audit

## 目标

验证交互式管理终端在 `manual_confirm` 等待态收到 `continue` 或 `stop` 时，会把命令写入当前 run 的 `commands.jsonl`，并同步记录到 `events.jsonl`。

## 运行方式

```powershell
python .\main.py
use .\test-plans\regression\manual-command-audit\plan.json
run command-audit
continue
report
```

## 输出

- `output/<run>/commands.jsonl`
- `output/<run>/state.json`
- `output/<run>/report.md`
- `output/<run>/events.jsonl`
