# AI 终端工具开发检查清单

AI 终端工具是 plan 级能力，只服务创建、管理、运行、调试、修复和报告 plan。不要把开放式聊天或普通 plan action 能力塞进工具层。

## 新增工具步骤

1. 在 `src/ai_automate_contro/ai/terminal_tools.py` 中实现确定性工具函数，返回 JSON 可序列化的 `dict`。
2. 在 `AI_TERMINAL_TOOLS` 注册工具名和函数。
3. 如果工具需要 `project_root`，同步加入 `PROJECT_ROOT_TOOLS`。
4. 如果工具会修改原始 plan 包，优先重新设计为 debug workspace 内操作；确实需要写回原始 plan 时必须走 `PROTECTED_AI_TERMINAL_TOOLS` 和 Human-in-the-loop。
5. 在 `src/ai_automate_contro/ai/tool_schemas.py` 中新增显式 Pydantic 参数模型，并加入 `TOOL_ARGS_SCHEMAS`。
6. 在 `TOOL_DESCRIPTIONS` 增加一句明确描述。
7. 运行 `python .\main.py tool check`，确认工具函数、schema 和描述完全对齐。
8. 运行 `python .\main.py self-check ai-tools`，确认 LangChain `StructuredTool` 构建、共享 Pydantic schema、工具 invoke 回调和受保护工具 HITL 守卫都通过。
9. 运行 `python .\main.py tool schema <tool-name>`，检查 schema 是否只暴露必要字段。
10. 运行 `python .\main.py tool call <tool-name> --args-json '{...}'` 做 CLI 回归。
11. 如果工具会被 AI 自动选择，至少跑一次真实 AI 终端回归，确认模型会通过原生 `tool_calls` 调用它。

## 设计约束

- 参数必须能被 Pydantic schema 表达；不要在工具里接受随意结构再自行猜测。
- 多余参数默认拒绝，避免模型把不受控字段传入执行层。
- 工具只能返回结构化结果，不输出需要模型再解析的长文本协议。
- 文件写入必须限制在当前 plan 包、debug workspace 或当前 plan 的 `output/` 约束内。
- 原始 plan 修改必须形成 debug workspace patch，并经用户批准后应用。
- 工具失败要抛出明确异常或返回 `ok=false` 的结构化结果，不能吞掉错误。

## 必跑命令

```powershell
python -m py_compile .\main.py (Get-ChildItem .\src -Recurse -Filter *.py | ForEach-Object { $_.FullName })
python .\main.py tool check
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
