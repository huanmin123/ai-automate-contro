from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListPlanPackagesArgs(ToolArgsModel):
    filter_text: str = Field(default="", description="Optional text filter.")


class ReadPlanPackageArgs(ToolArgsModel):
    plan_path: str = Field(..., description="Path to plan.json or a plan package directory.")


class CreatePlanPackageArgs(ToolArgsModel):
    package_path: str = Field(..., description="Target plan package directory.")
    name: str | None = Field(default=None, description="Optional plan name.")
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
    max_bytes: int = Field(default=256_000, description="Maximum text bytes to return.")


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


TOOL_ARGS_SCHEMAS: dict[str, type[BaseModel]] = {
    "list_plan_packages": ListPlanPackagesArgs,
    "read_plan_package": ReadPlanPackageArgs,
    "create_plan_package": CreatePlanPackageArgs,
    "validate_plan": ValidatePlanArgs,
    "run_plan": RunPlanArgs,
    "read_latest_run_state": ReadLatestRunStateArgs,
    "read_latest_run_report": ReadLatestRunReportArgs,
    "analyze_latest_run_failure": AnalyzeLatestRunFailureArgs,
    "read_run_log": ReadRunLogArgs,
    "read_run_events": ReadRunEventsArgs,
    "list_output_artifacts": ListOutputArtifactsArgs,
    "read_output_artifact": ReadOutputArtifactArgs,
    "create_debug_workspace": CreateDebugWorkspaceArgs,
    "list_debug_workspaces": ListDebugWorkspacesArgs,
    "find_debug_workspace": FindDebugWorkspaceArgs,
    "read_debug_workspace": ReadDebugWorkspaceArgs,
    "prepare_failure_debug_workspace": PrepareFailureDebugWorkspaceArgs,
    "inject_debug_steps": InjectDebugStepsArgs,
    "write_debug_workspace_file": WriteDebugWorkspaceFileArgs,
    "patch_debug_workspace_json": PatchDebugWorkspaceJsonArgs,
    "propose_debug_fix": ProposeDebugFixArgs,
    "validate_debug_plan": ValidateDebugPlanArgs,
    "run_debug_plan": RunDebugPlanArgs,
    "generate_debug_patch": GenerateDebugPatchArgs,
    "apply_debug_patch_after_approval": ApplyDebugPatchAfterApprovalArgs,
}


TOOL_DESCRIPTIONS = {
    "list_plan_packages": "List available plan packages in plans/ and test-plans/.",
    "read_plan_package": "Read a plan package, including plan.json, config, docs, sub-plans, and resources.",
    "create_plan_package": "Create a new plan package template.",
    "validate_plan": "Validate a plan package without running it.",
    "run_plan": "Run a plan package.",
    "read_latest_run_state": "Read state.json from the latest run output.",
    "read_latest_run_report": "Read report.md from the latest run output.",
    "analyze_latest_run_failure": "Analyze latest failed run evidence, including logs, events, screenshots, HTML, page state, and DOM summary.",
    "read_run_log": "Read run.log from a run output.",
    "read_run_events": "Read events.jsonl from a run output.",
    "list_output_artifacts": "List files under the current plan package output/ directory.",
    "read_output_artifact": "Read one artifact under output/; text artifacts return content.",
    "create_debug_workspace": "Create an isolated output/debug workspace for a plan package.",
    "list_debug_workspaces": "List debug workspaces for a plan package.",
    "find_debug_workspace": "Find a debug workspace by name, suffix, or latest.",
    "read_debug_workspace": "Read a debug workspace manifest, source-copy, injected-plan, notes, report, and patch.",
    "prepare_failure_debug_workspace": "Create a debug workspace from failed run evidence and inject diagnostics before the failed step.",
    "inject_debug_steps": "Inject diagnostic steps into injected-plan/.",
    "write_debug_workspace_file": "Write only allowed files inside injected-plan/, notes.md, or report.md.",
    "patch_debug_workspace_json": "Apply minimal JSON path edits to a JSON file under injected-plan/.",
    "propose_debug_fix": "Generate a conservative clean fix candidate inside a debug workspace.",
    "validate_debug_plan": "Validate injected-plan/plan.json inside a debug workspace.",
    "run_debug_plan": "Run injected-plan/plan.json inside a debug workspace.",
    "generate_debug_patch": "Generate patch.diff by comparing source-copy/ and injected-plan/.",
    "apply_debug_patch_after_approval": "Apply patch.diff to the original plan package after explicit user approval.",
}
