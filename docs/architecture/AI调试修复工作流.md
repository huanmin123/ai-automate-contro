# AI 调试修复工作流

## 目标

AI 终端的 bug 修复能力必须围绕 plan 包工作，而不是直接改用户原始需求。

调试流程要做到：

- 原始 plan 不被调试注入污染。
- 所有调试产物留在当前 plan 包 `output/`。
- 需要用户协助的登录、验证码、二次验证等步骤提前告知，并通过可见 Playwright 浏览器中的 `manual_confirm` 等待/继续。
- 确认问题后，只把最小修复补丁应用到原始 plan。

## 调试工作区

当用户要求 AI 修复某个 plan 时，AI 终端先在当前 plan 包下创建隔离调试副本：

```text
<plan-package>/
  output/
    debug/
      <timestamp>-<debug-run-name>/
        source-copy/
          plan.json
          config.json
          sub-plans/
          resources/
          docs/
        injected-plan/
          plan.json
          config.json
          sub-plans/
          resources/
          docs/
        notes.md
        patch.diff
        report.md
```

`source-copy/` 是用户原始 plan 包的只读快照。`injected-plan/` 是 AI 可以注入调试步骤的副本。

这两个目录都是运行产物，必须留在 `output/debug/`，不提交 Git。

当前确定性入口分两类：AI 终端日常通过 LangChain 工具执行调试工作区读写和补丁流程；无 AI 的人工排查或回归脚本使用 `cplan`。Textual 交互客户端不再提供 `/debug`、`/artifacts` 这类低频管理命令。

```powershell
python .\cplan.py debug-create --file <plan.json> --name <name>
python .\cplan.py debug-prepare --file <plan.json> --name <name>
python .\cplan.py debug-inject --workspace <output/debug/run> --preset print --preset variables
python .\cplan.py debug-patch --workspace <output/debug/run>
python .\cplan.py debug-apply --workspace <output/debug/run> --yes
python .\main.py tool call read_debug_workspace --args-json '{"workspace":"<output/debug/run>"}'
python .\main.py tool call patch_debug_workspace_json --args-json '{"workspace":"<output/debug/run>","root":"injected-plan","relative_path":"plan.json","operations":[{"op":"replace","path":["steps",0,"message"],"value":"debug message"}]}'
python .\main.py tool call write_debug_workspace_file --args-json '{"workspace":"<output/debug/run>","root":"injected-plan","relative_path":"plan.json","content":"..."}'
python .\main.py tool call validate_debug_plan --args-json '{"workspace":"<output/debug/run>"}'
python .\main.py tool call run_debug_plan --args-json '{"workspace":"<output/debug/run>","run_name":"debug-run"}'
```

## 注入规则

AI 只能向 `injected-plan/` 注入调试手段：

- `print`：输出当前阶段说明。
- `write type: variables`：保存变量快照。
- `capture type: screenshot`：关键页面截图。
- `capture type: html`：关键页面 DOM。
- `manual_confirm`：需要用户登录、输入账号密码、处理验证码或确认页面状态时，在同一个可见 Playwright 浏览器里等待。
- 更短的 `wait`、更明确的 `assert`：定位失败点。

通用注入支持 `start`、`end`、`before_step`、`after_step` 四种位置。失败修复优先使用 `before_step`，把截图、HTML、变量快照和人工确认插到失败步骤前，避免原失败步骤中断后导致末尾诊断永远无法执行。

确认修复方向后，AI 优先通过 `patch_debug_workspace_json` 修改 `injected-plan/` 中的 JSON plan/config 文件。该工具按 JSON 路径执行 `replace`、`add`、`remove`，用于生成更小的补丁，避免整文件重写导致字段顺序噪声。

自动候选修复使用 `propose_debug_fix`。该工具默认只返回候选，不写文件；传入 `apply: true` 后，也只会把 `source-copy/` 作为干净基线复制回 `injected-plan/`，再把最小修复写入 `injected-plan/plan.json`。这样 `patch.diff` 只包含真正修复，不会把 `print`、截图、HTML、变量快照或 `manual_confirm` 等调试注入带回原始 plan。

