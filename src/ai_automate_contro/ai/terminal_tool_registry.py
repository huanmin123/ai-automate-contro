from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from ai_automate_contro.ai import terminal_tools
from ai_automate_contro.ai.plan_tools import (
    create_plan_package_tool,
    list_plan_packages_tool,
    read_plan_package_tool,
    validate_plan_tool,
)
from ai_automate_contro.ai.tool_schemas import (
    AnalyzeLatestRunFailureArgs,
    ApplyDebugPatchAfterApprovalArgs,
    CreateDebugWorkspaceArgs,
    CreatePlanPackageArgs,
    FindDebugWorkspaceArgs,
    GenerateDebugPatchArgs,
    InjectDebugStepsArgs,
    ListDebugWorkspacesArgs,
    ListOutputArtifactsArgs,
    ListPlanPackagesArgs,
    PatchDebugWorkspaceJsonArgs,
    PrepareFailureDebugWorkspaceArgs,
    ProposeDebugFixArgs,
    ReadDebugWorkspaceArgs,
    ReadLatestRunReportArgs,
    ReadLatestRunStateArgs,
    ReadOutputArtifactArgs,
    ReadPlanPackageArgs,
    ReadRunEventsArgs,
    ReadRunLogArgs,
    RunDebugPlanArgs,
    RunPlanArgs,
    ValidateDebugPlanArgs,
    ValidatePlanArgs,
    WriteDebugWorkspaceFileArgs,
)


@dataclass(frozen=True)
class ToolSpec:
    handler: Callable[..., dict[str, Any]]
    args_schema: type[BaseModel]
    description: str
    requires_project_root: bool = False
    protected: bool = False


