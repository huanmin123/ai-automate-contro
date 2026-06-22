# AI 终端提示词与上下文策略

## 目标

AI 终端要同时满足两个目标：

- 少打扰用户：能通过工具、上下文、plan、handbook、网页检查或运行证据自行确认的事情，不反复追问。
- 不瞎干：如果缺失信息会导致错误 plan、越权操作、真实账号风险、返工或不可逆动作，必须在开始执行前一次性问清楚。

这份文档用于跟踪 AI 终端提示词、上下文注入和长会话缓存策略的长期设计。它不替代 `handbook/` 的 action 说明；`handbook/` 仍是 plan 字段和示例的权威来源。

## 外部借鉴

OpenAI/Codex 和 Claude/Anthropic 的共同方向是分层管理提示词：

- 稳定身份、行为原则、工具边界和项目规则放在最前面。
- 项目级规则用类似 `AGENTS.md` 或 `CLAUDE.md` 的文件承载，作为长期记忆和协作契约。
- 当前任务、当前路径、最近输出、压缩摘要等动态状态放在后面，并保持短小、结构稳定。
- 长日志、完整 HTML、完整事件流和大型产物不直接塞进模型上下文，而是先给路径、摘要和受限读取工具。

OpenAI prompt caching 和 Anthropic prompt caching 都依赖长而稳定的前缀。缓存友好的提示词结构不是“少写规则”，而是把稳定规则固定下来，把变化内容移动到后缀。Codex 本地项目也能看到类似分层：`base_instructions` 是稳定基础指令，运行时上下文和 developer 更新是后续消息，长会话靠压缩和上下文更新维持。

参考资料：

