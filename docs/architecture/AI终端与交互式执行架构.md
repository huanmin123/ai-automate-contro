# AI 终端与交互式执行架构

## 背景

自动化框架的核心是 plan 包。用户真正需要 AI 参与的地方，不是让模型混入每一步浏览器动作，而是让 AI 帮助维护 plan：

- 创建 plan。
- 管理 plan 配置和文档。
- 运行与观察 plan。
- 分析失败。
- 生成修复补丁。
- 产出报告。

因此 CLI 是一个统一终端，里面分为 `plan>` 管理模式和 `ai>` AI 模式。默认进入 `plan>`，不加载 AI 服务；用户输入 `ai`、`ai <message>` 或直接运行 `python .\main.py ai` 时，才懒加载 AI 终端。

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

## 统一终端与管理模式

`plan>` 管理模式是确定性入口，不依赖 AI，也不会读取或初始化模型服务。

当前交互 CLI 使用 `prompt_toolkit` 实现统一输入、命令提示、模式切换和 AI 图片输入。非交互命令仍保留在 `python .\main.py plan ...`、`python .\main.py tool ...` 和 `python .\main.py ai ask ...`，用于脚本、回归和打包 smoke test。

第一批命令：

- `create`: 创建 plan 包模板。
- `validate`: 校验 plan 结构、路径、组件字段和输出约束。
- `run`: 先校验再运行 plan。
- `status`: 查看当前运行状态。
- `continue`: 继续等待中的 plan。
- `stop`: 停止等待中的 plan。
- `var`: 修改运行变量。
- `logs`: 查看运行日志。
- `events`: 查看结构化事件。
- `output`: 查看输出目录。
- `report`: 查看运行报告。
- `ai`: 切换到 `ai>`，或用 `ai <message>` 发送一条 AI 消息。

`plan>` 中命令支持普通形式和斜杠形式，例如 `status` 与 `/status` 等价。管理模式不猜需求，只执行明确命令。

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

当前版本使用 `prompt_toolkit` 提供统一终端输入体验和 AI 图片输入体验，并用 `langchain.agents.create_agent` 编排模型与工具循环。项目工具通过 LangChain `StructuredTool` 暴露给模型，每个工具使用显式 Pydantic 参数模型定义输入 schema；CLI 的 `tool call` 入口也复用同一套 schema 校验。模型使用原生 `tool_calls`，工具执行由 LangChain/LangGraph agent 图处理，不再使用自定义 JSON 工具调用协议，也不再通过运行时动态拼装工具 schema。

模型请求边界保持 OpenAI-compatible：AI 终端不向模型请求体塞自定义事件、thread metadata、附件 metadata 或项目内部上下文字段。线程上下文在模型调用前作为普通 system message 文本追加；图片附件在发送前临时转换为 Chat Completions 兼容的 `content` 列表，形态为 `text` 加 `image_url`；工具调用交给 LangChain/OpenAI 原生 `tool_calls`。本地 checkpoint、会话索引和附件 metadata 只服务恢复与归档，不作为自定义协议字段发给模型厂商。

会话状态由 LangGraph `SqliteSaver` 持久化到本地 `.keygen/ai-terminal-checkpoints.sqlite`，用户可以用 `--thread <id>` 进入或恢复同一个 AI 会话。终端内提供 `status`、`sessions [limit|all]`、`resume <thread-id-or-index>`、`context`、`history [limit]`、`thread [id]`、`new` 和 `compress` 管理当前线程。会话列表摘要维护在 `.keygen/ai-terminal-sessions/index.json`，只保存线程、时间、计数、最近消息预览和上下文路径摘要；旧会话没有 index 时会从 checkpoint 回填。`sessions` 不打印完整消息历史。`.keygen/` 属于本地运行状态，由 Git 忽略。

AI 终端回合由后台 worker 执行，输入行保持可用。用户发送自然语言后，LangGraph `stream_mode=["messages", "values"]` 持续把 AI token 输出到终端；期间继续发送的普通消息进入队列，底部状态展示运行中和排队数量。按 `Esc` 不会硬杀当前模型或工具调用，只会把下一条输入标记为安全介入：当前回合继续 drain 到安全边界，但后续流式输出被抑制，队首消息随后处理。服务端 503、欠费、协议不兼容或 schema 错误会直接展示，不做本地兼容兜底。

真实回归中，线程 `real-tool-regression-validate-plan` 已确认模型生成 `tool_calls=validate_plan`，工具结果以 `ToolMessage` 返回 `ok=true`，并由 `SqliteSaver` 保存同一线程的消息与工具调用历史。

AI 终端还有线程级业务上下文状态，和消息历史一起进入 LangGraph checkpoint：

- `current_plan_path`
- `current_debug_workspace`
- `latest_output_dir`
- `latest_compression_summary_path`
- `latest_compression_messages_path`
- `latest_compression_archive_dir`

终端命令 `use [plan]`、`workspace [debug-workspace]`、`run_context [output-dir]` 可以显式设置这些状态；`/new [thread-id]` 开新线程，`/status` 查看当前线程摘要，`/sessions` 查询已落盘会话，`/resume <id-or-index>` 恢复会话，`/compress [reason]` 手动压缩当前线程。结构化工具返回 plan、debug workspace 或 run output 时也会自动更新状态。模型调用前，`AITerminalContextMiddleware` 会把这些上下文追加到 system message，让用户可以说“当前 plan”“最近失败输出”“这个 debug workspace”，不必每次重复路径。

