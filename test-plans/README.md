# test-plans

这里存放项目真实自动化需求。

## Plan 包规则

每个目录代表一个独立需求，主入口固定为 `plan.json`：

```text
test-plans/<category>/<requirement>/
  plan.json
  config.json
  sub-plans/
    *-plan.json
  resources/
  output/
  docs/
```

- `plan.json`: 这个需求的最小执行单元，也是唯一可直接执行的入口。
- `config.json`: 这个需求的局部配置，只对当前 plan 包生效。
- `sub-plans/*-plan.json`: 同一需求内部的子计划，只能由本目录的 `plan.json` 通过 `run_sub_plan` 引用。
- `resources/`: 本需求独占资源，例如 HTML、CSV、JSON、图片。
- `output/`: 本需求运行输出，由 Git 忽略。截图、录屏、下载、日志、报告和运行中间产物都必须写在这里。
- `docs/`: 本需求说明文档。

禁止让一个主 `plan.json` 引用另一个需求的 `plan.json`。不同需求之间保持独立；需要批量执行时，优先由外部脚本扫描多个 plan 包。

本测试集合共享配置放在 `test-plans/config.json`。如果当前 plan 包也有 `config.json`，相同字段以当前 plan 包为准。

`test-plans/` 下面直接按类别存放 plan 包，不再增加 `plans/`、`suites/`、`workspaces/` 这类中间目录：

```text
test-plans/
  ai/
    <requirement>/
      plan.json
  basic/
    <requirement>/
      plan.json
  data-driven/
    <requirement>/
      plan.json
  regression/
    <requirement>/
      plan.json
```

运行产物必须落在当前 plan 包的 `output/` 下。组件会自动进入固定分区，例如 `output/screenshots/`、`output/downloads/`、`output/html/`、`output/json/`、`output/text/`、`output/csv/`、`output/storage-states/`、`output/variables/`。

`test-plans/config.json` 当前包含用户提供的临时 AI 测试服务，用于 `test-plans/ai/` 下的真实模型回归。除非用户明确要求，不要删除或迁移；如果密钥过期或需要更换，由用户更新或明确要求移除。

## 运行示例

```powershell
python .\main.py plan run --file .\test-plans\basic\fill-system-account\plan.json
python .\main.py plan run --file .\test-plans\ai\controlled-text\plan.json --run-name ai-controlled-text
python .\main.py plan run --file .\test-plans\ai\text-processing\plan.json --run-name ai-text-processing
```
