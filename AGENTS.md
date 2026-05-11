# AGENTS.md

## 项目定位

这是一个基于 Python + Playwright 的 JSON 编排自动化内核。入口是 `main.py`，核心代码在 `src/ai_automate_contro/`，执行器读取 JSON plan 后按步骤驱动浏览器、变量、断言、文件读写、控制流组件和受控专项 AI 组件。

## Windows Shell 默认约定

- 本项目默认运行在 Windows 环境。
- 交互命令优先使用 PowerShell 7 (`pwsh`) 语法。
- 给用户示例命令时默认使用 PowerShell 写法，不假设 bash、zsh、sh、WSL 或 cmd.exe。
- 如果 shell 行为会影响结果，先用 `$PSVersionTable.PSVersion`、`$PSHOME` 或 `$env:ComSpec` 确认环境。

## 目录职责

- `main.py`: 极薄 CLI 启动入口，负责把项目 `src/` 加入导入路径并交给应用层分发。
- `src/ai_automate_contro/app/`: CLI 参数解析、一次性命令分发和交互式管理终端。
- `src/ai_automate_contro/engine/`: plan 执行器、动作运行时、浏览器会话、条件和模板。
- `src/ai_automate_contro/plans/`: plan 加载、校验、包发现、配置、输出报告和产物读取。
- `src/ai_automate_contro/ai/`: 受控专项 AI action、plan 级 AI 终端、LangChain 工具和工具 schema。
- `src/ai_automate_contro/debug/`: debug workspace、patch 生成和补丁应用。
- `src/ai_automate_contro/support/`: 日志和通用工具函数。
- `handbook/`: 唯一教程来源；新增或变更动作组件时，必须同步补充对应手册。
- `plans/`: 对外参考的最小 plan 包示例；`plans/config.json` 是公开示例 plan 的集合级配置。
- `test-plans/`: 项目真实自动化 plan 包。
- `docs/`: 架构、功能设计、计划、缺陷和重构记录。
- `test-plans/config.json`: 项目测试 plan 的集合级共享配置，可放测试计划共用变量。
- `.keygen/`: 本地 AI 终端 checkpoint、会话归档、图片附件和运行状态，不应提交。
- `plans/**/output/` 和 `test-plans/**/output/`: plan 的运行输出，不应提交。

## 常用命令

```powershell
python -m pip install -e .
winget install --id BurntSushi.ripgrep.MSVC -e
rg --version
python -m playwright install chromium
python .\main.py self-check ai-stream
python .\main.py self-check ai-terminal
python .\main.py self-check ai-tools
python .\main.py plan run --file .\plans\minimal-browser-plan\plan.json
python .\main.py plan run --file .\test-plans\basic\fill-system-account\plan.json
```

项目采用 `src/` 布局。IDE 未识别导入时，优先把 `src` 标记为 Sources Root，或运行 `python -m pip install -e .` 安装为 editable 包。

## 开发规则

