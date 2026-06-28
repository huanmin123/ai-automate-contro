# AI协作开发规范

本文承接不适合放进根目录 `AGENTS.md` 的细化规则。`AGENTS.md` 只做轻量入口；当任务涉及开发、AI 终端、plan 结构、资源路径、验证或调试修复时，再按需读取本文和相关专题文档。

## 读取顺序

按任务选择最小必要文档：

- plan 结构、action 写法、字段契约：先读 [handbook/README.md](../../handbook/README.md)，再读对应 action 文档和 [handbook/计划结构.md](../../handbook/计划结构.md)。
- 架构、模块边界、执行模型：读 [architecture/架构总览.md](../architecture/架构总览.md) 和 [functions/核心功能设计.md](../functions/核心功能设计.md)。
- AI 终端、工具、上下文、图片附件、压缩：读 [architecture/AI终端与交互式执行架构.md](../architecture/AI终端与交互式执行架构.md)、[architecture/AI终端提示词与上下文策略.md](../architecture/AI终端提示词与上下文策略.md) 和 [AI终端工具开发检查清单.md](./AI终端工具开发检查清单.md)。
- 调试修复、失败现场、补丁注入：读 [architecture/AI调试修复工作流.md](../architecture/AI调试修复工作流.md)。
- 验证命令、自检范围、浏览器回归：读 [测试与验证说明.md](./测试与验证说明.md) 和 [浏览器组件回归说明.md](./浏览器组件回归说明.md)。

## 通用开发原则

- 默认按当前最优模型推进：当前 JSON schema、当前 action 契约、当前 CLI/UI 流程、当前项目目录约定。
- 除非用户明确要求迁移期兼容，否则实现、文档、补全和帮助只保留当前最优、最新的单一路径。
- 不把旧字段、旧命令、旧别名、旧入口、双读、双写、启动迁移、临时同步或兼容兜底挂进正常运行路径。
- 如果必须处理既有数据或旧结构，记录为明确的一次性离线脚本、重建步骤或例外说明，并写清退出条件和验证证据。
- 新增结构前先读现有文档和代码边界；优先复用现有模块、helper、schema 和示例，不新增平行体系。
- 不为了文件大小本身拆分模块。单文件未超过约 1000 行且职责清晰时优先保持内聚，只有职责边界、风险隔离、测试可读性或长期维护收益明确时才拆。

## 本地调试原文原则

本项目是本地脚本程序，调试证据优先保留原文。

- 运行时代码、AI 终端、工具、日志、报告、归档、失败现场和自检不得自动脱敏、遮罩、替换、隐藏、摘要化或拒绝账号、密码、token、api_key、Cookie、storage state、验证码、请求头、命令、stdout/stderr、截图、HTML、DOM、图片 data URL 等本机数据。
- 不新增“敏感字段掩码”“明文凭据拒写”“危险命令关键词拦截”“本机输入文件因路径不在 plan 包内被拒绝”等安全式防护，除非用户明确要求。
- 用户明确要求把真实数据写入 plan、config、resources、docs、output、`.keygen` 或本机任意路径时，按请求执行，不因为字段看起来敏感而改成环境变量、模板引用、占位符或说明文字。
- Git 是否提交这些内容由用户决定；项目规范只要求 `output/`、`.keygen/`、缓存、pyc、egg-info、IDE 配置和本地密钥配置默认不作为常规提交内容。

## Plan 包与资源路径

- 一个 plan 包代表一个独立需求；主入口固定命名为 `plan.json`。
- `plan.json` 是最小可执行单元，可以通过 `run_sub_plan` 调用同包内的 `sub-plans/*-plan.json`。
- 子计划只能放在当前 plan 包的 `sub-plans/` 目录下，文件名使用 kebab-case 并以 `-plan.json` 结尾；顺序敏感时可使用 `01-xxx-plan.json`。
- `test-plans/` 下面直接按类别放 plan 包，不要再增加 `plans/`、`suites/`、`workspaces/` 中间层。
- 集合级 plan 配置固定放在 `plans/config.json` 或 `test-plans/config.json`；局部配置固定放在当前 plan 包根目录的 `config.json`，且局部配置优先。
- `config.json` 只保存运行配置，不保存 plan 变量；plan 变量写在 `plan.json.variables`。
- 禁止让一个主 `plan.json` 引用另一个主 `plan.json`，不同需求包之间保持独立。

