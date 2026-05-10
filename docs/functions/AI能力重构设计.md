# AI 能力重构设计

## 目标

AI 能力分成两类，避免执行器、终端和专项模型能力混在一起：

- plan 级 AI：帮助用户创建、管理、调试、修复和总结 plan。
- 专项 AI：在 plan 执行中处理明确的数据、图像或文本任务。

执行器本身仍保持确定性。AI 终端可以调用管理命令和工具，但不直接接管浏览器控制。

## 非目标

- 不让自然语言对话节点进入普通执行链路。
- 不让 AI 绕过人工验证、验证码、二次认证或人工确认。
- 公开示例不保存真实密钥。`test-plans/config.json` 可保存用户主动提供的临时测试密钥，用于真实 AI 回归；除非用户明确要求，不要自动删除。
- 不让专项 AI 修改文件系统、执行命令或控制浏览器。

## plan 级 AI

plan 级 AI 运行在 AI 终端中，面向整个 plan 包生命周期：

- 需求澄清。
- 创建 plan 包。
- 生成 `plan.json`。
- 生成 `config.json` 和 `docs/README.md`。
- 校验 plan 结构、路径和输出约束。
- 运行 plan。
- 读取日志、事件和输出产物。
- 分析失败原因。
- 生成修复补丁。
- 经用户确认后应用补丁。
- 生成运行报告。

plan 级 AI 不是 plan action，不写入 `steps`。

第一版 plan 级 AI 已通过持续 AI 终端落地：

```powershell
python .\main.py ai
python .\main.py ai --thread login-debug
```

它使用 `langchain.agents.create_agent` 编排模型与工具循环，并通过 LangChain `StructuredTool` 访问项目。每个工具入口都有显式 Pydantic 参数模型，schema 由框架读取并绑定到原生 `tool_calls`；CLI 的 `tool call` 入口也使用同一套 schema 校验参数。工具结果以 `ToolMessage` 回到图中；不再要求模型输出自定义 JSON 工具调用对象。

工具注册表、Pydantic 参数模型和工具描述必须一一对应。新增或删除工具后运行 `python .\main.py tool check`，该检查也会在工具列表、工具 schema、工具调用和 LangChain tool 构建前执行，避免漏配后进入真实 AI 会话。

`python .\main.py self-check ai-tools` 会进一步真实构建 LangChain `StructuredTool`，确认工具名、描述、`args_schema` 和 Pydantic 字段一致，调用 `validate_plan` 验证工具 invoke 回调链路，验证 `read_plan_package`、`grep_project_text` 和 `read_project_file_slice` 的渐进式读取约束，并确认 `apply_debug_patch_after_approval` 没有 HITL approve resume 时不能执行。

AI 终端文本定位依赖 `ripgrep` 的 `rg` 命令。`grep_project_text` 和 AI 终端启动都会检查 `rg` 是否可用；缺失时直接提示用 PowerShell 7 执行 `winget install --id BurntSushi.ripgrep.MSVC -e`，不使用 Windows 内置搜索替代。

会话状态由 LangGraph `SqliteSaver` 持久化到 `.keygen/ai-terminal-checkpoints.sqlite`。同一个 `--thread` 可以跨终端进程恢复上下文；终端内可用 `context` 查看 checkpoint 信息、`history [limit]` 查看近期消息、`thread [id]` 切换线程、`reset` 删除当前线程。

线程状态包含当前 plan、当前 debug workspace 和最近输出目录。用户可以用 `use`、`workspace`、`run_context` 显式设置；工具返回相关路径时也会自动更新。模型调用前会通过 LangChain middleware 把这些状态注入 system message，减少重复路径输入和上下文误判。

原始 plan 补丁应用使用 LangChain `HumanInTheLoopMiddleware` 做人机审批。当模型请求 `apply_debug_patch_after_approval` 时，Agent 图先中断并等待用户；用户在 AI 终端输入 `approve` 才会通过 `Command(resume=...)` 恢复执行，终端会把 `approved: true` 注入工具参数。输入 `reject <reason>` 会拒绝工具调用，并把拒绝原因返回给模型继续处理。

工具包装层还有二次确认：`apply_debug_patch_after_approval` 只接受 `approve` 恢复期间的人工批准状态。模型即使在普通对话轮次中传入 `approved: true`，也不能绕过中断审批。该受保护工具不开放给 `python .\main.py tool call` 直接调用；脚本应用补丁必须走 `plan debug-apply --yes` 这条显式管理入口。

- `list_plan_packages`
- `read_plan_package`
- `validate_plan`
- `run_plan`
- `analyze_latest_run_failure`
- `read_latest_run_state`
- `read_latest_run_report`
- `read_run_log`
- `read_run_events`
- `list_output_artifacts`
- `read_output_artifact`
- `create_debug_workspace`
- `read_debug_workspace`
- `inject_debug_steps`
- `propose_debug_fix`
- `patch_debug_workspace_json`
- `write_debug_workspace_file`
- `validate_debug_plan`
- `run_debug_plan`
- `generate_debug_patch`
- `apply_debug_patch_after_approval`

同一组工具也可以通过 `python .\main.py tool call <name> --args-json '{...}'` 调用，便于真实回归和后续替换 agent 框架。

