from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from keygen_automation.artifacts import list_output_artifacts
from keygen_automation.debug_workspace import (
    apply_debug_patch,
    create_debug_workspace,
    find_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
    list_debug_workspaces,
)
from keygen_automation.executor import execute_plan
from keygen_automation.plan_loader import detect_document_type, load_plan
from keygen_automation.plan_packages import (
    create_plan_package,
    discover_plan_packages,
    find_latest_run_output,
    plan_matches_filter,
    summarize_plan,
)
from keygen_automation.validator import ValidationIssue, validate_plan_file


MAX_TEXT_ARTIFACT_BYTES = 256_000
MAX_FAILURE_HTML_SUMMARY_BYTES = 256_000
DOM_SUMMARY_TAGS = {"a", "button", "form", "input", "label", "option", "select", "textarea"}
DOM_TEXT_IGNORED_TAGS = {"head", "script", "style", "template"}
TEXT_ARTIFACT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def call_ai_terminal_tool(
    tool_name: str,
    project_root: str | Path,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_name not in AI_TERMINAL_TOOLS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOLS))
        raise ValueError(f"Unsupported AI terminal tool: {tool_name}. Supported tools: {supported}")
    tool = AI_TERMINAL_TOOLS[tool_name]
    tool_arguments = dict(arguments or {})
    if tool_name in PROJECT_ROOT_TOOLS:
        return tool(project_root, **tool_arguments)
    return tool(**tool_arguments)


def list_ai_terminal_tools() -> dict[str, Any]:
    return {
        "ok": True,
        "tools": [
            {
                "name": name,
                "requires_project_root": name in PROJECT_ROOT_TOOLS,
            }
            for name in sorted(AI_TERMINAL_TOOLS)
        ],
    }


def list_plan_packages_tool(project_root: str | Path, *, filter_text: str = "") -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_filter = filter_text.lower().strip()
    plan_paths = discover_plan_packages(root)
    if normalized_filter:
        plan_paths = [
            plan_path
            for plan_path in plan_paths
            if plan_matches_filter(plan_path, root, normalized_filter)
        ]
    return {
        "ok": True,
        "plans": [summarize_plan(plan_path, root) for plan_path in plan_paths],
    }


def read_plan_package_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = _resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent
    document = _read_json_if_exists(resolved_plan_path)
    local_config = _read_json_if_exists(package_dir / "config.json")
    docs = _read_package_docs(package_dir)
    sub_plans = _read_sub_plans(package_dir)
    resources = _list_package_files(package_dir / "resources", package_dir)
    return {
        "ok": True,
        "summary": summarize_plan(resolved_plan_path, root),
        "plan": document,
        "config": local_config,
        "docs": docs,
        "sub_plans": sub_plans,
        "resources": resources,
    }


def create_plan_package_tool(
    project_root: str | Path,
    package_path: str | Path,
    *,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    package_dir = create_plan_package(package_path, project_root=root, name=name, force=force)
    return {
        "ok": True,
        "package_dir": str(package_dir),
        "plan_path": str(package_dir / "plan.json"),
        "summary": summarize_plan(package_dir / "plan.json", root),
    }


def validate_plan_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    result = validate_plan_file(plan_path, project_root)
    return {
        "ok": result.ok,
        "plan_path": str(result.plan_path),
        "errors": [_issue_to_dict(error) for error in result.errors],
    }


def run_plan_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    document = load_plan(plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("Only plan documents can be executed.")
    try:
        result = execute_plan(
            document,
            root,
            plan_path=plan_path,
            run_name=run_name,
            variable_overrides=variable_overrides or {},
        )
    except Exception as error:
        latest_state = read_latest_run_state_tool(plan_path)
        return {
            "ok": False,
            "error": str(error),
            "latest_state": latest_state,
        }
    return {
        "ok": result.status == "passed",
        "result": result.to_dict(),
    }


def read_latest_run_state_tool(plan_path: str | Path) -> dict[str, Any]:
    resolved_plan_path = _resolve_plan_path(plan_path)
    output_dir = find_latest_run_output(resolved_plan_path.parent)
    if output_dir is None:
        return {"ok": True, "output_dir": "", "state": None}
    state_path = output_dir / "state.json"
    state = _read_json_if_exists(state_path)
    return {
        "ok": True,
        "output_dir": str(output_dir),
        "state": state,
    }


def read_latest_run_report_tool(plan_path: str | Path) -> dict[str, Any]:
    resolved_plan_path = _resolve_plan_path(plan_path)
    output_dir = find_latest_run_output(resolved_plan_path.parent)
    if output_dir is None:
        return {"ok": True, "output_dir": "", "path": "", "content": ""}
    report_path = output_dir / "report.md"
    return {
        "ok": report_path.exists(),
        "output_dir": str(output_dir),
        "path": str(report_path),
        "content": _read_text_if_exists(report_path),
    }


def analyze_latest_run_failure_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    log_lines: int = 80,
    event_lines: int = 80,
) -> dict[str, Any]:
    resolved_plan_path = _resolve_plan_path(plan_path)
    run_output_dir = _resolve_run_output_dir(resolved_plan_path, output_dir)
    state = _read_json_if_exists(run_output_dir / "state.json")
    result = _read_json_if_exists(run_output_dir / "result.json")
    events = _read_jsonl_tail(run_output_dir / "events.jsonl", event_lines)
    commands = _read_jsonl_tail(run_output_dir / "commands.jsonl", event_lines)
    log_tail = _tail_lines(run_output_dir / "run.log", log_lines) if (run_output_dir / "run.log").exists() else []
    report = _read_text_if_exists(run_output_dir / "report.md")

    status = _first_string(
        _dict_get(result, "status"),
        _dict_get(state, "status"),
        "<unknown>",
    )
    error = _first_string(
        _dict_get(result, "error"),
        _dict_get(state, "error"),
        _last_event_error(events),
        "",
    )
    failed_step = _detect_failed_step(events, state)
    plan_context = _read_plan_step_context(resolved_plan_path, failed_step)
    warnings = _filter_events(events, levels={"WARNING"})
    errors = _filter_events(events, levels={"ERROR"})
    failure_screenshots = _collect_failure_screenshots(run_output_dir, result)
    failure_htmls = _collect_failure_files(run_output_dir, result, result_key="failure_htmls", directory_name="failure-html")
    failure_page_states = _collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_page_states",
        directory_name="failure-page-state",
    )
    dom_summaries = [
        _summarize_failure_html(run_output_dir, html_path)
        for html_path in failure_htmls[:5]
    ]
    hints = _build_failure_hints(error=error, failed_step=failed_step, events=events)

    return {
        "ok": True,
        "plan_path": str(resolved_plan_path),
        "output_dir": str(run_output_dir),
        "status": status,
        "is_failure": status not in {"passed", "created", "running", "waiting"},
        "failed_step": failed_step,
        "plan_context": plan_context,
        "error": error,
        "hints": hints,
        "failure_screenshots": failure_screenshots,
        "failure_htmls": failure_htmls,
        "failure_page_states": failure_page_states,
        "dom_summaries": [summary for summary in dom_summaries if summary],
        "recent_errors": errors[-10:],
        "recent_warnings": warnings[-10:],
        "commands": commands[-20:],
        "report": report,
        "log_tail": log_tail,
        "events_tail": events[-20:],
        "next_actions": [
            "Read the failed step and nearby plan steps before changing anything.",
            "Create a debug workspace before injecting diagnostics or proposing a fix.",
            "Use patch_debug_workspace_json for minimal plan/config edits.",
            "Run and validate the injected debug plan before generating patch.diff.",
        ],
    }


