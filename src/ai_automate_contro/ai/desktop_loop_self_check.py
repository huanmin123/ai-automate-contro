from __future__ import annotations

import copy
import json
import platform
import tempfile
from pathlib import Path
from typing import Any

from ai_automate_contro.ai import debug_desktop_fix
from ai_automate_contro.ai.terminal_tool_registry import call_ai_terminal_tool
from ai_automate_contro.app.desktop_component_check import (
    build_temporary_desktop_form_plan,
    cleanup_temporary_desktop_form_case,
    desktop_temporary_form_skip_reason,
)


def self_check_ai_desktop_loop(project_root: str | Path) -> dict[str, Any]:
    resolved_project_root = Path(project_root).resolve()
    system = platform.system()
    skip_reason = desktop_temporary_form_skip_reason(system)
    if skip_reason:
        return {
            "ok": True,
            "check": "ai_desktop_loop",
            "skipped": True,
            "reason": skip_reason,
            "project_root": str(resolved_project_root),
        }

    with tempfile.TemporaryDirectory(prefix="ai-desktop-loop-self-check-") as raw_temp_dir:
        loop_root = Path(raw_temp_dir).resolve()
        _write_minimal_project_config(loop_root)
        checks = [
            _run_success_loop(loop_root, system),
            _run_failure_repair_loop(loop_root, system),
            _run_desktop_debug_auto_apply_gate_case(),
        ]

    return {
        "ok": all(check["passed"] for check in checks),
        "check": "ai_desktop_loop",
        "project_root": str(resolved_project_root),
        "runtime_root": "temporary",
        "platform": system,
        "checks": checks,
        "commands": {
            "run": "python .\\main.py self-check ai-desktop-loop",
            "desktop_components": "python .\\cplan.py self-check desktop-components",
        },
    }


def _run_success_loop(project_root: Path, system: str) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    package_dir: Path | None = None
    try:
        inspect_result = _call_tool(
            project_root,
            tool_calls,
            "inspect_desktop",
            {
                "platform_name": "auto",
                "request_permissions": False,
                "include_windows": True,
                "include_elements": False,
                "max_windows": 8,
            },
        )
        prepared = _create_fixture_plan_package(
            project_root,
            tool_calls,
            package_path="plans/ai-desktop-loop-success",
            name="ai desktop loop success",
            system=system,
        )
        package_dir = prepared["package_dir"]
        plan_path = prepared["plan_path"]
        plan = prepared["plan"]
        assertion_file = prepared["assertion_file"]

        _call_tool(
            project_root,
            tool_calls,
            "write_plan_package_file",
            {"plan_path": str(plan_path), "relative_path": "plan.json", "json_value": plan},
        )
        validation = _call_tool(project_root, tool_calls, "validate_plan", {"plan_path": str(plan_path)})
        quality = _call_tool(
            project_root,
            tool_calls,
            "review_plan_quality",
            {
                "plan_path": str(plan_path),
                "user_request": "控制本机桌面轻量表单，输入文本，触发保存按钮，并用桌面断言验证控件状态。",
                "evidence_summary": (
                    "已通过 inspect_desktop 获取桌面能力矩阵、coordinate_profile、窗口列表和 target_candidates；"
                    "target=candidate target_candidates.best_candidate candidate_id=element_match-0 "
                    "strategy=semantic_locator confidence=high screen_clickable=true，"
                    "控件 bounds/coordinate_profile 可用于少量真实鼠标事件；"
                    "plan 使用 open_desktop、desktop_app launch、desktop_wait window、desktop_element list/dump/set_text/invoke、desktop_assert element 和桌面关闭步骤，"
                    "坐标点击后有 desktop_assert element 验证结果。"
                ),
            },
        )
        run = _call_tool(
            project_root,
            tool_calls,
            "run_plan",
            {"plan_path": str(plan_path), "run_name": "ai-desktop-loop-success"},
            allow_run_plan=True,
        )
        artifacts = _call_tool(
            project_root,
            tool_calls,
            "list_output_artifacts",
            {"plan_path": str(plan_path), "filter_text": "desktop-annotations", "limit": 20},
        )
        annotation_read, annotation_payload = _read_first_annotation(project_root, tool_calls, plan_path, artifacts)
        probe_read, probe_payload = _read_json_artifact(project_root, tool_calls, plan_path, "json/desktop-probe.json")

        run_payload = run.get("result") if isinstance(run.get("result"), dict) else {}
        expected_text = str(plan.get("variables", {}).get("expected_text", ""))
        assertion_content = assertion_file.read_text(encoding="utf-8", errors="replace") if assertion_file.exists() else ""
        sequence = [call["tool"] for call in tool_calls]
        capability_matrix = (
            inspect_result.get("capability_matrix")
            if isinstance(inspect_result.get("capability_matrix"), dict)
            else {}
        )
        probe_matrix = (
            probe_payload.get("capability_matrix")
            if isinstance(probe_payload, dict) and isinstance(probe_payload.get("capability_matrix"), dict)
            else {}
        )
        passed = (
            inspect_result.get("ok") is True
            and capability_matrix.get("schema_version") == 1
            and validation.get("ok") is True
            and quality.get("ok") is True
            and run.get("ok") is True
            and run_payload.get("metadata", {}).get("automation_type") == "desktop"
            and expected_text in assertion_content
            and probe_matrix.get("schema_version") == 1
            and isinstance(annotation_payload, dict)
            and annotation_payload.get("schema_version") == 1
            and bool(annotation_payload.get("annotated_screenshot_path"))
            and _ordered_subset(
                sequence,
                ["inspect_desktop", "create_plan_package", "write_plan_package_file", "validate_plan", "review_plan_quality", "run_plan"],
            )
        )
        return _self_check_result(
            name="ai_desktop_success_plan_runs_with_annotations",
            passed=passed,
            detail={
                "tool_sequence": sequence,
                "plan_path": str(plan_path),
                "output_dir": run_payload.get("output_dir", ""),
                "inspect_capability_matrix_ok": capability_matrix.get("schema_version") == 1,
                "probe_capability_matrix_ok": probe_matrix.get("schema_version") == 1,
                "validation_ok": validation.get("ok"),
                "quality_ok": quality.get("ok"),
                "run_ok": run.get("ok"),
                "automation_type": run_payload.get("metadata", {}).get("automation_type"),
                "expected_text_found": expected_text in assertion_content,
                "annotation_relative_path": annotation_read.get("relative_path", ""),
                "annotation_schema_version": annotation_payload.get("schema_version") if isinstance(annotation_payload, dict) else None,
            },
        )
    except Exception as error:
        return _self_check_result(
            name="ai_desktop_success_plan_runs_with_annotations",
            passed=False,
            detail={"error": str(error), "tool_calls": tool_calls},
        )
    finally:
        if package_dir is not None:
            cleanup_temporary_desktop_form_case(package_dir, system)


