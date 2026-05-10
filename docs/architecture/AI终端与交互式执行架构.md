# AI 终端与交互式执行架构

## 背景

自动化框架的核心是 plan 包。用户真正需要 AI 参与的地方，不是让模型混入每一步浏览器动作，而是让 AI 帮助维护 plan：

- 创建 plan。
- 管理 plan 配置和文档。
- 运行与观察 plan。
- 分析失败。
- 生成修复补丁。
- 产出报告。

因此 CLI 分为管理终端和 AI 终端。管理终端提供确定性命令，AI 终端通过这些命令完成 plan 级协作。

## 总体分层

```text
CLI
├── 管理终端
│   ├── 创建 plan 模板
│   ├── 校验 plan
│   ├── 运行 plan
│   ├── 查看状态、日志、输出
│   ├── 暂停、继续、停止
│   └── 修改运行变量或环境
│
└── AI 终端
    ├── 理解用户需求
    ├── 创建 plan 包
    ├── 管理 plan 文档和配置
    ├── 启动运行
    ├── 分析失败日志和输出
    ├── 生成修复补丁
    ├── 请求用户确认
    └── 生成结果报告

执行内核
├── InteractivePlanRunner
├── Event Stream
├── Command Queue
├── Run State
└── Output
```

## 管理终端

管理终端是确定性入口，不依赖 AI。

第一版使用 `cmd2` 作为交互式 CLI 底座。它负责持续会话、命令帮助、历史、脚本化执行和基础解析；项目只实现和 plan 相关的业务命令。

第一批命令：

- `plan create`: 创建 plan 包模板，第一版已可用。
- `plan validate`: 校验 plan 结构、路径、组件字段和输出约束，第一版已可用。
- `plan run`: 先校验再运行 plan，第一版已可用。
- `plan status`: 查看当前运行状态。
- `plan pause`: 暂停正在运行的 plan。
- `plan continue`: 继续运行。
- `plan stop`: 停止运行。
- `plan set-variable`: 修改运行变量。
- `plan logs`: 查看运行日志。
- `plan output`: 打开或列出输出目录。
- `plan report`: 生成运行报告。

管理终端不猜需求，只执行明确命令。

## AI 终端

AI 终端是面向自然语言的 plan 助手。

用户可以描述目标：

```text
帮我做一个登录页自动化 plan，打开页面后等待用户名输入框，填入测试账号，再保存截图。
```

AI 终端负责：

1. 询问缺失信息。
2. 创建 plan 包。
3. 写入 `plan.json`、`config.json`、`docs/README.md`。
4. 运行校验。
5. 询问用户是否运行。
6. 运行 plan。
7. 读取日志、输出和失败截图。
8. 给出修复建议。
9. 生成补丁并请求确认。
10. 应用修复并再次验证。
11. 输出最终报告。

AI 终端不直接绕过管理终端能力。它调用管理终端暴露的工具。

第一版 AI 终端已经落地：

```powershell
python .\main.py ai
python .\main.py ai --thread login-debug
```

当前版本使用 `cmd2` 提供持续交互，用 `langchain.agents.create_agent` 编排模型与工具循环。项目工具通过 LangChain `StructuredTool` 暴露给模型，模型使用原生 `tool_calls`，工具执行由 LangChain/LangGraph agent 图处理，不再使用自定义 JSON 工具调用协议。

会话状态由 LangGraph `SqliteSaver` 持久化到本地 `.keygen/ai-terminal-checkpoints.sqlite`，用户可以用 `--thread <id>` 进入或恢复同一个 AI 会话。终端内提供 `context`、`history [limit]`、`thread [id]` 和 `reset` 管理当前线程。`.keygen/` 属于本地运行状态，由 Git 忽略。

AI 终端还有线程级业务上下文状态，和消息历史一起进入 LangGraph checkpoint：

- `current_plan_path`
- `current_debug_workspace`
- `latest_output_dir`