AI_TERMINAL_TOOL_SPECS: dict[str, ToolSpec] = {
    "analyze_latest_run_failure": ToolSpec(
        terminal_tools.analyze_latest_run_failure_tool,
        AnalyzeLatestRunFailureArgs,
        "Analyze latest failed run evidence, including logs, events, screenshots, HTML, page state, and DOM summary.",
    ),
    "apply_debug_patch_after_approval": ToolSpec(
        terminal_tools.apply_debug_patch_after_approval_tool,
        ApplyDebugPatchAfterApprovalArgs,
        "Apply patch.diff to the original plan package after explicit user approval.",
        protected=True,
    ),
    "create_debug_workspace": ToolSpec(
        terminal_tools.create_debug_workspace_tool,
        CreateDebugWorkspaceArgs,
        "Create an isolated output/debug workspace for a plan package.",
        requires_project_root=True,
    ),
    "create_plan_package": ToolSpec(
        create_plan_package_tool,
        CreatePlanPackageArgs,
        "Create a new plan package template.",
        requires_project_root=True,
    ),
    "find_debug_workspace": ToolSpec(
        terminal_tools.find_debug_workspace_tool,
        FindDebugWorkspaceArgs,
        "Find a debug workspace by name, suffix, or latest.",
    ),
    "generate_debug_patch": ToolSpec(
        terminal_tools.generate_debug_patch_tool,
        GenerateDebugPatchArgs,
        "Generate patch.diff by comparing source-copy/ and injected-plan/.",
    ),
    "inject_debug_steps": ToolSpec(
        terminal_tools.inject_debug_steps_tool,
        InjectDebugStepsArgs,
        "Inject diagnostic steps into injected-plan/.",
    ),
    "list_debug_workspaces": ToolSpec(
        terminal_tools.list_debug_workspaces_tool,
        ListDebugWorkspacesArgs,
        "List debug workspaces for a plan package.",
    ),
    "list_output_artifacts": ToolSpec(
        terminal_tools.list_output_artifacts_tool,
        ListOutputArtifactsArgs,
        "List files under the current plan package output/ directory.",
    ),
    "list_plan_packages": ToolSpec(
        list_plan_packages_tool,
        ListPlanPackagesArgs,
        "List available plan packages in plans/ and test-plans/.",
        requires_project_root=True,
    ),
    "patch_debug_workspace_json": ToolSpec(
        terminal_tools.patch_debug_workspace_json_tool,
        PatchDebugWorkspaceJsonArgs,
        "Apply minimal JSON path edits to a JSON file under injected-plan/.",
    ),
    "prepare_failure_debug_workspace": ToolSpec(
        terminal_tools.prepare_failure_debug_workspace_tool,
        PrepareFailureDebugWorkspaceArgs,
        "Create a debug workspace from failed run evidence and inject diagnostics before the failed step.",
        requires_project_root=True,
    ),
    "propose_debug_fix": ToolSpec(
        terminal_tools.propose_debug_fix_tool,
        ProposeDebugFixArgs,
        "Generate a conservative clean fix candidate inside a debug workspace.",
        requires_project_root=True,
    ),
    "read_debug_workspace": ToolSpec(
        terminal_tools.read_debug_workspace_tool,
        ReadDebugWorkspaceArgs,
        "Read a debug workspace manifest, source-copy, injected-plan, notes, report, and patch.",
    ),
    "read_latest_run_report": ToolSpec(
        terminal_tools.read_latest_run_report_tool,
        ReadLatestRunReportArgs,
        "Read report.md from the latest run output.",
    ),
    "read_latest_run_state": ToolSpec(
        terminal_tools.read_latest_run_state_tool,
        ReadLatestRunStateArgs,
        "Read state.json from the latest run output.",
    ),
    "read_output_artifact": ToolSpec(
        terminal_tools.read_output_artifact_tool,
        ReadOutputArtifactArgs,
        "Read one artifact under output/; text artifacts return content.",
    ),
    "read_plan_package": ToolSpec(
        read_plan_package_tool,
        ReadPlanPackageArgs,
        "Read a plan package, including plan.json, config, docs, sub-plans, and resources.",
        requires_project_root=True,
    ),
    "read_run_events": ToolSpec(
        terminal_tools.read_run_events_tool,
        ReadRunEventsArgs,
        "Read events.jsonl from a run output.",
    ),
    "read_run_log": ToolSpec(
        terminal_tools.read_run_log_tool,
        ReadRunLogArgs,
        "Read run.log from a run output.",
    ),
    "run_debug_plan": ToolSpec(
        terminal_tools.run_debug_plan_tool,
        RunDebugPlanArgs,
        "Run injected-plan/plan.json inside a debug workspace.",
        requires_project_root=True,
    ),
    "run_plan": ToolSpec(
        terminal_tools.run_plan_tool,
        RunPlanArgs,
        "Run a plan package.",
        requires_project_root=True,
    ),
    "validate_debug_plan": ToolSpec(
        terminal_tools.validate_debug_plan_tool,
        ValidateDebugPlanArgs,
        "Validate injected-plan/plan.json inside a debug workspace.",
        requires_project_root=True,
    ),
    "validate_plan": ToolSpec(
        validate_plan_tool,
        ValidatePlanArgs,
        "Validate a plan package without running it.",
        requires_project_root=True,
    ),
    "write_debug_workspace_file": ToolSpec(
        terminal_tools.write_debug_workspace_file_tool,
        WriteDebugWorkspaceFileArgs,
        "Write only allowed files inside injected-plan/, notes.md, or report.md.",
    ),
}