def _run_failure_repair_loop(project_root: Path, system: str) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    package_dir: Path | None = None
    debug_package_dir: Path | None = None
    try:
        _call_tool(
            project_root,
            tool_calls,
            "inspect_desktop",
            {
                "platform_name": "auto",
                "request_permissions": False,
                "include_windows": True,
                "include_elements": False,
                "max_windows": 8,
            },
        )
        prepared = _create_fixture_plan_package(
            project_root,
            tool_calls,
            package_path="plans/ai-desktop-loop-failure",
            name="ai desktop loop failure",
            system=system,
        )
        package_dir = prepared["package_dir"]
        plan_path = prepared["plan_path"]
        original_plan = prepared["plan"]
        failing_plan, repair_operation, failed_step_index = _make_failing_plan(original_plan)

        _call_tool(
            project_root,
            tool_calls,
            "write_plan_package_file",
            {"plan_path": str(plan_path), "relative_path": "plan.json", "json_value": failing_plan},
        )
        validation = _call_tool(project_root, tool_calls, "validate_plan", {"plan_path": str(plan_path)})
        quality = _call_tool(
            project_root,
            tool_calls,
            "review_plan_quality",
            {
                "plan_path": str(plan_path),
                "user_request": "控制本机桌面轻量表单，输入文本，触发保存按钮，并用桌面断言验证控件状态。",
                "evidence_summary": (
                    "已通过 inspect_desktop 获取桌面能力矩阵、coordinate_profile、窗口列表和 target_candidates；"
                    "target=candidate target_candidates.best_candidate candidate_id=element_match-0 "
                    "strategy=semantic_locator confidence=high screen_clickable=true，"
                    "控件 bounds/coordinate_profile 可用于少量真实鼠标事件；"
                    "plan 包含 desktop_wait window、desktop_element list/dump、desktop_assert element；"
                    "本用例故意写错一个控件定位字段，用于验证失败诊断和 debug 修复闭环。"
                ),
            },
        )
        run = _call_tool(
            project_root,
            tool_calls,
            "run_plan",
            {"plan_path": str(plan_path), "run_name": "ai-desktop-loop-failure"},
            allow_run_plan=True,
        )
        failed_output_dir = _failed_output_dir(run)
        analysis = _call_tool(
            project_root,
            tool_calls,
            "analyze_latest_run_failure",
            {"plan_path": str(plan_path), "output_dir": failed_output_dir, "log_lines": 40, "event_lines": 80},
        )
        prepare = _call_tool(
            project_root,
            tool_calls,
            "prepare_failure_debug_workspace",
            {"plan_path": str(plan_path), "output_dir": failed_output_dir, "name": "ai-desktop-loop-repair"},
        )
        workspace = _workspace_root(prepare)
        adjusted_repair_operation = _adjust_operation_for_debug_injection(repair_operation, prepare)
        cleanup_temporary_desktop_form_case(package_dir, system)
        read_workspace = _call_tool(project_root, tool_calls, "read_debug_workspace", {"workspace": workspace})
        propose_preview = _call_tool(
            project_root,
            tool_calls,
            "propose_debug_fix",
            {
                "workspace": workspace,
                "user_hint": "DesktopElementTextBox Edit automation id",
            },
        )
        propose_apply = _call_tool(
            project_root,
            tool_calls,
            "propose_debug_fix",
            {
                "workspace": workspace,
                "user_hint": "DesktopElementTextBox Edit automation id",
                "apply": True,
                "run_after_apply": True,
                "run_name": "ai-desktop-loop-debug-fixed",
            },
        )
        patch_json = propose_apply.get("patch_result") if isinstance(propose_apply.get("patch_result"), dict) else {}
        if not patch_json:
            patch_json = _call_tool(
                project_root,
                tool_calls,
                "patch_debug_workspace_json",
                {
                    "workspace": workspace,
                    "root": "injected-plan",
                    "relative_path": "plan.json",
                    "operations": [adjusted_repair_operation],
                },
            )
        validate_debug = _call_tool(project_root, tool_calls, "validate_debug_plan", {"workspace": workspace})
        run_debug = (
            propose_apply.get("debug_run")
            if isinstance(propose_apply.get("debug_run"), dict)
            else _call_tool(
                project_root,
                tool_calls,
                "run_debug_plan",
                {"workspace": workspace, "run_name": "ai-desktop-loop-debug-fixed"},
            )
        )
        generate_patch = (
            propose_apply.get("patch")
            if isinstance(propose_apply.get("patch"), dict)
            else _call_tool(project_root, tool_calls, "generate_debug_patch", {"workspace": workspace})
        )
        if not any(call.get("tool") == "generate_debug_patch" for call in tool_calls):
            tool_calls.append(
                {
                    "tool": "generate_debug_patch",
                    "arguments": {"workspace": workspace, "via": "propose_debug_fix"},
                    "ok": bool(generate_patch.get("ok")),
                    "error": str(generate_patch.get("error", ""))[:500],
                }
            )
        apply_rejected = _call_tool(
            project_root,
            tool_calls,
            "apply_debug_patch_after_approval",
            {"workspace": workspace},
        )

        injected_plan_path = Path(workspace) / "injected-plan" / "plan.json"
        debug_package_dir = injected_plan_path.parent
        debug_artifacts = _call_tool(
            project_root,
            tool_calls,
            "list_output_artifacts",
            {"plan_path": str(injected_plan_path), "filter_text": "desktop-annotations", "limit": 20},
        )
        debug_annotation_read, debug_annotation_payload = _read_first_annotation(
            project_root,
            tool_calls,
            injected_plan_path,
            debug_artifacts,
        )

        diagnostics = analysis.get("desktop_diagnostics") if isinstance(analysis.get("desktop_diagnostics"), list) else []
        repair_suggestions = (
            analysis.get("desktop_repair_suggestions")
            if isinstance(analysis.get("desktop_repair_suggestions"), list)
            else []
        )
        run_debug_payload = run_debug.get("result") if isinstance(run_debug.get("result"), dict) else {}
        patch_payload = generate_patch.get("result") if isinstance(generate_patch.get("result"), dict) else {}
        changed_files = patch_payload.get("changed_files") if isinstance(patch_payload, dict) else []
        notes_metadata = (
            read_workspace.get("text_files", {}).get("notes")
            if isinstance(read_workspace.get("text_files"), dict)
            else {}
        )
        proposed_selected = (
            propose_preview.get("selected")
            if isinstance(propose_preview.get("selected"), dict)
            else {}
        )
        proposed_operations = (
            proposed_selected.get("operations")
            if isinstance(proposed_selected.get("operations"), list)
            else [proposed_selected.get("operation")]
        )
        propose_applied = bool(propose_apply.get("applied"))
        sequence = [call["tool"] for call in tool_calls]
        passed = (
            validation.get("ok") is True
            and quality.get("ok") is True
            and run.get("ok") is False
            and bool(failed_output_dir)
            and analysis.get("is_failure") is True
            and bool(diagnostics)
            and bool(repair_suggestions)
            and any(
                isinstance(item, dict)
                and isinstance(item.get("element"), dict)
                and item["element"].get("locator")
                for item in diagnostics
            )
            and prepare.get("ok") is True
            and propose_preview.get("ok") is True
            and proposed_selected.get("type") == "desktop_element_locator_replace"
            and any(
                isinstance(operation, dict)
                and operation.get("path") == ["steps", repair_operation["path"][1], "automation_id"]
                and operation.get("value") == repair_operation["value"]
                for operation in proposed_operations
            )
            and propose_apply.get("ok") is True
            and propose_applied
            and patch_json.get("ok") is True
            and validate_debug.get("ok") is True
            and run_debug.get("ok") is True
            and run_debug_payload.get("metadata", {}).get("automation_type") == "desktop"
            and generate_patch.get("ok") is True
            and changed_files == ["plan.json"]
            and apply_rejected.get("ok") is False
            and isinstance(debug_annotation_payload, dict)
            and debug_annotation_payload.get("schema_version") == 1
            and _ordered_subset(
                sequence,
                [
                    "create_plan_package",
                    "write_plan_package_file",
                    "validate_plan",
                    "review_plan_quality",
                    "run_plan",
                    "analyze_latest_run_failure",
                    "prepare_failure_debug_workspace",
                    "propose_debug_fix",
                    "propose_debug_fix",
                    "validate_debug_plan",
                    "generate_debug_patch",
                ],
            )
        )
        return _self_check_result(
            name="ai_desktop_failure_diagnostics_and_debug_repair",
            passed=passed,
            detail={
                "tool_sequence": sequence,
                "plan_path": str(plan_path),
                "failed_step_index": failed_step_index,
                "failed_output_dir": failed_output_dir,
                "analysis_is_failure": analysis.get("is_failure"),
                "desktop_diagnostics_count": len(diagnostics),
                "desktop_repair_suggestions": repair_suggestions[:3],
                "workspace": workspace,
                "notes_metadata": notes_metadata,
                "proposed_type": proposed_selected.get("type"),
                "proposed_to": proposed_selected.get("to"),
                "propose_auto_apply_gate": propose_apply.get("auto_apply_gate"),
                "propose_applied": propose_applied,
                "patch_operation": repair_operation,
                "manual_fallback_patch_operation": adjusted_repair_operation,
                "patch_changed_files": changed_files,
                "debug_run_ok": run_debug.get("ok"),
                "debug_output_dir": run_debug_payload.get("output_dir", ""),
                "debug_annotation_relative_path": debug_annotation_read.get("relative_path", ""),
                "apply_without_approval_error": apply_rejected.get("error", ""),
            },
        )
    except Exception as error:
        return _self_check_result(
            name="ai_desktop_failure_diagnostics_and_debug_repair",
            passed=False,
            detail={"error": str(error), "tool_calls": tool_calls},
        )
    finally:
        if package_dir is not None:
            cleanup_temporary_desktop_form_case(package_dir, system)
        if debug_package_dir is not None:
            cleanup_temporary_desktop_form_case(debug_package_dir, system)


