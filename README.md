# keygen-openai-account

这是一个基于 Playwright + Python 的 JSON 编排自动化内核。

你不需要每次改 Python 代码，而是通过维护 plan 包描述动作流程。执行器读取 `plan.json` 后按顺序执行。

`handbook/` 是唯一教程来源。

## 快速开始

```powershell
python -m pip install -e .
python -m playwright install chromium
python .\main.py
```

项目使用 `src/` 布局。开发环境建议执行 `python -m pip install -e .`，或者在 IDE 里把 `src` 标记为 Sources Root；否则 IDE 或裸 `python -c "import keygen_automation"` 可能找不到 `keygen_automation`，但通过 `python .\main.py ...` 运行时会由入口自动加入 `src` 路径。

进入持续管理终端后：

```powershell
use .\plans\minimal-browser-plan\plan.json
validate
run
status
output
```

创建新的 plan 包模板：

```powershell
python .\main.py plan create --path .\test-plans\basic\new-plan
```

进入持续 AI 终端：

```powershell
python .\main.py ai
python .\main.py ai --thread login-debug
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

## 管理终端

- 默认运行 `python .\main.py` 会进入基于 `cmd2` 的持续管理终端。
- `list`: 扫描 `plans/` 和 `test-plans/` 下的 plan 包。
- `use`: 选择当前 plan 包入口。
- `inspect`: 查看当前 plan 的名称、变量、步骤数量、子计划和最近输出。
- `validate`: 校验 plan 结构、子计划路径、组件字段和输出路径约束。
- `run`: 先校验再运行当前 plan。
- `continue` / `stop`: 继续或终止等待在 `manual_confirm` 的当前 run。
- `var set/list/unset/clear`: 管理当前终端会话变量覆盖。
- `status` / `status --short` / `output` / `report` / `logs` / `events`: 查看最近一次运行结果、输出目录、运行报告、运行日志和结构化事件。
- `artifacts [filter] [limit]`: 列出当前 plan 包 `output/` 下的产物。
- `debug prepare [name]` / `debug create [name]` / `debug list` / `debug fix [--apply] [workspace]` / `debug inject <preset[,preset...]> [workspace]`: 基于最近失败准备调试副本、创建/查看工作区、生成干净修复候选或注入诊断步骤。
- `debug patch [workspace]` / `debug apply --yes [workspace]`: 生成补丁并在显式确认后应用回原始 plan 包。

一次性命令 `python .\main.py plan validate --file <plan.json>` 和 `python .\main.py plan run --file <plan.json>` 用于脚本、回归和后续 AI 工具调用。运行 plan 只保留这一套显式子命令入口，避免形成两套运行路径。

## AI 终端

- `python .\main.py ai`: 进入基于 LangChain Agent + LangGraph 的持续 AI 终端。
- `python .\main.py ai --thread <id>`: 进入或恢复指定 AI 会话线程。
- AI 终端读取 `test-plans/config.json` 的 `ai_services.default` 作为默认模型服务；当前测试服务和临时密钥是用户提供的真实回归配置，不要自动删除。
- AI 终端使用 `langchain.agents.create_agent`、`langchain-openai` 和 LangChain `StructuredTool` 暴露工具，模型通过原生 `tool_calls` 调用工具，不再使用自定义 JSON 工具调用协议。
- 会话状态由 LangGraph `SqliteSaver` 持久化到本地 `.keygen/ai-terminal-checkpoints.sqlite`，该目录由 Git 忽略。终端内可用 `context` 查看当前线程、`history [limit]` 查看消息、`thread [id]` 切换线程、`reset` 删除当前线程。
- AI 终端有线程级上下文状态：`use [plan.json-or-package-dir]` 设置当前 plan，`workspace [output/debug/<run>]` 设置当前 debug workspace，`run_context [output-dir]` 设置最近输出目录。工具调用返回 plan、workspace 或 output 时也会自动更新这些状态；模型调用前会通过 LangChain middleware 注入当前上下文。
- AI 终端只能通过结构化工具操作 plan，例如 `list_plan_packages`、`read_plan_package`、`validate_plan`、`run_plan`、`analyze_latest_run_failure`、`prepare_failure_debug_workspace`、`propose_debug_fix`、`read_latest_run_report`、`read_run_log`、`create_debug_workspace`、`read_debug_workspace`、`patch_debug_workspace_json`、`write_debug_workspace_file`、`run_debug_plan`、`generate_debug_patch`。
- AI 只能把修复候选写入 debug workspace 的 `injected-plan/`、`notes.md` 或 `report.md`，不能直接写原始 plan。
- 修改 JSON plan/config 时优先用 `patch_debug_workspace_json` 做路径级最小修改；`write_debug_workspace_file` 主要用于整文件写入、文档、资源、notes 和 report。
- 应用补丁必须走 `apply_debug_patch_after_approval`。AI 请求该工具时会被 LangChain `HumanInTheLoopMiddleware` 暂停，终端显示 `[WAIT_APPROVAL]`；用户输入 `approve` 后才会恢复并注入 `approved: true` 执行，输入 `reject <reason>` 则拒绝这次工具调用。
- `python .\main.py tool list`: 查看 AI 终端可调用的工具。
- `python .\main.py tool call <name> --args-json '{...}'`: 以 JSON 形式调用单个工具，便于脚本、回归和后续 agent 框架复用。

示例：

```powershell
python .\main.py tool call list_plan_packages --args-json '{"filter_text":"ai"}'
python .\main.py tool call read_plan_package --args-json '{"plan_path":".\test-plans\ai\controlled-text\plan.json"}'
python .\main.py tool call read_debug_workspace --args-json '{"workspace":"<output\debug\run>"}'
```

创建调试工作区的一次性命令：

```powershell
python .\main.py plan debug-create --file .\test-plans\basic\file-io\plan.json --name selector-investigation
python .\main.py plan debug-prepare --file .\test-plans\regression\failure-capture\plan.json --name selector-investigation
python .\main.py plan debug-fix --workspace .\test-plans\regression\failure-capture\output\debug\<run> --hint "系统账户"
python .\main.py plan debug-fix --workspace .\test-plans\regression\failure-capture\output\debug\<run> --hint "系统账户" --apply
python .\main.py plan debug-inject --workspace .\test-plans\basic\file-io\output\debug\<run> --preset print --preset variables --message "debug checkpoint"
python .\main.py plan debug-patch --workspace .\test-plans\basic\file-io\output\debug\<run>
python .\main.py plan debug-apply --workspace .\test-plans\basic\file-io\output\debug\<run> --yes
```

## 配置优先级

- `plans/config.json`: 公开示例 plan 的集合级共享配置。
- `test-plans/config.json`: 项目测试 plan 的集合级共享配置，可放测试计划共用变量。
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
- `ai`: 通过 `type` 执行受控专项 AI 任务，例如连通性、文本抽取、分类、转换和摘要

`open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download` 这类参数或生命周期明显不同的能力保持独立组件。

## AI 边界

- AI 终端是后续 plan 级能力，负责创建、运行、调试、修复和报告 plan，不作为普通 `steps` 动作存在。
- 第一版 AI 终端已可通过 `python .\main.py ai` 持续对话，并通过确定性工具读取、校验、运行和调试 plan；同一 `--thread` 的上下文可跨终端进程恢复。
- AI 调试修复必须先用 `debug create` 创建 `output/debug/<run>/source-copy/` 和 `output/debug/<run>/injected-plan/`，在调试副本里注入日志、截图、变量快照或人工确认；修复候选只能写入 `injected-plan/`，再生成补丁并经确认后应用回原始 plan。
- `ai` 是受控专项组件，只处理输入输出明确的数据任务，并强制把调试产物写入当前 plan 包 `output/ai/`。
- `test-plans/config.json` 里的 AI 服务是用户提供的临时测试服务，用于真实 AI 场景回归；除非用户明确要求，不要删除或迁移。公开示例配置不应放真实密钥。
