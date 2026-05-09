# AI 终端与交互式执行架构

## 背景

自动化框架的核心是 plan 包。用户真正需要 AI 参与的地方，不是让模型混入每一步浏览器动作，而是让 AI 帮助维护 plan：

- 创建 plan。
- 管理 plan 配置和文档。
- 运行与观察 plan。
- 分析失败。
- 生成修复补丁。
- 产出报告。

因此 CLI 分为管理终端和 AI 终端。管理终端提供确定性命令，AI 终端通过这些命令完成 plan 级协作。

## 总体分层

```text
CLI
├── 管理终端
│   ├── 创建 plan 模板
│   ├── 校验 plan
│   ├── 运行 plan
│   ├── 查看状态、日志、输出
│   ├── 暂停、继续、停止
│   └── 修改运行变量或环境
│
└── AI 终端
    ├── 理解用户需求
    ├── 创建 plan 包
    ├── 管理 plan 文档和配置
    ├── 启动运行
    ├── 分析失败日志和输出
    ├── 生成修复补丁
    ├── 请求用户确认
    └── 生成结果报告

执行内核
├── InteractivePlanRunner
├── Event Stream
├── Command Queue
├── Run State
└── Output
```

## 管理终端

管理终端是确定性入口，不依赖 AI。

第一批命令：

- `plan create`: 创建 plan 包模板。
- `plan validate`: 校验 plan 结构、路径、组件字段和输出约束。
- `plan run`: 运行 plan。
- `plan status`: 查看当前运行状态。
- `plan pause`: 暂停正在运行的 plan。
- `plan continue`: 继续运行。
- `plan stop`: 停止运行。
- `plan set-variable`: 修改运行变量。
- `plan logs`: 查看运行日志。
- `plan output`: 打开或列出输出目录。
- `plan report`: 生成运行报告。

管理终端不猜需求，只执行明确命令。

## AI 终端

AI 终端是面向自然语言的 plan 助手。

用户可以描述目标：

```text
帮我做一个登录页自动化 plan，打开页面后等待用户名输入框，填入测试账号，再保存截图。
```

AI 终端负责：

1. 询问缺失信息。
2. 创建 plan 包。
3. 写入 `plan.json`、`config.json`、`docs/README.md`。
4. 运行校验。
5. 询问用户是否运行。
6. 运行 plan。
7. 读取日志、输出和失败截图。
8. 给出修复建议。
9. 生成补丁并请求确认。
10. 应用修复并再次验证。
11. 输出最终报告。

AI 终端不直接绕过管理终端能力。它调用管理终端暴露的工具。

## 交互式执行器

当前执行器是一跑到底的同步模型。后续需要演进为交互式执行模型。

核心对象：

```text
InteractivePlanRunner
├── run_id
├── plan_path
├── state
├── variables
├── current_step
├── event_stream
├── command_queue
└── output_dir
```

### 事件流

执行器持续输出结构化事件：

- `run_started`
- `step_started`
- `step_finished`
- `step_failed`
- `waiting_for_user`
- `user_command_received`
- `variable_changed`
- `artifact_created`
- `run_paused`
- `run_resumed`
- `run_stopped`
- `run_finished`

终端、人类用户和 AI 终端都只读事件流，不直接读执行器内部状态。

### 命令队列

执行器接收外部命令：

- `pause`
- `continue`
- `stop`
- `set_variable`
- `set_config`
- `mark_manual_step_done`
- `request_status`

命令必须可审计，写入运行日志。

### 人工交互

账号密码输入、验证码、二次验证、人工确认等场景由用户完成。plan 中可以使用人工等待动作：

```json
{
  "action": "manual_confirm",
  "prompt": "请在浏览器中完成账号密码输入，然后回到终端输入 continue。"
}
```

管理终端展示：

```text
[WAIT_USER] 请在浏览器中完成账号密码输入，然后回到终端输入 continue。
> continue
```

AI 终端可以解释等待原因，但继续执行的命令仍由用户确认。

## LangGraph 落点

AI 终端建议使用 LangGraph 作为第一版编排层。

原因：

- AI 终端是长状态任务。
- 需要 human-in-the-loop。
- 需要中断、恢复、重试。
- 需要把“运行 plan -> 读取失败 -> 修复 -> 再运行”表达成图。

推荐图结构：

```text
UserRequest
  -> IntentRouter
  -> ContextLoader
  -> PlanDesigner
  -> Validator
  -> HumanApproval
  -> PlanRunnerTool
  -> RunObserver
  -> FailureAnalyzer
  -> PatchDesigner
  -> HumanApproval
  -> PatchApplier
  -> ReportWriter
```

LangGraph 只编排 AI 工作流，不接管浏览器执行器。

## 工具边界

AI 终端只能通过工具操作项目。

第一批工具：

- `list_plan_packages`
- `read_plan_package`
- `create_plan_package`
- `validate_plan`
- `run_plan`
- `read_run_events`
- `read_run_log`
- `list_output_artifacts`
- `read_output_artifact`
- `propose_patch`
- `apply_patch_after_approval`
- `write_report`

文件修改必须形成可读补丁，并经过用户确认。

## 专项 AI 边界

专项 AI 不等于 AI 终端。专项 AI 只做可控任务：

- 图像 OCR。
- 文本分类。
- 文本结构化抽取。
- 数据清洗。
- 字段归一化。
- 简单内容生成。

专项 AI 必须具备：

- 固定输入 schema。
- 固定输出 schema。
- 固定系统提示词。
- 服务别名。
- 输出解析和校验。
- 失败产物保存到当前 plan 包 `output/ai/`。

专项 AI 不负责创建、运行、修复 plan。

## 设计结论

- CLI 是唯一操作入口。
- 管理终端负责确定性控制。
- AI 终端负责 plan 级协作。
- 交互式执行器负责事件流和命令队列。
- LangGraph 用于 AI 终端，不接管浏览器执行。
- 专项 AI 是受控数据处理组件，不参与 plan 管理。