def _run_desktop_debug_auto_apply_gate_case() -> dict[str, Any]:
    window_proposal = {
        "type": "desktop_window_query_replace",
        "confidence": "high",
        "score": 90,
        "operation": {"op": "replace", "path": ["steps", 1, "title_contains"], "value": "Target"},
    }
    low_confidence_element_proposal = {
        "type": "desktop_element_locator_replace",
        "confidence": "low",
        "score": 30,
        "auto_apply_allowed": False,
        "operation": {"op": "replace", "path": ["steps", 2, "automation_id"], "value": "SaveButton"},
    }
    stable_element_proposal = {
        "type": "desktop_element_locator_replace",
        "confidence": "high",
        "score": 95,
        "auto_apply_allowed": True,
        "operation": {"op": "replace", "path": ["steps", 2, "automation_id"], "value": "SaveButton"},
    }
    window_without_hint = debug_desktop_fix.desktop_auto_apply_gate([window_proposal], user_hint="")
    window_with_hint = debug_desktop_fix.desktop_auto_apply_gate([window_proposal], user_hint="目标窗口")
    low_element = debug_desktop_fix.desktop_auto_apply_gate([low_confidence_element_proposal], user_hint="保存按钮")
    stable_element = debug_desktop_fix.desktop_auto_apply_gate([stable_element_proposal], user_hint="")
    passed = (
        window_without_hint.get("ok") is False
        and window_with_hint.get("ok") is True
        and low_element.get("ok") is False
        and stable_element.get("ok") is True
    )
    return _self_check_result(
        name="desktop_debug_auto_apply_gate",
        passed=passed,
        detail={
            "window_without_hint": window_without_hint,
            "window_with_hint": window_with_hint,
            "low_confidence_element": low_element,
            "stable_element": stable_element,
        },
    )


