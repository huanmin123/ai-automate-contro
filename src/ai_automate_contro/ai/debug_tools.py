from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.debug.workspace import create_debug_workspace, inject_debug_steps, list_debug_workspaces
from ai_automate_contro.ai import debug_fix
from ai_automate_contro.ai.debug_workspace_io import (
    read_debug_manifest,
    reset_injected_file_to_source,
)
from ai_automate_contro.ai.plan_tools import validate_plan_tool
from ai_automate_contro.support.utils import dict_get, first_string, safe_int


def create_debug_workspace_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    workspace = create_debug_workspace(plan_path, project_root, name=name)
    return {
        "ok": True,
        "workspace": workspace.to_dict(),
    }


def list_debug_workspaces_tool(plan_path: str | Path) -> dict[str, Any]:
    return {
        "ok": True,
        "workspaces": list_debug_workspaces(plan_path),
    }


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
    result = inject_debug_steps(
        workspace,
        presets=presets,
        message=message,
        browser=browser,
        page=page,
        position=position,
        step=step,
    )
    return {
        "ok": True,
        "result": result.to_dict(),
    }


def prepare_failure_debug_workspace_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    analyze_latest_run_failure: Any,
    output_dir: str | Path | None = None,
    name: str | None = None,
    include_manual_confirm: bool = False,
) -> dict[str, Any]:
    analysis = analyze_latest_run_failure(
        plan_path,
        output_dir=output_dir,
        log_lines=40,
        event_lines=80,
    )
    status = first_string(dict_get(analysis, "status"))
    if status != "failed":
        raise ValueError(
            f"prepare_failure_debug_workspace requires a failed run; latest status is '{status}'. "
            "Run the plan first or pass a failed output_dir."
        )
    failed_step_number = safe_int(dict_get(dict_get(analysis, "failed_step"), "step"))
    browser, page = debug_fix.failure_browser_page(analysis)
    presets = ["print", "variables"]
    if browser:
        presets.extend(["screenshot", "html"])
    if include_manual_confirm:
        presets.append("manual_confirm")

    workspace = create_debug_workspace(
        plan_path,
        project_root,
        name=name or "failure-debug",
    )
    position = "before_step" if failed_step_number else "end"
    message = debug_fix.failure_debug_message(analysis)
    injection = inject_debug_steps(
        workspace.root,
        presets=presets,
        message=message,
        browser=browser,
        page=page,
        position=position,
        step=failed_step_number,
    )
    debug_fix.append_failure_debug_note(
        workspace.root,
        analysis=analysis,
        presets=presets,
        position=position,
        step=failed_step_number,
        browser=browser,
        page=page,
    )
    validation = validate_plan_tool(project_root, workspace.injected_plan_dir / "plan.json")
    return {
        "ok": validation["ok"],
        "workspace": workspace.to_dict(),
        "analysis": analysis,
        "injection": injection.to_dict(),
        "validation": validation,
        "recommended_next_actions": [
            "Read the debug workspace notes and injected plan before running.",
            "Run run_debug_plan against the workspace to reproduce with diagnostics.",
            "Inspect output/debug artifacts from the injected plan run.",
            "Use patch_debug_workspace_json for the smallest fix, then validate and run again.",
        ],
    }


def propose_debug_fix_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    analyze_latest_run_failure: Any,
    patch_debug_workspace_json: Any,
    validate_debug_plan: Any,
    generate_debug_patch_result: Any,
    run_debug_plan: Any,
    user_hint: str = "",
    apply: bool = False,
    run_after_apply: bool = False,
    run_name: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    source_plan_path = Path(manifest["source_copy_dir"]).resolve() / "plan.json"
    original_plan_path = Path(manifest["plan_path"]).resolve()
    analysis = analyze_latest_run_failure(
        original_plan_path,
        log_lines=40,
        event_lines=80,
    )
    proposals = debug_fix.build_debug_fix_proposals(analysis, source_plan_path, user_hint=user_hint)
    selected = proposals[0] if proposals else None
    result: dict[str, Any] = {
        "ok": bool(proposals),
        "workspace": str(workspace_root),
        "analysis": {
            "status": analysis.get("status"),
            "output_dir": analysis.get("output_dir"),
            "failed_step": analysis.get("failed_step"),
            "plan_context": analysis.get("plan_context"),
            "hints": analysis.get("hints"),
        },
        "proposals": proposals,
        "selected": selected,
        "applied": False,
        "notes": [
            "This tool only writes to debug workspace injected-plan/.",
            "The original plan is unchanged until a generated patch is explicitly applied after approval.",
        ],
    }
    if not proposals:
        result["reason"] = "No supported automatic fix proposal could be inferred from the failure evidence."
        return result
    auto_apply_gate = debug_fix.selector_auto_apply_gate(proposals, user_hint=user_hint)
    result["auto_apply_gate"] = auto_apply_gate
    if not apply:
        result["next_actions"] = [
            "Review selected.operation and selected.reason.",
            "Call propose_debug_fix with apply=true to write the clean fix candidate to injected-plan/.",
            "Validate and run the debug plan before applying patch.diff to the original plan.",
        ]
        return result
    if not auto_apply_gate["ok"]:
        result.update(
            {
                "ok": False,
                "applied": False,
                "reason": auto_apply_gate["reason"],
                "next_actions": [
                    "Provide a clearer user_hint that names the target field, button, text, or expected selector.",
                    "Review proposals and use patch_debug_workspace_json for a deliberate minimal edit.",
                    "Run and validate the debug plan before generating or applying a patch.",
                ],
            }
        )
        return result

    reset_injected_file_to_source(manifest, "plan.json")
    patch_result = patch_debug_workspace_json(
        workspace_root,
        root="injected-plan",
        relative_path="plan.json",
        operations=[selected["operation"]],
    )
    debug_fix.append_debug_fix_note(workspace_root, selected)
    validation = validate_debug_plan(project_root, workspace=workspace_root)
    patch = generate_debug_patch_result(workspace_root)
    result.update(
        {
            "ok": bool(validation.get("ok")),
            "applied": True,
            "patch_result": patch_result,
            "validation": validation,
            "patch": patch,
            "next_actions": [
                "Run run_debug_plan to verify the clean fix candidate.",
                "Inspect patch.diff before asking the user for approval.",
                "Only call apply_debug_patch_after_approval after explicit user approval.",
            ],
        }
    )
    if run_after_apply and validation.get("ok"):
        result["debug_run"] = run_debug_plan(
            project_root,
            workspace=workspace_root,
            run_name=run_name or "debug-fix-candidate",
        )
    elif run_after_apply:
        result["debug_run"] = {
            "ok": False,
            "error": "Debug plan was not run because validation failed.",
        }
    return result