资源路径策略：

- 输入文件默认放在当前 plan 包 `resources/`，读取已生成产物时才使用 `output/...`。
- AI 创建或修改 plan 时，用户给出本机文件路径但没有明确要求长期依赖该路径的，默认先把文件导入当前 plan 包 `resources/`，再在 plan 中引用 `resources/...` 或 `{{resources_file_url}}/...`。
- 不得默认把 `C:\...`、`D:\...`、`/Users/...`、`/home/...`、UNC 路径或其他 plan 包路径写进可复现 plan。
- 只有用户明确要求固定依赖本机路径、共享盘或外部工作目录时才允许例外。例外前必须告知跨机器、跨系统、CI 和团队协作风险，并在当前 plan 包 `docs/` 下记录沟通和决策原因。
- 绝对输入路径、共享盘或越出 plan 包的相对路径允许直接写入对应 step；不需要任何额外审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠；运行时由 `pathlib` 转成本机路径。
- plan action 的运行证据和中间产物必须写入当前 plan 包 `output/` 目录。输出动作的配置路径是相对于 `output/` 的路径，不能以 `output/` 开头。
- 用户明确要求最终交付文件保存到 Downloads、桌面或绝对路径时，AI 终端应在运行成功后用 `export_local_file` 写入或从 `output/` 复制过去，不要求用户手动复制。

## Action 与组件边界

- 优先保持 JSON 计划格式、动作命名和现有字段风格一致。
- 新建或大改 plan 前必须明确 `automation_type`，只能是 `browser` 或 `desktop`。不明确时先问用户，不能通过 action 名称猜测。
- 主 `plan.json` 必须声明 `automation_type`；子计划继承主 plan 类型，显式声明时必须一致。
- 参数级别一致的组件必须收敛为单个 action，并通过 `type` 区分具体操作，例如 `navigate`、`page`、`element`、`wait`、`extract`、`assert`、`capture`、`read`、`write`。
- 只有参数结构或执行生命周期无法统一时才新增独立组件，例如 `open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`。
- 桌面自动化是独立执行线，不能并入 `command`、浏览器 `element`、浏览器 `mouse` 或浏览器 `keyboard`；桌面流程使用 `open_desktop`、`desktop_app`、`desktop_window`、`desktop_element`、`desktop_input`、`desktop_capture`、`desktop_wait`、`desktop_assert` 等独立 action。
- 新增或修改桌面 action、desktop runtime、backend payload、桌面输出分区、失败采集或 self-check 时，必须先对照 [桌面Action与Runtime契约](../functions/桌面Action与Runtime契约.md)，不要在代码里临时发明字段。
- `automation_type: "browser"` 只能使用浏览器专属 action 和通用 action；`automation_type: "desktop"` 只能使用桌面专属 action 和通用 action。跨线 action 必须在校验阶段失败。
- `write` 统一使用 `value` 表示要写出的内容；`type: variables` 不需要 `value`。
- `read` 统一使用 `path`、`type`、`save_as`。
- 新增动作组件时，同步更新 `src/ai_automate_contro/engine/actions/` 下对应行为模块和 action 注册出口、`handbook/<action>.md`、`handbook/README.md` 和必要的 `test-plans/` 示例。

## AI 终端与工具