def _create_fixture_plan_package(
    project_root: Path,
    tool_calls: list[dict[str, Any]],
    *,
    package_path: str,
    name: str,
    system: str,
) -> dict[str, Any]:
    create = _call_tool(
        project_root,
        tool_calls,
        "create_plan_package",
        {"package_path": package_path, "automation_type": "desktop", "name": name},
    )
    if not create.get("ok"):
        raise RuntimeError(str(create.get("error") or "create_plan_package failed"))
    plan_path = Path(str(create.get("plan_path"))).resolve()
    package_dir = plan_path.parent
    (package_dir / "resources").mkdir(parents=True, exist_ok=True)
    plan, assertion_relative_file, cleanup_hint = build_temporary_desktop_form_plan(package_dir, system)
    plan["name"] = name
    plan = _stable_ai_loop_plan(plan)
    assertion_file = package_dir / assertion_relative_file
    return {
        "plan_path": plan_path,
        "package_dir": package_dir,
        "plan": plan,
        "assertion_file": assertion_file,
        "cleanup": cleanup_hint,
    }


def _stable_ai_loop_plan(plan: dict[str, Any]) -> dict[str, Any]:
    stable_plan = copy.deepcopy(plan)
    skipped_outputs = {
        "agree_checkbox",
        "agree_checkbox_click",
        "mouse_panel_focus_click",
        "mouse_panel_double_click",
        "mouse_panel_right_click",
        "mouse_panel_scroll",
        "mouse_panel_drag",
        "mode_combo_state",
        "mode_combo_select",
        "options_list",
        "options_list_select",
    }
    steps = stable_plan.get("steps")
    if not isinstance(steps, list):
        return stable_plan
    stable_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        output = step.get("output")
        output_as = output.get("as") if isinstance(output, dict) else ""
        published_name = str(output_as or "")
        if published_name in skipped_outputs:
            continue
        if step.get("action") == "command" and published_name == "content_assertion":
            argv = step.get("argv")
            if isinstance(argv, list) and len(argv) > 5:
                step = {**step, "argv": argv[:5]}
        stable_steps.append(step)
    stable_plan["steps"] = stable_steps
    return stable_plan


