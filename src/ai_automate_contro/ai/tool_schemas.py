from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListPlanPackagesArgs(ToolArgsModel):
    filter_text: str = Field(default="", description="可选过滤文本。")


class InspectWebPageArgs(ToolArgsModel):
    url: str = Field(..., description="要探测的 HTTP(S)、file URL 或本地项目文件。")
    wait_until: str = Field(default="domcontentloaded", description="导航等待状态：commit/domcontentloaded/load/networkidle。")
    timeout_ms: int = Field(default=15_000, description="导航超时毫秒；工具会限幅。")
    wait_ms: int = Field(default=1_000, description="导航后额外等待毫秒；工具会限幅。")
    max_elements: int = Field(default=80, description="最多返回标题、字段、按钮、链接、表单和表格数；工具会限幅。")
    text_limit: int = Field(default=6_000, description="正文预览字符上限；工具会限幅。")
    headed: bool = Field(default=False, description="仅显示一次性探测浏览器；真实交互改用 headed 探索 plan + manual_confirm。")


class GrepProjectTextArgs(ToolArgsModel):
    pattern: str = Field(..., description="ripgrep 搜索文本或正则。")
    root_path: str = Field(default=".", description="项目相对目录/文件；查 handbook action 先定位，不猜 handbook/actions/<action>。")
    literal: bool = Field(default=True, description="按固定字符串搜索。")
    include_output: bool = Field(default=False, description="是否包含 plan output/；仅明确需要时开启。")
    file_glob: str = Field(default="", description="可选 rg glob，如 *.md 或 **/*.json。")
    context_lines: int = Field(default=0, description="命中上下文行数；工具会限幅。")
    max_matches: int = Field(default=50, description="最大命中数；工具会限幅。")


class ReadProjectFileSliceArgs(ToolArgsModel):
    path: str = Field(..., description="项目相对路径，或项目根内绝对路径。")
    start_line: int = Field(default=1, description="起始行，1-based。")
    line_count: int = Field(default=80, description="读取行数；工具会限幅。")
    max_bytes: int = Field(default=64_000, description="返回字节上限；工具会限幅。")


class ReadCompressionArchiveArgs(ToolArgsModel):
    thread_id: str = Field(default="", description="AI 终端 thread id；终端内自动注入，CLI 手动调用必填。")
    mode: Literal["list", "summary", "messages", "manifest", "search"] = Field(
        default="summary",
        description="读取模式：list/summary/messages/manifest/search。",
    )
    archive_path: str = Field(default="", description="可选归档目录或 summary/messages/manifest 路径；空则最近归档。")
    pattern: str = Field(default="", description="search 模式搜索文本或正则。")
    literal: bool = Field(default=True, description="search 是否按固定字符串。")
    start_line: int = Field(default=1, description="summary/messages 起始行，1-based。")
    line_count: int = Field(default=80, description="summary/messages 行数；工具会限幅。")
    max_bytes: int = Field(default=64_000, description="summary/messages 字节上限；工具会限幅。")
    max_matches: int = Field(default=50, description="search 最大命中数；工具会限幅。")
    max_archives: int = Field(default=20, description="list 最大归档数；工具会限幅。")


class WorkPlanItemArgs(ToolArgsModel):
    title: str = Field(..., description="用户可见的短步骤标题，不写隐藏推理。")
    status: Literal["pending", "in_progress", "completed"] = Field(
        ...,
        description="步骤状态；最多一个 in_progress。",
    )
    note: str = Field(default="", description="可选短说明，只写客观进展/阻塞/验收。")


class UpdateWorkPlanArgs(ToolArgsModel):
    items: list[WorkPlanItemArgs] = Field(
        ...,
        description="完整替换可见工作计划；复杂任务通常 3-7 步，最多一个 in_progress。",
    )
    summary: str = Field(default="", description="可选一句话目标/阶段；items 为空可清空计划。")


class ReadPlanPackageArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class CreatePlanPackageArgs(ToolArgsModel):
    package_path: str | None = Field(default=None, description="目标 plan 包目录；空则用默认 plan 根和 name。")
    name: str | None = Field(default=None, description="plan 名称。省略 package_path 时必填。")
    force: bool = Field(default=False, description="允许已有非空包目录。")


class WritePlanPackageFileArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    relative_path: str = Field(..., description="包内白名单路径：plan.json、config.json、docs/**、resources/**、sub-plans/*-plan.json。")
    content: str | None = Field(default=None, description="文本内容。")
    json_value: Any = Field(
        default=None,
        description="JSON 内容，可替代 content；浏览器字段按当前 handbook，如 wait.type=time、aria_snapshot.mode=default/ai。",
    )
    mode: str = Field(default="overwrite", description="写入模式：overwrite 或 append。")


class ImportPlanResourceFileArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    source_path: str = Field(..., description="要导入的本机源文件路径；绝对路径、~ 路径或项目相对路径。")
    relative_path: str = Field(default="", description="目标 resources/ 下相对路径；空则使用源文件名，可省略 resources/ 前缀。")
    overwrite: bool = Field(default=False, description="目标资源已存在时是否覆盖。")


class ValidatePlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class ReviewPlanQualityArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    user_request: str = Field(..., description="用户原始需求、目标或任务描述。")
    evidence_summary: str = Field(default="", description="探测、headed 探索、manual_confirm 或运行证据摘要。")
    planned_output_path: str = Field(default="", description="用户要求的最终本机交付路径，如 Downloads/AI账户.txt。")


class RunPlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    run_name: str | None = Field(default=None, description="可选运行名称。")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="本次运行的临时变量覆盖。",
    )


