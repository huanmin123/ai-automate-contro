# AI 终端工具参考

## 定位与边界

AI 终端工具是 plan 级终端能力，只服务 AI 终端创建、管理、运行、调试、修复和报告 plan。它们不是 plan action，不能写入普通 plan 的 `steps`；执行链路里只允许受控专项 `ai` action（见 [../README.md](../README.md) 的能力优先级）。

本文档是当前版本的完整静态参考，覆盖全部 42 个注册工具。运行时的权威枚举以终端命令为准：`cplan tool list` 列出全部工具的名称、描述、参数名和权限标志，`cplan tool schema <工具名>` 返回单个工具的完整参数 schema，`cplan tool check` 校验注册表一致性。版本升级后以命令输出为准。

所有工具参数都按显式 Pydantic schema 校验，未知参数会被拒绝；本文档的参数表与该 schema 一一对应。

## 延伸阅读

以下项目文档提供架构与流程背景（路径相对项目根，不作为本手册链接）：

- `docs/architecture/AI终端与交互式执行架构.md`: AI 终端分层、工具循环和人工审批架构。
- `docs/architecture/AI终端提示词与上下文策略.md`: 上下文压缩、图片附件和提示词策略；`read_compression_archive` 的归档来源。
- `docs/architecture/AI调试修复工作流.md`: 失败分析到补丁审批的完整调试流程。
- `docs/develop/AI终端工具开发检查清单.md`: 新增或修改 AI 终端工具时的步骤和门禁。

## 权限与门禁

每个工具有两个权限标志：

- `protected`: 受保护工具，只能经 AI 终端人工审批流程执行。当前只有 `apply_debug_patch_after_approval`；它把补丁写回原始 plan 包，必须在用户显式批准（终端 `/approve`）后由终端注入确认字段执行。
- `requires_project_root`: 工具以当前项目根为作用域，由终端自动注入项目根；意味着该工具只读写当前项目内的资源（`export_local_file` 例外，它专门写项目外交付路径）。

两个运行门禁独立于权限标志：

- `run_plan`: 只能通过 AI 终端质量门禁后的工具循环执行；直接调用会被拒绝，且运行前最近一次 `review_plan_quality` 必须通过。无 AI 管理运行使用 `cplan run`。
- `run_schedule_now`: 当前 AI 工具直调会被拒绝；确定性立即运行使用 `cplan schedule run-now`。

| 分组 | 工具 |
| --- | --- |
| plan 包管理 | create_plan_package, list_plan_packages, read_plan_package, write_plan_package_file, import_plan_resource_file, validate_plan, review_plan_quality |
| 运行与调试工作区 | run_plan, run_debug_plan, validate_debug_plan, create_debug_workspace, find_debug_workspace, list_debug_workspaces, read_debug_workspace, inject_debug_steps, write_debug_workspace_file, patch_debug_workspace_json |
| 失败分析与修复 | analyze_latest_run_failure, read_latest_run_state, read_latest_run_report, read_run_log, read_run_events, prepare_failure_debug_workspace, propose_debug_fix, generate_debug_patch, apply_debug_patch_after_approval |
| 输出与产物 | list_output_artifacts, read_output_artifact |
| 调度 | list_schedules, add_schedule, remove_schedule, enable_schedule, disable_schedule, run_schedule_now |
| 项目文件与会话归档 | grep_project_text, read_project_file_slice, read_compression_archive |
| 工作计划 | update_work_plan |
| 页面与桌面检查 | inspect_web_page, inspect_desktop |
| 本机命令与导出 | run_local_command, export_local_file |

参数表中"默认值"列为 schema 默认值；标"必填"的参数没有默认值。"工具会限幅"表示实现会把超出范围的值收敛到上下限，不是报错。

## plan 包管理

### create_plan_package

创建新的 plan 包；空白 plan 传 `automation_type`，官方场景模板可传 `template_id`，并可用 `template_params` 覆盖模板变量。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| package_path | 字符串 | 否 | 无 | 目标 plan 包目录；相对路径按项目根解析。省略时用默认 plan 根和 `name`。 |
| name | 字符串 | 否 | 无 | plan 名称。省略 `package_path` 时必填。 |
| automation_type | `browser` 或 `desktop` | 否 | 无 | plan 执行线。空白 plan 必填；使用 `template_id` 时可由模板自动声明。 |
| template_id | 字符串 | 否 | 无 | 可选场景模板 id，例如 `browser-login-extract`。 |
| template_params | 对象 | 否 | `{}` | 使用 `template_id` 时覆盖模板变量；键必须是模板声明的变量名，复杂值可传数组或对象。 |
| force | 布尔 | 否 | `false` | CLI 兼容字段；AI 工具不允许覆盖已有非空 plan 包，传 `true` 也会被拒绝。 |

行为要点：

- 只能在当前项目根内、且位于运行根 `plan.config.plan_roots` 声明的目录内创建；拒绝在 `output/`、`profiles/`、缓存、checkpoint、git 或 pycache 路径创建。
- 目标目录已存在且非空时报错并提示：修复已有 plan 应先创建 debug workspace，再通过 patch 审批应用。
- `package_path` 和 `name` 至少提供一个；`template_params` 只能和 `template_id` 一起使用。
- 创建成功后写入 AI 终端本地注册表；只有注册在案的包才能用 `write_plan_package_file` 写入。
- 失败路径：路径不在 plan_roots、目标是非空目录、空白 plan 缺 `automation_type` 时抛出错误。

示例：

```json
{
  "name": "daily-report",
  "automation_type": "browser"
}
```

### list_plan_packages

按当前运行根的 `plan_roots` 列出可用 plan 包。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| filter_text | 字符串 | 否 | `""` | 可选过滤文本，不区分大小写匹配包路径。 |

