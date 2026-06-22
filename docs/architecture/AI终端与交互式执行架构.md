# AI 终端与交互式执行架构

## 背景

自动化框架的核心是 plan 包。用户真正需要 AI 参与的地方，不是让模型混入每一步浏览器动作，而是让 AI 帮助维护 plan：

- 创建 plan。
- 管理 plan 配置和文档。
- 运行与观察 plan。
- 分析失败。
- 生成修复补丁。
- 产出报告。

因此交互入口改为 AI-first Textual 客户端。默认运行 `python .\main.py` 或 `python .\main.py ai` 都进入同一套对话式客户端；无 AI 的 plan 控制拆到独立 `cplan` CLI，服务脚本、回归和打包 smoke test 不再通过 Textual 客户端操作 plan。

## 总体分层

```text
CLI
├── Textual AI Client
│   ├── 用户消息灰底块
│   ├── AI 回复正文块
│   ├── 工具进度块
│   ├── 审批/错误块
│   └── 多行 composer
│
├── AI 诊断/tool/self-check 命令
│   └── AI 工具注册表、模型连通性和客户端自检
│
├── cplan CLI
│   ├── 创建、校验和运行 plan
│   ├── 查看状态、日志和输出
│   └── 调试工作区创建、注入和补丁应用
│
└── AI Backend
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

## AI-first 客户端与确定性命令

Textual 客户端是面向自然语言的默认入口。它不再展示 `plan>`、`ai>`、`AI>` 或 `你>` 前缀，而是把用户消息、AI 回复、工具进度、系统输出、审批和错误分别渲染成块。工具开始和完成会更新同一个工具块，审批和错误不混入普通工具输出。输入区是灰底无边框的多行 composer，Enter 发送；`Shift+Enter`、`Alt+Enter` 或行尾 `\` 后 Enter 插入换行；多行粘贴保留换行。高度随内容在 4 到 8 行内增长。AI 忙碌时继续发送会进入队列；按 Esc 会中断当前 AI/plan，已有队列时把排队内容合并为下一轮介入消息并优先处理。

客户端采用主流 agent CLI/TUI 的命令发现方式：在输入行输入 `/` 会打开常用命令候选，继续输入前缀实时过滤，Up / Down 选择候选，Tab 或 Enter 补全命令；带参数的命令继续由 Enter 发送。候选只展示 AI 会话入口，常用命令收敛为 `/status`、`/plan`、`/sessions`、`/resume`、`/new`、`/image`、`/approve`、`/reject`、`/export`、`/copy-last`、`/clear` 和 `/exit`。`/plan` 表示 AI 当前工作计划，不是 plan 包管理命令；无 AI 的 list/create/validate/run/schedule/debug 统一由 `cplan` 处理。命令入口不再提供重复别名；模型连通性诊断使用一次性命令 `python .\main.py ai check --json`。

底部状态条持续显示当前服务、thread、AI 上下文里的 plan/debug workspace/最近 output、排队数量、审批状态和待发送图片数量。plan 的确定性管理状态不再塞进 Textual 客户端。

确定性入口不走交互 UI，直接使用 CLI 子命令：

- `python .\cplan.py create --path .\plans\demo`
- `python .\cplan.py validate --file .\plans\demo\plan.json`
- `python .\cplan.py run --file .\plans\demo\plan.json`
- `python .\main.py tool list`
- `python .\main.py tool check`
- `python .\main.py self-check textual-client`
- `python .\main.py self-check ai-terminal`
- `python .\cplan.py self-check runtime`
- `python .\cplan.py self-check browser-components`
- `python .\main.py ai ask --message "<text>" --json`

这条边界避免旧交互模式和新 AI 客户端混在一起：自然语言进 Textual 客户端，非 AI 的 plan 操作进 `cplan`，AI 工具诊断仍留在 `main.py`/`aic`。

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

AI 终端不直接绕过确定性 plan 管理能力。它通过结构化工具调用校验、运行、调试和导出能力；无 AI 的确定性 plan 管理统一走 `cplan`。Textual 客户端只负责对话展示、工具进度、工作计划、队列、审批和错误状态，不承载固定 plan 管理命令。

当前 AI 客户端入口：

```powershell
python .\main.py
python .\main.py ai
python .\main.py ai --thread login-debug
```

当前交互客户端使用 Textual 渲染消息块、工具进度、上下文状态条和多行 composer，并用 `langchain.agents.create_agent` 编排模型与工具循环。AITerminal 向客户端暴露结构化事件轮次和轻量状态快照，Textual 后端只消费事件，不再维护旧兼容终端模式。项目工具通过 LangChain `StructuredTool` 暴露给模型，每个工具使用显式 Pydantic 参数模型定义输入 schema；CLI 的 `tool call` 入口也复用同一套 schema 校验。模型使用原生 `tool_calls`，工具执行由 LangChain/LangGraph agent 图处理，不再使用自定义 JSON 工具调用协议，也不再通过运行时动态拼装工具 schema。

模型请求边界保持 OpenAI-compatible：AI 终端不向模型请求体塞自定义事件、thread metadata、附件 metadata 或项目内部上下文字段。线程上下文在模型调用前作为普通 system message 文本追加；图片附件在发送前临时转换为 Chat Completions 兼容的 `content` 列表，形态为 `text` 加 `image_url`；工具调用交给 LangChain/OpenAI 原生 `tool_calls`。本地 checkpoint、会话索引和附件 metadata 只服务恢复与归档，不作为自定义协议字段发给模型厂商。

会话状态由 LangGraph `SqliteSaver` 持久化到本地 `.keygen/ai-terminal-checkpoints.sqlite`，用户可以用 `--thread <id>` 进入或恢复同一个 AI 会话。Textual 客户端面向用户只暴露统一 `/status`、`/sessions [limit|all]`、`/resume <thread-id-or-index>` 和 `/new` 这几个会话入口。会话列表摘要维护在 `.keygen/ai-terminal-sessions/index.json`，只保存线程、时间、计数、最近消息预览和上下文路径摘要；`/sessions` 不打印完整消息历史。`.keygen/` 属于本地运行状态，由 Git 忽略。

AI 客户端回合由后台 worker 执行，输入区保持可用。用户发送自然语言后，LangGraph `stream_mode=["messages", "values"]` 持续把 AI token 转成客户端事件；期间继续发送的普通消息进入队列，当前轮完成后继续处理。服务端 503、欠费、协议不兼容或 schema 错误会直接展示，不做本地兼容兜底。

真实回归中，线程 `real-tool-regression-validate-plan` 已确认模型生成 `tool_calls=validate_plan`，工具结果以 `ToolMessage` 返回 `ok=true`，并由 `SqliteSaver` 保存同一线程的消息与工具调用历史。

AI 终端还有线程级业务上下文状态，和消息历史一起进入 LangGraph checkpoint：

- `current_plan_path`
- `current_debug_workspace`
- `latest_output_dir`
- `latest_compression_summary_path`
- `latest_compression_messages_path`
- `latest_compression_archive_dir`

线程状态会在选择、运行、调试 plan 或结构化工具返回 plan、debug workspace、run output 时自动更新；Textual 客户端通过统一状态快照展示 `/status`，并保留 `/new`、`/sessions` 和 `/resume` 管理会话。模型调用前，`AITerminalContextMiddleware` 会把这些上下文追加到 system message，让用户可以说“当前 plan”“最近失败输出”“这个 debug workspace”，不必每次重复路径。

长会话压缩使用 LangChain `SummarizationMiddleware`。项目按 128k token 作为通用上下文标准，约 64k tokens 自动触发压缩，压缩后保留约 32k tokens 的近期上下文；完整消息、摘要和 manifest 归档到 `.keygen/ai-terminal-sessions/<thread>/compressions/`，实时模型上下文只保留摘要和归档位置。摘要生成依赖当前模型服务，服务侧报错会直接暴露给用户，不做项目内兼容兜底。

图片输入是客户端侧能力，不进入普通 plan action。如果图片已经保存成文件，可用 `/image <image-path>` 加入下一条消息。图片复制到 `.keygen/ai-terminal-sessions/<thread>/attachments/`，checkpoint 和压缩归档只保存附件 metadata，发送时临时转换成 LangChain `HumanMessage` 的多模态 content list，并移除内部 metadata。发送成功后清空 pending attachments；如果模型服务报错，错误直接显示给用户，附件保留以便重试。剪贴板图片粘贴会在 Textual 客户端内实现，不要求用户切到本机浏览器或其他入口。

补丁应用审批使用 LangChain `HumanInTheLoopMiddleware`。当模型请求 `apply_debug_patch_after_approval` 时，Agent 图会在工具执行前中断并写入 checkpoint，Textual 客户端显示独立审批块，包含工具名、参数和说明。用户输入 `/approve` 后，终端用 `Command(resume=...)` 恢复图，并把 `approved: true` 注入工具参数；用户输入 `/reject <reason>` 则把拒绝结果作为 ToolMessage 返回给模型。

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

Textual 客户端、人类用户和 AI 后端都只读事件流，不直接读执行器内部状态。

第一版同时写入 `state.json` 作为稳定状态快照。Textual 客户端、外部脚本和后续 AI 后端优先读取该文件判断当前 run 是否处于 `running`、`waiting`、`passed` 或 `failed`。

每次运行还会生成 `report.md`，和 `result.json`、`run.log`、`events.jsonl` 放在同一个 run 目录。报告只汇总状态、路径、错误、失败截图、失败 HTML、失败页面状态、下载和标准运行文件，不展开变量内容，便于 AI 终端和人工排查快速读取。

### 命令队列

当前执行器对外只暴露确定性的等待恢复和中断能力：

- 等待态继续。
- 等待态停止。
- 请求中断当前运行。
- 查询运行状态和事件产物。

变量覆盖、配置修改和调试注入不作为运行中的自由命令处理；无 AI 场景通过 `cplan` 的固定命令执行，AI 场景通过结构化工具先生成或修复 plan，再运行。

命令必须可审计，写入运行日志。

等待态 run 的人工确认现在分两条路：`cplan run` 在当前命令行等待确认；AI 工具运行到确认点时，Textual 客户端在当前对话里请求用户自然语言确认，并把恢复结果写入运行事件。

### 人工交互

用户明确同意并提供账号密码时，AI 可以协助填写登录字段或生成使用变量/资源的登录步骤。验证码、短信/邮箱验证、二次验证、权限确认等安全门槛只能按页面正常流程处理：能用用户提供的一次性信息就输入，不能破解、绕过或代解；自动化尝试失败、缺少外部信息或风险不明确时，plan 使用人工等待动作在同一个可见 Playwright 浏览器里交接：

```json
{
  "action": "manual_confirm",
  "prompt": "请在当前自动化浏览器窗口中完成验证码或二次验证，然后回到 Textual 客户端确认继续。"
}
```

Textual 客户端展示独立等待块：

```text
等待审批 请在当前自动化浏览器窗口中完成验证码或二次验证，然后回到 Textual 客户端确认继续。
在当前命令行或 AI 对话里回复继续或停止。
```

AI 客户端通过 `run_plan` 或 `run_debug_plan` 运行到 `manual_confirm` 或运行后检查时，会注入确认 handler：确认提示显示在当前对话中，用户可以自然语言回复，后端用模型分类和本地兜底判断为继续、停止或不明确。不明确时不会恢复 plan，会继续要求用户澄清。无 AI 环境使用 `cplan run`，不进入 Textual 客户端。

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

当前工具清单以 `src/ai_automate_contro/ai/terminal_tool_registry.py` 里的 `AI_TERMINAL_TOOL_SPECS` 为准，也可以用 `python .\main.py tool list` 查看；文档不再维护容易过期的完整静态枚举。工具按职责分为几类：

- plan 包发现、读取、创建、资源导入和受控写入：用于新建 `plan.json`、`config.json`、`docs/**`、`resources/**` 和 `sub-plans/*-plan.json`；用户提供本机输入文件时默认通过导入工具复制到当前 plan 包 `resources/`；拒绝 `output/`、`.keygen/`、缓存、pyc 和 egg-info 路径。
- 真实网页探测和质量门禁：`inspect_web_page` 必须在真实网站最终 plan 前优先使用；`review_plan_quality` 会结合最近探测上下文、用户需求和 plan 内容做门禁。
- 运行、产物和失败分析：运行证据仍留在当前 plan 包 `output/`；用户明确要求 Downloads、桌面或绝对路径时，最终交付通过 `export_local_file` 写出，不要求用户手动复制。
- debug workspace 和补丁：无 AI 人工调试走 `cplan debug-*`；AI 修复先写 `injected-plan/`、`notes.md` 或 `report.md`，生成补丁后再经审批应用。
- 渐进式读取、会话召回和可见计划：文本搜索、文件切片、压缩归档读取和 `update_work_plan` 都属于 AI 终端内部工作流能力，不放入 `cplan`。

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

`apply_debug_patch_after_approval` 有双重保护：AI 终端通过 `HumanInTheLoopMiddleware` 在工具执行前中断，只有用户在终端输入 `/approve` 后才会通过 `Command(resume=...)` 恢复；工具自身仍要求参数包含 `approved: true`，避免绕过终端审批直接调用。

AI 终端渐进式文本搜索只支持 `ripgrep` 的 `rg` 命令。缺失时必须先安装 `ripgrep`，或经用户确认后由助手执行 PowerShell 全局安装命令；工具层不提供 Windows 内置搜索兜底。

`self-check ai-tools` 不调用真实模型，但会真实构建 LangChain `StructuredTool`、验证共享 Pydantic schema 绑定、通过工具 invoke 执行 `validate_plan`，并确认受保护工具在没有 HITL approve resume 时被拒绝。

`self-check ai-terminal` 不调用真实模型，用本地夹具验证会话摘要、`resume` 选择器、常用命令流、压缩归档、图片附件 metadata 和图片 data URL 原文保留。

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

真实模型服务配置按本地调试原文优先处理；示例配置也可以按需要保留真实密钥，工具不做自动脱敏或拒写。

## 设计结论

- `main.py`/`aic` 是 AI-first 入口，`cplan.py`/`cplan` 是无 AI plan 管理入口。
- Textual 客户端负责 AI 对话、工作计划、队列、工具进度、审批和错误显示。
- AI 后端负责 plan 级协作，并通过结构化工具调用确定性能力。
- 执行器负责 plan 运行、等待态、事件流和运行产物。
- LangGraph 用于 AI 终端，不接管浏览器执行。
- 专项 AI 是受控数据处理组件，不参与 plan 管理。