class ListSchedulesArgs(ToolArgsModel):
    pass


class AddScheduleArgs(ToolArgsModel):
    schedule_id: str = Field(..., description="schedule id，不能包含空白字符。")
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    daily_at: str = Field(default="", description="每天执行时间，格式 HH:MM；和 every_seconds 二选一。")
    every_seconds: float | None = Field(default=None, description="固定间隔秒数；和 daily_at 二选一。")
    run_immediately: bool = Field(default=False, description="interval 首次 daemon 扫描是否立即运行。")
    schedule_project_root: str = Field(default="", description="该 schedule 运行 plan 时使用的 project root；空则当前运行根。")
    timezone_name: str = Field(default="Asia/Shanghai", description="时区。")
    enabled: bool = Field(default=True, description="创建后是否启用。")
    timeout_seconds: int | None = Field(default=None, description="单次运行超时秒数。")
    run_name: str | None = Field(default=None, description="可选运行名称；空则使用 schedule id。")
    replace: bool = Field(default=False, description="是否覆盖同 id schedule。")


class ScheduleIdArgs(ToolArgsModel):
    schedule_id: str = Field(..., description="schedule id。")


class ReadLatestRunStateArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class ReadLatestRunReportArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class AnalyzeLatestRunFailureArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选指定运行输出目录。")
    log_lines: int = Field(default=80, description="包含的日志行数。")
    event_lines: int = Field(default=80, description="包含的事件行数。")


class ReadRunLogArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选指定运行输出目录。")
    lines: int = Field(default=80, description="读取行数。")


class ReadRunEventsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选指定运行输出目录。")
    lines: int = Field(default=40, description="读取事件数。")


class ListOutputArtifactsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    filter_text: str = Field(default="", description="可选产物过滤条件。")
    limit: int = Field(default=100, description="最大返回产物数。")


class ReadOutputArtifactArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    relative_path: str = Field(..., description="相对于 plan 包 output/ 目录的路径。")
    max_bytes: int = Field(default=64_000, description="返回字节上限；工具会限幅。")


class ExportLocalFileArgs(ToolArgsModel):
    target_path: str = Field(..., description="项目外的本机目标路径：绝对路径或 ~ 路径，例如 ~/Downloads/AI账户.txt。")
    content: str | None = Field(default=None, description="文本内容。")
    json_value: Any = Field(default=None, description="JSON 内容，可替代 content，按缩进写入。")
    plan_path: str = Field(default="", description="复制 output 产物时的 plan.json 或包目录。")
    source_output_path: str = Field(default="", description="可选 output/ 相对源产物；提供则复制到 target_path。")
    mode: str = Field(default="overwrite", description="overwrite 或 append；复制源产物只支持 overwrite。")


class CreateDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    name: str | None = Field(default=None, description="可选 workspace 名称后缀。")


class ListDebugWorkspacesArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")


class FindDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    name: str | None = Field(default=None, description="可选 workspace 名称或后缀。")


class ReadDebugWorkspaceArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")


class PrepareFailureDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="plan.json 路径或 plan 包目录。")
    output_dir: str | None = Field(default=None, description="可选失败运行输出目录。")
    name: str | None = Field(default=None, description="可选 workspace 名称后缀。")
    include_manual_confirm: bool = Field(
        default=False,
        description="是否在失败步骤前注入 manual_confirm。",
    )


class InjectDebugStepsArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    presets: list[str] = Field(..., description="诊断预设列表。")
    message: str | None = Field(default=None, description="print/manual_confirm 消息。")
    browser: str | None = Field(default=None, description="screenshot/html 浏览器会话名。")
    page: str | None = Field(default=None, description="screenshot/html 页面名。")
    position: str = Field(default="end", description="注入位置：start、end、before_step 或 after_step。")
    step: int | None = Field(default=None, description="before/after_step 的 1-based 锚点步骤。")


class WriteDebugWorkspaceFileArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    root: str = Field(default="injected-plan", description="目标根目录：injected-plan、notes 或 report。")
    relative_path: str = Field(default="plan.json", description="injected-plan 下的路径；notes/report 会忽略该字段。")
    content: str | None = Field(default=None, description="文本内容。")
    json_value: Any = Field(default=None, description="JSON 内容，可替代 content。")
    mode: str = Field(default="overwrite", description="写入模式：overwrite 或 append。")


class PatchDebugWorkspaceJsonArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    root: str = Field(default="injected-plan", description="目标根目录；必须是 injected-plan。")
    relative_path: str = Field(default="plan.json", description="injected-plan 下 JSON 文件路径。")
    operations: list[dict[str, Any]] = Field(..., description="JSON patch 操作数组。")


class ProposeDebugFixArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    user_hint: str = Field(default="", description="可选用户提示，用于候选排序。")
    apply: bool = Field(default=False, description="把选中修复写入 injected-plan/。")
    run_after_apply: bool = Field(default=False, description="应用候选后运行调试 plan。")
    run_name: str | None = Field(default=None, description="run_after_apply 时的可选运行名称。")


class ValidateDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")


class RunDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    run_name: str | None = Field(default=None, description="可选运行名称。")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="本次运行的临时变量覆盖。",
    )


class GenerateDebugPatchArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")


class ApplyDebugPatchAfterApprovalArgs(ToolArgsModel):
    workspace: str = Field(..., description="debug workspace 根路径。")
    approved: bool = Field(
        default=False,
        description="AI 终端在 /approve 后注入的确认字段。",
    )