行为要点：

- 只读；返回每个包的摘要（路径、名称、执行线、步骤数等）。
- 不需要 plan 运行证据，适合作为定位入口。

示例：

```json
{
  "filter_text": "report"
}
```

### read_plan_package

读取 plan 包结构和元数据，不加载完整文档或资源正文。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录；目录会自动补 `plan.json`。 |

行为要点：

- 只读；返回 plan/config 的顶层键、步骤大纲（每步 action/type/name/字段名，最多 80 步）、docs/sub-plans/resources 文件清单（各限 20/50/200 项）。
- 正文细节用 `grep_project_text` 加 `read_project_file_slice` 渐进读取。
- 失败路径：plan 入口不存在时报错。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### write_plan_package_file

写受控 plan 文件：`plan.json`、`config.json`、`docs/**`、`resources/**`、`sub-plans/*-plan.json`。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| relative_path | 字符串 | 是 | 无 | 包内白名单路径；必须是相对路径。 |
| content | 字符串 | 否 | 无 | 文本内容；与 `json_value` 二选一。 |
| json_value | 任意 JSON | 否 | 无 | JSON 内容，可替代 `content`；写入 `.json` 文件时按缩进序列化。浏览器字段按当前 handbook，如 `wait.type=time`、`aria_snapshot.mode=default/ai`。 |
| mode | 字符串 | 否 | `"overwrite"` | 写入模式：`overwrite` 或 `append`。 |

行为要点：

- 只能写入本 AI 工具新建的 plan 包（按本地注册表判断）；修改已有原始 plan 必须走 debug workspace 加 patch 审批流程。
- 允许的目标只有 `plan.json`、`config.json`、`docs/**`、`resources/**`、`sub-plans/*-plan.json`；拒绝 `output/`、`profiles/`、缓存、checkpoint、git、pyc、pyo、egg-info 路径。
- 内容保留原文，不因账号、密码、token 或 api_key 等明文字段拒绝写入。
- `json_value` 只支持 overwrite 模式，且只能写 `.json` 后缀；`content` 写 `.json` 文件时会先校验 JSON 语法。
- 写后先 `validate_plan`，再 `review_plan_quality`。
- 失败路径：包不在项目根内、入口不存在、非 AI 新建包、路径越出白名单、`content` 与 `json_value` 同时提供或都不提供时抛错。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "relative_path": "plan.json",
  "json_value": {
    "name": "daily-report",
    "automation_type": "browser",
    "steps": []
  }
}
```

### import_plan_resource_file

把用户提供的本机文件复制到当前 plan 包 `resources/` 下，并返回可写入 plan 的 `resources/...` 相对路径。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| source_path | 字符串 | 是 | 无 | 要导入的本机源文件路径；绝对路径、`~` 路径或项目相对路径。 |
| relative_path | 字符串 | 否 | `""` | 目标 `resources/` 下相对路径；空则使用源文件名，可省略 `resources/` 前缀。 |
| overwrite | 布尔 | 否 | `false` | 目标资源已存在时是否覆盖。 |

行为要点：

- 只能写入当前 plan 包 `resources/` 下；这是提升可复现性的可选工具，不是对绝对输入路径的拦截。
- 拒绝导入到 `output/`、缓存、checkpoint、git、pycache 路径和 pyc、pyo、egg-info 文件。
- 失败路径：源文件不存在、目标已存在且未开 `overwrite`、目标是目录时抛错。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "source_path": "~/Downloads/accounts.txt"
}
```

### validate_plan

只校验 plan 包，不运行。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |

行为要点：

- 返回 `ok` 与逐条错误（位置、消息、格式化文本）；不做语义质量复查。
- 是 `run_plan` 门禁链的第一环；语义门禁用 `review_plan_quality`。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### review_plan_quality

运行前语义门禁：核对关键事实、真实网站证据、账号密码、输出路径和 `manual_confirm` 后续是否落到步骤里。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| user_request | 字符串 | 是 | 无 | 用户原始需求、目标或任务描述。 |
| evidence_summary | 字符串 | 否 | `""` | 按执行线传入证据摘要：browser 使用网页探测、headed 探索、manual_confirm 或运行证据；desktop 使用窗口列表、截图、权限诊断、控件/状态快照、target_candidates、candidate_id、coordinate_profile/coordinate_diagnostics、manual_confirm 或运行证据；坐标/candidate 类 plan 必须说明候选策略、置信度、screen_clickable、坐标来源和操作后验证方式。 |
| planned_output_path | 字符串 | 否 | `""` | 用户要求的最终本机交付路径，如 `Downloads/AI账户.txt`。 |

行为要点：

