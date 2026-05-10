from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ai_automate_contro.plans.packages import find_latest_run_output
from ai_automate_contro.ai import debug_tools, run_inspection
from ai_automate_contro.ai.plan_tools import (
    create_plan_package_tool,
    list_plan_packages_tool,
    read_plan_package_tool,
    resolve_plan_path,
    run_plan_tool as _run_plan_tool,
    validate_plan_tool,
)
from ai_automate_contro.ai.tool_schemas import TOOL_ARGS_SCHEMAS, TOOL_DESCRIPTIONS


def call_ai_terminal_tool(
    tool_name: str,
    project_root: str | Path,
    arguments: dict[str, Any] | None = None,
    *,
    allow_protected: bool = False,
) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOLS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOLS))
        raise ValueError(f"Unsupported AI terminal tool: {tool_name}. Supported tools: {supported}")
    if tool_name in PROTECTED_AI_TERMINAL_TOOLS and not allow_protected:
        raise ValueError(
            f"Tool '{tool_name}' is protected and can only run through the AI terminal human approval flow."
        )
    tool = AI_TERMINAL_TOOLS[tool_name]
    tool_arguments = _validate_ai_terminal_tool_arguments(tool_name, arguments or {})
    if tool_name in PROJECT_ROOT_TOOLS:
        return tool(project_root, **tool_arguments)
    return tool(**tool_arguments)


def list_ai_terminal_tools() -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    return {
        "ok": True,
        "tools": [
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, name),
                "requires_project_root": name in PROJECT_ROOT_TOOLS,
                "protected": name in PROTECTED_AI_TERMINAL_TOOLS,
                "args": list(TOOL_ARGS_SCHEMAS[name].model_fields),
            }
            for name in sorted(AI_TERMINAL_TOOLS)
        ],
    }


def describe_ai_terminal_tool(tool_name: str) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOLS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOLS))
        raise ValueError(f"Unsupported AI terminal tool: {tool_name}. Supported tools: {supported}")
    return {
        "ok": True,
        "name": tool_name,
        "description": TOOL_DESCRIPTIONS.get(tool_name, tool_name),
        "requires_project_root": tool_name in PROJECT_ROOT_TOOLS,
        "protected": tool_name in PROTECTED_AI_TERMINAL_TOOLS,
        "args_schema": TOOL_ARGS_SCHEMAS[tool_name].model_json_schema(),
    }


def check_ai_terminal_tool_registry() -> dict[str, Any]:
    tool_names = set(AI_TERMINAL_TOOLS)
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
        "errors": errors,
    }


def _ensure_ai_terminal_tool_registry_consistent() -> None:
    result = check_ai_terminal_tool_registry()
    if not result["ok"]:
        raise RuntimeError("AI terminal tool registry is inconsistent: " + "; ".join(result["errors"]))


def _validate_ai_terminal_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args_schema = TOOL_ARGS_SCHEMAS.get(tool_name)
    if args_schema is None:
        raise ValueError(f"Missing argument schema for AI terminal tool: {tool_name}")
    return args_schema.model_validate(arguments).model_dump()


def run_plan_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _run_plan_tool(
        project_root,
        plan_path,
        run_name=run_name,
        variable_overrides=variable_overrides,
        latest_state_reader=read_latest_run_state_tool,
    )


def read_latest_run_state_tool(plan_path: str | Path) -> dict[str, Any]:
    return run_inspection.read_latest_run_state_tool(resolve_plan_path, plan_path)


def read_latest_run_report_tool(plan_path: str | Path) -> dict[str, Any]:
    return run_inspection.read_latest_run_report_tool(resolve_plan_path, plan_path)


def analyze_latest_run_failure_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    log_lines: int = 80,
    event_lines: int = 80,
) -> dict[str, Any]:
    return run_inspection.analyze_latest_run_failure_tool(
        resolve_plan_path,
        _resolve_run_output_dir,
        plan_path,
        output_dir=output_dir,
        log_lines=log_lines,
        event_lines=event_lines,
    )


def read_run_log_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 80,
) -> dict[str, Any]:
    return run_inspection.read_run_log_tool(
        _resolve_run_output_dir,
        plan_path,
        output_dir=output_dir,
        lines=lines,
    )


def read_run_events_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 40,
) -> dict[str, Any]:
    return run_inspection.read_run_events_tool(
        _resolve_run_output_dir,
        plan_path,
        output_dir=output_dir,
        lines=lines,
    )


def list_output_artifacts_tool(
    plan_path: str | Path,
    *,
    filter_text: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    return run_inspection.list_output_artifacts_tool(plan_path, filter_text=filter_text, limit=limit)


def read_output_artifact_tool(
    plan_path: str | Path,
    relative_path: str | Path,
    *,
    max_bytes: int = run_inspection.MAX_TEXT_ARTIFACT_BYTES,
) -> dict[str, Any]:
    return run_inspection.read_output_artifact_tool(
        resolve_plan_path,
        plan_path,
        relative_path,
        max_bytes=max_bytes,
    )


def create_debug_workspace_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    return debug_tools.create_debug_workspace_tool(project_root, plan_path, name=name)


def list_debug_workspaces_tool(plan_path: str | Path) -> dict[str, Any]:
    return debug_tools.list_debug_workspaces_tool(plan_path)


def inject_debug_steps_tool(
    workspace: str | Path,
    *,
    presets: list[str],
    message: str | None = None,
    browser: str | None = None,
    page: str | None = None,
    position: str = "end",
    step: int | None = None,
) -> dict[str, Any]:
    return debug_tools.inject_debug_steps_tool(
        workspace,
        presets=presets,
        message=message,
        browser=browser,
        page=page,
        position=position,
        step=step,
    )


def prepare_failure_debug_workspace_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
    include_manual_confirm: bool = False,
) -> dict[str, Any]:
    return debug_tools.prepare_failure_debug_workspace_tool(
        project_root,
        plan_path,
        analyze_latest_run_failure=analyze_latest_run_failure_tool,
        output_dir=output_dir,
        name=name,
        include_manual_confirm=include_manual_confirm,
    )


