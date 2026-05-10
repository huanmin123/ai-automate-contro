from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model
from pydantic.fields import FieldInfo

from keygen_automation.ai_terminal_tools import call_ai_terminal_tool


ToolField = tuple[Any, Any, str]


TOOL_ARGUMENT_SCHEMAS: dict[str, dict[str, ToolField]] = {
    "list_plan_packages": {
        "filter_text": (str, "", "Optional text filter."),
    },
    "read_plan_package": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
    },
    "create_plan_package": {
        "package_path": (str, ..., "Target plan package directory."),
        "name": (str | None, None, "Optional plan name."),
        "force": (bool, False, "Allow using an existing non-empty package directory."),
    },
    "validate_plan": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
    },
    "run_plan": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "run_name": (str | None, None, "Optional run name."),
        "variable_overrides": (dict[str, Any], Field(default_factory=dict), "Temporary variable overrides."),
    },
    "read_latest_run_state": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
    },
    "read_latest_run_report": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
    },
    "analyze_latest_run_failure": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "output_dir": (str | None, None, "Optional specific run output directory."),
        "log_lines": (int, 80, "Number of log lines to include."),
        "event_lines": (int, 80, "Number of event lines to include."),
    },
    "read_run_log": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "output_dir": (str | None, None, "Optional specific run output directory."),
        "lines": (int, 80, "Number of lines to read."),
    },
    "read_run_events": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "output_dir": (str | None, None, "Optional specific run output directory."),
        "lines": (int, 40, "Number of events to read."),
    },
    "list_output_artifacts": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "filter_text": (str, "", "Optional artifact filter."),
        "limit": (int, 100, "Maximum number of artifacts to return."),
    },
    "read_output_artifact": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "relative_path": (str, ..., "Path relative to the plan package output/ directory."),
        "max_bytes": (int, 256_000, "Maximum text bytes to return."),
    },
    "create_debug_workspace": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "name": (str | None, None, "Optional debug workspace name suffix."),
    },
    "list_debug_workspaces": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
    },
    "find_debug_workspace": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "name": (str | None, None, "Optional workspace name or suffix."),
    },
    "read_debug_workspace": {
        "workspace": (str, ..., "Debug workspace root path."),
    },
    "prepare_failure_debug_workspace": {
        "plan_path": (str, ..., "Path to plan.json or a plan package directory."),
        "output_dir": (str | None, None, "Optional failed run output directory."),
        "name": (str | None, None, "Optional debug workspace name suffix."),
        "include_manual_confirm": (bool, False, "Whether to inject manual_confirm before the failed step."),
    },
    "inject_debug_steps": {
        "workspace": (str, ..., "Debug workspace root path."),
        "presets": (list[str], ..., "Diagnostic presets to inject."),
        "message": (str | None, None, "Message for print or manual_confirm presets."),
        "browser": (str | None, None, "Browser session name for screenshot/html presets."),
        "page": (str | None, None, "Page name for screenshot/html presets."),
        "position": (str, "end", "Injection position: start, end, before_step, or after_step."),
        "step": (int | None, None, "1-based anchor step for before_step or after_step."),
    },
    "write_debug_workspace_file": {
        "workspace": (str, ..., "Debug workspace root path."),
        "root": (str, "injected-plan", "Target root: injected-plan, notes, or report."),
        "relative_path": (str, "plan.json", "Path under injected-plan; ignored for notes/report."),
        "content": (str | None, None, "Text content to write."),
        "json_value": (Any, None, "JSON value alternative to content."),
        "mode": (str, "overwrite", "Write mode: overwrite or append."),
    },
    "patch_debug_workspace_json": {
        "workspace": (str, ..., "Debug workspace root path."),
        "root": (str, "injected-plan", "Target root; must be injected-plan."),
        "relative_path": (str, "plan.json", "JSON file path under injected-plan."),
        "operations": (list[dict[str, Any]], ..., "JSON patch operations."),
    },
    "propose_debug_fix": {
        "workspace": (str, ..., "Debug workspace root path."),
        "user_hint": (str, "", "Optional user hint used to rank candidates."),
        "apply": (bool, False, "Write the selected clean fix candidate to injected-plan/."),
        "run_after_apply": (bool, False, "Run the debug plan after applying the candidate."),
        "run_name": (str | None, None, "Optional run name when run_after_apply is true."),
    },
    "validate_debug_plan": {
        "workspace": (str, ..., "Debug workspace root path."),
    },
    "run_debug_plan": {
        "workspace": (str, ..., "Debug workspace root path."),
        "run_name": (str | None, None, "Optional run name."),
        "variable_overrides": (dict[str, Any], Field(default_factory=dict), "Temporary variable overrides."),
    },
    "generate_debug_patch": {
        "workspace": (str, ..., "Debug workspace root path."),
    },
    "apply_debug_patch_after_approval": {
        "workspace": (str, ..., "Debug workspace root path."),
        "approved": (bool, False, "Must be true, and the latest user message must explicitly approve."),
    },
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


def build_langchain_tools(
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None = None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
) -> list[StructuredTool]:
    return [
        _build_structured_tool(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
        )
        for tool_name in TOOL_ARGUMENT_SCHEMAS
    ]


def _build_structured_tool(
    tool_name: str,
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
) -> StructuredTool:
    args_schema = _create_args_schema(tool_name, TOOL_ARGUMENT_SCHEMAS[tool_name])
    return StructuredTool.from_function(
        func=_make_tool_function(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
        ),
        name=tool_name,
        description=TOOL_DESCRIPTIONS.get(tool_name, tool_name),
        args_schema=args_schema,
    )


def _create_args_schema(tool_name: str, fields: dict[str, ToolField]) -> type[Any]:
    model_fields: dict[str, tuple[Any, Any]] = {}
    for field_name, (annotation, default, description) in fields.items():
        if isinstance(default, FieldInfo):
            model_fields[field_name] = (annotation, default)
        else:
            model_fields[field_name] = (annotation, Field(default=default, description=description))
    class_name = "".join(part.title() for part in tool_name.split("_")) + "Args"
    return create_model(class_name, **model_fields)


def _make_tool_function(
    tool_name: str,
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
) -> Callable[..., str]:
    def _tool(**kwargs: Any) -> str:
        if tool_name == "apply_debug_patch_after_approval":
            if not bool(kwargs.get("approved")):
                raise ValueError("Applying a debug patch requires approved=true from a human approval flow.")
            if latest_user_approved is not None and not latest_user_approved():
                raise ValueError("Applying a debug patch requires explicit approval in the latest user message.")
        result = call_ai_terminal_tool(tool_name, project_root, kwargs)
        if after_tool_call is not None:
            after_tool_call(tool_name, kwargs, result)
        return json.dumps(result, ensure_ascii=False, indent=2)

    _tool.__name__ = tool_name
    return _tool