- 先做结构校验，未通过时直接判 fail 并要求先修 `validate_plan` 错误。
- 是 `run_plan` 质量门禁的输入：最近一次复查未通过时终端拒绝运行 plan。
- 终端会自动附加会话内的证据上下文（探测、headed 探索、运行记录），`evidence_summary` 仍应写清关键事实来源。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "user_request": "每天早上登录后台导出昨天的营业日报到本机",
  "evidence_summary": "已用 inspect_web_page 探测登录页和报表页，selector 来自返回的 DOM 证据；导出按钮为 button[name='导出']",
  "planned_output_path": "Downloads/日报.xlsx"
}
```

## 运行与调试工作区

### run_plan

运行 plan 包；前置必须通过 `validate_plan` 和 `review_plan_quality`，尤其是真实网站、登录、人工介入和本机导出。

权限：requires_project_root；非 protected；受运行门禁。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| run_name | 字符串 | 否 | 无 | 可选运行名称。 |
| variable_overrides | 对象 | 否 | `{}` | 本次运行的临时变量覆盖。 |

行为要点：

- 双重门禁：未走 AI 终端质量门禁后的工具循环时直接拒绝（提示改用 `cplan run`）；工具循环内还要求最近一次 `review_plan_quality` 通过。
- 只能运行 plan 文档；入口是其他文档类型时报错。
- 运行中的 `manual_confirm` 和运行后检查由终端接管交互；执行异常时返回 `ok=false` 并附最近 `state.json`。
- 运行证据写入当前 plan 包 `output/`。

示例（终端内通过门禁后调用）：

```json
{
  "plan_path": "plans/daily-report"
}
```

### run_debug_plan

运行调试工作区内的 `injected-plan/plan.json`。

权限：requires_project_root；非 protected；不受 `run_plan` 门禁（调试副本专用）。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| run_name | 字符串 | 否 | 无 | 可选运行名称。 |
| variable_overrides | 对象 | 否 | `{}` | 本次运行的临时变量覆盖。 |

行为要点：

- 读取 workspace `manifest.json` 定位 `injected-plan/plan.json`，复用 `run_plan` 执行链（含 `manual_confirm` 交互注入）。
- 产物写入调试 plan 的运行输出，不污染原始 plan 包。
- 失败路径：workspace 缺 `manifest.json` 或注入 plan 不存在时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug"
}
```

### validate_debug_plan

校验调试工作区内的 `injected-plan/plan.json`。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |

行为要点：

- 等价于对 `injected-plan/plan.json` 跑 `validate_plan`；注入或修改调试步骤后、运行前使用。
- 失败路径：workspace 缺 `manifest.json` 时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug"
}
```

### create_debug_workspace

为 plan 包创建隔离的 `output/debug` 调试工作区。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| name | 字符串 | 否 | 无 | 可选 workspace 名称后缀；默认 `包名-debug`。 |

行为要点：

- 写入范围严格限定在当前 plan 包 `output/debug/<时间戳>-<名称>/`；原始 plan 包其余部分只读。
- 工作区结构：`source-copy/` 是原始 plan 的只读快照（不含 `output/` 与缓存）；`injected-plan/` 是可注入诊断步骤的副本；另有 `notes.md`、`report.md`、`patch.diff` 和 `manifest.json`。
- `manifest.json` 记录路径契约：只有 `patch.diff` 描述预期回写原始包的变更。
- 失败路径：plan 入口不存在时抛错。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "name": "selector-fix"
}
```

### find_debug_workspace

按名称、后缀或最近一次查找调试工作区。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| name | 字符串 | 否 | 无 | 可选 workspace 名称或后缀；省略时返回最近一次。 |

行为要点：

- 匹配规则：workspace 名称精确等于 `name`、根路径等于 `name`，或名称以 `name` 结尾。
- 失败路径：plan 没有任何调试工作区或按名称找不到时抛 `FileNotFoundError`。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "name": "selector-fix"
}
```

### list_debug_workspaces

列出某个 plan 包的调试工作区。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |

行为要点：

- 扫描 plan 包 `output/debug/` 下的目录；有 `manifest.json` 的返回完整清单，否则返回名称和根路径。
- 按名称倒序排列，最近的在前；没有任何工作区时返回空列表，不报错。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### read_debug_workspace

读取调试工作区结构和文本文件元数据，不加载完整 notes、report 或 patch 正文。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |

行为要点：

- 返回 `manifest.json`、`source-copy/` 与 `injected-plan/` 两棵目录树的结构概览（plan/config 顶层键、步骤大纲、docs/sub-plans/resources 清单），以及 notes、report、patch 的路径和大小元数据。
- 正文用 `grep_project_text` 定位、`read_project_file_slice` 读片段。
- 失败路径：workspace 缺 `manifest.json` 或其缺少必需键时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug"
}
```

### inject_debug_steps

向 `injected-plan/` 注入诊断步骤。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| presets | 字符串数组 | 是 | 无 | 诊断预设列表：`print`、`variables`、`manual_confirm`、`screenshot`、`html`、`desktop_screenshot`、`desktop_snapshot`、`desktop_observe`、`desktop_windows`。 |
| message | 字符串 | 否 | 无 | `print`/`manual_confirm` 消息。 |
| browser | 字符串 | 否 | 无 | `screenshot`/`html` 必填的浏览器会话名。 |
| page | 字符串 | 否 | 无 | `screenshot`/`html` 可选页面名。 |
| desktop | 字符串 | 否 | 无 | `desktop_*` 预设使用的桌面会话名；默认 `desktop`。 |
| position | 字符串 | 否 | `"end"` | 注入位置：`start`、`end`、`before_step` 或 `after_step`。 |
| step | 整数 | 否 | 无 | `before_step`/`after_step` 的 1-based 锚点步骤。 |

行为要点：

