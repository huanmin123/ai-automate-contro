# ai-terminal-full-cycle

Regression fixture for a full AI-terminal lifecycle: create a plan package through a debug workspace, apply a protected patch, run, diagnose a selector failure, apply the final fix, and verify delivery output.

## Structure

- `plan.json` delegates to `sub-plans/01-dashboard-audit-plan.json`.
- `resources/ops-dashboard.html` is a local operations dashboard fixture.
- The final sub-plan waits for `#export-risk-report`, clicks it, asserts the report status, extracts the status text, and writes `output/json/reports/risk-report.json`.

## Run

```powershell
python .\cplan.py run --file .\test-plans\regression\ai-terminal-full-cycle\plan.json --run-name ai-terminal-full-cycle-final
```