- AI 终端属于 plan 级能力，用于创建、管理、运行、调试、修复和报告 plan，不允许作为普通 plan action 写入 `steps`。
- Textual 交互客户端使用 AI-first UI，不再保留 `plan>`/`ai>` 交互模式或 `AI>`/`你>` 文本前缀。无 AI 的 plan list/create/validate/run/debug 统一放到 `cplan`。
- AI 终端、LangChain `StructuredTool` 和 `python .\main.py tool call` 必须共享同一套 Pydantic 工具参数模型。
- 新增 AI 终端工具时，必须在 `src/ai_automate_contro/ai/tool_schemas.py` 新增显式 Pydantic 参数模型，并在 `src/ai_automate_contro/ai/terminal_tool_registry.py` 的 `AI_TERMINAL_TOOL_SPECS` 单表登记处理函数、参数模型、描述、是否需要 `project_root` 和是否受保护。
- 新增或修改 AI 终端工具后运行 `python .\main.py tool check` 和 `python .\main.py self-check ai-tools`。
- AI 新建 plan 包可使用 `create_plan_package`、`write_plan_package_file` 和资源导入工具写入 `plan.json`、`config.json`、`docs/**`、`resources/**`、`sub-plans/*-plan.json`。工具只拒绝 `output/`、`.keygen/`、缓存、pyc 和 egg-info 等非 plan 包结构路径，不得因明文账号、密码、token、api_key、Cookie 或验证码拒绝写入。
- AI 根据自然语言创建 plan 时，先判断用户要的是浏览器网页自动化还是本机桌面控制。除非用户明确说网页、URL、浏览器、DOM，或明确说桌面应用、窗口、系统键鼠、macOS/Windows 应用，否则必须先追问确认执行线。
- AI 终端线程状态包含当前 plan、当前 debug workspace 和最近输出目录等摘要状态，由选择、运行、调试 plan 和工具返回自动维护，不暴露旧式手动设置命令。

## 真实网站与桌面证据

