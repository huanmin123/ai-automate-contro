from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListPlanPackagesArgs(ToolArgsModel):
    filter_text: str = Field(default="", description="可选文本过滤条件。")


class InspectWebPageArgs(ToolArgsModel):
    url: str = Field(..., description="创建浏览器步骤前要检查的 HTTP(S) URL、file URL 或本地项目文件。")
    wait_until: str = Field(default="domcontentloaded", description="Playwright 导航等待状态：commit、domcontentloaded、load 或 networkidle。")
    timeout_ms: int = Field(default=15_000, description="导航超时时间，单位毫秒；工具会限制到安全上限。")
    wait_ms: int = Field(default=1_000, description="导航后额外等待时间，单位毫秒，用于客户端渲染内容；工具会限制。")
    max_elements: int = Field(default=80, description="最多返回的可见标题、字段、按钮、链接、表单和表格数量；工具会限制。")
    text_limit: int = Field(default=6_000, description="最多返回的正文预览字符数；工具会限制。")
    headed: bool = Field(default=False, description="是否显示一次性探测浏览器；真实流程或需要用户操作时应改用 open_browser.headed=true 的探索 plan + manual_confirm。")


class GrepProjectTextArgs(ToolArgsModel):
    pattern: str = Field(..., description="要用 ripgrep 搜索的文本或正则表达式。")
    root_path: str = Field(default=".", description="要搜索的项目相对目录或文件；查 handbook action 时先用 handbook/actions 或 handbook/README.md 定位，不要猜 handbook/actions/<action>。")
    literal: bool = Field(default=True, description="使用固定字符串搜索，而不是正则表达式。")
    include_output: bool = Field(default=False, description="只有明确需要时才包含 plan output/ 目录。")
    file_glob: str = Field(default="", description="可选 ripgrep glob，例如 *.md 或 **/*.json。")
    context_lines: int = Field(default=0, description="命中附近的上下文行数；工具会限制到较小上限。")
    max_matches: int = Field(default=50, description="最多返回的命中行数；工具会限制到较小上限。")


class ReadProjectFileSliceArgs(ToolArgsModel):
    path: str = Field(..., description="项目相对路径，或项目根目录下的绝对路径。")
    start_line: int = Field(default=1, description="要读取的起始行，按 1 开始计数。")
    line_count: int = Field(default=80, description="要读取的行数；工具会限制到较小上限。")
    max_bytes: int = Field(default=64_000, description="最多返回的文本字节数；工具会限制到较小上限。")


class ReadCompressionArchiveArgs(ToolArgsModel):
    thread_id: str = Field(default="", description="AI 终端 thread id；AI 终端内会自动注入，CLI 手动调用时必填。")
    mode: Literal["list", "summary", "messages", "manifest", "search"] = Field(
        default="summary",
        description="读取模式：list 列归档，summary 读摘要，messages 读消息片段，manifest 读清单，search 搜索归档。",
    )
    archive_path: str = Field(default="", description="可选归档目录，或 summary.md/messages.jsonl/manifest.json 路径；省略时使用最近归档。")
    pattern: str = Field(default="", description="search 模式要搜索的文本或正则表达式。")
    literal: bool = Field(default=True, description="search 模式是否按固定字符串搜索。")
    start_line: int = Field(default=1, description="summary/messages 模式读取起始行，按 1 开始计数。")
    line_count: int = Field(default=80, description="summary/messages 模式读取行数；工具会限制到较小上限。")
    max_bytes: int = Field(default=64_000, description="summary/messages 模式最多返回文本字节数；工具会限制到较小上限。")
    max_matches: int = Field(default=50, description="search 模式最多返回命中数；工具会限制到较小上限。")
    max_archives: int = Field(default=20, description="list 模式最多返回归档数；工具会限制到较小上限。")


class WorkPlanItemArgs(ToolArgsModel):
    title: str = Field(..., description="用户可见的短步骤标题，不写隐藏推理。")
    status: Literal["pending", "in_progress", "completed"] = Field(
        ...,
        description="步骤状态；同一计划最多一个 in_progress。",
    )
    note: str = Field(default="", description="可选短说明，只写客观进展、阻塞或验收信息。")


class UpdateWorkPlanArgs(ToolArgsModel):
    items: list[WorkPlanItemArgs] = Field(
        ...,
        description="完整替换当前可见工作计划。简单任务可以不调用；复杂任务通常 3-7 步，最多一个 in_progress。",
    )
    summary: str = Field(default="", description="可选一句话概括当前目标或阶段。传空列表可清空计划。")


class ReadPlanPackageArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class CreatePlanPackageArgs(ToolArgsModel):
    package_path: str | None = Field(default=None, description="目标 plan 包目录。省略时使用配置的默认 plan 根目录和 plan 名称。")
    name: str | None = Field(default=None, description="plan 名称。省略 package_path 时必填。")
    force: bool = Field(default=False, description="允许使用已有的非空包目录。")


class WritePlanPackageFileArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    relative_path: str = Field(..., description="plan 包内允许写入的路径：plan.json、config.json、docs/**、resources/** 或 sub-plans/*-plan.json。")
    content: str | None = Field(default=None, description="要写入的文本内容。")
    json_value: Any = Field(
        default=None,
        description="写入 plan/config/sub-plan JSON 文件时可替代 content 的 JSON 值。浏览器 plan 必须使用当前 action 字段，例如 wait.type=time + seconds 表示固定等待，aria_snapshot.mode 只能是 default 或 ai。",
    )
    mode: str = Field(default="overwrite", description="写入模式：overwrite 或 append。")


class ValidatePlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class RunPlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    run_name: str | None = Field(default=None, description="可选运行名称。")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="临时变量覆盖。",
    )


class ReadLatestRunStateArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class ReadLatestRunReportArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class AnalyzeLatestRunFailureArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选的指定运行输出目录。")
    log_lines: int = Field(default=80, description="要包含的日志行数。")
    event_lines: int = Field(default=80, description="要包含的事件行数。")


class ReadRunLogArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选的指定运行输出目录。")
    lines: int = Field(default=80, description="要读取的行数。")


class ReadRunEventsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选的指定运行输出目录。")
    lines: int = Field(default=40, description="要读取的事件数量。")


class ListOutputArtifactsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    filter_text: str = Field(default="", description="可选产物过滤条件。")
    limit: int = Field(default=100, description="最多返回的产物数量。")


class ReadOutputArtifactArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    relative_path: str = Field(..., description="相对于 plan 包 output/ 目录的路径。")
    max_bytes: int = Field(default=64_000, description="最多返回的文本字节数；工具会限制过大的请求。")


class CreateDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    name: str | None = Field(default=None, description="可选调试工作区名称后缀。")


class ListDebugWorkspacesArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class FindDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    name: str | None = Field(default=None, description="可选调试工作区名称或后缀。")


class ReadDebugWorkspaceArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")


class PrepareFailureDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选失败运行输出目录。")
    name: str | None = Field(default=None, description="可选调试工作区名称后缀。")
    include_manual_confirm: bool = Field(
        default=False,
        description="是否在失败步骤前注入 manual_confirm。",
    )


class InjectDebugStepsArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    presets: list[str] = Field(..., description="要注入的诊断预设。")
    message: str | None = Field(default=None, description="print 或 manual_confirm 预设使用的消息。")
    browser: str | None = Field(default=None, description="screenshot/html 预设使用的浏览器会话名。")
    page: str | None = Field(default=None, description="screenshot/html 预设使用的页面名。")
    position: str = Field(default="end", description="注入位置：start、end、before_step 或 after_step。")
    step: int | None = Field(default=None, description="before_step 或 after_step 使用的 1-based 锚点步骤。")


class WriteDebugWorkspaceFileArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    root: str = Field(default="injected-plan", description="目标根目录：injected-plan、notes 或 report。")
    relative_path: str = Field(default="plan.json", description="injected-plan 下的路径；notes/report 会忽略该字段。")
    content: str | None = Field(default=None, description="要写入的文本内容。")
    json_value: Any = Field(default=None, description="可替代 content 的 JSON 值。")
    mode: str = Field(default="overwrite", description="写入模式：overwrite 或 append。")


class PatchDebugWorkspaceJsonArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    root: str = Field(default="injected-plan", description="目标根目录；必须是 injected-plan。")
    relative_path: str = Field(default="plan.json", description="injected-plan 下的 JSON 文件路径。")
    operations: list[dict[str, Any]] = Field(..., description="JSON patch 操作数组。")


class ProposeDebugFixArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    user_hint: str = Field(default="", description="可选用户提示，用于排序候选。")
    apply: bool = Field(default=False, description="把选中的干净修复候选写入 injected-plan/。")
    run_after_apply: bool = Field(default=False, description="应用候选后运行调试 plan。")
    run_name: str | None = Field(default=None, description="run_after_apply 为 true 时使用的可选运行名称。")


class ValidateDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")


class RunDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    run_name: str | None = Field(default=None, description="可选运行名称。")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="临时变量覆盖。",
    )


class GenerateDebugPatchArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")


class ApplyDebugPatchAfterApprovalArgs(ToolArgsModel):
    workspace: str = Field(..., description="调试工作区根路径。")
    approved: bool = Field(
        default=False,
        description="AI 终端在人工 approve 后注入的确认字段。",
    )