其中 `patch_debug_workspace_json` 用于对 `injected-plan/` 下的 JSON 文件做路径级最小修改，例如只替换 `["steps",0,"message"]`。`write_debug_workspace_file` 保留为整文件写入、文档、资源、notes 和 report 的受限写入工具。

`propose_debug_fix` 用于从失败证据生成受限修复候选。第一版只覆盖 selector 超时，默认只返回候选；应用候选时会先回到 `source-copy/` 的干净基线，再把最小修复写入 `injected-plan/`，保证后续 patch 不包含调试注入。

原始 plan 修改必须通过 debug workspace 生成补丁，并在用户明确确认后才能应用。AI 终端不会直接把调试注入或修复候选写回原始 plan；修复候选只能写入 `output/debug/<run>/injected-plan/`、`notes.md` 或 `report.md`。

## 专项 AI

专项 AI 是受控组件，只处理输入输出明确的任务：

- `ai` / `type: connectivity`: 模型连通性测试。
- `ai` / `type: extract_data`: 从文本中抽取结构化数据。
- `ai` / `type: transform_data`: 数据清洗和格式转换。
- `ai` / `type: classify_text`: 文本分类。
- `ai` / `type: summarize_text`: 文本摘要。

专项 AI 可以作为 plan action，但每个组件必须有固定字段、固定系统提示词、固定输出 schema 和输出校验。

示例：

```json
{
  "action": "ai",
  "type": "extract_data",
  "service": "text_extractor",
  "input": "{{raw_text}}",
  "schema": {
    "email": "string",
    "status": "string"
  },
  "save_as": "parsed"
}
```

## 配置模型

AI 服务注册进入当前 plan 集合配置或 plan 局部配置：

```text
plans/config.json
test-plans/config.json
<plan-package>/config.json
```

优先级：

```text
集合级 config < plan 局部 config < plan.json variables
```

建议字段：

```json
{
  "ai_services": {
    "text_extractor": {
      "provider": "openai-compatible",
      "base_url": "http://127.0.0.1:18733/v1",
      "model": "model-name",
      "api_key_env": "TEXT_EXTRACTOR_API_KEY",
      "response_format": "json_schema",
      "stream": false,
      "timeout_seconds": 60
    }
  }
}
```

`response_format` 可选 `json_schema`、`json_object` 或 `plain`，默认 `json_schema`。专项 AI 不对用户提供的模型服务做自动降级、手动重试或兼容兜底；服务欠费、503、协议不兼容、返回内容为空或不符合 schema 时，执行会直接失败。SDK/LangChain 自身的传输重试可以通过 `max_retries` 显式配置。

`stream` 只影响 `chat_completions` 模式。需要 streaming 时必须在配置中显式设置 `"stream": true`，专项 AI 会从 streaming chunks 中还原文本，再执行 JSON 解析和 schema 校验。

修改 streaming 解析逻辑后运行 `python .\main.py self-check ai-stream`，先用本地 chunk、reasoning chunk 忽略、SDK 对象 chunk 和空流拒绝夹具验证解析器，再运行真实 `test-plans/ai/controlled-text/plan.json` 做模型级回归。

公开示例配置只能放服务别名、模型名、超时等非敏感字段。项目测试集合 `test-plans/config.json` 可以放用户提供的临时测试密钥和显式调用参数，用于真实模型回归。

## 输出约束

专项 AI 的运行产物必须写入当前 plan 包的 `output/ai/`：

```text
output/ai/
  ocr/
  connectivity/
  extract-data/
  transform-data/
  classify-text/
  summarize-text/
```

每次调用至少保留：

- 请求摘要。
- 原始响应。
- 解析结果。
- schema 校验结果。
- 错误信息。

禁止写入源码目录、`resources/`、`docs/` 或其他 plan 包。

## AI 终端工作流

### 创建 plan

```text
用户描述需求
  -> AI 澄清目标页面、输入数据、断言和输出
  -> 生成 plan 包结构
  -> 写入 plan.json / config.json / docs
  -> 校验 plan
  -> 用户确认
```

### 调试 plan

```text
用户选择 plan
  -> AI 读取 plan、docs、最近 output
  -> 调用管理终端运行
  -> 调用 analyze_latest_run_failure 汇总失败证据
  -> 读取 events.jsonl / run.log / result.json / failure-html / failure-page-state
  -> 读取 DOM 摘要中的表单、按钮、链接和 selector 提示
  -> 定位失败 step、页面状态和原因
  -> 证据不足时创建 debug workspace 并运行 injected-plan 真实复现
  -> 写入 injected-plan/ 修复候选
  -> 校验并运行 injected-plan
  -> 生成修复补丁
  -> 用户确认
  -> 应用补丁并再次验证
```

### 生成报告

```text
读取 result.json
读取关键 artifacts
读取失败截图、失败 HTML、DOM 摘要、失败页面状态或输出文件
生成 Markdown 报告到 output/reports/
```

## 验收标准

- 用户可以通过 AI 终端创建一个新 plan 包。
- AI 终端可以运行 plan 并解释失败原因。
- AI 终端可以生成修复补丁，并在用户确认后应用。
- AI 终端可以通过结构化工具读取 plan、运行 plan、读取日志和输出产物。
- 专项 AI 组件输出可被 schema 校验。
- 所有专项 AI 调试产物都落在当前 plan 包 `output/ai/`。
