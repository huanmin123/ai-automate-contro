# command-run

## 目标

验证 `command` action 的同步本地命令执行能力：

- 使用 `argv` 方式执行本地 Python 脚本。
- 通过 `stdin` 传入内容。
- 把 stdout 解析为 JSON 变量。
- 把 stdout/stderr 写入 `output/commands/`。
- 后续步骤继续读取 command 结果并通过条件分支验证。

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\basic\command-run\plan.json
python .\cplan.py run --file .\test-plans\basic\command-run\plan.json --run-name command-run
```

## 输出

- `output/commands/command-tool-stdout.json`
- `output/commands/command-tool-stderr.txt`
- `output/variables/command-run-variables.json`