- 只修改 `injected-plan/plan.json`，不触碰原始 plan 包和 `source-copy/`；注入前自动把当前 plan 备份到 `injected-plan/.debug-backups/`。
- 预设映射：`print` 生成 `print` 步骤；`variables` 写变量快照到 `debug/`；`screenshot`/`html` 用 `capture`；`desktop_*` 用 `desktop_capture`/`desktop_window`，产物均写入 `debug/` 分区。
- 每次注入会向 `notes.md` 追加注入记录（时间、位置、注入的步骤 JSON）。
- 失败路径：preset 不在支持列表、`screenshot`/`html` 缺 `browser`、`position` 非法或 `step` 超出范围时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug",
  "presets": ["print", "variables", "screenshot"],
  "browser": "main",
  "position": "before_step",
  "step": 3
}
```

### write_debug_workspace_file

只写入 `injected-plan/`、`notes.md` 或 `report.md` 中允许的文件。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| root | 字符串 | 否 | `"injected-plan"` | 目标根目录：`injected-plan`、`notes` 或 `report`。 |
| relative_path | 字符串 | 否 | `"plan.json"` | `injected-plan` 下的路径；`notes`/`report` 会忽略该字段。 |
| content | 字符串 | 否 | 无 | 文本内容；与 `json_value` 二选一。 |
| json_value | 任意 JSON | 否 | 无 | JSON 内容，可替代 `content`。 |
| mode | 字符串 | 否 | `"overwrite"` | 写入模式：`overwrite` 或 `append`。 |

行为要点：

- 写入范围由 manifest 限定在调试工作区内；`injected-plan` 下只允许 `plan.json`、`config.json`、`docs/`、`resources/`、`sub-plans/`，拒绝 `output/`、`.debug-backups/`、缓存、git 等路径。
- `append` 模式只允许用于 `notes` 和 `report`；`injected-plan` 只能 overwrite。
- 失败路径：`content` 与 `json_value` 同时提供或都不提供、`root` 非法、路径越界时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug",
  "root": "notes",
  "content": "## 发现\n失败步骤 3 的 selector 依赖动态 id。",
  "mode": "append"
}
```

### patch_debug_workspace_json

对 `injected-plan/` 下的 JSON 文件执行最小 JSON 路径修改。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| root | 字符串 | 否 | `"injected-plan"` | 目标根目录；必须是 `injected-plan`。 |
| relative_path | 字符串 | 否 | `"plan.json"` | `injected-plan` 下 JSON 文件路径。 |
| operations | 对象数组 | 是 | 无 | JSON patch 操作数组；`op` 只支持 `add`、`replace`、`remove`，`add`/`replace` 必须带 `value`，`path` 使用 JSON 路径。 |

行为要点：

- 读取原文本并保留换行风格，按操作变更后最小化写回；返回写入策略和操作数。
- 失败路径：`root` 不是 `injected-plan`、目标不是 `.json`、文件不存在、不是有效 JSON、`operations` 为空数组时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug",
  "relative_path": "plan.json",
  "operations": [
    {
      "op": "replace",
      "path": "/steps/2/selector",
      "value": "button[name='导出']"
    }
  ]
}
```

## 失败分析与修复

### analyze_latest_run_failure

分析最近一次失败运行的证据，包括日志、事件、截图、HTML、页面状态、DOM 摘要和桌面 diagnostics 修复建议。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| output_dir | 字符串 | 否 | 无 | 可选指定运行输出目录；空则取最近一次运行。 |
| log_lines | 整数 | 否 | `80` | 包含的日志行数；工具会限幅（上限 200）。桌面失败会额外返回 desktop_diagnostics 和 desktop_repair_suggestions。 |
| event_lines | 整数 | 否 | `80` | 包含的事件行数；工具会限幅（上限 200）。 |

行为要点：

- 汇总 `state.json`、`result.json`、`events.jsonl`、`commands.jsonl`、`run.log` 尾部、`report.md` 预览，以及 `failure-screenshots/`、`failure-html/`、`failure-page-state/`、`failure-desktop-screenshots/`、`failure-desktop-state/` 清单。
- 识别失败步骤并带出 plan 上下文与修复提示；是 `prepare_failure_debug_workspace` 和 `propose_debug_fix` 的证据来源。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### read_latest_run_state

读取最近运行输出中的 `state.json`。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |

行为要点：

- 定位 plan 包 `output/` 下最近一次运行目录；没有运行记录时回退读 `output/` 根。只读。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### read_latest_run_report

读取最近运行输出中的 `report.md`。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |

行为要点：

- 只读；返回报告文本预览（限幅约 64KB），超过会截断并标记。

示例：

```json
{
  "plan_path": "plans/daily-report"
}
```

### read_run_log

读取运行输出中的 `run.log`。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| output_dir | 字符串 | 否 | 无 | 可选指定运行输出目录；空则取最近一次运行。 |
| lines | 整数 | 否 | `80` | 读取行数；从尾部取，工具会限幅（上限 200）。 |

行为要点：

- 只读；返回日志尾部行。失败分析优先用 `analyze_latest_run_failure`。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "lines": 120
}
```

### read_run_events

读取运行输出中的 `events.jsonl`。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| output_dir | 字符串 | 否 | 无 | 可选指定运行输出目录；空则取最近一次运行。 |
| lines | 整数 | 否 | `40` | 读取事件数；从尾部取，工具会限幅（上限 200）。 |

行为要点：

- 只读；返回事件尾部行，适合核对单步行为和守卫模式细节。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "lines": 60
}
```

### prepare_failure_debug_workspace

基于失败运行证据创建调试工作区，并在失败步骤前注入诊断。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| output_dir | 字符串 | 否 | 无 | 可选失败运行输出目录；空则取最近一次运行。 |
| name | 字符串 | 否 | 无 | 可选 workspace 名称后缀；默认 `failure-debug`。 |
| include_manual_confirm | 布尔 | 否 | `false` | 是否在失败步骤前注入 `manual_confirm`。 |

行为要点：

- 组合流程：先跑失败分析，创建调试工作区，再按失败上下文自动挑选预设（`print`、`variables`，浏览器失败加 `html`，桌面失败加 `desktop_snapshot`/`desktop_observe`/`desktop_windows`）注入到失败步骤前。
- 写入范围与 `create_debug_workspace` 相同：当前 plan 包 `output/debug/` 下，原始 plan 不变。
- 失败路径：最近运行状态不是 `failed` 时拒绝，提示先运行或传入失败的 `output_dir`。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "include_manual_confirm": true
}
```

### propose_debug_fix

