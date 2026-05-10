# AGENTS.md

## 项目定位

这是一个基于 Python + Playwright 的 JSON 编排自动化内核。入口是 `main.py`，核心代码在 `src/keygen_automation/`，执行器读取 JSON plan 后按步骤驱动浏览器、变量、断言、文件读写、控制流组件和受控专项 AI 组件。

## Windows Shell 默认约定

- 本项目默认运行在 Windows 环境。
- 交互命令优先使用 PowerShell 7 (`pwsh`) 语法。
- 给用户示例命令时默认使用 PowerShell 写法，不假设 bash、zsh、sh、WSL 或 cmd.exe。
- 如果 shell 行为会影响结果，先用 `$PSVersionTable.PSVersion`、`$PSHOME` 或 `$env:ComSpec` 确认环境。

## 目录职责

- `main.py`: CLI 入口，负责加载 `plan.json` 并执行。
- `src/keygen_automation/`: 自动化执行内核，修改功能逻辑优先从这里入手。
- `handbook/`: 唯一教程来源；新增或变更动作组件时，必须同步补充对应手册。
- `plans/`: 对外参考的最小 plan 包示例；`plans/config.json` 是公开示例 plan 的集合级配置。
- `test-plans/`: 项目真实自动化 plan 包。
- `docs/`: 架构、功能设计、计划、缺陷和重构记录。
- `test-plans/config.json`: 项目测试 plan 的集合级共享配置，可放测试计划共用变量。
- `.keygen/`: 本地 AI 终端 checkpoint 和运行状态，不应提交。
- `plans/**/output/` 和 `test-plans/**/output/`: plan 的运行输出，不应提交。

## 常用命令

```powershell
python -m pip install -e .
python -m playwright install chromium
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
- AI 终端使用 `langchain.agents.create_agent`、LangChain `StructuredTool`、`HumanInTheLoopMiddleware` 和 LangGraph checkpoint；会话状态放在本地 `.keygen/ai-terminal-checkpoints.sqlite`，可通过 `python .\main.py ai --thread <id>` 恢复。
- AI 终端线程状态包含 `current_plan_path`、`current_debug_workspace` 和 `latest_output_dir`，由 `use`、`workspace`、`run_context` 命令和工具返回自动维护，并通过 middleware 注入模型上下文。
- AI 调试修复必须先把原始 plan 包复制到当前 plan 的 `output/debug/<run>/source-copy/`，再在 `output/debug/<run>/injected-plan/` 注入日志、截图、变量落盘或人工确认；修复候选只能写入 `injected-plan/`、`notes.md` 或 `report.md`，确认问题后只把最小补丁应用回原始 plan。
- selector 自动修复必须保守：没有明确用户提示或候选分数接近时，只能返回候选和歧义原因，不能自动写入 `injected-plan/`。
- 专项 AI 统一使用 `ai` action，并通过 `type` 区分 `connectivity`、`extract_data`、`classify_text`、`transform_data`、`summarize_text`；必须有固定输入、固定输出 schema、固定系统提示词和 `output/ai/` 调试产物。
- 执行链路里只允许受控专项 `ai` action；开放式聊天能力只能存在于 plan 级 AI 终端。
- `test-plans/config.json` 可以保存用户主动提供的临时 AI 测试服务和密钥，用于真实 AI 场景回归；除非用户明确要求，不要删除或迁移这段配置。
- 新增动作组件时，同步更新 `src/keygen_automation/actions.py` 相关执行逻辑、`handbook/<action>.md`、`handbook/README.md` 和必要的 `test-plans/` 示例。
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
