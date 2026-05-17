from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.plans.packages import find_latest_run_output
from ai_automate_contro.ai import debug_tools, debug_workspace_tools
from ai_automate_contro.ai.plan_tools import (
    resolve_plan_path,
    run_plan_tool as _run_plan_tool,
)
from ai_automate_contro.ai.run_artifacts import (
    MAX_TEXT_ARTIFACT_BYTES,
    list_output_artifacts_tool as _list_output_artifacts_tool,
    read_latest_run_report_tool as _read_latest_run_report_tool,
    read_latest_run_state_tool as _read_latest_run_state_tool,
    read_output_artifact_tool as _read_output_artifact_tool,
    read_run_events_tool as _read_run_events_tool,
    read_run_log_tool as _read_run_log_tool,
)
from ai_automate_contro.ai.run_failure_analysis import (
    analyze_latest_run_failure_tool as _analyze_latest_run_failure_tool,
)
from ai_automate_contro.ai.web_inspection import inspect_web_page_tool as _inspect_web_page_tool
from ai_automate_contro.ai.work_plan import normalize_work_plan_items, normalize_work_plan_summary
from ai_automate_contro.support.paths import path_from_text


def run_plan_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
    _manual_confirmation_handler: Any | None = None,
    _inspection_confirmation_handler: Any | None = None,
    _run_event_handler: Any | None = None,
) -> dict[str, Any]:
    return _run_plan_tool(
        project_root,
        plan_path,
        run_name=run_name,
        variable_overrides=variable_overrides,
        latest_state_reader=read_latest_run_state_tool,
        manual_confirmation_handler=_manual_confirmation_handler,
        inspection_confirmation_handler=_inspection_confirmation_handler,
        run_event_handler=_run_event_handler,
    )


def read_latest_run_state_tool(plan_path: str | Path) -> dict[str, Any]:
    return _read_latest_run_state_tool(resolve_plan_path, plan_path)


def read_latest_run_report_tool(plan_path: str | Path) -> dict[str, Any]:
    return _read_latest_run_report_tool(resolve_plan_path, plan_path)


def analyze_latest_run_failure_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    log_lines: int = 80,
    event_lines: int = 80,
) -> dict[str, Any]:
    return _analyze_latest_run_failure_tool(
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
    return _read_run_log_tool(
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
    return _read_run_events_tool(
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
    return _list_output_artifacts_tool(plan_path, filter_text=filter_text, limit=limit)


def read_output_artifact_tool(
    plan_path: str | Path,
    relative_path: str | Path,
    *,
    max_bytes: int = MAX_TEXT_ARTIFACT_BYTES,
) -> dict[str, Any]:
    return _read_output_artifact_tool(
        resolve_plan_path,
        plan_path,
        relative_path,
        max_bytes=max_bytes,
    )


def inspect_web_page_tool(
    project_root: str | Path,
    *,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 15_000,
    wait_ms: int = 1_000,
    max_elements: int = 80,
    text_limit: int = 6_000,
    headed: bool = False,
) -> dict[str, Any]:
    return _inspect_web_page_tool(
        project_root,
        url=url,
        wait_until=wait_until,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        max_elements=max_elements,
        text_limit=text_limit,
        headed=headed,
    )


def update_work_plan_tool(
    *,
    items: list[dict[str, Any]],
    summary: str = "",
) -> dict[str, Any]:
    normalized_items = normalize_work_plan_items(items)
    normalized_summary = normalize_work_plan_summary(summary)
    completed = sum(1 for item in normalized_items if item["status"] == "completed")
    active = next((item["title"] for item in normalized_items if item["status"] == "in_progress"), "")
    return {
        "ok": True,
        "summary": normalized_summary,
        "items": normalized_items,
        "total": len(normalized_items),
        "completed": completed,
        "active": active,
    }


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
    return debug_workspace_tools.generate_debug_patch_tool(workspace)


def apply_debug_patch_after_approval_tool(workspace: str | Path, *, approved: bool = False) -> dict[str, Any]:
    return debug_workspace_tools.apply_debug_patch_after_approval_tool(workspace, approved=approved)


def find_debug_workspace_tool(plan_path: str | Path, *, name: str | None = None) -> dict[str, Any]:
    return debug_workspace_tools.find_debug_workspace_tool(plan_path, name=name)


def read_debug_workspace_tool(workspace: str | Path) -> dict[str, Any]:
    return debug_workspace_tools.read_debug_workspace_tool(workspace)


def write_debug_workspace_file_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    content: str | None = None,
    json_value: Any | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    return debug_workspace_tools.write_debug_workspace_file_tool(
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
    return debug_workspace_tools.patch_debug_workspace_json_tool(
        workspace,
        root=root,
        relative_path=relative_path,
        operations=operations,
    )


def validate_debug_plan_tool(project_root: str | Path, *, workspace: str | Path) -> dict[str, Any]:
    return debug_workspace_tools.validate_debug_plan_tool(project_root, workspace=workspace)


def run_debug_plan_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
    _manual_confirmation_handler: Any | None = None,
    _inspection_confirmation_handler: Any | None = None,
    _run_event_handler: Any | None = None,
) -> dict[str, Any]:
    return debug_workspace_tools.run_debug_plan_tool(
        project_root,
        workspace=workspace,
        run_plan=run_plan_tool,
        run_name=run_name,
        variable_overrides=variable_overrides,
        _manual_confirmation_handler=_manual_confirmation_handler,
        _inspection_confirmation_handler=_inspection_confirmation_handler,
        _run_event_handler=_run_event_handler,
    )


def _resolve_run_output_dir(plan_path: str | Path, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return path_from_text(output_dir).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    latest_output = find_latest_run_output(resolved_plan_path.parent)
    if latest_output is None:
        return resolved_plan_path.parent / "output"
    return latest_output