AI_TERMINAL_TOOLS = {
    name: spec.handler
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
TOOL_ARGS_SCHEMAS = {
    name: spec.args_schema
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
TOOL_DESCRIPTIONS = {
    name: spec.description
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
PROJECT_ROOT_TOOLS = {
    name
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
    if spec.requires_project_root
}
PROTECTED_AI_TERMINAL_TOOLS = {
    name
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
    if spec.protected
}


def call_ai_terminal_tool(
    tool_name: str,
    project_root: str | Path,
    arguments: dict[str, Any] | None = None,
    *,
    allow_protected: bool = False,
) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOL_SPECS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOL_SPECS))
        raise ValueError(f"Unsupported AI terminal tool: {tool_name}. Supported tools: {supported}")
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    if spec.protected and not allow_protected:
        raise ValueError(
            f"Tool '{tool_name}' is protected and can only run through the AI terminal human approval flow."
        )
    tool_arguments = _validate_ai_terminal_tool_arguments(tool_name, arguments or {})
    if spec.requires_project_root:
        return spec.handler(project_root, **tool_arguments)
    return spec.handler(**tool_arguments)


def list_ai_terminal_tools() -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    return {
        "ok": True,
        "tools": [
            {
                "name": name,
                "description": spec.description,
                "requires_project_root": spec.requires_project_root,
                "protected": spec.protected,
                "args": list(spec.args_schema.model_fields),
            }
            for name, spec in sorted(AI_TERMINAL_TOOL_SPECS.items())
        ],
    }


def describe_ai_terminal_tool(tool_name: str) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOL_SPECS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOL_SPECS))
        raise ValueError(f"Unsupported AI terminal tool: {tool_name}. Supported tools: {supported}")
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    return {
        "ok": True,
        "name": tool_name,
        "description": spec.description,
        "requires_project_root": spec.requires_project_root,
        "protected": spec.protected,
        "args_schema": spec.args_schema.model_json_schema(),
    }


def check_ai_terminal_tool_registry() -> dict[str, Any]:
    tool_names = set(AI_TERMINAL_TOOL_SPECS)
    schema_names = set(TOOL_ARGS_SCHEMAS)
    description_names = set(TOOL_DESCRIPTIONS)
    project_root_names = set(PROJECT_ROOT_TOOLS)
    protected_names = set(PROTECTED_AI_TERMINAL_TOOLS)
    missing_schemas = sorted(tool_names - schema_names)
    extra_schemas = sorted(schema_names - tool_names)
    missing_descriptions = sorted(tool_names - description_names)
    extra_descriptions = sorted(description_names - tool_names)
    invalid_project_root_tools = sorted(project_root_names - tool_names)
    invalid_protected_tools = sorted(protected_names - tool_names)
    invalid_specs = sorted(
        name
        for name, spec in AI_TERMINAL_TOOL_SPECS.items()
        if not callable(spec.handler) or not spec.description or not issubclass(spec.args_schema, BaseModel)
    )
    errors = []
    if missing_schemas:
        errors.append(f"Missing Pydantic args schemas: {', '.join(missing_schemas)}")
    if extra_schemas:
        errors.append(f"Args schemas without registered tools: {', '.join(extra_schemas)}")
    if missing_descriptions:
        errors.append(f"Missing tool descriptions: {', '.join(missing_descriptions)}")
    if extra_descriptions:
        errors.append(f"Descriptions without registered tools: {', '.join(extra_descriptions)}")
    if invalid_project_root_tools:
        errors.append(f"PROJECT_ROOT_TOOLS contains unknown tools: {', '.join(invalid_project_root_tools)}")
    if invalid_protected_tools:
        errors.append(f"PROTECTED_AI_TERMINAL_TOOLS contains unknown tools: {', '.join(invalid_protected_tools)}")
    if invalid_specs:
        errors.append(f"Invalid tool specs: {', '.join(invalid_specs)}")
    return {
        "ok": not errors,
        "registered_tools": len(tool_names),
        "schemas": len(schema_names),
        "descriptions": len(description_names),
        "project_root_tools": len(project_root_names),
        "protected_tools": len(protected_names),
        "missing_schemas": missing_schemas,
        "extra_schemas": extra_schemas,
        "missing_descriptions": missing_descriptions,
        "extra_descriptions": extra_descriptions,
        "invalid_project_root_tools": invalid_project_root_tools,
        "invalid_protected_tools": invalid_protected_tools,
        "invalid_specs": invalid_specs,
        "errors": errors,
    }


def _ensure_ai_terminal_tool_registry_consistent() -> None:
    result = check_ai_terminal_tool_registry()
    if not result["ok"]:
        raise RuntimeError("AI terminal tool registry is inconsistent: " + "; ".join(result["errors"]))


def _validate_ai_terminal_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = AI_TERMINAL_TOOL_SPECS.get(tool_name)
    if spec is None:
        raise ValueError(f"Missing argument schema for AI terminal tool: {tool_name}")
    return spec.args_schema.model_validate(arguments).model_dump()
