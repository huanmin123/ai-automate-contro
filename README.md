# keygen-openai-account

这是一个基于 Playwright + Python 的 JSON 编排自动化内核。用户和 AI 通过维护 plan 包描述流程，执行器读取 `plan.json` 后按顺序驱动浏览器、变量、断言、文件读写、控制流和受控专项 AI 组件。

`handbook/` 是唯一组件手册入口；`docs/` 只记录架构、设计、开发和验证说明。

## 快速开始

开发环境默认使用 Windows + PowerShell 7 + 全局或用户级 Python。项目不要求在仓库根目录创建 `.venv`；本机已有的 `.venv/` 只算临时开发环境，不作为文档、脚本或 plan 的固定路径。

```powershell
python -m pip install -e .
python -m playwright install chromium
python .\main.py
```

项目使用 `src/` 布局，声明支持 Python 3.11 及以上，推荐 Python 3.13。开发环境建议执行 `python -m pip install -e .`，由 `pyproject.toml` 统一安装 Playwright、Pydantic、LangChain/LangGraph、OpenAI SDK 等依赖；也可以在 IDE 里把 `src` 标记为 Sources Root。

默认入口会打开 Textual AI 客户端。直接描述需求，客户端会把用户消息、AI 回复、工具进度和审批状态分块显示；确定性脚本入口仍使用 CLI 子命令：

```powershell
python .\main.py plan validate --file .\plans\minimal-browser-plan\plan.json
python .\main.py plan run --file .\plans\minimal-browser-plan\plan.json
python .\main.py tool check
```

创建新的 plan 包模板：

```powershell
python .\main.py plan create --path .\plans\new-plan --name "New Plan"
```

进入 AI 终端：

```powershell
python .\main.py ai
python .\main.py ai --thread login-debug
```

## 先看哪里