终端命令 `use [plan]`、`workspace [debug-workspace]`、`run_context [output-dir]` 可以显式设置这些状态。结构化工具返回 plan、debug workspace 或 run output 时也会自动更新状态。模型调用前，`AITerminalContextMiddleware` 会把这些上下文追加到 system message，让用户可以说“当前 plan”“最近失败输出”“这个 debug workspace”，不必每次重复路径。

补丁应用审批使用 LangChain `HumanInTheLoopMiddleware`。当模型请求 `apply_debug_patch_after_approval` 时，Agent 图会在工具执行前中断并写入 checkpoint，终端显示 `[WAIT_APPROVAL]`、工具名、参数和说明。用户输入 `approve` 后，终端用 `Command(resume=...)` 恢复图，并把 `approved: true` 注入工具参数；用户输入 `reject <reason>` 则把拒绝结果作为 ToolMessage 返回给模型。

模型服务从 `test-plans/config.json` 的 `ai_services.default` 读取。该配置当前用于真实 AI 回归，包含用户主动提供的临时测试服务和密钥。

## 交互式执行器

当前执行器是一跑到底的同步模型。后续需要演进为交互式执行模型。

核心对象：

```text
InteractivePlanRunner
├── run_id
├── plan_path
├── state
├── variables
├── current_step
├── event_stream
├── command_queue
└── output_dir
```

### 事件流

执行器持续输出结构化事件：

- `run_started`
- `step_started`
- `step_finished`
- `step_failed`
- `waiting_for_user`
- `user_command_received`
- `variable_changed`
- `artifact_created`
- `run_paused`
- `run_resumed`
- `run_stopped`
- `run_finished`

终端、人类用户和 AI 终端都只读事件流，不直接读执行器内部状态。

第一版同时写入 `state.json` 作为稳定状态快照。终端、外部脚本和后续 AI 终端优先读取该文件判断当前 run 是否处于 `running`、`waiting`、`passed` 或 `failed`。

每次运行还会生成 `report.md`，和 `result.json`、`run.log`、`events.jsonl` 放在同一个 run 目录。报告只汇总状态、路径、错误、失败截图、失败 HTML、失败页面状态、下载和标准运行文件，不展开变量内容，便于 AI 终端和人工排查快速读取。

### 命令队列

执行器接收外部命令：

- `pause`
- `continue`
- `stop`
- `set_variable`
- `set_config`
- `mark_manual_step_done`
- `request_status`

命令必须可审计，写入运行日志。

第一版先落地审计结构：管理终端对等待态 run 执行 `continue` 或 `stop` 时，会把命令写入当前 run 目录的 `commands.jsonl`，并同步写入 `events.jsonl`。跨进程命令消费后续再扩展。

### 人工交互

账号密码输入、验证码、二次验证、人工确认等场景由用户完成。plan 中可以使用人工等待动作：

```json
{
  "action": "manual_confirm",
  "prompt": "请在浏览器中完成账号密码输入，然后回到终端输入 continue。"
}
```

管理终端展示：

```text
[WAIT_USER] 请在浏览器中完成账号密码输入，然后回到终端输入 continue。
> continue
```

AI 终端可以解释等待原因，但继续执行的命令仍由用户确认。

## LangGraph 落点

AI 终端使用 LangGraph 作为编排层。

原因：

- AI 终端是长状态任务。
- 需要 human-in-the-loop。
- 需要中断、恢复、重试。
- 需要把“运行 plan -> 读取失败 -> 修复 -> 再运行”表达成图。

当前落地图结构：

```text
UserRequest
  -> langchain.agents.create_agent
  -> ChatOpenAI.bind_tools(StructuredTool[])
  -> AIMessage.tool_calls
  -> Agent 图执行受控项目工具
  -> ToolMessage 返回结果
  -> AIMessage 总结或继续调用工具
```

长期推荐图结构：

```text
UserRequest
  -> IntentRouter
  -> ContextLoader
  -> PlanDesigner
  -> Validator
  -> HumanApproval
  -> PlanRunnerTool
  -> RunObserver
  -> FailureAnalyzer
  -> PatchDesigner
  -> HumanApproval
  -> PatchApplier
  -> ReportWriter
```