selector 自动修复有额外门禁：如果用户没有提供明确目标提示，或者候选之间分数过近，`apply: true` 也只能返回候选和拒绝原因，不能写入 `injected-plan/`。AI 终端必须把候选、证据和歧义点告诉用户，等待更明确的目标字段、按钮、文本或 selector；不能只因为某个元素存在于 DOM 中就自动修复。

需要整文件写入、补充文档、写资源文件或记录 notes/report 时，AI 可以使用 `write_debug_workspace_file`。写入范围被限制为：

- `injected-plan/plan.json`
- `injected-plan/config.json`
- `injected-plan/sub-plans/`
- `injected-plan/resources/`
- `injected-plan/docs/`
- debug workspace 的 `notes.md`
- debug workspace 的 `report.md`

该工具不能写原始 plan 包，不能写 `output/`，也不能写源码目录。

注入的截图、HTML、变量和 AI 分析产物仍按组件固定分区写入原 plan 包 `output/`。

当前已实现的固定 preset：

- `print`
- `variables`
- `manual_confirm`
- `screenshot`
- `html`
- `desktop_screenshot`
- `desktop_snapshot`
- `desktop_observe`
- `desktop_windows`

`debug prepare` / `prepare_failure_debug_workspace` 会读取最近失败运行，自动创建 debug workspace，并根据失败页面状态选择浏览器会话，把 `print`、`variables`、`screenshot`、`html` 插到失败步骤前；需要用户协助时可额外启用 `manual_confirm`。桌面失败时会额外注入 `desktop_screenshot`、`desktop_snapshot`、`desktop_observe` 和 `desktop_windows`，并在 notes 写入 `failure_desktop_states`、`failure_desktop_screenshots`、`desktop_diagnostics`、`desktop_repair_suggestions`、Window Query、Element Locator、near matches、selector hints 和 `capability_matrix.limitations` 摘要，便于 AI 进入 debug workspace 后直接按证据修正 plan。

`screenshot` 和 `html` 需要指定浏览器会话名。`desktop_*` 预设使用 `desktop` 参数指定桌面会话名，未指定时默认 `desktop`。

AI 不得在调试副本中绕过验证码、绕过人工验证或自动输入用户没有提供的凭据。用户已经提供或要求写入的凭据按本地调试原文保留，不做自动脱敏。

`debug patch` 只比较 `source-copy/` 和 `injected-plan/` 中的 plan 包文件，排除 `output/`、`.debug-backups/` 和缓存目录。`debug apply` 必须显式传入 `--yes`，并在应用前创建原始文件备份。

AI 终端应用补丁还必须经过 LangChain `HumanInTheLoopMiddleware`。模型请求 `apply_debug_patch_after_approval` 时会先中断并在 Textual 客户端显示独立审批块，用户只能用 `/approve` 或 `/reject <reason>` 恢复。工具包装层还有二次守卫：只有 `/approve` 恢复期间注入的 `approved: true` 才能真正执行补丁应用，普通对话里出现“同意”“批准”等文字不能绕过审批。这个受保护工具也不能通过 `python .\main.py tool call ...` 直接调用；脚本显式应用补丁必须使用 `python .\cplan.py debug-apply --workspace <output/debug/run> --yes`。

## 失败现场采集

普通浏览器执行失败时，框架必须尽量保留当时页面现场，而不是只依赖日志：

- `failure-screenshots/`: 失败时的页面截图，用于判断视觉状态。
- `failure-html/`: 失败时的页面 HTML DOM，用于判断 selector、文本、表单和元素结构。
- `failure-page-state/`: 失败时的 URL、title、browser、page、step 以及截图/HTML 路径。

截图只能说明“用户看到什么”，HTML DOM 才能说明“自动化应该如何定位”。AI 终端分析失败时应优先调用 `analyze_latest_run_failure` 读取状态、日志、事件、失败截图、失败 HTML、页面状态和桌面失败状态。

