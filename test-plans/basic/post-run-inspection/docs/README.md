# post-run-inspection

## 说明

验证 `config.json` 中的 `post_run_inspection.enabled` 可以在 plan 步骤正常执行完毕后保留浏览器，等待用户确认后再关闭浏览器并结束运行。

## 运行

```powershell
python .\main.py plan run --file .\test-plans\basic\post-run-inspection\plan.json
```