在调试工作区内生成保守的干净修复候选。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| user_hint | 字符串 | 否 | `""` | 可选用户提示，用于候选排序。 |
| apply | 布尔 | 否 | `false` | 把选中修复写入 `injected-plan/`。 |
| run_after_apply | 布尔 | 否 | `false` | 应用候选后运行调试 plan。 |
| run_name | 字符串 | 否 | 无 | `run_after_apply` 时的可选运行名称。 |

行为要点：

- 先对原始 plan 跑失败分析，再从证据推断修复候选并排序；无法推断时返回 `ok=false` 和原因。
- `apply=true` 需通过自动应用门禁（候选保守且证据充分，必要时用更明确的 `user_hint`）；应用时先把 `injected-plan/plan.json` 重置回 source 快照，再写入选中 patch，然后校验并生成 `patch.diff`。
- 写入范围只在调试工作区 `injected-plan/`；生成的 patch 经明确审批并应用前，原始 plan 不会改变。
- `run_after_apply=true` 时校验通过才运行，校验失败则返回未运行的原因。
- 失败路径：workspace 缺 `manifest.json`、无候选或门禁未通过时返回失败信息。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug",
  "user_hint": "导出按钮 selector 失效，改用 role=button name=导出",
  "apply": true,
  "run_after_apply": true
}
```

### generate_debug_patch

比较 `source-copy/` 和 `injected-plan/` 生成 `patch.diff`；返回补丁元数据，不返回完整正文。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |

行为要点：

- 对两侧目录做字节级比较，用统一 diff 写入工作区 `patch.diff`，并向 `notes.md` 追加记录；比较时忽略 `output/`、`.debug-backups/`、缓存、git、pyc 等路径。
- 返回变更文件列表、补丁路径和大小；正文用 `grep_project_text` 搜索、`read_project_file_slice` 读片段。
- 失败路径：workspace 缺 `manifest.json` 时抛错。

示例：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug"
}
```

### apply_debug_patch_after_approval

在用户明确批准后，把 `patch.diff` 应用回原始 plan 包。

权限：**protected**（唯一受保护工具）；不需要 project_root。只能通过 AI 终端人工审批流程执行：AI 发起申请，用户在终端 `/approve` 后由终端注入确认字段放行，`/reject` 可带理由拒绝。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| workspace | 字符串 | 是 | 无 | debug workspace 根路径。 |
| approved | 布尔 | 否 | `false` | AI 终端在 `/approve` 后注入的确认字段；调用方不应手填。 |

行为要点：

- 应用前流程：`patch.diff` 为空时先生成；先做补丁可应用校验，再把原始 plan 待改文件备份到工作区 `.debug-backups/`，最后应用补丁到原始 plan 包并向 `notes.md` 追加记录。
- 三重门禁：未走人工审批直接调用被注册表拒绝；审批字段为 `false` 被拒绝；会话内没有有效的 `/approve` 恢复状态被拒绝。
- 失败路径：补丁校验不通过或应用失败时抛错，原始文件已有备份可恢复。

示例（由终端审批流程注入后执行）：

```json
{
  "workspace": "plans/daily-report/output/debug/20260917-093000-daily-report-debug"
}
```

## 输出与产物

### list_output_artifacts

列出当前 plan 包 `output/` 目录下的文件。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| filter_text | 字符串 | 否 | `""` | 可选产物过滤条件。 |
| limit | 整数 | 否 | `100` | 最大返回产物数；工具会限幅（上限 200）。 |

行为要点：

