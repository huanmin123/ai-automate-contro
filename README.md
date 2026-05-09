# keygen-openai-account

这是一个基于 Playwright + Python 的 JSON 编排自动化内核。

你不需要每次改 Python 代码，而是通过维护 plan 包描述动作流程。执行器读取 `plan.json` 后按顺序执行。

`handbook/` 是唯一教程来源。

## 快速开始

```powershell
python -m pip install -r .\requirements.txt
python -m playwright install chromium
python .\main.py --file .\plans\minimal-browser-plan\plan.json
```

运行项目测试 plan：

```powershell
python .\main.py --file .\test-plans\basic\fill-system-account\plan.json
```

## 先看哪里

- 组件手册入口：`.\handbook\README.md`
- 计划结构说明：`.\handbook\计划结构.md`
- 根目录参考样例：`.\plans\minimal-browser-plan\`
- 项目测试计划：`.\test-plans\README.md`

## 当前目录

- `main.py`: 命令行入口，负责读取 `plan.json` 并执行。
- `src/keygen_automation/`: 自动化执行内核。
- `plans/`: 对外参考的最小 plan 包示例；`plans/config.json` 是公开示例 plan 的集合级配置。
- `test-plans/`: 项目真实自动化需求 plan 包。
- `handbook/`: 面向人的组件手册。
- `docs/`: 项目架构、设计、排期、问题和重构记录。

## Plan 包结构

每个 plan 包代表一个独立需求：

```text
plan-package/
  plan.json
  config.json
  sub-plans/
    *-plan.json
  resources/
  output/
  docs/
```

- `plan.json`: 需求入口，也是最小可执行单元。
- `config.json`: 本 plan 包局部配置，只对当前 plan 可见，优先级高于所属集合的 `config.json`。
- `sub-plans/*-plan.json`: 同包内部子计划，只能被本包 `plan.json` 通过 `run_sub_plan` 引用。
- `resources/`: 本需求独占资源。
- `output/`: 本需求运行输出，由 Git 忽略。截图、录屏、下载、日志、报告和运行中间产物都必须写在这里。
- `docs/`: 本需求说明文档。

不同需求的 `plan.json` 之间不能互相引用。需要批量执行时，优先由外部脚本扫描多个 plan 包，而不是让 plan 互相依赖。

`test-plans/` 下面直接放分类目录和 plan 包，不再使用 `suites/`、`workspaces/` 或额外 `plans/` 层级。根目录的 `plans/` 只放公开最小示例，项目内部验证都放到 `test-plans/`。

## 配置优先级

- `plans/config.json`: 公开示例 plan 的集合级共享配置。
- `test-plans/config.json`: 项目测试 plan 的集合级共享配置，可放测试计划共用变量和 AI 服务注册。
- `plan-package/config.json`: 当前 plan 包局部配置，只能当前 plan 访问。
- 相同字段局部配置覆盖全局配置。
- `config.variables` 会注入为变量，也可以通过 `{{config.xxx}}` 访问完整合并配置。
- 变量优先级：内置变量 < 集合级 `config.variables` < 局部 `config.variables` < `plan.json` 的 `variables`。

## 当前支持的动作组件

具体字段说明、适用场景和使用方式请直接看 `handbook` 目录。

常见同族动作已按参数结构收敛：

- `navigate`: 通过 `type` 执行 `goto`、`refresh`、`back`、`forward`
- `page`: 通过 `type` 执行 `open`、`switch`、`close`
- `element`: 通过 `type` 执行 `click`、`fill`、`hover`、`select` 等元素操作
- `wait` / `assert` / `extract`: 通过 `type` 区分等待、断言和提取类型
- `capture`: 通过 `type` 保存截图、HTML、storage state
- `read`: 通过 `type` 读取 `json`、`text`、`csv`
- `write`: 通过 `type` 写出 `json`、`text`、`csv`、`variables`

`open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`、AI 节点这类参数或生命周期明显不同的能力保持独立组件。
