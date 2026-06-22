# AGENTS.md

## 项目定位

这是一个基于 Python + Playwright 的 JSON 编排自动化内核。AI 入口是 `main.py`/`aic`，无 AI 的 plan 控制入口是 `cplan.py`/`cplan`，核心代码在 `src/ai_automate_contro/`。执行器读取 plan 包后驱动浏览器、变量、断言、文件读写、控制流组件和受控专项 AI 组件。

`AGENTS.md` 只保留项目级入口、目录地图和必须随时遵守的全局约束。具体开发规范、AI 终端规则、验证矩阵和组件细节放在 `docs/` 与 `handbook/`，按任务需要读取，不要把所有规则预加载进上下文。

## 工作原则

- 默认按当前最优方案开发：当前 JSON schema、当前 action 契约、当前 CLI/UI 流程和当前文档规范。除非用户明确要求兼容，否则不保留旧字段、旧命令、旧入口或运行时兼容分支。
- 架构边界、执行模型、action 契约、AI 终端能力或 plan 结构变化时，代码、手册、功能文档和验证说明要同步更新。
- 本项目按本地调试原文优先处理。运行日志、报告、失败现场、截图、HTML、DOM、Cookie、storage state、token、api_key 等本机数据不得自动脱敏、遮罩、摘要化或拒写；是否提交由用户决定。
- 保持 JSON plan、action 命名、参数风格和目录结构一致，不为单个需求引入平行体系。

## Windows Shell 默认约定

- 本项目默认运行在 Windows 环境。
- 交互命令优先使用 PowerShell 7 (`pwsh`) 语法。
- 给用户示例命令时默认使用 PowerShell 写法，不假设 bash、zsh、sh、WSL 或 `cmd.exe`。
- 如果 shell 行为会影响结果，先用 `$PSVersionTable.PSVersion`、`$PSHOME` 或 `$env:ComSpec` 确认环境。

## 文档入口

AI 和维护者应先按任务选择文档，不要一次性读取全部文档：

- [docs/README.md](./docs/README.md): 全局文档地图、任务入口和维护规则。
- [handbook/README.md](./handbook/README.md): plan 与 action 的唯一教程入口；新增或变更 action 时必须同步更新。
- [docs/architecture/架构总览.md](./docs/architecture/架构总览.md): 稳定架构、模块边界和关键流程。
- [docs/develop/AI协作开发规范.md](./docs/develop/AI协作开发规范.md): 详细开发规则、AI 协作规则、资源路径策略和验证矩阵。
- [docs/develop/运行说明.md](./docs/develop/运行说明.md): 本地运行、CLI、自检和常用命令。
- [docs/develop/测试与验证说明.md](./docs/develop/测试与验证说明.md): 按改动范围选择验证方式。
- [docs/develop/AI终端工具开发检查清单.md](./docs/develop/AI终端工具开发检查清单.md): 新增或修改 AI 终端工具时读取。
- [docs/architecture/AI终端与交互式执行架构.md](./docs/architecture/AI终端与交互式执行架构.md)、[docs/architecture/AI终端提示词与上下文策略.md](./docs/architecture/AI终端提示词与上下文策略.md)、[docs/architecture/AI调试修复工作流.md](./docs/architecture/AI调试修复工作流.md): 修改 AI 终端、上下文压缩、图片附件、调试修复时读取。
- [docs/functions/核心功能设计.md](./docs/functions/核心功能设计.md) 和 [docs/functions/AI能力重构设计.md](./docs/functions/AI能力重构设计.md): 功能能力、执行模型和 AI 能力边界。

## 目录职责

- `main.py`: AI-first CLI 启动入口。
- `cplan.py`: 无 AI 的 plan 创建、校验、运行和调试入口。
- `src/ai_automate_contro/app/`: CLI 参数解析和一次性命令分发。
- `src/ai_automate_contro/client/`: Textual AI-first 交互客户端。
- `src/ai_automate_contro/engine/`: plan 执行器、动作运行时、浏览器会话、条件和模板。
- `src/ai_automate_contro/plans/`: plan 加载、校验、包发现、配置、输出报告和产物读取。
- `src/ai_automate_contro/ai/`: 受控专项 AI action、plan 级 AI 终端、LangChain 工具和工具 schema。
- `src/ai_automate_contro/debug/`: debug workspace、patch 生成和补丁应用。
- `src/ai_automate_contro/support/`: 日志和通用工具函数。
- `handbook/`: plan/action 教程和 schema 说明。
- `plans/`: 对外参考的最小 plan 包示例。
- `test-plans/`: 项目真实自动化 plan 包和回归示例。
- `docs/`: 架构、功能设计、计划、缺陷、重构和开发规范。
- `.keygen/`: 本地 AI 终端 checkpoint、会话归档、图片附件和运行状态，不应提交。

## 全局硬约束

- 一个 plan 包代表一个独立需求；主入口固定为 `plan.json`。子计划只能放在当前 plan 包的 `sub-plans/`，通过 `run_sub_plan` 调用。
- 输入资源推荐放入当前 plan 包 `resources/`；读取已生成产物时使用 `output/...`。这是可复现性建议，不是安全拦截规则；用户要求使用本机绝对路径、共享盘、外部工作目录或越出 plan 包的相对路径时，按请求执行。
- plan 内部路径推荐使用 `/`。不要因为路径是 `C:\...`、`D:\...`、`/Users/...`、`/home/...`、UNC 路径或越出 plan 包的相对路径而拒绝读取、上传、stdin、storage state、HAR 或命令工作目录。
- plan action 的运行证据和中间产物必须写入当前 plan 包 `output/`；输出动作的配置路径相对于 `output/`，不能以 `output/` 开头。
- AI 为真实网站、URL、后台页面或网页流程创建最终 plan 前，必须先用自动化跑通流程证据，不能只按用户文字猜 selector。需要用户介入登录、验证码或权限流程时，用同一个 Playwright 浏览器窗口里的 `manual_confirm` 交接。
- AI 终端是 plan 级能力，用于创建、管理、运行、调试、修复和报告 plan；开放式聊天能力不能作为普通 plan action 写入 `steps`。执行链路里只允许受控专项 `ai` action。
- `plans/**/output/`、`test-plans/**/output/`、`.keygen/`、`__pycache__/`、IDE 配置和本地密钥配置属于本地产物，应由 `.gitignore` 过滤，不作为常规提交内容。

## 验证约定

- 只改文档时通常不需要运行代码自检，但要确认链接和文档入口一致。
- 窄范围代码改动至少运行一个相关示例 plan 或对应自检。
- 修改 action、执行器、计划加载、变量渲染、条件或循环等共享逻辑时，优先运行覆盖该能力的 `test-plans/` 示例。
- 修改 AI 终端、Textual 客户端、专项 AI streaming 或 AI 工具时，按 [测试与验证说明](./docs/develop/测试与验证说明.md) 和相关检查清单运行对应 self-check。

## Git 注意事项

- 允许提交源码、文档、手册和可复现示例。
- 不提交任何 plan 包下的 `output/` 目录或 `.keygen/` 本地产物。
- 如果历史上已经跟踪了应忽略文件，`.gitignore` 不会自动移除它们，需要单独从索引中移除。