def _make_failing_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], int]:
    failing_plan = copy.deepcopy(plan)
    steps = failing_plan.get("steps")
    original_steps = plan.get("steps")
    if not isinstance(steps, list) or not isinstance(original_steps, list):
        raise ValueError("fixture plan steps must be a list")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if step.get("action") != "desktop_element" or step.get("type") != "set_text":
            continue
        original_step = original_steps[index]
        if not isinstance(original_step, dict):
            continue
        if "automation_id" in step:
            step["automation_id"] = "__ai_desktop_loop_missing_textbox__"
            operation = {
                "op": "replace",
                "path": ["steps", index, "automation_id"],
                "value": original_step["automation_id"],
            }
            return failing_plan, operation, index
        if "role" in step:
            step["role"] = "__ai_desktop_loop_missing_role__"
            operation = {
                "op": "replace",
                "path": ["steps", index, "role"],
                "value": original_step["role"],
            }
            return failing_plan, operation, index
    raise ValueError("fixture plan does not contain a patchable desktop_element.set_text step")


def _adjust_operation_for_debug_injection(operation: dict[str, Any], prepare_result: dict[str, Any]) -> dict[str, Any]:
    adjusted = copy.deepcopy(operation)
    path = adjusted.get("path")
    if not isinstance(path, list) or len(path) < 2 or path[0] != "steps" or not isinstance(path[1], int):
        return adjusted
    injection = prepare_result.get("injection") if isinstance(prepare_result.get("injection"), dict) else {}
    injected_steps = injection.get("injected_steps") if isinstance(injection.get("injected_steps"), list) else []
    path[1] = path[1] + len(injected_steps)
    return adjusted