- [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
- [OpenAI Codex AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [OpenAI GPT-5.1-Codex prompting guide](https://cookbook.openai.com/examples/gpt-5/gpt-5-1-codex-max_prompting_guide)
- [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Anthropic Clear and Direct Prompting](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct)
- [Claude Code Memory](https://docs.claude.com/en/docs/claude-code/memory)

本地 Codex 参考路径：

- `/Users/anminhu/temp-project/codex/codex-rs/protocol/src/openai_models.rs`
- `/Users/anminhu/temp-project/codex/codex-rs/core/src/context_manager/history.rs`
- `/Users/anminhu/temp-project/codex/codex-rs/core/src/session_startup_prewarm.rs`
- `/Users/anminhu/temp-project/codex/codex-rs/core/gpt_5_2_prompt.md`

## 启动判断

AI 终端收到新需求后，先做一次轻量任务判定，不急着写 plan 或跑调试。

需要先确认的典型信息：

- 目标：用户到底要创建、运行、修复、解释还是总结 plan。
- 范围：目标 plan 包、目标 URL、目标文件、账号环境、输出格式或验收标准是否明确。
- 权限：是否需要登录、验证码、二次验证、真实支付、真实发信、真实账号变更或人工确认；本机调试数据按原文保留。
- 风险：是否可能写错目录、覆盖已有 plan、修改原始 plan、删除产物或把密钥写进仓库。
- 证据：是否已有网页 DOM、截图、HTML、失败输出或可运行 plan 作为依据。

确认时要一次性问关键问题，不把可预见的问题拖到执行中才暴露。问题应短、具体、可回答；不要把用户已经提供的信息再问一遍。

## 自主取证

AI 终端优先用工具补足事实，而不是把所有不确定性都抛给用户。

可以自主确认的事情：

- 用 `list_plan_packages` 找现有 plan。
- 用 `read_plan_package` 看 plan 包结构。
- 用 `grep_project_text` 和 `read_project_file_slice` 查 handbook、docs、plan、config 和资源。
- 用 `inspect_web_page` 检查真实 URL 或本地 HTML；涉及登录、验证码、二次验证、后台菜单或动态页面时，再创建并运行 `open_browser.headed=true` 的探索 plan。
- 用 `read_latest_run_state`、`read_latest_run_report`、`read_run_log`、`read_run_events` 和 `analyze_latest_run_failure` 获取运行证据。
- 用 `validate_plan` 在写入或修复后做结构校验。
- 用户提供本机输入文件但没有明确要求长期依赖该路径时，用 `import_plan_resource_file` 复制到当前 plan 包 `resources/`，再写 `resources/...`。

不能自主假设的事情：

- 用户账号、密码、一次性验证码、短信、邮箱验证或二次认证。
- 真实支付、真实下单、真实发信、真实删除或修改生产数据。
- 网站安全策略、验证码绕过或权限绕过。
- 用户业务目标存在多种合理解释，且选择会明显影响 plan 结构。
- 目标目录不明确，且默认落点可能覆盖或污染已有需求包。
- 可复现资源位置不明确时，不能默认依赖另一个 plan 包的 `resources/`、本机绝对路径或本机绝对 `file://` 路径；应复制到当前 plan 包 `resources/`，并使用 `{{resources_file_url}}` 或 `resources/...`。
- plan 输入路径可以使用当前 plan 包资源、本机绝对路径、共享盘、外部工作目录或越出当前 plan 包的相对路径；工具不因路径位置拒绝。

## 打扰用户的边界

AI 终端应按下面顺序决策：

1. 能用上下文直接确定：直接执行。
2. 能用只读工具确定：先取证，再执行。
3. 能创建探索 plan 降低不确定性：先创建并运行探索 plan；需要人工动作时，必须停在同一个可见 Playwright 浏览器窗口里交接。
4. 需要用户授权、一次性验证码、二次验证、外部设备确认或业务选择：开工前问清楚，执行时通过自动化浏览器承接。
5. 执行中出现新的安全门槛或页面状态变化：暂停并说明当前自动化浏览器停在哪一步、当前证据、缺口和用户要在该浏览器里做什么。

执行中可以打扰用户，但必须有明确理由。典型理由是登录态过期、验证码出现、页面需要人工判断、工具证据互相矛盾、补丁应用需要批准。网页流程的人工介入不能要求用户另开自己的浏览器；必须依托当前 headed Playwright 浏览器和 `manual_confirm`。

## 提示词分层

建议长期拆成五层：

```text
稳定系统提示词
  -> 项目规则和工具边界
  -> 当前运行根和 handbook/plan_roots 说明
  -> 当前线程动态上下文
  -> 用户本轮消息和附件
```

稳定系统提示词应少改，主要放角色、边界、工具使用原则、开工前判断、用户确认策略和回答要求。

项目规则可以继续内置在系统提示词，也可以后续拆到独立 prompt 模块。无论如何，动态值不要插入稳定规则中间。

动态上下文包括：

- `current_plan_path`
- `current_debug_workspace`
- `latest_output_dir`
- `latest_compression_summary_path`
- `latest_compression_messages_path`
- `latest_compression_archive_dir`

动态上下文只保存路径和短摘要，不保存完整日志、完整 HTML、完整事件流或完整图片内容。

## 缓存策略

缓存友好的目标是最大化请求前缀匹配：

- `build_system_prompt()` 返回的稳定文本尽量不随线程、路径、时间、plan 名称变化。
- 动态上下文固定格式追加到后缀，字段顺序稳定，空字段不输出。
- 工具列表、schema 和描述保持稳定；新增工具集中修改并跑工具自检。
- 压缩摘要只保存继续工作需要的稳定结论，不记录流水账。
- 大型内容通过路径和受限读取工具渐进读取，不进入长期上下文。

当前实现已经把动态上下文追加在 system message 尾部。短期可以接受；后续若要进一步优化，应评估改成独立的后缀消息或更严格的固定格式，确保稳定系统提示词完全不被动态文本重建污染。

## 当前落点

已存在能力：

- `src/ai_automate_contro/ai/prompts/terminal.py`: AI 终端稳定系统提示词。
- `src/ai_automate_contro/ai/terminal_context.py`: 当前 plan、debug workspace、latest output 和压缩归档路径注入。
- `src/ai_automate_contro/ai/prompts/session_compression.py`: 长会话压缩提示词。
- `src/ai_automate_contro/ai/terminal_tool_registry.py`: AI 终端工具单表。
- `src/ai_automate_contro/ai/tool_schemas.py`: 工具参数 schema。

短期改造：

- 在系统提示词中加入“开工前判断”和“自主取证优先”规则。
- 明确只有关键缺口才问用户，且应在开始执行前一次性问清楚。
- 保留真实网页最终 plan 创建前必须 `inspect_web_page` 取入口证据、必要时运行 headed 探索 plan 的硬规则。

中期改造：

- 把动态上下文格式收敛成更稳定的后缀块，并增加自检覆盖字段顺序和空字段行为。
- 给 AI 终端添加“澄清决策”回归用例，验证模型不会在目标 URL、登录方式、输出要求缺失时直接写 plan。
- 给真实网页 plan 新建流程增加回归：模型先调用 `inspect_web_page`，再按需创建并运行 `open_browser.headed=true` 的探索 plan；需要人工动作时必须通过同一个 Playwright 浏览器里的 `manual_confirm` 交接。

长期改造：

- 评估将稳定系统提示词、项目规则、工具行为准则拆成独立 prompt section，以便变更审计和缓存命中分析。
- 记录模型返回的 token usage 中 cached input tokens，用于观察提示词变更对成本的影响。
- 为压缩摘要增加质量检查，确保摘要保留目标、当前 plan、最新输出、未决问题和下一步。

## 验收标准

一次提示词或上下文策略变更至少满足：

- 没有把动态路径、时间、日志或大型产物插入稳定系统提示词中间。
- 不鼓励模型绕过工具边界、验证码、登录安全策略或用户审批。
- 对新建 plan 和修复已有 plan 的写入路径边界清楚。
- 对新建可复现 plan，不硬编码本机绝对 `file://` 路径，也不依赖其他 plan 包资源。
- 对用户提供的本机输入文件，推荐导入当前 plan 包 `resources/` 以便复现；用户要求固定本机路径时可以直接写绝对输入路径。
- 对真实 URL plan，仍要求先拿页面证据。
- 修改 Python prompt 文件后至少运行 `python -m py_compile`。
- 修改工具、上下文注入、会话、压缩或图片附件逻辑后运行 `python .\main.py self-check ai-terminal`。