def propose_debug_fix_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    user_hint: str = "",
    apply: bool = False,
    run_after_apply: bool = False,
    run_name: str | None = None,
) -> dict[str, Any]:
    return debug_tools.propose_debug_fix_tool(
        project_root,
        workspace=workspace,
        analyze_latest_run_failure=analyze_latest_run_failure_tool,
        patch_debug_workspace_json=patch_debug_workspace_json_tool,
        validate_debug_plan=validate_debug_plan_tool,
        generate_debug_patch_result=generate_debug_patch_tool,
        run_debug_plan=run_debug_plan_tool,
        user_hint=user_hint,
        apply=apply,
        run_after_apply=run_after_apply,
        run_name=run_name,
    )


def generate_debug_patch_tool(workspace: str | Path) -> dict[str, Any]:
    return debug_tools.generate_debug_patch_tool(workspace)


def apply_debug_patch_after_approval_tool(workspace: str | Path, *, approved: bool = False) -> dict[str, Any]:
    return debug_tools.apply_debug_patch_after_approval_tool(workspace, approved=approved)


def find_debug_workspace_tool(plan_path: str | Path, *, name: str | None = None) -> dict[str, Any]:
    return debug_tools.find_debug_workspace_tool(plan_path, name=name)


def read_debug_workspace_tool(workspace: str | Path) -> dict[str, Any]:
    return debug_tools.read_debug_workspace_tool(workspace)


def write_debug_workspace_file_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    content: str | None = None,
    json_value: Any | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    return debug_tools.write_debug_workspace_file_tool(
        workspace,
        root=root,
        relative_path=relative_path,
        content=content,
        json_value=json_value,
        mode=mode,
    )


def patch_debug_workspace_json_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    return debug_tools.patch_debug_workspace_json_tool(
        workspace,
        root=root,
        relative_path=relative_path,
        operations=operations,
    )


def validate_debug_plan_tool(project_root: str | Path, *, workspace: str | Path) -> dict[str, Any]:
    return debug_tools.validate_debug_plan_tool(project_root, workspace=workspace)


def run_debug_plan_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return debug_tools.run_debug_plan_tool(
        project_root,
        workspace=workspace,
        run_plan=run_plan_tool,
        run_name=run_name,
        variable_overrides=variable_overrides,
    )


def _resolve_run_output_dir(plan_path: str | Path, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    latest_output = find_latest_run_output(resolved_plan_path.parent)
    if latest_output is None:
        return resolved_plan_path.parent / "output"
    return latest_output


AI_TERMINAL_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "analyze_latest_run_failure": analyze_latest_run_failure_tool,
    "apply_debug_patch_after_approval": apply_debug_patch_after_approval_tool,
    "create_debug_workspace": create_debug_workspace_tool,
    "create_plan_package": create_plan_package_tool,
    "find_debug_workspace": find_debug_workspace_tool,
    "generate_debug_patch": generate_debug_patch_tool,
    "inject_debug_steps": inject_debug_steps_tool,
    "list_debug_workspaces": list_debug_workspaces_tool,
    "list_output_artifacts": list_output_artifacts_tool,
    "list_plan_packages": list_plan_packages_tool,
    "patch_debug_workspace_json": patch_debug_workspace_json_tool,
    "prepare_failure_debug_workspace": prepare_failure_debug_workspace_tool,
    "propose_debug_fix": propose_debug_fix_tool,
    "read_debug_workspace": read_debug_workspace_tool,
    "read_latest_run_report": read_latest_run_report_tool,
    "read_latest_run_state": read_latest_run_state_tool,
    "read_output_artifact": read_output_artifact_tool,
    "read_plan_package": read_plan_package_tool,
    "read_run_events": read_run_events_tool,
    "read_run_log": read_run_log_tool,
    "run_debug_plan": run_debug_plan_tool,
    "run_plan": run_plan_tool,
    "validate_debug_plan": validate_debug_plan_tool,
    "validate_plan": validate_plan_tool,
    "write_debug_workspace_file": write_debug_workspace_file_tool,
}

PROJECT_ROOT_TOOLS = {
    "create_debug_workspace",
    "create_plan_package",
    "list_plan_packages",
    "prepare_failure_debug_workspace",
    "propose_debug_fix",
    "read_plan_package",
    "run_debug_plan",
    "run_plan",
    "validate_debug_plan",
    "validate_plan",
}

PROTECTED_AI_TERMINAL_TOOLS = {
    "apply_debug_patch_after_approval",
}
