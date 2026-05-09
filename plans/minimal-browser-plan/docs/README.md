# minimal-browser-plan

最小自包含 plan 包示例。

## 目录说明

- `plan.json`: 自动化计划入口，也是这个需求的最小执行单元。
- `config.json`: 本 plan 的局部配置，会覆盖 `plans/config.json` 中的相同字段。
- `sub-plans/open-demo-plan.json`: 主计划引用的子计划，只能被本目录的 `plan.json` 通过 `run_sub_plan` 调用。
- `resources/`: 本 plan 独占的页面、数据、图片等资源。
- `output/`: 本 plan 的运行输出，由 Git 忽略。
- `docs/`: 本 plan 的说明文档。

`plan.json` 不能引用其他需求目录下的 `plan.json`。不同 plan 包之间应保持独立。

## 运行

```powershell
python .\main.py --file .\plans\minimal-browser-plan\plan.json
```