`analyze_latest_run_failure` 还会对失败 HTML 做轻量 DOM 摘要，提取常见交互元素、关键属性和 selector 提示，例如 `id`、`name`、`placeholder`、`autocomplete`、`aria-label`。这样 AI 或人工排查不需要先打开完整 HTML，也能快速看到页面上真正存在的输入框、按钮、链接和表单。

桌面失败时，`analyze_latest_run_failure` 会读取 `failure-desktop-state/`，返回 `desktop_diagnostics` 和 `desktop_repair_suggestions`。AI 应先按建议检查 `desktop_diagnostics.capability_matrix.limitations`，再检查 `diagnostics.window.near_matches` 修正 Window Query，并按 `diagnostics.element.near_matches` 和 `selector_hints` 修正 Element Locator。AI 终端上下文会保留最近桌面失败的状态、诊断数量、修复建议和失败 state/screenshot 路径摘要。

如果这些证据仍不足以定位问题，AI 才进入真实调试流程：创建 debug workspace，在 `injected-plan/` 中注入截图、HTML、桌面截图、桌面快照、窗口列表、变量落盘、`manual_confirm` 或更细的断言，然后运行调试副本真实复现。桌面修复优先使用 `propose_debug_fix` 生成 Window Query 或 Element Locator 候选；控件候选只有来自唯一、高稳定度 `selector_hints` 时才允许自动应用，窗口候选默认要求人工 review 或明确 `user_hint`。候选应用后仍必须运行 `validate_debug_plan` 和 `run_debug_plan`，最后用 `generate_debug_patch` 生成干净补丁。这个过程仍然不能直接修改原始 plan。

## 修复流程

```text
用户描述问题
  -> AI 读取原始 plan、docs、最近 output
  -> AI 调用 analyze_latest_run_failure 汇总失败证据
  -> 复制原始 plan 包到 output/debug/<run>/source-copy
  -> 复制一份到 output/debug/<run>/injected-plan
  -> 向 injected-plan 注入日志、截图、变量落盘或人工确认
  -> 运行 injected-plan/plan.json
  -> 读取 state.json、events.jsonl、run.log、截图、HTML、页面状态、桌面 diagnostics 和变量快照
  -> 分析失败原因
  -> 基于 source-copy 生成干净修复候选并写入 injected-plan/
  -> 校验并运行 injected-plan/plan.json
  -> 生成 patch.diff，只针对原始 plan 包
  -> 请求用户确认
  -> 应用补丁到原始 plan 包
  -> 运行原始 plan 验证
  -> 写 report.md
```

## 用户协助

遇到以下情况，AI 终端必须提前告诉用户要做什么：

- 登录账号密码。
- 验证码、短信、邮箱验证、二次认证。
- 第三方支付、真实下单、真实发信等不可自动执行的动作。
- 需要人工判断页面状态的步骤。

plan 中使用 `manual_confirm` 进入等待态。用户在当前可见 Playwright 浏览器窗口中完成操作后，AI 工具确认流程会回到 Textual 对话里用自然语言确认继续；无 AI 的 `cplan run` 则在当前命令行按提示继续。

## 修复边界

AI 可以修复：

- selector 不稳定。
- 等待时机不合理。
- 输出路径错误。
- 变量名、字段名、断言条件错误。
- 子计划路径、局部配置、资源路径错误。

AI 不应直接修复：

- 用户业务需求不明确的问题。
- 需要真实账号策略决策的问题。
- 需要绕过网站安全机制的问题。
- 不在当前 plan 包职责内的问题。

## 验收

一次 AI 修复完成后，至少产生：

- `output/debug/<run>/source-copy/`
- `output/debug/<run>/injected-plan/`
- `output/debug/<run>/report.md`
- 必要时产生 `output/debug/<run>/patch.diff`
- 原始 plan 的一次验证运行输出