- 只读；返回产物的相对路径、大小和修改时间，按路径排序。定位后用 `read_output_artifact` 读内容。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "filter_text": "report"
}
```

### read_output_artifact

在 grep 或列表定位后，读取 `output/` 下某个产物的受限片段。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| relative_path | 字符串 | 是 | 无 | 相对于 plan 包 `output/` 目录的路径。 |
| max_bytes | 整数 | 否 | `64000` | 返回字节上限；工具会限幅（上限 64000）。 |

行为要点：

- 只读；只处理文本类产物（`.csv`、`.html`、`.json`、`.jsonl`、`.log`、`.md`、`.txt`、`.xml`、`.yaml`、`.yml`），超过上限截断并标记。
- 失败路径：产物不存在时抛错。

示例：

```json
{
  "plan_path": "plans/daily-report",
  "relative_path": "20260917-090000/report.md"
}
```

## 调度

### list_schedules

列出当前运行根 `schedules.json` 中的长期定时计划。

权限：requires_project_root；非 protected。

本工具没有参数。

行为要点：

- 只读；返回每个 schedule 的 id、目标 plan、触发器、时区、启用状态和超时配置。

示例：

```json
{}
```

### add_schedule

新增或覆盖 cplan schedule；每天执行用 `daily_at`，固定间隔用 `every_seconds`。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| schedule_id | 字符串 | 是 | 无 | schedule id，不能包含空白字符。 |
| plan_path | 字符串 | 是 | 无 | plan.json 路径或 plan 包目录。 |
| daily_at | 字符串 | 否 | `""` | 每天执行时间，格式 `HH:MM`；和 `every_seconds` 二选一。 |
| every_seconds | 数字 | 否 | 无 | 固定间隔秒数；和 `daily_at` 二选一。 |
| run_immediately | 布尔 | 否 | `false` | interval 首次 daemon 扫描是否立即运行。 |
| schedule_project_root | 字符串 | 否 | `""` | 该 schedule 运行 plan 时使用的 project root；空则当前运行根。 |
| timezone_name | 字符串 | 否 | `"Asia/Shanghai"` | 时区。 |
| enabled | 布尔 | 否 | `true` | 创建后是否启用。 |
| timeout_seconds | 整数 | 否 | 无 | 单次运行超时秒数。 |
| run_name | 字符串 | 否 | 无 | 可选运行名称；空则使用 schedule id。 |
| replace | 布尔 | 否 | `false` | 是否覆盖同 id schedule。 |

行为要点：

- 写入当前运行根 `schedules.json`；`daily_at` 和 `every_seconds` 必须恰好提供一个。
- 失败路径：两者都提供或都不提供、id 含空白字符时抛错。

示例：

```json
{
  "schedule_id": "daily-report-9am",
  "plan_path": "plans/daily-report",
  "daily_at": "09:00"
}
```

### remove_schedule

删除一个 cplan schedule。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| schedule_id | 字符串 | 是 | 无 | schedule id。 |

行为要点：

- 从 `schedules.json` 删除；id 不存在时返回失败信息。

示例：

```json
{
  "schedule_id": "daily-report-9am"
}
```

### enable_schedule

启用一个 cplan schedule。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| schedule_id | 字符串 | 是 | 无 | schedule id。 |

行为要点：

- 把指定 schedule 置为启用；id 不存在时返回失败信息。

示例：

```json
{
  "schedule_id": "daily-report-9am"
}
```

### disable_schedule

禁用一个 cplan schedule。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| schedule_id | 字符串 | 是 | 无 | schedule id。 |

行为要点：

- 把指定 schedule 置为禁用，不删除；id 不存在时返回失败信息。

示例：

```json
{
  "schedule_id": "daily-report-9am"
}
```

### run_schedule_now

立即运行一个 cplan schedule；当前 AI 工具直调会拒绝，确定性运行请使用 `cplan schedule run-now`。

权限：requires_project_root；非 protected；受运行门禁。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| schedule_id | 字符串 | 是 | 无 | schedule id。 |

行为要点：

- 与 `run_plan` 共用运行门禁：AI 工具直调一律拒绝，错误提示改用 `cplan schedule run-now`。
- 本文档列出它是因为它属于注册工具集；实际触发立即运行走 cplan CLI。

示例（当前会被门禁拒绝，仅示意参数）：

```json
{
  "schedule_id": "daily-report-9am"
}
```

## 项目文件与会话归档

### grep_project_text

用 ripgrep 渐进式搜索项目文本，再按需读取文件片段；路径不存在时会返回候选路径供继续修正。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| pattern | 字符串 | 是 | 无 | ripgrep 搜索文本或正则。 |
| root_path | 字符串 | 否 | `"."` | 项目相对目录/文件。查 handbook action 文档先定位真实路径，按 browser/desktop/common 分类查，不直接猜单页路径。 |
| literal | 布尔 | 否 | `true` | 按固定字符串搜索。 |
| include_output | 布尔 | 否 | `false` | 是否包含 plan `output/`；仅明确需要时开启。 |
| file_glob | 字符串 | 否 | `""` | 可选 rg glob，如 `*.md` 或 `**/*.json`。 |
| context_lines | 整数 | 否 | `0` | 命中上下文行数；工具会限幅（上限 5）。 |
| max_matches | 整数 | 否 | `50` | 最大命中数；工具会限幅（上限 100）。 |

行为要点：

- 依赖本机 ripgrep（`rg`）；缺失时返回安装建议，不使用系统搜索兜底。
- 默认排除 `output/`、浏览器 profiles、会话与 checkpoint 目录、缓存、git、pyc 等路径。
- 搜索路径不存在时不报错终止，返回错误提示加候选路径列表（含 handbook action 分类目录下的匹配文件）。
- 单行超过 1000 字符截断；命中数达到上限时标记 `truncated`。

示例：

```json
{
  "pattern": "manual_confirm",
  "file_glob": "**/*.json"
}
```

### read_project_file_slice

在 grep 或列表定位后，读取某个项目文件的受限行片段。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| path | 字符串 | 是 | 无 | 项目相对路径，或项目根内绝对路径。 |
| start_line | 整数 | 否 | `1` | 起始行，1-based。 |
| line_count | 整数 | 否 | `80` | 读取行数；工具会限幅（上限 200）。 |
| max_bytes | 整数 | 否 | `64000` | 返回字节上限；工具会限幅（上限 64000）。 |

行为要点：

- 只读；路径必须位于项目根内，拒绝读取浏览器 profiles/browser 状态、缓存、checkpoint、git、pyc、egg-info 路径。
- 超过字节上限时截断当前行并标记 `truncated`。
- 失败路径：文件不存在或不是文件时抛错。

示例：

```json
{
  "path": "handbook/reference/config.md",
  "start_line": 1,
  "line_count": 40
}
```

### read_compression_archive

受限读取当前 AI 终端线程的压缩归档：列出归档、读取摘要、搜索或读取 `messages.jsonl` 小片段。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| thread_id | 字符串 | 否 | `""` | AI 终端 thread id；终端内自动注入，CLI 手动调用必填。 |
| mode | `list`/`summary`/`messages`/`manifest`/`search` | 否 | `"summary"` | 读取模式。 |
| archive_path | 字符串 | 否 | `""` | 可选归档目录或 `summary`/`messages`/`manifest` 文件路径；空则最近归档。 |
| pattern | 字符串 | 否 | `""` | `search` 模式搜索文本或正则。 |
| literal | 布尔 | 否 | `true` | `search` 是否按固定字符串。 |
| start_line | 整数 | 否 | `1` | `summary`/`messages` 起始行，1-based。 |
| line_count | 整数 | 否 | `80` | `summary`/`messages` 行数；工具会限幅（上限 200）。 |
| max_bytes | 整数 | 否 | `64000` | `summary`/`messages` 字节上限；工具会限幅（上限 64000）。 |
| max_matches | 整数 | 否 | `50` | `search` 最大命中数；工具会限幅（上限 100）。 |
| max_archives | 整数 | 否 | `20` | `list` 最大归档数；工具会限幅（上限 100）。 |

行为要点：

- 读取范围严格限定在当前线程本地会话目录的 `compressions/<archive>/` 下；`archive_path` 解析后必须落在该目录内，否则拒绝。
- `list` 列出归档清单（时间、原因、消息数、token 数、摘要预览）；`summary`/`messages` 按行限幅读取；`manifest` 读取归档元数据；`search` 在 `summary.md`、`manifest.json`、`messages.jsonl` 内搜索并给出命中行。
- `messages` 模式把每行提炼为角色和内容摘要，过长内容截断。
- `search` 依赖本机 ripgrep（`rg`），`pattern` 为空时拒绝。
- 失败路径：`thread_id` 为空、归档目录或目标文件不存在时抛错。

示例：

```json
{
  "mode": "list"
}
```

## 工作计划

### update_work_plan

维护当前唯一用户可见工作计划；首次 `start`，进行中 `continue`，完成 `complete`，放弃 `cancel`。

权限：非 protected；不需要 project_root。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| items | 对象数组 | 是 | 无 | 当前唯一可见工作计划的完整快照；复杂任务通常 3-7 步，最多一个 `in_progress`。每项字段：`title`（必填，用户可见短标题）、`status`（必填，`pending`/`in_progress`/`completed`）、`note`（可选短说明，只写客观进展/阻塞/验收）。 |
| summary | 字符串 | 否 | `""` | 可选一句话目标/阶段；`items` 为空可清空计划。 |
| operation | `start`/`continue`/`complete`/`cancel` | 否 | `"continue"` | 计划生命周期操作：`start` 仅在没有进行中计划时创建；`continue` 更新当前计划；`complete`/`cancel` 结束当前计划。用户后续消息默认是当前计划的引导。 |

行为要点：

- `items` 最多 12 项（超出截断）；`title` 上限 120 字符、`note` 上限 180 字符、`summary` 上限 160 字符；最多一个 `in_progress`。
- 生命周期由终端状态机校验：`active` 计划未结束前禁止 `start` 第二份待办；已结束计划不能用 `continue` 重开；没有进行中计划不能 `complete`/`cancel`；`complete` 前所有待办项必须 `completed`。
- 这是终端 UI 能力，不产生文件副作用。

示例：

```json
{
  "summary": "完成日报自动化 plan",
  "operation": "start",
  "items": [
    {
      "title": "创建 plan 包并探测登录页",
      "status": "completed"
    },
    {
      "title": "编写导出步骤并运行取证",
      "status": "in_progress"
    },
    {
      "title": "配置每日 9 点调度",
      "status": "pending"
    }
  ]
}
```

## 页面与桌面检查

### inspect_web_page

一次性打开 URL/本地 HTML，返回受限 DOM、表单、按钮、链接、表格和登录/验证证据；真实流程用 headed 探索 plan。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| url | 字符串 | 是 | 无 | 要探测的 HTTP(S)、file URL 或本地项目文件。 |
| wait_until | 字符串 | 否 | `"domcontentloaded"` | 导航等待状态：`commit`/`domcontentloaded`/`load`/`networkidle`。 |
| timeout_ms | 整数 | 否 | `15000` | 导航超时毫秒；工具会限幅（1000-60000）。 |
| wait_ms | 整数 | 否 | `1000` | 导航后额外等待毫秒；工具会限幅（0-10000）。 |
| max_elements | 整数 | 否 | `80` | 最多返回标题、字段、按钮、链接、表单和表格数；工具会限幅（1-120）。 |
| text_limit | 整数 | 否 | `6000` | 正文预览字符上限；工具会限幅（200-12000）。 |
| headed | 布尔 | 否 | `false` | 仅显示一次性探测浏览器；真实交互改用 headed 探索 plan 加 `manual_confirm`。 |

行为要点：

- 启动一次性 Chromium（默认无头，视口 1365x900），导航超时不终止，会返回 `navigation_error` 并继续提取当时可见的页面。
- 本地文件路径必须位于项目根内，转为 `file://` URL 探测。
- 检测登录字段和验证码/人机验证信号并放入 `auth` 证据，附下一步建议；selector 证据用于写浏览器步骤，不能凭空猜。
- 浏览器会话用完即关，不保留登录态；真实交互流程用 headed 探索 plan，需要用户介入时在同一 Playwright 浏览器窗口用 `manual_confirm` 交接。

