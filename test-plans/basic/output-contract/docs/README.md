# output-contract

验证 step 级 `output` 可以把 action 原始结果中的 JSON 片段发布为变量，并用轻量类型声明校验后供后续步骤直接引用。

## 覆盖点

- `command.stdout_type=json` 解析 stdout。
- `output.as` 发布变量。
- `output.from` 从 action 原始结果中选择子对象。
- `output.type` 和 `output.fields` 校验输出。
- 后续步骤直接引用 `{{user_info.id}}` 和 `{{last.name}}`。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\basic\output-contract\plan.json
python .\cplan.py run --file .\test-plans\basic\output-contract\plan.json --run-name output-contract
```
