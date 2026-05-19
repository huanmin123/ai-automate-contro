# AI 终端工具开发检查清单

AI 终端工具是 plan 级能力，只服务创建、管理、运行、调试、修复和报告 plan。不要把开放式聊天或普通 plan action 能力塞进工具层。

## 新增工具步骤

1. 在合适的 `src/ai_automate_contro/ai/` 行为模块里实现确定性工具函数，返回 JSON 可序列化的 `dict`。常见 plan/run/debug 编排入口可放在 `terminal_tools.py`，debug workspace 文件操作放在 `debug_workspace_tools.py`，plan 包读写放在 `plan_tools.py`；不要为了文件大小单独拆模块。
2. 在 `src/ai_automate_contro/ai/tool_schemas.py` 中新增显式 Pydantic 参数模型。
3. 在 `src/ai_automate_contro/ai/terminal_tool_registry.py` 的 `AI_TERMINAL_TOOL_SPECS` 单表登记工具名、处理函数、参数模型、描述、是否需要 `project_root` 和是否受保护。
4. 如果工具会修改原始 plan 包，优先重新设计为 debug workspace 内操作；确实需要写回原始 plan 时必须把该工具规格标记为 `protected=True` 并走 Human-in-the-loop。
5. 运行 `python .\main.py tool check`，确认工具规格、schema、描述和保护边界完全对齐。
6. 运行 `python .\main.py self-check ai-tools`，确认 LangChain `StructuredTool` 构建、共享 Pydantic schema、工具 invoke 回调、渐进式读取工具和受保护工具 HITL 守卫都通过。
7. 运行 `python .\main.py tool schema <tool-name>`，检查 schema 是否只暴露必要字段。
8. 运行 `python .\main.py tool call <tool-name> --args-json '{...}'` 做 CLI 回归。
9. 如果工具会被 AI 自动选择，至少跑一次真实 AI 终端回归，确认模型会通过原生 `tool_calls` 调用它。

## 设计约束

- 参数必须能被 Pydantic schema 表达；不要在工具里接受随意结构再自行猜测。
- 多余参数默认拒绝，避免模型把不受控字段传入执行层。
- 工具只能返回结构化结果，不输出需要模型再解析的长文本协议。
- 读取文本证据必须渐进式：默认返回结构、路径、大小或尾部摘要；需要正文时先用 `grep_project_text` 通过 `rg` 定位，再用 `read_project_file_slice` 读取小范围行段。
- `grep_project_text` 只支持 `ripgrep` 的 `rg` 命令；缺失时必须提示用户安装或经用户确认后帮助安装，不能用 Windows 内置搜索兜底。
- plan action 的运行证据和中间产物必须限制在当前 plan 包、debug workspace 或当前 plan 的 `output/` 约束内。
- 用户明确要求最终交付物写到 Downloads、桌面或绝对路径时，使用 `export_local_file` 写入最终文件，或从当前 plan `output/` 复制已生成产物；不要要求用户手动复制。
- 新建 plan 包阶段可以使用 `write_plan_package_file` 写 `plan.json`、`config.json`、`docs/**`、`resources/**` 和 `sub-plans/*-plan.json`；它必须拒绝 `output/`、`.keygen/`、缓存、pyc 和 egg-info 路径。
- 已有原始 plan 的修复必须形成 debug workspace patch，并经用户批准后应用。
- 工具失败要抛出明确异常或返回 `ok=false` 的结构化结果，不能吞掉错误。
- 不因文件未超过 1000 行或看起来偏大就拆模块；拆分必须服务职责边界、风险隔离、测试可读性或长期维护收益。
- 为真实网站、URL、后台页面或网页流程创建最终 plan 时，AI 终端必须先跑通流程证据，不能只根据文字描述猜 selector。第一步用 `inspect_web_page` 获取入口 DOM/表单/按钮/链接/登录和验证信号；涉及登录、验证码、二次验证、后台菜单或动态页面时，继续创建并运行 `open_browser.headed=true` 的探索 plan。需要用户介入时，用 `manual_confirm` 停在同一个 Playwright 浏览器窗口里交接，不要让用户另开本机浏览器后再提供 URL、截图或 HTML。

## 必跑命令

```powershell
python -m py_compile .\main.py (Get-ChildItem .\src -Recurse -Filter *.py | ForEach-Object { $_.FullName })
python .\main.py tool check
python .\main.py self-check ai-terminal
python .\main.py self-check ai-tools
python .\main.py tool list
python .\main.py tool schema <tool-name>
python .\main.py tool call <tool-name> --args-json '{...}'
```

受保护工具还需要验证：

```powershell
python .\main.py tool call apply_debug_patch_after_approval --args-json '{"workspace":"x","approved":true}' --compact
```

这个命令应该失败，并提示只能通过 AI 终端 human approval flow 执行。