- 组件手册入口：`.\handbook\README.md`
- 计划结构说明：`.\handbook\计划结构.md`
- 最小计划示例：`.\handbook\第一个计划示例.md`
- 根目录参考样例：`.\plans\minimal-browser-plan\`
- 开发验证说明：`.\docs\develop\测试与验证说明.md`

## 当前目录

- `main.py`: 极薄命令行启动入口，负责把项目 `src/` 加入导入路径并交给应用层分发。
- `src/ai_automate_contro/app/`: CLI 参数解析和一次性命令分发。
- `src/ai_automate_contro/client/`: Textual AI-first 交互客户端。
- `src/ai_automate_contro/engine/`: plan 执行器、动作运行时、浏览器会话、条件和模板。
- `src/ai_automate_contro/plans/`: plan 加载、校验、包发现、配置、输出报告和产物读取。
- `src/ai_automate_contro/ai/`: 受控专项 AI action、plan 级 AI 终端、LangChain 工具和工具 schema。
- `src/ai_automate_contro/debug/`: debug workspace、patch 生成和补丁应用。
- `src/ai_automate_contro/support/`: 日志和通用工具函数。
- `plans/`: 默认示例和发行包 plan 工作区。
- `test-plans/`: 源码开发和回归测试夹具；发行包不携带。
- `handbook/`: 给用户和 AI 阅读的组件手册。
- `docs/`: 架构、设计、开发、验证和演进记录。

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
- `resources/`: 本需求独占输入资源。
- `output/`: 本需求运行输出，由 Git 忽略。截图、录屏、下载、日志、报告和运行中间产物都必须写在这里。
- `docs/`: 本需求说明文档。

不同需求的 `plan.json` 之间不能互相引用。需要批量执行时，优先由外部脚本扫描多个 plan 包。

## 运行根与配置

运行根可以是源码仓库，也可以是发行包目录 `out\ai-automate-contro`。`plan.config` 控制运行根下的手册和 plan 集合：

```json
{
  "handbook_path": "handbook",
  "plan_roots": ["plans"],
  "default_ai_config_dir": "plans"
}
```

没有 `plan.config` 的源码开发仓库会默认发现 `plans/` 和 `test-plans/`，并优先使用测试配置目录服务本地回归。发行包会带 `plan.config`，默认只使用 exe 同目录下的 `plans/`。

AI 终端或工具创建 plan 且没有明确目录时，会使用当前运行根的第一个 `plan_roots`。配置字段详见 `handbook/reference/config.md`。

## AI 客户端与一次性命令

- 默认运行 `python .\main.py` 会进入 Textual AI 客户端；`python .\main.py ai` 进入同一客户端并可指定 `--thread`。
- 用户输入显示为灰色块，AI 回复直接输出内容，不再出现 `plan>`、`ai>`、`AI>` 或 `你>` 前缀。
- 工具调研、执行进度、审批等待和错误会作为独立消息块显示，避免长时间只有空白等待。
- 输入区是无边框灰底多行 composer：Enter 发送，Ctrl+J 换行，高度随内容在 1 到 6 行内增长。
- 输入 `/` 会打开命令候选，Up / Down 选择，Tab 或 Enter 补全；可用 `/details` 切换工具细节，`/export [path]` 导出当前可见对话。
- `python .\main.py ai ask --message "<text>" --json` 用于脚本化 AI 回归。
- 确定性命令 `python .\main.py plan ...`、`python .\main.py tool ...` 和 `python .\main.py self-check ...` 保留给脚本、打包 smoke test 和可重复验证。

## AI 终端

- AI 终端使用 `langchain.agents.create_agent`、LangChain `StructuredTool`、显式 Pydantic schema 和 LangGraph checkpoint。
- 模型服务从当前运行根的 `default_ai_config_dir/config.json` 读取，服务名默认是 `ai_services.default`。
- 会话状态保存在本地 `.keygen/ai-terminal-checkpoints.sqlite`，会话附件和压缩归档保存在 `.keygen/ai-terminal-sessions/`。
- 线程级上下文会在选择、运行和调试 plan 时自动更新；工具返回 plan、debug workspace 或 output 时也会自动更新上下文。
- Textual 客户端保持输入区可用：AI 正在回复或运行工具时，普通输入会进入队列，当前轮完成后继续处理。
- AI 为真实网站创建最终 plan 前必须先用自动化跑通流程证据：先用 `inspect_web_page` 获取入口证据；涉及登录、验证码、后台菜单或动态页面时，继续创建并运行 `open_browser.headed=true` 的探索 plan。需要用户介入时，用 `manual_confirm` 停在同一个 Playwright 浏览器窗口里交接，不要求用户另开本机浏览器。
- 一次性 plan run 遇到 `manual_confirm` 时仍使用 `continue` / `stop`；AI 通过工具运行到确认点时，确认会回到当前 Textual 对话里，用自然语言判断继续或停止。
- AI 调试修复只能先写入 debug workspace 的 `injected-plan/`、`notes.md` 或 `report.md`，再生成 patch。
- 应用补丁必须走 `apply_debug_patch_after_approval`，并等待用户 `/approve`。
- 文本读取必须渐进式：先看结构，再 `grep_project_text` 定位，最后 `read_project_file_slice` 读取小范围行段。

常用检查：

```powershell
python .\main.py tool list
python .\main.py tool check
python .\main.py self-check textual-client
python .\main.py self-check ai-stream
python .\main.py self-check ai-terminal
python .\main.py self-check ai-tools
```

## 支持的动作组件

具体字段说明看 `handbook/README.md` 的按需读取地图。常见同族动作已按参数结构收敛：

- `navigate`: 通过 `type` 执行 `goto`、`refresh`、`back`、`forward`
- `page`: 通过 `type` 执行 `open`、`switch`、`close`
- `element`: 通过 `type` 执行 `click`、`fill`、`hover`、`select` 等元素操作
- `wait` / `assert` / `extract`: 通过 `type` 区分等待、断言和提取类型
- `capture`: 通过 `type` 保存截图、HTML、storage state
- `read`: 通过 `type` 读取 `json`、`text`、`csv`
- `write`: 通过 `type` 写出 `json`、`text`、`csv`、`variables`
- `ai`: 通过 `type` 执行受控专项 AI 任务，例如连通性、文本抽取、分类、转换和摘要

`open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download` 这类参数或生命周期明显不同的能力保持独立组件。

## 边界

- AI 终端是 plan 级能力，不作为普通 `steps` 动作存在。
- `ai` 是受控专项组件，只处理输入输出明确的数据任务，并强制把调试产物写入当前 plan 包 `output/ai/`。
- 不要把真实账号、密钥、Cookie、storage state、运行截图或执行日志写入仓库。
- `test-plans/`、`.keygen/` 和各 plan 包 `output/` 都是本地开发/运行产物边界，发行包和用户 plan 语义以 `plan.config` 为准。