LangGraph 只编排 AI 工作流，不接管浏览器执行器。浏览器执行、输出路径、debug workspace、patch 和审批仍由项目工具自身约束。

## 工具边界

AI 终端只能通过工具操作项目。

第一批工具：

- `list_plan_packages`
- `read_plan_package`
- `create_plan_package`
- `validate_plan`
- `run_plan`
- `analyze_latest_run_failure`
- `read_latest_run_state`
- `read_latest_run_report`
- `read_run_events`
- `read_run_log`
- `list_output_artifacts`
- `read_output_artifact`
- `create_debug_workspace`：已完成底层工具和管理终端命令。
- `list_output_artifacts`：已完成底层工具和管理终端命令。
- `list_debug_workspaces`
- `find_debug_workspace`
- `read_debug_workspace`
- `prepare_failure_debug_workspace`：已完成基于最近失败的 debug workspace 创建和失败步骤前诊断注入。
- `propose_debug_fix`：已完成 selector 超时的第一版候选修复，候选应用只写入 debug workspace。
- `inject_debug_steps`：已完成底层工具和管理终端命令。
- `write_debug_workspace_file`：已完成受限写入，只能写 debug workspace 内的 `injected-plan/`、`notes.md` 和 `report.md`。
- `validate_debug_plan`
- `run_debug_plan`
- `generate_debug_patch`：已完成底层工具和管理终端命令。
- `apply_debug_patch_after_approval`：已完成底层工具和 `--yes` 显式确认命令。

文件修改必须形成可读补丁，并经过用户确认。
AI 终端不得直接写原始 plan 包；所有修复候选必须先落到当前 debug workspace 的 `injected-plan/`，再由 `generate_debug_patch` 生成补丁。

结构化工具也可以直接从 CLI 调用，便于脚本、CI 和回归验证：

```powershell
python .\main.py tool list
python .\main.py tool call list_plan_packages --args-json '{"filter_text":"ai"}'
```

`apply_debug_patch_after_approval` 有双重保护：AI 终端通过 `HumanInTheLoopMiddleware` 在工具执行前中断，只有用户在终端输入 `approve` 后才会通过 `Command(resume=...)` 恢复；工具自身仍要求参数包含 `approved: true`，避免绕过终端审批直接调用。

AI 调试修复的详细隔离工作区、注入规则和用户协助流程见 [AI调试修复工作流](./AI调试修复工作流.md)。

## 专项 AI 边界

专项 AI 不等于 AI 终端。专项 AI 只做可控任务：

- 图像 OCR。
- 文本分类。
- 文本结构化抽取。
- 数据清洗。
- 字段归一化。
- 简单内容生成。

专项 AI 必须具备：

- 固定输入 schema。
- 固定输出 schema。
- 固定系统提示词。
- 服务别名。
- 输出解析和校验。
- 失败产物保存到当前 plan 包 `output/ai/`；普通浏览器执行失败会保存失败截图、失败 HTML 和失败页面状态。

专项 AI 不负责创建、运行、修复 plan。

第一版专项 AI 以统一 `ai` action 落地，通过 `type` 区分 `connectivity`、`extract_data`、`classify_text`、`transform_data` 和 `summarize_text`。它使用 OpenAI-compatible 服务配置，优先请求结构化 JSON 输出，再进行本地 schema 校验，并把请求摘要、原始响应、解析结果和校验信息写入 `output/ai/`。

`test-plans/config.json` 可以包含用户提供的临时测试模型服务，用于真实 AI 场景回归；公开示例配置不放真实密钥。

## 设计结论

- CLI 是唯一操作入口。
- 管理终端负责确定性控制。
- AI 终端负责 plan 级协作。
- 交互式执行器负责事件流和命令队列。
- LangGraph 用于 AI 终端，不接管浏览器执行。
- 专项 AI 是受控数据处理组件，不参与 plan 管理。