def read_run_log_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 80,
) -> dict[str, Any]:
    run_output_dir = _resolve_run_output_dir(plan_path, output_dir)
    log_path = run_output_dir / "run.log"
    return {
        "ok": log_path.exists(),
        "output_dir": str(run_output_dir),
        "path": str(log_path),
        "lines": _tail_lines(log_path, lines) if log_path.exists() else [],
    }


def read_run_events_tool(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 40,
) -> dict[str, Any]:
    run_output_dir = _resolve_run_output_dir(plan_path, output_dir)
    events_path = run_output_dir / "events.jsonl"
    events: list[Any] = []
    if events_path.exists():
        for line in _tail_lines(events_path, lines):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"raw": line})
    return {
        "ok": events_path.exists(),
        "output_dir": str(run_output_dir),
        "path": str(events_path),
        "events": events,
    }


def list_output_artifacts_tool(
    plan_path: str | Path,
    *,
    filter_text: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
    return {
        "ok": True,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }


def read_output_artifact_tool(
    plan_path: str | Path,
    relative_path: str | Path,
    *,
    max_bytes: int = MAX_TEXT_ARTIFACT_BYTES,
) -> dict[str, Any]:
    resolved_plan_path = _resolve_plan_path(plan_path)
    output_root = (resolved_plan_path.parent / "output").resolve()
    artifact_path = (output_root / relative_path).resolve()
    if not _is_relative_to(artifact_path, output_root):
        raise ValueError("Artifact path must stay inside the current plan output directory.")
    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact does not exist: {artifact_path}")
    stat = artifact_path.stat()
    payload: dict[str, Any] = {
        "ok": True,
        "path": str(artifact_path),
        "relative_path": str(artifact_path.relative_to(output_root)),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "content": None,
        "truncated": False,
    }
    if artifact_path.suffix.lower() not in TEXT_ARTIFACT_SUFFIXES:
        return payload
    content = artifact_path.read_text(encoding="utf-8", errors="replace")
    if len(content.encode("utf-8")) > max_bytes:
        content = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        payload["truncated"] = True
    payload["content"] = content
    return payload


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
    output_dir: str | Path | None = None,
    name: str | None = None,
    include_manual_confirm: bool = False,
) -> dict[str, Any]:
    analysis = analyze_latest_run_failure_tool(
        plan_path,
        output_dir=output_dir,
        log_lines=40,
        event_lines=80,
    )
    status = _first_string(_dict_get(analysis, "status"))
    if status != "failed":
        raise ValueError(
            f"prepare_failure_debug_workspace requires a failed run; latest status is '{status}'. "
            "Run the plan first or pass a failed output_dir."
        )
    failed_step_number = _safe_int(_dict_get(_dict_get(analysis, "failed_step"), "step"))
    browser, page = _failure_browser_page(analysis)
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
    message = _failure_debug_message(analysis)
    injection = inject_debug_steps(
        workspace.root,
        presets=presets,
        message=message,
        browser=browser,
        page=page,
        position=position,
        step=failed_step_number,
    )
    _append_failure_debug_note(
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
    user_hint: str = "",
    apply: bool = False,
    run_after_apply: bool = False,
    run_name: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = _read_debug_manifest(workspace_root)
    source_plan_path = Path(manifest["source_copy_dir"]).resolve() / "plan.json"
    original_plan_path = Path(manifest["plan_path"]).resolve()
    analysis = analyze_latest_run_failure_tool(
        original_plan_path,
        log_lines=40,
        event_lines=80,
    )
    proposals = _build_debug_fix_proposals(analysis, source_plan_path, user_hint=user_hint)
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
    auto_apply_gate = _selector_auto_apply_gate(proposals, user_hint=user_hint)
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

    _reset_injected_file_to_source(manifest, "plan.json")
    patch_result = patch_debug_workspace_json_tool(
        workspace_root,
        root="injected-plan",
        relative_path="plan.json",
        operations=[selected["operation"]],
    )
    _append_debug_fix_note(workspace_root, selected)
    validation = validate_debug_plan_tool(project_root, workspace=workspace_root)
    patch = generate_debug_patch_tool(workspace_root)
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
        result["debug_run"] = run_debug_plan_tool(
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
    manifest = _read_debug_manifest(workspace_root)
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    return {
        "ok": True,
        "manifest": manifest,
        "source": _read_debug_plan_tree(source_copy_dir),
        "injected": _read_debug_plan_tree(injected_plan_dir),
        "notes": _read_text_if_exists(Path(manifest["notes_path"]).resolve()),
        "report": _read_text_if_exists(Path(manifest["report_path"]).resolve()),
        "patch": _read_text_if_exists(Path(manifest["patch_path"]).resolve()),
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
    manifest = _read_debug_manifest(workspace_root)
    target_path = _resolve_debug_write_path(
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
        "relative_path": _debug_relative_path(manifest, target_path),
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
    manifest = _read_debug_manifest(workspace_root)
    target_path = _resolve_debug_write_path(
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

    original_text = _read_text_preserve_newlines(target_path)
    try:
        document = json.loads(original_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Target file is not valid JSON: {error.msg}") from error

    normalized_operations = [_normalize_json_patch_operation(operation) for operation in operations]
    updated_document = _apply_json_patch_operations(document, normalized_operations)
    updated_text, strategy = _serialize_json_patch_result(
        original_text,
        updated_document,
        normalized_operations,
    )
    _write_text_preserve_newlines(target_path, updated_text)

    return {
        "ok": True,
        "path": str(target_path),
        "relative_path": _debug_relative_path(manifest, target_path),
        "operations": len(normalized_operations),
        "write_strategy": strategy,
        "size": target_path.stat().st_size,
    }


def validate_debug_plan_tool(project_root: str | Path, *, workspace: str | Path) -> dict[str, Any]:
    manifest = _read_debug_manifest(Path(workspace).resolve())
    return validate_plan_tool(project_root, Path(manifest["injected_plan_dir"]) / "plan.json")


def run_debug_plan_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _read_debug_manifest(Path(workspace).resolve())
    injected_plan_path = Path(manifest["injected_plan_dir"]) / "plan.json"
    return run_plan_tool(
        project_root,
        injected_plan_path,
        run_name=run_name,
        variable_overrides=variable_overrides,
    )


def _resolve_plan_path(raw_plan_path: str | Path) -> Path:
    plan_path = Path(raw_plan_path).resolve()
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"
    return plan_path


def _resolve_run_output_dir(plan_path: str | Path, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).resolve()
    resolved_plan_path = _resolve_plan_path(plan_path)
    latest_output = find_latest_run_output(resolved_plan_path.parent)
    if latest_output is None:
        return resolved_plan_path.parent / "output"
    return latest_output


def _issue_to_dict(issue: ValidationIssue) -> dict[str, str]:
    return {
        "location": issue.location,
        "message": issue.message,
        "formatted": issue.format(),
    }


def _read_package_docs(package_dir: Path) -> list[dict[str, Any]]:
    docs_dir = package_dir / "docs"
    docs: list[dict[str, Any]] = []
    if not docs_dir.exists():
        return docs
    for path in sorted(docs_dir.rglob("*.md"), key=lambda item: str(item).lower()):
        docs.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "content": path.read_text(encoding="utf-8", errors="replace"),
            }
        )
    return docs


def _read_sub_plans(package_dir: Path) -> list[dict[str, Any]]:
    sub_plans_dir = package_dir / "sub-plans"
    sub_plans: list[dict[str, Any]] = []
    if not sub_plans_dir.exists():
        return sub_plans
    for path in sorted(sub_plans_dir.glob("*-plan.json"), key=lambda item: str(item).lower()):
        sub_plans.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "document": _read_json_if_exists(path),
            }
        )
    return sub_plans


def _list_package_files(root: Path, package_dir: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return files


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0:
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]


def _read_jsonl_tail(path: Path, count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in _tail_lines(path, count):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = {"raw": line}
        if isinstance(value, dict):
            events.append(value)
        else:
            events.append({"value": value})
    return events


def _dict_get(value: Any, key: str) -> Any:
    if not isinstance(value, dict):
        return None
    return value.get(key)


def _first_string(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def _safe_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _failure_browser_page(analysis: dict[str, Any]) -> tuple[str | None, str | None]:
    failure_page_states = _dict_get(analysis, "failure_page_states")
    if isinstance(failure_page_states, list):
        for raw_path in failure_page_states:
            try:
                state = _read_json_if_exists(Path(str(raw_path)))
            except OSError:
                state = None
            browser = _first_string(_dict_get(state, "browser"))
            page = _first_string(_dict_get(state, "page"))
            if browser:
                return browser, page or None

    failed_plan_step = _dict_get(_dict_get(analysis, "plan_context"), "failed_step")
    browser = _first_string(_dict_get(failed_plan_step, "browser"))
    page = _first_string(_dict_get(failed_plan_step, "page"))
    if browser:
        return browser, page or None
    return None, None


def _failure_debug_message(analysis: dict[str, Any]) -> str:
    failed_step = _dict_get(analysis, "failed_step")
    step_number = _dict_get(failed_step, "step")
    plan_failed_step = _dict_get(_dict_get(analysis, "plan_context"), "failed_step")
    action = _dict_get(failed_step, "action") or _dict_get(plan_failed_step, "action") or "step"
    error = _first_string(_dict_get(analysis, "error")).splitlines()[0:1]
    error_text = error[0] if error else "unknown failure"
    if step_number:
        return f"[debug] before failed step {step_number}: {action}; {error_text}"
    return f"[debug] failure diagnostic checkpoint: {error_text}"


def _append_failure_debug_note(
    workspace_root: Path,
    *,
    analysis: dict[str, Any],
    presets: list[str],
    position: str,
    step: int | None,
    browser: str | None,
    page: str | None,
) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Failure Debug Preparation\n\n")
        file.write(f"- Source run: `{_dict_get(analysis, 'output_dir')}`\n")
        file.write(f"- Failed step: `{step or '<unknown>'}`\n")
        file.write(f"- Injection position: `{position}`\n")
        file.write(f"- Presets: `{', '.join(presets)}`\n")
        file.write(f"- Browser/Page: `{browser or '<none>'}` / `{page or '<default>'}`\n")
        error = _first_string(_dict_get(analysis, "error")).strip()
        if error:
            file.write("\n### Error\n\n")
            file.write("```text\n")
            file.write(error[:2000])
            file.write("\n```\n")
        dom_summaries = _dict_get(analysis, "dom_summaries")
        if isinstance(dom_summaries, list) and dom_summaries:
            elements = _dict_get(dom_summaries[0], "elements")
            if isinstance(elements, list) and elements:
                file.write("\n### DOM Selector Hints\n\n")
                for element in elements[:20]:
                    if not isinstance(element, dict):
                        continue
                    tag = _dict_get(element, "tag")
                    selector = _dict_get(element, "selector_hint")
                    text = _dict_get(element, "text")
                    file.write(f"- `{tag}` `{selector}`")
                    if text:
                        file.write(f" - {text}")
                    file.write("\n")


def _build_debug_fix_proposals(
    analysis: dict[str, Any],
    source_plan_path: Path,
    *,
    user_hint: str,
) -> list[dict[str, Any]]:
    plan_context = _dict_get(analysis, "plan_context")
    step_index = _safe_int(_dict_get(plan_context, "step_number"))
    if step_index is None:
        return []
    zero_based_index = step_index - 1
    source_document = _read_json_if_exists(source_plan_path)
    steps = _dict_get(source_document, "steps")
    if not isinstance(steps, list) or zero_based_index >= len(steps):
        return []
    failed_step = steps[zero_based_index]
    if not isinstance(failed_step, dict):
        return []
    if failed_step.get("action") != "wait" or failed_step.get("type") != "selector":
        return []
    current_selector = _first_string(failed_step.get("selector"))
    if not current_selector:
        return []

    candidates = _rank_selector_candidates(
        _dict_get(analysis, "dom_summaries"),
        current_selector=current_selector,
        user_hint=user_hint,
    )
    proposals: list[dict[str, Any]] = []
    for candidate in candidates[:5]:
        selector = candidate["selector"]
        proposal = {
            "type": "selector_replace",
            "confidence": candidate["confidence"],
            "score": candidate["score"],
            "step_number": step_index,
            "from": current_selector,
            "to": selector,
            "operation": {
                "op": "replace",
                "path": ["steps", zero_based_index, "selector"],
                "value": selector,
            },
            "reason": _selector_fix_reason(current_selector, candidate, user_hint=user_hint),
            "evidence": candidate["element"],
        }
        proposals.append(proposal)
    return proposals


def _rank_selector_candidates(
    dom_summaries: Any,
    *,
    current_selector: str,
    user_hint: str,
) -> list[dict[str, Any]]:
    elements = _dom_summary_elements(dom_summaries)
    user_hint_tokens = _tokenize_selector_text(user_hint)
    current_tokens = _tokenize_selector_text(current_selector)
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        selector = _first_string(_dict_get(element, "selector_hint")).strip()
        tag = _first_string(_dict_get(element, "tag")).strip().lower()
        attrs = _dict_get(element, "attrs")
        if not selector or selector == current_selector:
            continue
        if selector in seen:
            continue
        if _is_weak_selector_hint(selector, tag):
            continue
        if isinstance(attrs, dict) and str(attrs.get("type", "")).lower() == "hidden":
            continue
        score = _score_selector_candidate(
            selector=selector,
            tag=tag,
            element=element,
            user_hint_tokens=user_hint_tokens,
            current_tokens=current_tokens,
        )
        seen.add(selector)
        candidates.append(
            {
                "selector": selector,
                "score": score,
                "confidence": _selector_confidence(score, user_hint_tokens=user_hint_tokens),
                "element": element,
            }
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def _selector_auto_apply_gate(proposals: list[dict[str, Any]], *, user_hint: str) -> dict[str, Any]:
    if not proposals:
        return {"ok": False, "reason": "No selector proposal is available."}
    selected = proposals[0]
    if selected.get("type") != "selector_replace":
        return {"ok": True, "reason": "Non-selector proposals do not use the selector ambiguity gate."}
    hint_tokens = _tokenize_selector_text(user_hint)
    if not hint_tokens:
        return {
            "ok": False,
            "reason": (
                "Selector replacement is ambiguous without a user_hint. "
                "The tool can list candidates, but will not auto-apply one only because it exists in the DOM."
            ),
        }
    confidence = str(selected.get("confidence", ""))
    score = _safe_int(selected.get("score")) or 0
    if confidence != "high" or score < 85:
        return {
            "ok": False,
            "reason": (
                f"Selected selector confidence is {confidence or '<unknown>'} with score {score}; "
                "auto-apply requires high confidence from a clear hint."
            ),
        }
    if len(proposals) > 1:
        second_score = _safe_int(proposals[1].get("score")) or 0
        if score - second_score < 10:
            return {
                "ok": False,
                "reason": (
                    "Top selector candidates are too close in score. "
                    f"Selected score is {score}, second score is {second_score}; review manually."
                ),
            }
    return {"ok": True, "reason": "Selector candidate is high-confidence and sufficiently distinct."}


def _dom_summary_elements(dom_summaries: Any) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    if not isinstance(dom_summaries, list):
        return elements
    for summary in dom_summaries:
        summary_elements = _dict_get(summary, "elements")
        if not isinstance(summary_elements, list):
            continue
        elements.extend(element for element in summary_elements if isinstance(element, dict))
    return elements


def _is_weak_selector_hint(selector: str, tag: str) -> bool:
    if selector.startswith("#") or "[" in selector:
        return False
    return tag in {"form", "label"} or selector == tag


def _score_selector_candidate(
    *,
    selector: str,
    tag: str,
    element: dict[str, Any],
    user_hint_tokens: set[str],
    current_tokens: set[str],
) -> int:
    attrs = _dict_get(element, "attrs")
    attrs_text = json.dumps(attrs if isinstance(attrs, dict) else {}, ensure_ascii=False)
    text = _first_string(_dict_get(element, "text"))
    searchable = " ".join([selector, tag, attrs_text, text]).lower()
    searchable_tokens = _tokenize_selector_text(searchable)

    score = 0
    if selector.startswith("#"):
        score += 40
    elif "[" in selector:
        score += 32
    else:
        score += 8
    if tag in {"input", "button", "select", "textarea"}:
        score += 24
    elif tag == "a":
        score += 16
    if isinstance(attrs, dict):
        if attrs.get("autocomplete"):
            score += 8
        if attrs.get("placeholder"):
            score += 8
        if attrs.get("name"):
            score += 8
        if attrs.get("aria-label"):
            score += 8
    if text:
        score += 6
    if user_hint_tokens:
        overlap = user_hint_tokens & searchable_tokens
        score += min(50, len(overlap) * 25)
        if _compact_search_text(user_hint_tokens) and _compact_search_text(user_hint_tokens) in _compact_search_text(searchable_tokens):
            score += 50
    if current_tokens:
        overlap = current_tokens & searchable_tokens
        score += min(20, len(overlap) * 10)
    return score


def _selector_confidence(score: int, *, user_hint_tokens: set[str]) -> str:
    if user_hint_tokens and score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _selector_fix_reason(current_selector: str, candidate: dict[str, Any], *, user_hint: str) -> str:
    selector = candidate["selector"]
    confidence = candidate["confidence"]
    reason = (
        f"Failed selector `{current_selector}` was not found, while `{selector}` appears in the captured failure DOM. "
        f"Confidence is {confidence} based on selector stability and DOM attributes."
    )
    if user_hint.strip():
        reason += f" User hint used for ranking: {user_hint.strip()!r}."
    else:
        reason += " No user hint was supplied, so review the selector before applying it to the original plan."
    return reason


def _tokenize_selector_text(value: str) -> set[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return {token for token in normalized.split() if len(token) >= 2}


def _compact_search_text(tokens: set[str]) -> str:
    return "".join(sorted(tokens))


def _reset_injected_file_to_source(manifest: dict[str, Any], relative_path: str) -> None:
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    raw_path = Path(relative_path)
    if raw_path.is_absolute() or _is_forbidden_debug_write_path(raw_path):
        raise ValueError(f"Refusing to reset forbidden debug path: {relative_path}")
    source_path = (source_copy_dir / raw_path).resolve()
    target_path = (injected_plan_dir / raw_path).resolve()
    if not _is_relative_to(source_path, source_copy_dir) or not _is_relative_to(target_path, injected_plan_dir):
        raise ValueError("Debug reset path must stay inside source-copy/ and injected-plan/.")
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"Source debug file does not exist: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())


def _append_debug_fix_note(workspace_root: Path, proposal: dict[str, Any]) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Fix Candidate\n\n")
        file.write("- Source: `propose_debug_fix`\n")
        file.write(f"- Type: `{proposal.get('type')}`\n")
        file.write(f"- Confidence: `{proposal.get('confidence')}`\n")
        file.write(f"- Step: `{proposal.get('step_number')}`\n")
        file.write(f"- Selector: `{proposal.get('from')}` -> `{proposal.get('to')}`\n")
        file.write("\n### Operation\n\n")
        file.write("```json\n")
        json.dump(proposal.get("operation"), file, ensure_ascii=False, indent=2)
        file.write("\n```\n")
        file.write("\n### Reason\n\n")
        file.write(str(proposal.get("reason", "")).strip() + "\n")


def _last_event_error(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if str(event.get("level", "")).upper() != "ERROR":
            continue
        fields = event.get("fields", {})
        if isinstance(fields, dict) and fields.get("error"):
            return str(fields["error"])
        if event.get("message"):
            return str(event["message"])
    return ""


def _detect_failed_step(events: list[dict[str, Any]], state: Any) -> dict[str, Any] | None:
    for event in reversed(events):
        message = str(event.get("message", ""))
        if "failed" not in message.lower():
            continue
        fields = event.get("fields", {})
        if not isinstance(fields, dict):
            continue
        if "step" not in fields and "action" not in fields:
            continue
        return {
            "step": fields.get("step"),
            "action": fields.get("action"),
            "step_name": fields.get("step_name"),
            "error": fields.get("error"),
            "event_message": message,
            "timestamp": event.get("timestamp"),
        }
    current_step = _dict_get(state, "current_step")
    if isinstance(current_step, dict):
        return dict(current_step)
    return None


def _read_plan_step_context(plan_path: Path, failed_step: dict[str, Any] | None) -> dict[str, Any]:
    if not failed_step:
        return {}
    step_number = failed_step.get("step")
    if not isinstance(step_number, int) or step_number <= 0:
        return {}
    document = _read_json_if_exists(plan_path)
    if not isinstance(document, dict):
        return {}
    steps = document.get("steps")
    if not isinstance(steps, list):
        return {}
    index = step_number - 1
    if index < 0 or index >= len(steps):
        return {}
    start = max(0, index - 1)
    end = min(len(steps), index + 2)
    return {
        "step_number": step_number,
        "step_index": index,
        "failed_step": steps[index],
        "nearby_steps": [
            {
                "step_number": item_index + 1,
                "step": steps[item_index],
            }
            for item_index in range(start, end)
        ],
    }


def _filter_events(events: list[dict[str, Any]], *, levels: set[str]) -> list[dict[str, Any]]:
    normalized_levels = {level.upper() for level in levels}
    return [
        event
        for event in events
        if str(event.get("level", "")).upper() in normalized_levels
    ]


def _collect_failure_screenshots(run_output_dir: Path, result: Any) -> list[str]:
    return _collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_screenshots",
        directory_name="failure-screenshots",
    )


def _collect_failure_files(
    run_output_dir: Path,
    result: Any,
    *,
    result_key: str,
    directory_name: str,
) -> list[str]:
    files: list[str] = []
    result_files = _dict_get(result, result_key)
    if isinstance(result_files, list):
        files.extend(str(item) for item in result_files)
    failure_dir = run_output_dir / directory_name
    if failure_dir.exists():
        files.extend(str(path.resolve()) for path in sorted(failure_dir.glob("*")) if path.is_file())
    return sorted(dict.fromkeys(files))


def _summarize_failure_html(run_output_dir: Path, raw_html_path: str) -> dict[str, Any]:
    html_path = Path(raw_html_path).resolve()
    if not _is_relative_to(html_path, run_output_dir.resolve()):
        return {}
    if not html_path.exists() or not html_path.is_file():
        return {}
    raw_text = html_path.read_text(encoding="utf-8", errors="replace")
    if len(raw_text.encode("utf-8")) > MAX_FAILURE_HTML_SUMMARY_BYTES:
        raw_text = raw_text.encode("utf-8")[:MAX_FAILURE_HTML_SUMMARY_BYTES].decode("utf-8", errors="ignore")
    parser = FailureDomSummaryParser()
    parser.feed(raw_text)
    return {
        "path": str(html_path),
        "relative_path": str(html_path.relative_to(run_output_dir.resolve())),
        "truncated": len(raw_text.encode("utf-8")) >= MAX_FAILURE_HTML_SUMMARY_BYTES,
        "elements": parser.elements[:80],
        "text_snippets": parser.text_snippets[:40],
    }


class FailureDomSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, Any]] = []
        self.text_snippets: list[str] = []
        self._capture_stack: list[dict[str, Any]] = []
        self._ignored_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in DOM_TEXT_IGNORED_TAGS:
            self._ignored_stack.append(normalized_tag)
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if normalized_tag in DOM_SUMMARY_TAGS:
            element = {
                "tag": normalized_tag,
                "selector_hint": _selector_hint(normalized_tag, attrs_dict),
                "attrs": _interesting_attrs(attrs_dict),
                "text": "",
            }
            self.elements.append(element)
            if normalized_tag in {"a", "button", "label", "option", "textarea"}:
                self._capture_stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._ignored_stack and self._ignored_stack[-1] == normalized_tag:
            self._ignored_stack.pop()
        if normalized_tag not in {"a", "button", "label", "option", "textarea"}:
            return
        if self._capture_stack:
            self._capture_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored_stack:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_stack:
            element = self._capture_stack[-1]
            current = str(element.get("text", ""))
            element["text"] = (current + " " + text).strip()[:200]
        if len(text) >= 2 and len(self.text_snippets) < 80:
            self.text_snippets.append(text[:200])


def _interesting_attrs(attrs: dict[str, str]) -> dict[str, str]:
    keys = [
        "id",
        "name",
        "type",
        "class",
        "placeholder",
        "autocomplete",
        "aria-label",
        "role",
        "href",
        "for",
        "value",
    ]
    return {key: attrs[key] for key in keys if attrs.get(key)}


def _selector_hint(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get("id"):
        return f"#{attrs['id']}"
    if attrs.get("name"):
        return f"{tag}[name='{attrs['name']}']"
    if attrs.get("autocomplete"):
        return f"{tag}[autocomplete='{attrs['autocomplete']}']"
    if attrs.get("placeholder"):
        return f"{tag}[placeholder='{attrs['placeholder']}']"
    if attrs.get("aria-label"):
        return f"{tag}[aria-label='{attrs['aria-label']}']"
    return tag


def _build_failure_hints(
    *,
    error: str,
    failed_step: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> list[str]:
    text = " ".join(
        [
            error.lower(),
            json.dumps(failed_step or {}, ensure_ascii=False).lower(),
            " ".join(str(event.get("message", "")).lower() for event in events[-10:]),
        ]
    )
    hints: list[str] = []
    if "timeout" in text or "selector" in text:
        hints.append("Likely selector or wait timing issue; inspect failed selector, page state, screenshot, and failure HTML DOM.")
    if "manual confirmation" in text:
        hints.append("Manual confirmation stopped or was not accepted; confirm whether user intervention should continue or abort.")
    if "schema validation" in text or "json" in text and "ai" in text:
        hints.append("AI response/schema mismatch is possible; inspect output/ai artifact raw response and parsed result.")
    if "runtime output" in text or "output paths" in text:
        hints.append("Output path constraint failed; ensure action paths are relative to output/ and do not start with output/resources/docs.")
    if not hints:
        hints.append("No specific heuristic matched; inspect recent_errors, log_tail, and the failed step in plan.json.")
    return hints


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _read_debug_manifest(workspace_root: Path) -> dict[str, Any]:
    manifest_path = workspace_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Debug workspace manifest not found: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"Debug workspace manifest must be a JSON object: {manifest_path}")
    required = ("source_copy_dir", "injected_plan_dir", "notes_path", "report_path", "patch_path")
    for key in required:
        if key not in manifest:
            raise ValueError(f"Debug workspace manifest missing {key}: {manifest_path}")
    return manifest


def _read_debug_plan_tree(root: Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "plan": _read_json_if_exists(root / "plan.json"),
        "config": _read_json_if_exists(root / "config.json"),
        "docs": _read_package_docs(root),
        "sub_plans": _read_sub_plans(root),
        "resources": _list_package_files(root / "resources", root),
    }


def _resolve_debug_write_path(
    manifest: dict[str, Any],
    *,
    root: str,
    relative_path: str,
) -> Path:
    normalized_root = root.strip().lower()
    if normalized_root == "notes":
        return Path(manifest["notes_path"]).resolve()
    if normalized_root == "report":
        return Path(manifest["report_path"]).resolve()
    if normalized_root != "injected-plan":
        raise ValueError("root must be injected-plan, notes, or report.")

    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise ValueError("relative_path must be relative to injected-plan/.")
    if not raw_path.parts:
        raise ValueError("relative_path cannot be empty.")
    if _is_forbidden_debug_write_path(raw_path):
        raise ValueError(f"Refusing to write forbidden debug path: {relative_path}")
    if not _is_allowed_plan_package_write_path(raw_path):
        raise ValueError(
            "Debug writes under injected-plan are limited to plan.json, config.json, docs/, resources/, and sub-plans/."
        )
    target_path = (injected_plan_dir / raw_path).resolve()
    if not _is_relative_to(target_path, injected_plan_dir):
        raise ValueError("relative_path must stay inside injected-plan/.")
    return target_path


def _is_forbidden_debug_write_path(path: Path) -> bool:
    forbidden_parts = {
        "output",
        "__pycache__",
        ".debug-backups",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    return any(part in forbidden_parts for part in path.parts)


def _is_allowed_plan_package_write_path(path: Path) -> bool:
    if len(path.parts) == 1 and path.name in {"plan.json", "config.json"}:
        return True
    if path.parts[0] in {"docs", "resources", "sub-plans"}:
        return True
    return False


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_text_preserve_newlines(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as file:
        return file.read()


def _write_text_preserve_newlines(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(content)


def _debug_relative_path(manifest: dict[str, Any], path: Path) -> str:
    workspace_root = Path(manifest["root"]).resolve() if manifest.get("root") else path.parent
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path)


def _normalize_json_patch_operation(operation: Any) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise ValueError("Each JSON patch operation must be an object.")
    op_name = str(operation.get("op", "")).strip().lower()
    if op_name not in {"add", "replace", "remove"}:
        raise ValueError("JSON patch operation op must be add, replace, or remove.")
    path = _normalize_json_path(operation.get("path"))
    if op_name in {"add", "replace"} and "value" not in operation:
        raise ValueError(f"JSON patch operation '{op_name}' requires value.")
    normalized: dict[str, Any] = {
        "op": op_name,
        "path": path,
    }
    if "value" in operation:
        normalized["value"] = operation["value"]
    return normalized


def _normalize_json_path(raw_path: Any) -> list[Any]:
    if isinstance(raw_path, list):
        path: list[Any] = []
        for segment in raw_path:
            if isinstance(segment, bool) or not isinstance(segment, (str, int)):
                raise ValueError("JSON path array segments must be strings or integers.")
            path.append(segment)
        return path
    if isinstance(raw_path, str):
        if raw_path == "":
            return []
        if not raw_path.startswith("/"):
            raise ValueError("String JSON paths must be JSON Pointer values, for example /steps/0/message.")
        return [_unescape_json_pointer_segment(segment) for segment in raw_path.split("/")[1:]]
    raise ValueError("JSON patch operation path must be an array or JSON Pointer string.")


def _unescape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _apply_json_patch_operations(document: Any, operations: list[dict[str, Any]]) -> Any:
    current_document = document
    for operation in operations:
        op_name = operation["op"]
        path = operation["path"]
        if op_name == "replace":
            current_document = _replace_json_path(current_document, path, operation["value"])
        elif op_name == "add":
            current_document = _add_json_path(current_document, path, operation["value"])
        elif op_name == "remove":
            current_document = _remove_json_path(current_document, path)
        else:
            raise ValueError(f"Unsupported JSON patch operation: {op_name}")
    return current_document


def _replace_json_path(document: Any, path: list[Any], value: Any) -> Any:
    if not path:
        return value
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {_format_json_path(path)}")
        parent[key] = value
        return document
    if isinstance(parent, list):
        index = _coerce_json_list_index(segment, len(parent), allow_end=False)
        parent[index] = value
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _add_json_path(document: Any, path: list[Any], value: Any) -> Any:
    if not path:
        return value
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        parent[str(segment)] = value
        return document
    if isinstance(parent, list):
        if segment == "-":
            parent.append(value)
            return document
        index = _coerce_json_list_index(segment, len(parent), allow_end=True)
        parent.insert(index, value)
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _remove_json_path(document: Any, path: list[Any]) -> Any:
    if not path:
        raise ValueError("Removing the JSON document root is not supported.")
    parent, segment = _resolve_json_parent(document, path)
    if isinstance(parent, dict):
        key = str(segment)
        if key not in parent:
            raise KeyError(f"JSON path does not exist: {_format_json_path(path)}")
        del parent[key]
        return document
    if isinstance(parent, list):
        index = _coerce_json_list_index(segment, len(parent), allow_end=False)
        del parent[index]
        return document
    raise TypeError(f"JSON path parent is not a container: {_format_json_path(path[:-1])}")


def _resolve_json_parent(document: Any, path: list[Any]) -> tuple[Any, Any]:
    current = document
    for depth, segment in enumerate(path[:-1], start=1):
        if isinstance(current, dict):
            key = str(segment)
            if key not in current:
                raise KeyError(f"JSON path does not exist: {_format_json_path(path[:depth])}")
            current = current[key]
            continue
        if isinstance(current, list):
            index = _coerce_json_list_index(segment, len(current), allow_end=False)
            current = current[index]
            continue
        raise TypeError(f"JSON path segment is not reachable: {_format_json_path(path[:depth])}")
    return current, path[-1]


def _coerce_json_list_index(segment: Any, length: int, *, allow_end: bool) -> int:
    if isinstance(segment, bool):
        raise TypeError("JSON array index cannot be a boolean.")
    if isinstance(segment, int):
        index = segment
    elif isinstance(segment, str) and segment.isdecimal():
        index = int(segment)
    else:
        raise TypeError(f"JSON array index must be an integer, got {segment!r}.")
    upper_bound = length if allow_end else length - 1
    if index < 0 or index > upper_bound:
        raise IndexError(f"JSON array index out of range: {index}")
    return index


def _format_json_path(path: list[Any]) -> str:
    if not path:
        return "<root>"
    return "/" + "/".join(str(segment).replace("~", "~0").replace("/", "~1") for segment in path)


def _serialize_json_patch_result(
    original_text: str,
    updated_document: Any,
    operations: list[dict[str, Any]],
) -> tuple[str, str]:
    patched_text = _try_patch_json_text_in_place(original_text, updated_document, operations)
    if patched_text is not None:
        return patched_text, "in_place"
    return json.dumps(updated_document, ensure_ascii=False, indent=2) + _detect_json_trailing_newline(original_text), "rewrite"


def _try_patch_json_text_in_place(
    original_text: str,
    updated_document: Any,
    operations: list[dict[str, Any]],
) -> str | None:
    candidate = original_text
    for operation in operations:
        if operation["op"] != "replace":
            return None
        value = operation["value"]
        if isinstance(value, (dict, list)):
            return None
        try:
            start, end = _find_json_value_span(candidate, operation["path"])
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        candidate = candidate[:start] + json.dumps(value, ensure_ascii=False) + candidate[end:]
    try:
        if json.loads(candidate) != updated_document:
            return None
    except json.JSONDecodeError:
        return None
    return candidate


def _detect_json_trailing_newline(original_text: str) -> str:
    if original_text.endswith("\r\n"):
        return "\r\n"
    if original_text.endswith("\n"):
        return "\n"
    return "\n"


def _find_json_value_span(text: str, path: list[Any]) -> tuple[int, int]:
    start = _skip_json_whitespace(text, 0)
    if start >= len(text):
        raise ValueError("JSON text is empty.")
    return _find_json_value_span_from(text, start, path)


def _find_json_value_span_from(text: str, index: int, path: list[Any]) -> tuple[int, int]:
    start = _skip_json_whitespace(text, index)
    if not path:
        return start, _scan_json_value_end(text, start)
    if start >= len(text):
        raise ValueError("Unexpected end of JSON text.")
    marker = text[start]
    if marker == "{":
        return _find_json_object_member_span(text, start, path)
    if marker == "[":
        return _find_json_array_item_span(text, start, path)
    raise TypeError(f"JSON path cannot continue through scalar at {_format_json_path(path)}")


def _find_json_object_member_span(text: str, object_start: int, path: list[Any]) -> tuple[int, int]:
    target_key = str(path[0])
    index = _skip_json_whitespace(text, object_start + 1)
    if index < len(text) and text[index] == "}":
        raise KeyError(f"JSON object key does not exist: {target_key}")
    while index < len(text):
        key, index = _parse_json_string(text, index)
        index = _skip_json_whitespace(text, index)
        if index >= len(text) or text[index] != ":":
            raise ValueError("Invalid JSON object: expected colon after key.")
        value_start = _skip_json_whitespace(text, index + 1)
        value_end = _scan_json_value_end(text, value_start)
        if key == target_key:
            if len(path) == 1:
                return value_start, value_end
            return _find_json_value_span_from(text, value_start, path[1:])
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "}":
            raise KeyError(f"JSON object key does not exist: {target_key}")
        raise ValueError("Invalid JSON object: expected comma or closing brace.")
    raise ValueError("Invalid JSON object: missing closing brace.")


def _find_json_array_item_span(text: str, array_start: int, path: list[Any]) -> tuple[int, int]:
    target_index = _coerce_json_list_index(path[0], _json_array_length(text, array_start), allow_end=False)
    index = _skip_json_whitespace(text, array_start + 1)
    current_index = 0
    if index < len(text) and text[index] == "]":
        raise IndexError(f"JSON array index out of range: {target_index}")
    while index < len(text):
        value_start = _skip_json_whitespace(text, index)
        value_end = _scan_json_value_end(text, value_start)
        if current_index == target_index:
            if len(path) == 1:
                return value_start, value_end
            return _find_json_value_span_from(text, value_start, path[1:])
        current_index += 1
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "]":
            raise IndexError(f"JSON array index out of range: {target_index}")
        raise ValueError("Invalid JSON array: expected comma or closing bracket.")
    raise ValueError("Invalid JSON array: missing closing bracket.")


def _json_array_length(text: str, array_start: int) -> int:
    index = _skip_json_whitespace(text, array_start + 1)
    length = 0
    if index < len(text) and text[index] == "]":
        return 0
    while index < len(text):
        value_start = _skip_json_whitespace(text, index)
        value_end = _scan_json_value_end(text, value_start)
        length += 1
        index = _skip_json_whitespace(text, value_end)
        if index < len(text) and text[index] == ",":
            index = _skip_json_whitespace(text, index + 1)
            continue
        if index < len(text) and text[index] == "]":
            return length
        raise ValueError("Invalid JSON array: expected comma or closing bracket.")
    raise ValueError("Invalid JSON array: missing closing bracket.")


def _parse_json_string(text: str, index: int) -> tuple[str, int]:
    index = _skip_json_whitespace(text, index)
    if index >= len(text) or text[index] != '"':
        raise ValueError("Invalid JSON: expected string.")
    value, end = json.JSONDecoder().raw_decode(text, index)
    if not isinstance(value, str):
        raise ValueError("Invalid JSON: expected string.")
    return value, end


def _scan_json_value_end(text: str, index: int) -> int:
    _, end = json.JSONDecoder().raw_decode(text, index)
    return end


def _skip_json_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


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