示例：

```json
{
  "url": "https://example.com/login"
}
```

### inspect_desktop

一次性探测当前桌面，返回权限/依赖、窗口列表、可选控件 dump 和可选截图路径；写 desktop plan 前先用它确认窗口和控件定位。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| platform_name | `auto`/`windows`/`macos` | 否 | `"auto"` | 桌面平台；`auto` 使用当前系统，显式指定时必须与当前系统一致。 |
| backend | `auto`/`native` | 否 | `"auto"` | 桌面 backend；当前工具只使用 native。 |
| request_permissions | 布尔 | 否 | `false` | 是否主动触发可探测的系统权限检查；返回结构与 `desktop_capture type=observe` 的统一观察 payload 对齐，并包含 target_candidates 定位候选和 coordinate_profile 坐标事实。 |
| include_windows | 布尔 | 否 | `true` | 是否返回窗口列表。 |
| include_invisible | 布尔 | 否 | `false` | 窗口列表是否包含不可见窗口。 |
| include_elements | 布尔 | 否 | `false` | 是否对匹配窗口做控件 dump；缺少窗口定位时默认使用当前聚焦窗口。 |
| include_screenshot | 布尔 | 否 | `false` | 是否保存一次桌面截图到 AI 终端本地检查目录（desktop-inspections）并返回路径。 |
| title | 字符串 | 否 | `""` | 窗口标题精确匹配。 |
| title_contains | 字符串 | 否 | `""` | 窗口标题包含文本。 |
| title_regex | 字符串 | 否 | `""` | 窗口标题正则。 |
| app | 字符串 | 否 | `""` | App/进程名称包含文本。 |
| process | 字符串 | 否 | `""` | 进程名称包含文本。 |
| process_name | 字符串 | 否 | `""` | 进程名称包含文本。 |
| class_name | 字符串 | 否 | `""` | 窗口 class_name 包含文本。 |
| window_id | 字符串 | 否 | `""` | 窗口 id。 |
| match_index | 整数 | 否 | `0` | 多窗口命中时的索引。 |
| element_locator | 对象 | 否 | `{}` | 可选 desktop_element locator 对象，如 `automation_id`、`name_contains`、`control_type`、`text_contains`。 |
| max_windows | 整数 | 否 | `20` | 最多返回窗口数；工具会限幅（1-50）。 |
| max_elements | 整数 | 否 | `120` | 最多返回控件数；工具会限幅（1-300）。 |
| max_depth | 整数 | 否 | `4` | 控件树最大深度；工具会限幅（0-8）。 |
| text_limit | 整数 | 否 | `120` | 控件文本截断长度；工具会限幅（0-500）。 |

