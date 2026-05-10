from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    create_debug_workspace,
    find_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
    list_debug_workspaces,
)
from ai_automate_contro.ai import debug_fix, run_inspection
from ai_automate_contro.ai.debug_workspace_io import (
    debug_relative_path,
    read_debug_manifest,
    read_debug_plan_tree,
    read_text_if_exists,
    read_text_preserve_newlines,
    reset_injected_file_to_source,
    resolve_debug_write_path,
    write_text_preserve_newlines,
)
from ai_automate_contro.ai.json_patch import (
    apply_json_patch_operations,
    normalize_json_patch_operation,
    serialize_json_patch_result,
)
from ai_automate_contro.ai.plan_tools import (
    list_package_files,
    read_json_if_exists,
    read_package_docs,
    read_sub_plans,
    validate_plan_tool,
)


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
    status = run_inspection.first_string(run_inspection.dict_get(analysis, "status"))
    if status != "failed":
        raise ValueError(
            f"prepare_failure_debug_workspace requires a failed run; latest status is '{status}'. "
            "Run the plan first or pass a failed output_dir."
        )
    failed_step_number = run_inspection.safe_int(run_inspection.dict_get(run_inspection.dict_get(analysis, "failed_step"), "step"))
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


def generate_debug_patch_tool(workspace: str | Path) -> dict[str, Any]:
    result = generate_debug_patch(workspace)
    patch_text = ""
    if result.patch_path.exists():
        patch_text = result.patch_path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "result": result.to_dict(),
        "patch": patch_text,
    }


def apply_debug_patch_after_approval_tool(workspace: str | Path, *, approved: bool = False) -> dict[str, Any]:
    result = apply_debug_patch(workspace, yes=approved)
    return {
        "ok": True,
        "result": result.to_dict(),
    }


def find_debug_workspace_tool(plan_path: str | Path, *, name: str | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "workspace": find_debug_workspace(plan_path, name),
    }


def read_debug_workspace_tool(workspace: str | Path) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    return {
        "ok": True,
        "manifest": manifest,
        "source": read_debug_plan_tree(
            source_copy_dir,
            read_json_if_exists=read_json_if_exists,
            read_package_docs=read_package_docs,
            read_sub_plans=read_sub_plans,
            list_package_files=list_package_files,
        ),
        "injected": read_debug_plan_tree(
            injected_plan_dir,
            read_json_if_exists=read_json_if_exists,
            read_package_docs=read_package_docs,
            read_sub_plans=read_sub_plans,
            list_package_files=list_package_files,
        ),
        "notes": read_text_if_exists(Path(manifest["notes_path"]).resolve()),
        "report": read_text_if_exists(Path(manifest["report_path"]).resolve()),
        "patch": read_text_if_exists(Path(manifest["patch_path"]).resolve()),
    }


def write_debug_workspace_file_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    content: str | None = None,
    json_value: Any | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    target_path = resolve_debug_write_path(
        manifest,
        root=root,
        relative_path=relative_path,
    )
    if content is None and json_value is None:
        raise ValueError("write_debug_workspace_file requires content or json_value.")
    if content is not None and json_value is not None:
        raise ValueError("write_debug_workspace_file accepts only one of content or json_value.")
    if mode not in {"overwrite", "append"}:
        raise ValueError("mode must be overwrite or append.")
    if mode == "append" and root == "injected-plan":
        raise ValueError("append mode is only allowed for notes and report.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if json_value is not None:
        serialized = json.dumps(json_value, ensure_ascii=False, indent=2) + "\n"
    else:
        serialized = content or ""
    if mode == "append":
        with target_path.open("a", encoding="utf-8") as file:
            file.write(serialized)
    else:
        target_path.write_text(serialized, encoding="utf-8")

    return {
        "ok": True,
        "path": str(target_path),
        "relative_path": debug_relative_path(manifest, target_path),
        "mode": mode,
        "size": target_path.stat().st_size,
    }


def patch_debug_workspace_json_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    target_path = resolve_debug_write_path(
        manifest,
        root=root,
        relative_path=relative_path,
    )
    if root.strip().lower() != "injected-plan":
        raise ValueError("patch_debug_workspace_json can only patch files under injected-plan/.")
    if target_path.suffix.lower() != ".json":
        raise ValueError("patch_debug_workspace_json requires a .json target file.")
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Debug JSON file does not exist: {target_path}")
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations must be a non-empty array.")

    original_text = read_text_preserve_newlines(target_path)
    try:
        document = json.loads(original_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Target file is not valid JSON: {error.msg}") from error

    normalized_operations = [normalize_json_patch_operation(operation) for operation in operations]
    updated_document = apply_json_patch_operations(document, normalized_operations)
    updated_text, strategy = serialize_json_patch_result(
        original_text,
        updated_document,
        normalized_operations,
    )
    write_text_preserve_newlines(target_path, updated_text)

    return {
        "ok": True,
        "path": str(target_path),
        "relative_path": debug_relative_path(manifest, target_path),
        "operations": len(normalized_operations),
        "write_strategy": strategy,
        "size": target_path.stat().st_size,
    }


def validate_debug_plan_tool(project_root: str | Path, *, workspace: str | Path) -> dict[str, Any]:
    manifest = read_debug_manifest(Path(workspace).resolve())
    return validate_plan_tool(project_root, Path(manifest["injected_plan_dir"]) / "plan.json")


def run_debug_plan_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    run_plan: Any,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = read_debug_manifest(Path(workspace).resolve())
    injected_plan_path = Path(manifest["injected_plan_dir"]) / "plan.json"
    return run_plan(
        project_root,
        injected_plan_path,
        run_name=run_name,
        variable_overrides=variable_overrides,
    )
