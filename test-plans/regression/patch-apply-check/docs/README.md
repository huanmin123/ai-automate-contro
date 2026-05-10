# patch-apply-check

## 目标

验证 `debug-patch` 和 `debug-apply --yes` 可以把调试工作区中的最小补丁应用回原始 plan 包。

## 运行方式

```powershell
python .\main.py plan validate --file .\test-plans\regression\patch-apply-check\plan.json
python .\main.py plan run --file .\test-plans\regression\patch-apply-check\plan.json --run-name patch-apply-check
```