行为要点：

- 用 native backend 做一次统一观察；macOS Accessibility、Screen Recording 等权限只做可探测的检查并立即返回当前状态，不会打开系统设置、不等待用户授权，也不能静默授权；未授权时相关能力不可用。
- 窗口查询字段组合使用，命中多窗口时用 `match_index` 选定；控件 dump 需先有明确窗口定位或使用当前聚焦窗口。
- 截图只写到项目内 AI 终端本地检查目录并返回路径；不自动截屏，未开 `include_screenshot` 不会有截图副作用。
- 失败路径：backend 或 platform 不支持、当前系统与显式 platform 不一致时抛错。

示例：

```json
{
  "include_windows": true,
  "title_contains": "日报",
  "include_elements": true
}
```

## 本机命令与导出

### run_local_command

直接执行任意本机命令，用于安装依赖、调用包管理器、检查环境或运行项目命令。不会拦截命令内容、路径、环境变量或 stdout/stderr；非零退出码和超时也返回原始结果供继续处理。

权限：requires_project_root；非 protected。它不是 plan action，不能写入 `steps`。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| command | 字符串 | 否 | `""` | 通过 shell 执行的任意本机命令文本；与 `argv` 二选一。 |
| argv | 字符串数组 | 否 | `[]` | 直接执行的任意本机程序及参数；与 `command` 二选一。 |
| shell | 字符串 | 否 | `"auto"` | `command` 使用的 shell：`auto`、`pwsh`、`powershell`、`cmd`、`bash`、`sh` 或 `zsh`；任意程序可使用 `argv`。 |
| cwd | 字符串 | 否 | `""` | 工作目录；空使用当前项目根目录，支持任意本机绝对或相对路径。 |
| env | 对象 | 否 | `{}` | 追加或覆盖的本机环境变量，保留原文。 |
| stdin | 字符串 | 否 | 无 | 可选标准输入文本，按 UTF-8 原样传入。 |
| timeout_seconds | 数字 | 否 | `0` | 命令超时秒数；0 或负数表示不设超时。 |

行为要点：

- `command` 和 `argv` 必须恰好提供一个；`shell=auto` 在 Windows 用 `pwsh`、其他系统用 `sh`。
- 环境继承当前进程后按 `env` 覆盖；输出按 UTF-8 解码（失败字节替换）原样返回。
- 超时返回 `timed_out=true` 和已捕获的输出；非零退出码返回 `ok=false` 和原始 `exit_code`，不视为工具错误。
- 失败路径：`command` 与 `argv` 同时提供或都不提供、shell 名不支持时抛错。

示例：

```json
{
  "command": "rg --version"
}
```

### export_local_file

把最终交付物写到用户指定本机路径，或从当前 plan `output/` 复制过去；Downloads、桌面、绝对路径必须用它交付。

权限：requires_project_root；非 protected。

| 参数 | 类型 | 必填 | 默认值 | 用途与注意事项 |
| --- | --- | --- | --- | --- |
| target_path | 字符串 | 是 | 无 | 项目外的本机目标路径：绝对路径或 `~` 路径，例如 `~/Downloads/AI账户.txt`。 |
| content | 字符串 | 否 | 无 | 文本内容。 |
| json_value | 任意 JSON | 否 | 无 | JSON 内容，可替代 `content`，按缩进写入。 |
| plan_path | 字符串 | 否 | `""` | 复制 output 产物时的 plan.json 或包目录。 |
| source_output_path | 字符串 | 否 | `""` | 可选 `output/` 相对源产物；提供则复制到 `target_path`。 |
| mode | 字符串 | 否 | `"overwrite"` | `overwrite` 或 `append`；复制源产物只支持 overwrite。 |

行为要点：

- `content`、`json_value`、`source_output_path` 三者必须恰好提供一个；复制产物时必须提供 `plan_path`。
- 目标必须在项目根外；项目内 plan/config/resources/debug/source 文件用受控 plan 或 debug 工具写入，运行证据写当前 plan 包 `output/`。
- `source_output_path` 相对于 plan `output/`，不能以 `output/` 开头，且必须位于该目录内。
- 自动创建目标父目录；返回写入字节数。
- 失败路径：目标是目录、目标在项目内、源产物不存在、参数组合非法时抛错。

示例：

```json
{
  "target_path": "~/Downloads/日报.xlsx",
  "plan_path": "plans/daily-report",
  "source_output_path": "20260917-090000/日报.xlsx"
}
```
