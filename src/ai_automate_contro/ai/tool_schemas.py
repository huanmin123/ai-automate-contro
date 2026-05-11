from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListPlanPackagesArgs(ToolArgsModel):
    filter_text: str = Field(default="", description="Optional text filter.")


class GrepProjectTextArgs(ToolArgsModel):
    pattern: str = Field(..., description="Text or regex pattern to search for with ripgrep.")
    root_path: str = Field(default=".", description="Project-relative directory or file to search.")
    literal: bool = Field(default=True, description="Use fixed-string search instead of regex.")
    include_output: bool = Field(default=False, description="Include plan output/ directories when explicitly needed.")
    file_glob: str = Field(default="", description="Optional ripgrep glob, for example *.md or **/*.json.")
    context_lines: int = Field(default=0, description="Context lines around matches; clamped to a small maximum.")
    max_matches: int = Field(default=50, description="Maximum match lines to return; clamped to a small maximum.")


class ReadProjectFileSliceArgs(ToolArgsModel):
    path: str = Field(..., description="Project-relative or absolute path under the project root.")
    start_line: int = Field(default=1, description="1-based first line to read.")
    line_count: int = Field(default=80, description="Number of lines to read; clamped to a small maximum.")
    max_bytes: int = Field(default=64_000, description="Maximum text bytes to return; clamped to a small maximum.")


class ReadPlanPackageArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class CreatePlanPackageArgs(ToolArgsModel):
    package_path: str | None = Field(default=None, description="Target plan package directory. If omitted, the tool uses the configured default plan root and the plan name.")
    name: str | None = Field(default=None, description="Plan name. Required when package_path is omitted.")
    force: bool = Field(default=False, description="Allow using an existing non-empty package directory.")


class ValidatePlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class RunPlanArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    run_name: str | None = Field(default=None, description="Optional run name.")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Temporary variable overrides.",
    )


class ReadLatestRunStateArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class ReadLatestRunReportArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class AnalyzeLatestRunFailureArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    output_dir: str | None = Field(default=None, description="Optional specific run output directory.")
    log_lines: int = Field(default=80, description="Number of log lines to include.")
    event_lines: int = Field(default=80, description="Number of event lines to include.")


class ReadRunLogArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    output_dir: str | None = Field(default=None, description="Optional specific run output directory.")
    lines: int = Field(default=80, description="Number of lines to read.")


class ReadRunEventsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    output_dir: str | None = Field(default=None, description="Optional specific run output directory.")
    lines: int = Field(default=40, description="Number of events to read.")


class ListOutputArtifactsArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    filter_text: str = Field(default="", description="Optional artifact filter.")
    limit: int = Field(default=100, description="Maximum number of artifacts to return.")


class ReadOutputArtifactArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    relative_path: str = Field(..., description="Path relative to the plan package output/ directory.")
    max_bytes: int = Field(default=64_000, description="Maximum text bytes to return; tool clamps oversized requests.")


class CreateDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    name: str | None = Field(default=None, description="Optional debug workspace name suffix.")


class ListDebugWorkspacesArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class FindDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    name: str | None = Field(default=None, description="Optional workspace name or suffix.")


class ReadDebugWorkspaceArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")


class PrepareFailureDebugWorkspaceArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")
    output_dir: str | None = Field(default=None, description="Optional failed run output directory.")
    name: str | None = Field(default=None, description="Optional debug workspace name suffix.")
    include_manual_confirm: bool = Field(
        default=False,
        description="Whether to inject manual_confirm before the failed step.",
    )


class InjectDebugStepsArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    presets: list[str] = Field(..., description="Diagnostic presets to inject.")
    message: str | None = Field(default=None, description="Message for print or manual_confirm presets.")
    browser: str | None = Field(default=None, description="Browser session name for screenshot/html presets.")
    page: str | None = Field(default=None, description="Page name for screenshot/html presets.")
    position: str = Field(default="end", description="Injection position: start, end, before_step, or after_step.")
    step: int | None = Field(default=None, description="1-based anchor step for before_step or after_step.")


class WriteDebugWorkspaceFileArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    root: str = Field(default="injected-plan", description="Target root: injected-plan, notes, or report.")
    relative_path: str = Field(default="plan.json", description="Path under injected-plan; ignored for notes/report.")
    content: str | None = Field(default=None, description="Text content to write.")
    json_value: Any = Field(default=None, description="JSON value alternative to content.")
    mode: str = Field(default="overwrite", description="Write mode: overwrite or append.")


class PatchDebugWorkspaceJsonArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    root: str = Field(default="injected-plan", description="Target root; must be injected-plan.")
    relative_path: str = Field(default="plan.json", description="JSON file path under injected-plan.")
    operations: list[dict[str, Any]] = Field(..., description="JSON patch operations.")


class ProposeDebugFixArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    user_hint: str = Field(default="", description="Optional user hint used to rank candidates.")
    apply: bool = Field(default=False, description="Write the selected clean fix candidate to injected-plan/.")
    run_after_apply: bool = Field(default=False, description="Run the debug plan after applying the candidate.")
    run_name: str | None = Field(default=None, description="Optional run name when run_after_apply is true.")


class ValidateDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")


class RunDebugPlanArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    run_name: str | None = Field(default=None, description="Optional run name.")
    variable_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Temporary variable overrides.",
    )


class GenerateDebugPatchArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")


class ApplyDebugPatchAfterApprovalArgs(ToolArgsModel):
    workspace: str = Field(..., description="Debug workspace root path.")
    approved: bool = Field(
        default=False,
        description="Injected by the AI terminal after a human approve decision.",
    )