def _read_first_annotation(
    project_root: Path,
    tool_calls: list[dict[str, Any]],
    plan_path: Path,
    artifacts: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    annotation_artifacts = [
        artifact
        for artifact in artifacts.get("artifacts", [])
        if isinstance(artifact, dict)
        and str(artifact.get("relative_path", "")).lower().endswith(".json")
    ]
    if not annotation_artifacts:
        return {}, {}
    relative_path = str(annotation_artifacts[0].get("relative_path", ""))
    return _read_json_artifact(project_root, tool_calls, plan_path, relative_path)


def _read_json_artifact(
    project_root: Path,
    tool_calls: list[dict[str, Any]],
    plan_path: Path,
    relative_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    read = _call_tool(
        project_root,
        tool_calls,
        "read_output_artifact",
        {"plan_path": str(plan_path), "relative_path": relative_path, "max_bytes": 64_000},
    )
    content = read.get("content")
    if isinstance(content, str) and content.strip():
        try:
            return read, json.loads(content)
        except json.JSONDecodeError:
            return read, {}
    return read, {}


def _call_tool(
    project_root: Path,
    tool_calls: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
    *,
    allow_run_plan: bool = False,
) -> dict[str, Any]:
    try:
        result = call_ai_terminal_tool(
            project_root=project_root,
            tool_name=tool_name,
            arguments=arguments,
            allow_run_plan=allow_run_plan,
        )
    except Exception as error:
        result = {"ok": False, "error": str(error), "error_type": type(error).__name__}
    tool_calls.append(
        {
            "tool": tool_name,
            "arguments": _compact_arguments(arguments),
            "ok": bool(result.get("ok")),
            "error": str(result.get("error", ""))[:500],
        }
    )
    return result


def _compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(arguments)
    if isinstance(compacted.get("json_value"), dict):
        document = compacted["json_value"]
        compacted["json_value"] = {
            "automation_type": document.get("automation_type"),
            "step_count": len(document.get("steps", [])) if isinstance(document.get("steps"), list) else 0,
        }
    if "operations" in compacted and isinstance(compacted["operations"], list):
        compacted["operations"] = len(compacted["operations"])
    return compacted


def _failed_output_dir(run_result: dict[str, Any]) -> str:
    latest_state = run_result.get("latest_state") if isinstance(run_result.get("latest_state"), dict) else {}
    output_dir = latest_state.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        return output_dir
    result = run_result.get("result") if isinstance(run_result.get("result"), dict) else {}
    output_dir = result.get("output_dir")
    return str(output_dir or "")


def _workspace_root(prepare_result: dict[str, Any]) -> str:
    workspace = prepare_result.get("workspace") if isinstance(prepare_result.get("workspace"), dict) else {}
    root = workspace.get("root")
    if not isinstance(root, str) or not root:
        raise RuntimeError(f"prepare_failure_debug_workspace did not return workspace root: {prepare_result}")
    return root


def _ordered_subset(sequence: list[str], expected: list[str]) -> bool:
    cursor = 0
    for item in sequence:
        if cursor < len(expected) and item == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def _write_minimal_project_config(project_root: Path) -> None:
    (project_root / "plans").mkdir(parents=True, exist_ok=True)
    (project_root / "test-plans").mkdir(parents=True, exist_ok=True)
    (project_root / "handbook").mkdir(parents=True, exist_ok=True)
    (project_root / "plan.config").write_text(
        json.dumps(
            {
                "handbook_path": "handbook",
                "plan_roots": ["plans", "test-plans"],
                "default_ai_config_dir": "plans",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _self_check_result(*, name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed}
    if detail is not None:
        result["detail"] = detail
    return result