- 优先保持 JSON 计划格式、动作命名和现有字段风格一致。
- 一个 plan 包代表一个独立需求；主入口固定命名为 `plan.json`。
- `plan.json` 是最小可执行单元，可以通过 `run_sub_plan` 调用同包内的 `sub-plans/*-plan.json` 子计划。
- 子计划只能放在当前 plan 包的 `sub-plans/` 目录下，文件名使用 kebab-case 并以 `-plan.json` 结尾；顺序敏感时可使用 `01-xxx-plan.json`。
- `test-plans/` 下面直接按类别放 plan 包，不要再增加 `plans/`、`suites/`、`workspaces/` 中间层。
- 集合级 plan 配置固定放在 `plans/config.json` 或 `test-plans/config.json`；局部 plan 配置固定放在当前 plan 包根目录的 `config.json`，且局部配置优先。
- 禁止让一个主 `plan.json` 引用另一个主 `plan.json`，不同需求包之间保持独立。
- 运行产物必须写入当前 plan 包的 `output/` 目录；输出动作的配置路径是相对于 `output/` 的路径，不能以 `output/` 开头。截图、录屏、下载、HTML、JSON、CSV、TXT、storage state、失败截图、失败 HTML 和失败页面状态都不能写到源码、`resources/` 或仓库其他位置。
- 参数级别一致的组件必须收敛为单个 action，并通过 `type` 区分具体操作，例如 `navigate`、`page`、`element`、`wait`、`extract`、`assert`、`capture`、`read`、`write`。
- 只有参数结构或执行生命周期无法统一时才新增独立组件，例如 `open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`。
- `write` 统一使用 `value` 表示要写出的内容；`type: variables` 不需要 `value`。
- `read` 统一使用 `path`、`type`、`save_as`，资源输入优先放在当前 plan 包 `resources/`。
- AI 终端属于 plan 级能力，用于创建、管理、运行、调试、修复和报告 plan，不允许作为普通 plan action 写入 `steps`。
- AI 终端使用 `langchain.agents.create_agent`、LangChain `StructuredTool`、显式 Pydantic 工具参数模型、`HumanInTheLoopMiddleware`、`SummarizationMiddleware` 和 LangGraph checkpoint；会话状态放在本地 `.keygen/ai-terminal-checkpoints.sqlite`，可通过 `python .\main.py ai --thread <id>` 恢复，进入后可用 `/sessions` 查询会话、`/resume <id-or-index>` 恢复会话、`/new` 开新会话、`/status` 查看状态、`/compress` 手动压缩会话。
- AI 终端、LangChain `StructuredTool` 和 `python .\main.py tool call` 必须共享同一套 Pydantic 工具参数模型，避免 CLI 与 AI 终端出现两套参数规则。
- 新增 AI 终端工具时，必须在 `src/ai_automate_contro/ai/tool_schemas.py` 新增显式 Pydantic 参数模型，并在 `src/ai_automate_contro/ai/terminal_tool_registry.py` 的 `AI_TERMINAL_TOOL_SPECS` 单表登记处理函数、参数模型、描述、是否需要 `project_root` 和是否受保护，然后运行 `python .\main.py tool check` 和 `python .\main.py self-check ai-tools`。
- AI 终端线程状态包含 `current_plan_path`、`current_debug_workspace` 和 `latest_output_dir`，由 `use`、`workspace`、`run_context` 命令和工具返回自动维护，并通过 middleware 注入模型上下文。
- AI 调试修复必须先把原始 plan 包复制到当前 plan 的 `output/debug/<run>/source-copy/`，再在 `output/debug/<run>/injected-plan/` 注入日志、截图、变量落盘或人工确认；修复候选只能写入 `injected-plan/`、`notes.md` 或 `report.md`，确认问题后只把最小补丁应用回原始 plan。
- selector 自动修复必须保守：没有明确用户提示或候选分数接近时，只能返回候选和歧义原因，不能自动写入 `injected-plan/`。
- 专项 AI 统一使用 `ai` action，并通过 `type` 区分 `connectivity`、`extract_data`、`classify_text`、`transform_data`、`summarize_text`；必须有固定输入、固定输出 schema、固定系统提示词和 `output/ai/` 调试产物。
- 用户提供的 AI 模型服务报错、欠费、503、协议不兼容或返回不符合 schema 时，直接报告错误，不做自动降级、自动换格式、手动重试或服务兼容兜底；SDK/LangChain 自身的传输重试可以保留或通过配置显式控制。
- AI 终端和专项 AI 请求必须遵循 OpenAI-compatible 协议。不要把自定义上下文、事件、thread metadata、附件 metadata 或项目内部字段塞进模型请求体；AI 终端上下文只能作为普通 system message 文本注入，图片只能在模型调用前转换成标准 `content: [{type: "text"}, {type: "image_url"}]`，工具调用使用 LangChain/OpenAI 原生 `tool_calls`。
- AI 终端上下文只保存当前 plan、当前 debug workspace、最近输出目录、最近压缩摘要路径和归档路径等摘要状态；自动压缩按 128k token 标准在约 64k tokens 触发，并把完整消息归档到 `.keygen/ai-terminal-sessions/<thread>/compressions/`。不要把完整 `run.log`、`events.jsonl`、`commands.jsonl` 或大型产物一股脑塞进模型上下文。文本读取必须渐进式：先看结构/路径，再用 `grep_project_text` 通过 `rg` 定位关键词，最后用 `read_project_file_slice` 或小范围 artifact 读取拿必要行段。
- AI 终端图片输入主路径是在交互式输入行按 `Alt+V` 或 `Ctrl+V` 从剪贴板粘贴图片，终端插入 `[Image #n]` 占位后用户继续输入文字；如果图片已经保存成文件，只保留 `image <image-path>` 作为兜底入口。图片附件落盘到 `.keygen/ai-terminal-sessions/<thread>/attachments/`，发送给模型时转换为 data URL，发送成功后清空，模型服务报错时保留以便用户重试。不要把 base64 图片内容写入源码、plan、日志或文档。
- AI 终端文本搜索只支持 `ripgrep` 的 `rg` 命令；缺失时必须提示用户安装，或在用户确认后帮助执行 `winget install --id BurntSushi.ripgrep.MSVC -e`，不能使用 Windows 内置搜索兜底。
- 修改 AI 终端会话、压缩、图片附件或上下文注入时，必须运行 `python .\main.py self-check ai-terminal`。
- 修改专项 AI streaming 解析时，必须运行 `python .\main.py self-check ai-stream`；真实服务回归仍使用 `test-plans/ai/controlled-text/plan.json`。
- 执行链路里只允许受控专项 `ai` action；开放式聊天能力只能存在于 plan 级 AI 终端。
- `test-plans/config.json` 可以保存用户主动提供的临时 AI 测试服务和密钥，用于真实 AI 场景回归；除非用户明确要求，不要删除或迁移这段配置。
- 新增动作组件时，同步更新 `src/ai_automate_contro/engine/actions/` 下对应行为模块和 action 注册出口、`handbook/<action>.md`、`handbook/README.md` 和必要的 `test-plans/` 示例。
- 不为了文件大小本身拆分模块；单文件未超过约 1000 行且职责清晰时优先保持内聚，只有职责边界、风险隔离、测试可读性或长期维护收益明确时才拆。
- 修改计划加载、变量渲染、条件、循环等共享逻辑时，检查已有示例是否仍能运行。
- 不要把真实账号、令牌、Cookie、storage state、接口密钥、运行截图或执行日志写入仓库。
- `plans/**/output/`、`test-plans/**/output/`、`.keygen/`、`__pycache__/`、IDE 配置和本地密钥配置属于本地产物，应由 `.gitignore` 过滤。

## 验证要求

- 对窄范围代码改动，至少运行一个相关示例计划。
- 对动作组件或执行器改动，优先运行覆盖该动作的 `test-plans/` 示例。
- 若验证依赖浏览器，需要先确保已执行 `python -m playwright install chromium`。

## Git 注意事项

- 允许提交源码、文档、手册和可复现示例。
- 不提交任何 plan 包下的 `output/` 目录。
- 不再使用根目录 `config/` 存放 plan 运行配置；共享配置放到对应 plan 集合的 `config.json`。
- 如果历史上已经跟踪了应忽略文件，`.gitignore` 不会自动移除它们，需要单独从索引中移除。