长会话压缩使用 LangChain `SummarizationMiddleware`。项目按 128k token 作为通用上下文标准，约 64k tokens 自动触发压缩，压缩后保留约 32k tokens 的近期上下文；完整消息、摘要和 manifest 归档到 `.keygen/ai-terminal-sessions/<thread>/compressions/`，实时模型上下文只保留摘要和归档位置。摘要生成依赖当前模型服务，服务侧报错会直接暴露给用户，不做项目内兼容兜底。

图片输入是终端侧能力，不进入普通 plan action。用户主路径是在 AI 终端输入行按 `Alt+V` 或 `Ctrl+V` 从剪贴板粘贴图片，终端把 `[图片 #n]` 占位插入当前文字；如果图片已经保存成文件，只保留 `image <image-path>` 作为兜底。图片复制到 `.keygen/ai-terminal-sessions/<thread>/attachments/`，checkpoint 和压缩归档只保存附件 metadata，发送时临时转换成 LangChain `HumanMessage` 的多模态 content list，并移除内部 metadata。发送成功后清空 pending attachments；如果模型服务报错，错误直接显示给用户，附件保留以便重试。剪贴板图片读取依赖 Pillow 和 prompt_toolkit。

补丁应用审批使用 LangChain `HumanInTheLoopMiddleware`。当模型请求 `apply_debug_patch_after_approval` 时，Agent 图会在工具执行前中断并写入 checkpoint，终端显示 `[WAIT_APPROVAL]`、工具名、参数和说明。用户输入 `approve` 后，终端用 `Command(resume=...)` 恢复图，并把 `approved: true` 注入工具参数；用户输入 `reject <reason>` 则把拒绝结果作为 ToolMessage 返回给模型。

模型服务从当前运行根的 `default_ai_config_dir/config.json` 读取，默认服务名为 `ai_services.default`。发行包默认使用 `plans/config.json`；源码开发仓库可以通过 `plan.config` 或默认运行配置指向开发回归配置。

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

这套 `continue` / `stop` 只属于 `plan>` 管理终端。AI 终端通过 `run_plan` 或 `run_debug_plan` 运行到 `manual_confirm` 或运行后检查时，会注入 AI 模式确认 handler：确认提示显示在 `ai>` 对话中，用户可以自然语言回复，终端用模型分类和本地兜底判断为继续、停止或不明确。不明确时不会恢复 plan，会继续要求用户澄清。

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
- `inspect_web_page`：使用 Playwright 真实打开 URL 或本地 HTML，返回受限 DOM 摘要、正文预览、表单、输入框、按钮、链接、表格以及登录/验证信号。AI 为真实网站创建 plan 前必须优先调用它，不能只根据用户文字猜 selector；如果页面需要登录、验证码、二次验证或权限确认，工具只报告证据和需要用户处理的状态。
- `read_plan_package`
- `create_plan_package`
- `write_plan_package_file`：已完成新建 plan 包阶段的受控写入，只能写 `plan.json`、`config.json`、`docs/**`、`resources/**` 和 `sub-plans/*-plan.json`，拒绝 `output/`、`.keygen/`、缓存、pyc 和 egg-info 路径。
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

新建 plan 包可以通过受控工具直接写入白名单文件。已有原始 plan 的修复必须形成可读补丁，并经过用户确认。
所有修复候选必须先落到当前 debug workspace 的 `injected-plan/`，再由 `generate_debug_patch` 生成补丁。

结构化工具也可以直接从 CLI 调用，便于脚本、CI 和回归验证：

```powershell
python .\main.py tool list
python .\main.py tool check
python .\main.py self-check ai-terminal
python .\main.py self-check ai-tools
python .\main.py tool schema validate_plan
python .\main.py tool call list_plan_packages --args-json '{"filter_text":"ai"}'
```

`apply_debug_patch_after_approval` 有双重保护：AI 终端通过 `HumanInTheLoopMiddleware` 在工具执行前中断，只有用户在终端输入 `approve` 后才会通过 `Command(resume=...)` 恢复；工具自身仍要求参数包含 `approved: true`，避免绕过终端审批直接调用。

AI 终端渐进式文本搜索只支持 `ripgrep` 的 `rg` 命令。缺失时必须先安装 `ripgrep`，或经用户确认后由助手执行 PowerShell 全局安装命令；工具层不提供 Windows 内置搜索兜底。

`self-check ai-tools` 不调用真实模型，但会真实构建 LangChain `StructuredTool`、验证共享 Pydantic schema 绑定、通过工具 invoke 执行 `validate_plan`，并确认受保护工具在没有 HITL approve resume 时被拒绝。

`self-check ai-terminal` 不调用真实模型，用本地夹具验证会话摘要、`resume` 选择器、常用命令流、压缩归档、图片附件 metadata 和 base64 redaction。

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

chat completions streaming 解析有独立本地回归入口 `python .\main.py self-check ai-stream`，用于在不访问模型服务的情况下验证 chunk、reasoning chunk 忽略、SDK 对象和空流拒绝逻辑。

真实模型服务只保存在本机运行根配置中；需要分发或提交的示例配置不放真实密钥。

## 设计结论

- CLI 是唯一操作入口。
- 管理终端负责确定性控制。
- AI 终端负责 plan 级协作。
- 交互式执行器负责事件流和命令队列。
- LangGraph 用于 AI 终端，不接管浏览器执行。
- 专项 AI 是受控数据处理组件，不参与 plan 管理。