- AI 为真实网站、URL、后台页面或网页流程创建最终 plan 前，必须先用自动化跑通流程证据，不能只按用户文字猜 selector。
- 第一步用 `inspect_web_page` 真实访问并读取受限 DOM 摘要、表单、输入框、按钮、链接、表格以及登录/验证信号。
- 涉及登录、验证码、二次验证、后台菜单、弹窗、权限页或动态页面时，继续创建并运行 `open_browser.headed=true` 的探索 plan。
- 需要用户介入时，必须用 `manual_confirm` 停在同一个 Playwright 浏览器窗口里交接，不要求用户另开本机浏览器、登录后发 URL、截图或 HTML 来替代自动化交接。
- 用户明确同意并提供账号密码或一次性验证信息时，AI 可以按页面正常流程填写、点击和提交；不得破解、绕过或代解验证码、人机验证、二次验证或登录安全策略。
- AI 为真实桌面应用创建最终 plan 前，优先调用 `inspect_desktop` 获取平台、backend、权限/依赖、窗口列表、可选控件树摘要和截图路径，并继续获取窗口列表、控件树、`desktop_element dump`/selector hints、控件读取/断言、表格/树读取、截图、图像定位结果或人工确认等运行证据，不能只按用户文字猜窗口标题、控件 selector 或坐标；`desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 是操作推进，不单独算识别证据。
- 桌面控制按当前运行环境选择平台能力：Windows 环境使用 UI Automation / Win32 控件语义，macOS 环境使用 Accessibility/AX 能力；`set_text` 和 `invoke` 优先走 UIA/AX 原生 pattern，坐标、键盘、剪贴板和图像定位只作为兜底；UAC、安全桌面、管理员权限、macOS TCC 授权和不同用户会话边界不做绕过。
- macOS 桌面控制必须检测 Accessibility、Screen Recording、Automation 等权限。代码可以触发授权提示、打开系统设置并暂停等待，但不能静默替用户授权，也不能自动点击系统隐私授权。

## 调试修复流程

- 已有原始 plan 的修复走 debug workspace、patch 和 HITL approval，不直接在失败现场上随意改原包。
- AI 调试修复必须先把原始 plan 包复制到当前 plan 的 `output/debug/<run>/source-copy/`，再在 `output/debug/<run>/injected-plan/` 注入日志、截图、变量落盘或人工确认。
- 修复候选只能写入 `injected-plan/`、`notes.md` 或 `report.md`；确认问题后只把最小补丁应用回原始 plan。
- selector 自动修复必须保守：没有明确用户提示或候选分数接近时，只能返回候选和歧义原因，不能自动写入 `injected-plan/`。

## 专项 AI 与模型协议

- 执行链路里只允许受控专项 `ai` action；开放式聊天能力只能存在于 plan 级 AI 终端。
- 专项 AI 统一使用 `ai` action，并通过 `type` 区分 `connectivity`、`extract_data`、`classify_text`、`transform_data`、`summarize_text`；必须有固定输入、固定输出 schema、固定系统提示词和 `output/ai/` 调试产物。
- AI 终端和专项 AI 请求必须遵循 OpenAI-compatible 协议。不要把自定义上下文、事件、thread metadata、附件 metadata 或项目内部字段塞进模型请求体。
- AI 终端上下文只能作为普通 system message 文本注入，图片只能在模型调用前转换成标准 `content: [{type: "text"}, {type: "image_url"}]`，工具调用使用 LangChain/OpenAI 原生 `tool_calls`。
- 用户提供的 AI 模型服务报错、欠费、503、协议不兼容或返回不符合 schema 时，直接报告错误，不做自动降级、自动换格式、手动重试或服务兼容兜底；SDK/LangChain 自身的传输重试可以保留或通过配置显式控制。
- `test-plans/config.json` 可以保存用户主动提供的临时 AI 测试服务和密钥，用于真实 AI 场景回归；除非用户明确要求，不要删除或迁移这段配置。

## 上下文、搜索与附件

- AI 终端上下文只保存当前 plan、当前 debug workspace、最近输出目录、最近压缩摘要路径和归档路径等摘要状态。
- 不要把完整 `run.log`、`events.jsonl`、`commands.jsonl` 或大型产物一股脑塞进模型上下文。文本读取必须渐进式：先看结构/路径，再用 `grep_project_text` 通过 `rg` 定位关键词，最后用 `read_project_file_slice` 或小范围 artifact 读取必要行段。
- AI 终端文本搜索只支持 `ripgrep` 的 `rg` 命令；缺失时提示用户安装，或在用户确认后帮助执行 `winget install --id BurntSushi.ripgrep.MSVC -e`，不能使用 Windows 内置搜索兜底。
- AI 终端图片输入主路径是在交互式输入行按 `Ctrl+V` 从剪贴板粘贴图片，终端插入 `[Image #n]` 占位后用户继续输入文字；如果图片已经保存成文件，只保留 `image <image-path>` 作为兜底入口。
- 图片附件落盘到 `.keygen/ai-terminal-sessions/<thread>/attachments/`，发送给模型时转换为 data URL，发送成功后清空，模型服务报错时保留以便用户重试。归档、日志和调试产物允许保留 base64 图片原文，不做自动替换。

## 验证矩阵

- 只改文档：确认链接、入口和维护规则一致，通常不需要运行代码自检。
- 窄范围代码改动：至少运行一个相关示例 plan 或对应自检。
- 修改 action 或执行器：优先运行覆盖该动作的 `test-plans/` 示例。
- 修改计划加载、变量渲染、条件、循环等共享逻辑：检查已有示例是否仍能运行。
- 修改 AI 终端会话、压缩、图片附件或上下文注入：运行 `python .\main.py self-check ai-terminal`。
- 修改 Textual 交互客户端、队列、消息块、输入框或客户端后端事件适配：运行 `python .\main.py self-check textual-client`。
- 修改专项 AI streaming 解析：运行 `python .\main.py self-check ai-stream`；真实服务回归仍使用 `test-plans/ai/controlled-text/plan.json`。
- 新增 AI 终端工具：运行 `python .\main.py tool check` 和 `python .\main.py self-check ai-tools`。
- 新增桌面 action、desktop backend、桌面失败采集或桌面校验规则：运行 `python .\cplan.py self-check desktop-components`；涉及 `desktop_vision locate_image` 时确认 OpenCV 模板匹配、`desktop-vision` JSON/原图/裁剪图/标注图回归覆盖；涉及 `desktop_vision locate_text` 时确认 Tesseract/OCR 依赖探测、schema 负例、默认 skipped 和 `--require-ocr` 强制语义；涉及真实系统 App、焦点、键鼠输入、保存、Explorer/Finder 类系统窗口、Open/Save 文件对话框或关闭链路时补跑 `python .\cplan.py self-check desktop-real-app`；涉及 `desktop_element dump/set_text/select/invoke`、`desktop_input` 鼠标目标或 `desktop_assert element` 时确认 schema 负例和临时表单（Windows WinForms / macOS Tkinter）回归覆盖；无 GUI、锁屏、权限不足或依赖缺失时应返回 skipped 和原因。
- 若验证依赖浏览器，需要先确保已执行 `python -m playwright install chromium`。
