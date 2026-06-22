from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from ai_automate_contro.app.runtime_config import plan_roots_for_project
from ai_automate_contro.ai.terminal_tool_registry import (
    AI_TERMINAL_TOOL_SPECS,
    call_ai_terminal_tool,
    check_ai_terminal_tool_registry,
)
from ai_automate_contro.ai.plan_quality import compute_plan_signature, review_plan_quality_tool as review_plan_quality_direct
from ai_automate_contro.ai.plan_tools import resolve_plan_path
from ai_automate_contro.plans.packages import create_plan_package


def build_langchain_tools(
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None = None,
    before_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    thread_id_provider: Callable[[], str] | None = None,
    manual_confirmation_handler: Callable[[str], bool] | None = None,
    inspection_confirmation_handler: Callable[[str], bool] | None = None,
    run_event_handler: Callable[[str, dict[str, Any]], None] | None = None,
    quality_gate_provider: Callable[[], dict[str, Any]] | None = None,
) -> list[StructuredTool]:
    _ensure_langchain_tool_registry_consistent()
    return [
        _build_structured_tool(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            before_tool_call=before_tool_call,
            after_tool_call=after_tool_call,
            thread_id_provider=thread_id_provider,
            manual_confirmation_handler=manual_confirmation_handler,
            inspection_confirmation_handler=inspection_confirmation_handler,
            run_event_handler=run_event_handler,
            quality_gate_provider=quality_gate_provider,
        )
        for tool_name in AI_TERMINAL_TOOL_SPECS
    ]


def _ensure_langchain_tool_registry_consistent() -> None:
    result = check_ai_terminal_tool_registry()
    if not result["ok"]:
        raise RuntimeError("AI 终端工具注册表不一致：" + "；".join(result["errors"]))


def _build_structured_tool(
    tool_name: str,
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None,
    before_tool_call: Callable[[str, dict[str, Any]], None] | None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
    thread_id_provider: Callable[[], str] | None,
    manual_confirmation_handler: Callable[[str], bool] | None,
    inspection_confirmation_handler: Callable[[str], bool] | None,
    run_event_handler: Callable[[str, dict[str, Any]], None] | None,
    quality_gate_provider: Callable[[], dict[str, Any]] | None,
) -> StructuredTool:
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    return StructuredTool.from_function(
        func=_make_tool_function(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            before_tool_call=before_tool_call,
            after_tool_call=after_tool_call,
            thread_id_provider=thread_id_provider,
            manual_confirmation_handler=manual_confirmation_handler,
            inspection_confirmation_handler=inspection_confirmation_handler,
            run_event_handler=run_event_handler,
            quality_gate_provider=quality_gate_provider,
        ),
        name=tool_name,
        description=spec.description,
        args_schema=spec.args_schema,
    )


def _make_tool_function(
    tool_name: str,
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None,
    before_tool_call: Callable[[str, dict[str, Any]], None] | None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
    thread_id_provider: Callable[[], str] | None,
    manual_confirmation_handler: Callable[[str], bool] | None,
    inspection_confirmation_handler: Callable[[str], bool] | None,
    run_event_handler: Callable[[str, dict[str, Any]], None] | None,
    quality_gate_provider: Callable[[], dict[str, Any]] | None,
) -> Callable[..., str]:
    def _tool(**kwargs: Any) -> str:
        kwargs = _json_safe_tool_payload(kwargs)
        if tool_name == "apply_debug_patch_after_approval":
            if not bool(kwargs.get("approved")):
                raise ValueError("应用 debug patch 需要人工审批流程传入 approved=true。")
            if latest_user_approved is not None and not latest_user_approved():
                raise ValueError("应用 debug patch 需要当前会话存在有效的人工 approve 恢复状态。")
        if tool_name == "read_compression_archive" and thread_id_provider is not None:
            kwargs["thread_id"] = thread_id_provider()
        elif tool_name == "read_compression_archive" and not kwargs.get("thread_id"):
            if thread_id_provider is None:
                raise ValueError("read_compression_archive 需要 thread_id。")
        if tool_name in {"run_plan", "run_debug_plan"}:
            if manual_confirmation_handler is not None:
                kwargs["_manual_confirmation_handler"] = manual_confirmation_handler
            if inspection_confirmation_handler is not None:
                kwargs["_inspection_confirmation_handler"] = inspection_confirmation_handler
            if run_event_handler is not None:
                kwargs["_run_event_handler"] = lambda event: run_event_handler(tool_name, event)
        if tool_name == "review_plan_quality" and quality_gate_provider is not None:
            kwargs["_evidence_context"] = quality_gate_provider()
        if before_tool_call is not None:
            try:
                before_tool_call(tool_name, kwargs)
            except Exception:
                pass
        try:
            if tool_name == "run_plan":
                _enforce_run_plan_quality_gate(project_root, kwargs, quality_gate_provider)
            result = call_ai_terminal_tool(
                tool_name,
                project_root,
                kwargs,
                allow_protected=tool_name == "apply_debug_patch_after_approval",
                allow_run_plan=tool_name == "run_plan",
            )
        except Exception as error:
            result = {
                "ok": False,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        if after_tool_call is not None:
            try:
                after_tool_call(tool_name, kwargs, result)
            except Exception:
                pass
        return json.dumps(result, ensure_ascii=False, indent=2)

    _tool.__name__ = tool_name
    return _tool


def _enforce_run_plan_quality_gate(
    project_root: Path,
    kwargs: dict[str, Any],
    quality_gate_provider: Callable[[], dict[str, Any]] | None,
) -> None:
    if quality_gate_provider is None:
        raise ValueError("run_plan 需要 AI 终端质量门禁上下文。请先调用 review_plan_quality，并通过 AITerminal 主路径运行。")
    review = quality_gate_provider()
    if not isinstance(review, dict) or not review:
        raise ValueError("运行前缺少 review_plan_quality 质量复查。请先调用 review_plan_quality，并修复所有 fail 后再运行。")
    if str(review.get("latest_plan_quality_review_ok", "")).lower() != "true":
        raise ValueError("最近一次 review_plan_quality 未通过，不能运行 plan。请先修复问题并重新复查。")
    plan_path = str(kwargs.get("plan_path") or "")
    reviewed_plan_path = str(review.get("latest_plan_quality_review_plan_path") or "")
    if not plan_path:
        raise ValueError("run_plan 缺少 plan_path。")
    resolved_plan_path = str(resolve_plan_path(plan_path))
    if reviewed_plan_path and str(resolve_plan_path(reviewed_plan_path)) != resolved_plan_path:
        raise ValueError("最近一次 review_plan_quality 针对的是另一个 plan，不能复用。请对当前 plan 重新复查。")
    expected_signature = str(review.get("latest_plan_quality_review_signature") or "")
    current_signature = compute_plan_signature(plan_path)
    if not expected_signature or expected_signature != current_signature:
        raise ValueError("plan 在最近一次 review_plan_quality 后发生变化，质量复查已失效。请重新调用 review_plan_quality。")


def _json_safe_tool_payload(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_safe_tool_payload(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _json_safe_tool_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_tool_payload(item) for item in value]
    return value


def self_check_langchain_tools(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    checks: list[dict[str, Any]] = []
    captured_calls: list[dict[str, Any]] = []

    tools = build_langchain_tools(
        root,
        latest_user_approved=lambda: False,
        after_tool_call=lambda name, args, result: captured_calls.append(
            {
                "name": name,
                "args": args,
                "ok": result.get("ok"),
            }
        ),
    )
    tool_by_name = {tool.name: tool for tool in tools}

    checks.append(
        _self_check_result(
            name="structured_tool_count",
            passed=len(tools) == len(AI_TERMINAL_TOOL_SPECS),
            detail={"tools": len(tools), "specs": len(AI_TERMINAL_TOOL_SPECS)},
        )
    )
    checks.append(
        _self_check_result(
            name="structured_tool_names",
            passed=set(tool_by_name) == set(AI_TERMINAL_TOOL_SPECS),
            detail={
                "missing": sorted(set(AI_TERMINAL_TOOL_SPECS) - set(tool_by_name)),
                "extra": sorted(set(tool_by_name) - set(AI_TERMINAL_TOOL_SPECS)),
            },
        )
    )

    schema_mismatches = []
    description_mismatches = []
    arg_mismatches = []
    for tool_name, spec in AI_TERMINAL_TOOL_SPECS.items():
        tool = tool_by_name.get(tool_name)
        if tool is None:
            continue
        if tool.args_schema is not spec.args_schema:
            schema_mismatches.append(tool_name)
        if tool.description != spec.description:
            description_mismatches.append(tool_name)
        tool_args = set(tool.args)
        schema_args = set(spec.args_schema.model_fields)
        if tool_args != schema_args:
            arg_mismatches.append(
                {
                    "name": tool_name,
                    "missing": sorted(schema_args - tool_args),
                    "extra": sorted(tool_args - schema_args),
                }
            )

    checks.append(
        _self_check_result(
            name="args_schema_identity",
            passed=not schema_mismatches,
            detail={"mismatches": schema_mismatches},
        )
    )
    checks.append(
        _self_check_result(
            name="tool_spec_descriptions",
            passed=not description_mismatches,
            detail={"mismatches": description_mismatches},
        )
    )
    checks.append(
        _self_check_result(
            name="tool_args_match_schema",
            passed=not arg_mismatches,
            detail={"mismatches": arg_mismatches},
        )
    )
    registry_result = check_ai_terminal_tool_registry()
    checks.append(
        _self_check_result(
            name="handler_signatures_match_schema",
            passed=not registry_result.get("schema_signature_mismatches"),
            detail={"mismatches": registry_result.get("schema_signature_mismatches", [])},
        )
    )

    plan_root = _self_check_plan_root(root)
    with _self_check_temp_plan_package(plan_root) as package_dir:
        create_plan_package(package_dir, project_root=root, name="AI Tools Self Check")
        plan_path = package_dir / "plan.json"

        validate_plan_tool = tool_by_name.get("validate_plan")
        validate_plan_ok = False
        validate_plan_error = ""
        if validate_plan_tool is not None:
            try:
                raw_result = validate_plan_tool.invoke({"plan_path": str(plan_path)})
                parsed_result = json.loads(raw_result)
                validate_plan_ok = bool(parsed_result.get("ok")) and captured_calls[-1]["name"] == "validate_plan"
            except Exception as error:
                validate_plan_error = str(error)
        checks.append(
            _self_check_result(
                name="structured_tool_invoke",
                passed=validate_plan_ok,
                detail={"error": validate_plan_error},
            )
        )

        read_plan_package_tool = tool_by_name.get("read_plan_package")
        grep_project_text_tool = tool_by_name.get("grep_project_text")
        inspect_web_page_tool = tool_by_name.get("inspect_web_page")
        read_project_file_slice_tool = tool_by_name.get("read_project_file_slice")
        write_plan_package_file_tool = tool_by_name.get("write_plan_package_file")
        update_work_plan_tool = tool_by_name.get("update_work_plan")
        export_local_file_tool = tool_by_name.get("export_local_file")
        read_output_artifact_tool = tool_by_name.get("read_output_artifact")
        review_plan_quality_tool = tool_by_name.get("review_plan_quality")
        run_plan_tool = tool_by_name.get("run_plan")
        schedule_tools_ok = False
        schedule_tools_error = ""
        schedule_tools_detail: dict[str, Any] = {}
        if all(
            tool_by_name.get(name) is not None
            for name in ("add_schedule", "list_schedules", "run_schedule_now", "remove_schedule")
        ):
            try:
                with tempfile.TemporaryDirectory(prefix="ai-tools-schedule-") as raw_schedule_dir:
                    schedule_root = Path(raw_schedule_dir)
                    schedule_package = schedule_root / "plans" / "scheduled-tool"
                    schedule_package.mkdir(parents=True, exist_ok=True)
                    schedule_plan_path = schedule_package / "plan.json"
                    schedule_plan_path.write_text(
                        json.dumps(
                            {
                                "name": "scheduled tool plan",
                                "steps": [
                                    {
                                        "action": "write",
                                        "type": "text",
                                        "path": "scheduled-tool.txt",
                                        "value": "ran",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    schedule_calls: list[dict[str, Any]] = []
                    schedule_tools = build_langchain_tools(
                        schedule_root,
                        after_tool_call=lambda name, args, result: schedule_calls.append(
                            {"name": name, "ok": result.get("ok"), "error": result.get("error")}
                        ),
                    )
                    schedule_by_name = {tool.name: tool for tool in schedule_tools}
                    add_schedule_result = json.loads(
                        schedule_by_name["add_schedule"].invoke(
                            {
                                "schedule_id": "tool-demo",
                                "plan_path": str(schedule_plan_path),
                                "every_seconds": 0.1,
                                "run_immediately": True,
                                "timeout_seconds": 30,
                            }
                        )
                    )
                    list_result = json.loads(schedule_by_name["list_schedules"].invoke({}))
                    run_now_result = json.loads(
                        schedule_by_name["run_schedule_now"].invoke({"schedule_id": "tool-demo"})
                    )
                    remove_result = json.loads(
                        schedule_by_name["remove_schedule"].invoke({"schedule_id": "tool-demo"})
                    )
                    list_after_remove_result = json.loads(schedule_by_name["list_schedules"].invoke({}))
                    output_text_path = schedule_package / "output" / "text" / "scheduled-tool.txt"
                    output_text = output_text_path.read_text(encoding="utf-8") if output_text_path.exists() else ""
                    schedule_config_exists = (schedule_root / "schedules.json").exists()
                    schedule_state_exists = (schedule_root / ".keygen" / "schedules-state.json").exists()
                    schedule_tools_ok = (
                        bool(add_schedule_result.get("ok"))
                        and len(list_result.get("schedules", [])) == 1
                        and run_now_result.get("ok") is True
                        and run_now_result.get("status") == "passed"
                        and remove_result.get("removed") is True
                        and list_after_remove_result.get("schedules") == []
                        and output_text == "ran"
                        and not schedule_config_exists
                        and not schedule_state_exists
                    )
                    schedule_tools_detail = {
                        "add_ok": add_schedule_result.get("ok"),
                        "list_count": len(list_result.get("schedules", [])),
                        "run_now_status": run_now_result.get("status"),
                        "removed": remove_result.get("removed"),
                        "list_after_remove_count": len(list_after_remove_result.get("schedules", [])),
                        "output_text": output_text,
                        "schedule_config_exists": schedule_config_exists,
                        "schedule_state_exists": schedule_state_exists,
                        "schedule_calls": schedule_calls,
                    }
            except Exception as error:
                schedule_tools_error = str(error)
        progressive_tools_ok = False
        progressive_tools_error = ""
        progressive_tools_detail: dict[str, Any] = {}
        if (
            read_plan_package_tool is not None
            and grep_project_text_tool is not None
            and read_project_file_slice_tool is not None
            and read_output_artifact_tool is not None
        ):
            try:
                artifact_relative = "text/accounts.txt"
                artifact_path = package_dir / "output" / artifact_relative
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text("alpha\n\nbeta\ngamma\n", encoding="utf-8")
                run_dir = package_dir / "output" / "20990101-000000-self-check-run"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "result.json").write_text("{}\n", encoding="utf-8")
                package_result = json.loads(read_plan_package_tool.invoke({"plan_path": str(plan_path)}))
                plan = package_result.get("plan", {})
                sub_plans = package_result.get("sub_plans", [])
                grep_result = json.loads(
                    grep_project_text_tool.invoke(
                        {
                            "pattern": "AI Tools Self Check",
                            "root_path": str(package_dir),
                            "literal": True,
                            "file_glob": "*.json",
                            "max_matches": 5,
                        }
                    )
                )
                slice_result = json.loads(
                    read_project_file_slice_tool.invoke(
                        {
                            "path": str(plan_path),
                            "start_line": 1,
                            "line_count": 3,
                        }
                    )
                )
                artifact_result = json.loads(
                    read_output_artifact_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": artifact_relative,
                        }
                    )
                )
                prefixed_artifact_result = json.loads(
                    read_output_artifact_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": f"{run_dir.name}/{artifact_relative}",
                        }
                    )
                )
                small_artifact_result = json.loads(
                    read_output_artifact_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": artifact_relative,
                            "max_bytes": 5,
                        }
                    )
                )
                package_is_metadata = (
                    isinstance(plan, dict)
                    and "steps_preview" in plan
                    and "steps" not in plan
                    and all(isinstance(sub_plan, dict) and "document" not in sub_plan for sub_plan in sub_plans)
                )
                progressive_tools_ok = (
                    bool(package_result.get("ok"))
                    and package_is_metadata
                    and int(grep_result.get("match_count", 0)) >= 1
                    and int(slice_result.get("line_count", 0)) <= 3
                    and artifact_result.get("line_count") == 4
                    and artifact_result.get("non_empty_line_count") == 3
                    and artifact_result.get("content_complete") is True
                    and small_artifact_result.get("max_bytes") == 5
                    and small_artifact_result.get("truncated") is True
                    and prefixed_artifact_result.get("relative_path") == "text\\accounts.txt"
                    and prefixed_artifact_result.get("path_resolution", {}).get("mode") == "stripped_run_output_prefix"
                )
                progressive_tools_detail = {
                    "package_is_metadata": package_is_metadata,
                    "grep_matches": grep_result.get("match_count", 0),
                    "slice_lines": slice_result.get("line_count", 0),
                    "artifact_lines": artifact_result.get("line_count", 0),
                    "artifact_non_empty_lines": artifact_result.get("non_empty_line_count", 0),
                    "small_artifact_max_bytes": small_artifact_result.get("max_bytes"),
                    "small_artifact_truncated": small_artifact_result.get("truncated"),
                    "prefixed_artifact_relative_path": prefixed_artifact_result.get("relative_path"),
                    "prefixed_artifact_resolution": prefixed_artifact_result.get("path_resolution", {}),
                }
            except Exception as error:
                progressive_tools_error = str(error)

        missing_root_recoverable_ok = False
        missing_root_recoverable_error = ""
        missing_root_recoverable_detail: dict[str, Any] = {}
        if grep_project_text_tool is not None:
            try:
                missing_root_result = json.loads(
                    grep_project_text_tool.invoke(
                        {
                            "pattern": "selector",
                            "root_path": "handbook/actions/element",
                            "literal": True,
                            "file_glob": "*.md",
                            "max_matches": 5,
                        }
                    )
                )
                suggested_paths = missing_root_result.get("suggested_paths")
                missing_root_recoverable_ok = (
                    missing_root_result.get("ok") is False
                    and "搜索路径不存在" in str(missing_root_result.get("error", ""))
                    and isinstance(suggested_paths, list)
                    and "handbook/actions/interaction/element.md" in suggested_paths
                )
                missing_root_recoverable_detail = {
                    "error": missing_root_result.get("error"),
                    "suggested_paths": suggested_paths,
                }
            except Exception as error:
                missing_root_recoverable_error = str(error)

        write_plan_package_file_ok = False
        write_plan_package_file_error = ""
        write_plan_package_file_detail: dict[str, Any] = {}
        if write_plan_package_file_tool is not None:
            try:
                write_result = json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "docs/AI_TOOLS_SELF_CHECK.md",
                            "content": "# AI Tools Self Check\n",
                        }
                    )
                )
                forbidden_rejected = False
                forbidden_error = ""
                forbidden_result = json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "output/forbidden.txt",
                            "content": "no",
                        }
                    )
                )
                forbidden_error = str(forbidden_result)
                forbidden_rejected = (
                    not bool(forbidden_result.get("ok"))
                    and (
                        "允许写入的目标" in forbidden_error
                        or "拒绝写入" in forbidden_error
                        or "Allowed write targets" in forbidden_error
                        or "Refusing to write" in forbidden_error
                    )
                )
                secret_literal_written = False
                secret_literal_error = ""
                try:
                    secret_literal_write_result = json.loads(
                        write_plan_package_file_tool.invoke(
                            {
                                "plan_path": str(plan_path),
                                "relative_path": "plan.json",
                                "json_value": {
                                    "name": "Secret Literal Check",
                                    "steps": [
                                        {
                                            "action": "element",
                                            "type": "fill",
                                            "browser": "main",
                                            "selector": "input[type=password]",
                                            "value": "plain-secret-value",
                                        }
                                    ],
                                },
                            }
                        )
                    )
                    secret_literal_written = bool(secret_literal_write_result.get("ok"))
                    secret_literal_error = str(secret_literal_write_result)
                except Exception as error:
                    secret_literal_error = str(error)
                safe_secret_reference_ok = False
                safe_secret_reference_error = ""
                try:
                    safe_write_result = json.loads(
                        write_plan_package_file_tool.invoke(
                            {
                                "plan_path": str(plan_path),
                                "relative_path": "sub-plans/secret-reference-plan.json",
                                "json_value": {
                                    "name": "Secret Reference Check",
                                    "steps": [
                                        {
                                            "action": "element",
                                            "type": "fill",
                                            "browser": "main",
                                            "selector": "input[type=password]",
                                            "value": "{{password}}",
                                        }
                                    ],
                                },
                            }
                        )
                    )
                    safe_secret_reference_ok = bool(safe_write_result.get("ok"))
                except Exception as error:
                    safe_secret_reference_error = str(error)
                secret_resource_written = False
                secret_resource_error = ""
                try:
                    secret_resource_write_result = json.loads(
                        write_plan_package_file_tool.invoke(
                            {
                                "plan_path": str(plan_path),
                                "relative_path": "resources/credentials.json",
                                "json_value": {
                                    "username": "demo",
                                    "password": "plain-secret-value",
                                },
                            }
                        )
                    )
                    secret_resource_written = bool(secret_resource_write_result.get("ok"))
                except Exception as error:
                    secret_resource_error = str(error)
                write_plan_package_file_ok = (
                    bool(write_result.get("ok"))
                    and (package_dir / "docs" / "AI_TOOLS_SELF_CHECK.md").exists()
                    and forbidden_rejected
                    and secret_literal_written
                    and safe_secret_reference_ok
                    and secret_resource_written
                )
                write_plan_package_file_detail = {
                    "relative_path": write_result.get("relative_path"),
                    "forbidden_error": forbidden_error,
                    "secret_literal_error": secret_literal_error,
                    "safe_secret_reference_error": safe_secret_reference_error,
                    "secret_resource_error": secret_resource_error,
                }
            except Exception as error:
                write_plan_package_file_error = str(error)

        web_inspection_ok = False
        web_inspection_error = ""
        web_inspection_detail: dict[str, Any] = {}
        if inspect_web_page_tool is not None:
            try:
                fixture_path = package_dir / "resources" / "web-inspection-self-check.html"
                fixture_path.write_text(
                    """<!doctype html>
<html>
  <head><title>Inspection Fixture</title></head>
  <body>
    <h1>Inspection Fixture Login</h1>
    <form id="login-form">
      <label for="email">Email</label>
      <input id="email" name="email" autocomplete="username">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password">
      <button id="submit-btn" type="submit">Sign in</button>
    </form>
    <p>Captcha required after too many attempts.</p>
  </body>
</html>
""",
                    encoding="utf-8",
                )
                inspection_result = json.loads(
                    inspect_web_page_tool.invoke(
                        {
                            "url": str(fixture_path),
                            "wait_until": "domcontentloaded",
                            "wait_ms": 0,
                            "max_elements": 20,
                            "text_limit": 1000,
                        }
                    )
                )
                page = inspection_result.get("page", {})
                auth = page.get("auth", {}) if isinstance(page, dict) else {}
                counts = page.get("counts", {}) if isinstance(page, dict) else {}
                inputs = page.get("inputs", []) if isinstance(page, dict) else []
                buttons = page.get("buttons", []) if isinstance(page, dict) else []
                selectors = {item.get("selector") for item in inputs + buttons if isinstance(item, dict)}
                web_inspection_ok = (
                    bool(inspection_result.get("ok"))
                    and inspection_result.get("tool") == "inspect_web_page"
                    and bool(auth.get("login_fields_detected"))
                    and bool(auth.get("challenge_detected"))
                    and int(counts.get("inputs", 0)) >= 2
                    and "#email" in selectors
                    and "#submit-btn" in selectors
                )
                web_inspection_detail = {
                    "login_fields_detected": auth.get("login_fields_detected"),
                    "challenge_detected": auth.get("challenge_detected"),
                    "input_count": counts.get("inputs"),
                    "button_count": counts.get("buttons"),
                    "selectors": sorted(str(selector) for selector in selectors if selector),
                }
            except Exception as error:
                web_inspection_error = str(error)

        work_plan_tool_ok = False
        work_plan_tool_error = ""
        work_plan_tool_detail: dict[str, Any] = {}
        if update_work_plan_tool is not None:
            try:
                plan_result = json.loads(
                    update_work_plan_tool.invoke(
                        {
                            "summary": "self-check plan",
                            "items": [
                                {"title": "确认目标", "status": "completed"},
                                {"title": "更新计划", "status": "in_progress"},
                                {"title": "验证结果", "status": "pending"},
                            ],
                        }
                    )
                )
                duplicate_active_rejected = False
                duplicate_active_error = ""
                duplicate_active_result = json.loads(
                    update_work_plan_tool.invoke(
                        {
                            "items": [
                                {"title": "one", "status": "in_progress"},
                                {"title": "two", "status": "in_progress"},
                            ],
                        }
                    )
                )
                duplicate_active_error = str(duplicate_active_result)
                duplicate_active_rejected = not bool(duplicate_active_result.get("ok")) and "最多只能有一个" in duplicate_active_error
                work_plan_tool_ok = (
                    bool(plan_result.get("ok"))
                    and plan_result.get("total") == 3
                    and plan_result.get("completed") == 1
                    and plan_result.get("active") == "更新计划"
                    and captured_calls[-2]["name"] == "update_work_plan"
                    and duplicate_active_rejected
                )
                work_plan_tool_detail = {
                    "total": plan_result.get("total"),
                    "completed": plan_result.get("completed"),
                    "active": plan_result.get("active"),
                    "duplicate_active_error": duplicate_active_error,
                }
            except Exception as error:
                work_plan_tool_error = str(error)

        export_local_file_ok = False
        export_local_file_error = ""
        export_local_file_detail: dict[str, Any] = {}
        if export_local_file_tool is not None:
            try:
                with tempfile.TemporaryDirectory(prefix="ai-tools-export-") as raw_export_dir:
                    export_dir = Path(raw_export_dir)
                    direct_target = export_dir / "direct.txt"
                    append_target = export_dir / "append.txt"
                    copied_target = export_dir / "copied.txt"
                    source_relative = "text/source.txt"
                    source_path = package_dir / "output" / source_relative
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    source_path.write_text("copied artifact\n", encoding="utf-8")

                    direct_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(direct_target),
                                "content": "final delivery\n",
                            }
                        )
                    )
                    append_first_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(append_target),
                                "content": "first\n",
                                "mode": "append",
                            }
                        )
                    )
                    append_second_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(append_target),
                                "content": "second\n",
                                "mode": "append",
                            }
                        )
                    )
                    copy_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(copied_target),
                                "plan_path": str(plan_path),
                                "source_output_path": source_relative,
                            }
                        )
                    )
                    traversal_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(export_dir / "bad.txt"),
                                "plan_path": str(plan_path),
                                "source_output_path": "../plan.json",
                            }
                        )
                    )
                    output_prefix_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(export_dir / "bad-prefix.txt"),
                                "plan_path": str(plan_path),
                                "source_output_path": "output/text/source.txt",
                            }
                        )
                    )
                    project_write_result = json.loads(
                        export_local_file_tool.invoke(
                            {
                                "target_path": str(root / "src" / "bad-export.txt"),
                                "content": "bad\n",
                            }
                        )
                    )
                    export_local_file_ok = (
                        bool(direct_result.get("ok"))
                        and direct_target.read_text(encoding="utf-8") == "final delivery\n"
                        and bool(append_first_result.get("ok"))
                        and bool(append_second_result.get("ok"))
                        and append_target.read_text(encoding="utf-8") == "first\nsecond\n"
                        and bool(copy_result.get("ok"))
                        and copied_target.read_text(encoding="utf-8") == "copied artifact\n"
                        and not bool(traversal_result.get("ok"))
                        and "output" in str(traversal_result.get("error", ""))
                        and not bool(output_prefix_result.get("ok"))
                        and "不能以 output/" in str(output_prefix_result.get("error", ""))
                        and not bool(project_write_result.get("ok"))
                        and "项目外" in str(project_write_result.get("error", ""))
                    )
                    export_local_file_detail = {
                        "direct_path": direct_result.get("path"),
                        "copy_source": copy_result.get("source_path"),
                        "copy_target": copy_result.get("path"),
                        "traversal_error": traversal_result.get("error"),
                        "output_prefix_error": output_prefix_result.get("error"),
                        "project_write_error": project_write_result.get("error"),
                    }
            except Exception as error:
                export_local_file_error = str(error)

        review_plan_quality_ok = False
        review_plan_quality_error = ""
        review_plan_quality_detail: dict[str, Any] = {}
        if review_plan_quality_tool is not None and write_plan_package_file_tool is not None:
            try:
                request = (
                    "打开 https://example.com/login 登录后台，账户名称 {{login_username}}，密码 {{login_password}}，"
                    "把全部账户名称写到 /Users/anminhu/Downloads/AI账户.txt，一行一个。"
                )
                secret_request = (
                    "打开 https://example.com/login 登录后台，账户名称 raw-account-value，密码 raw-password-value，"
                    "把全部账户名称写到 /Users/anminhu/Downloads/AI账户.txt，一行一个。"
                )
                incomplete_plan = {
                    "name": "quality incomplete",
                    "variables": {"login_url": "https://example.com/login"},
                    "steps": [
                        {"action": "open_browser", "name": "main", "headed": True},
                        {"action": "navigate", "type": "goto", "browser": "main", "url": "{{login_url}}"},
                        {"action": "manual_confirm", "prompt": "请完成登录。"},
                    ],
                }
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": incomplete_plan,
                        }
                    )
                )
                fail_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": request,
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/login final_url=https://example.com/login forms=1 inputs=2，headed 探索停在登录页。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                redaction_result = review_plan_quality_direct(
                    root,
                    plan_path=plan_path,
                    user_request=secret_request,
                    evidence_summary=(
                        "inspect_web_page requested_url=https://example.com/login "
                        "final_url=https://example.com/login forms=1 inputs=2，headed 探索停在登录页。"
                    ),
                    planned_output_path="/Users/anminhu/Downloads/AI账户.txt",
                )
                redaction_text = json.dumps(redaction_result, ensure_ascii=False, default=str)
                complete_plan = {
                    "name": "quality complete",
                    "variables": {
                        "login_url": "https://example.com/login",
                        "username": "{{login_username}}",
                        "password": "{{login_password}}",
                    },
                    "steps": [
                        {"action": "open_browser", "name": "main", "headed": True},
                        {"action": "navigate", "type": "goto", "browser": "main", "url": "{{login_url}}"},
                        {
                            "action": "element",
                            "type": "fill",
                            "browser": "main",
                            "selector": "input[autocomplete='username']",
                            "value": "{{username}}",
                        },
                        {
                            "action": "element",
                            "type": "fill",
                            "browser": "main",
                            "selector": "input[type='password']",
                            "value": "{{password}}",
                        },
                        {
                            "action": "element",
                            "type": "click",
                            "browser": "main",
                            "role": "button",
                            "name": "登录",
                        },
                        {"action": "manual_confirm", "prompt": "如出现验证码，请在当前浏览器完成后继续。"},
                        {
                            "action": "extract",
                            "type": "all_texts",
                            "browser": "main",
                            "selector": ".account-name",
                            "save_as": "account_names",
                        },
                        {
                            "action": "write",
                            "type": "text",
                            "path": "AI账户.txt",
                            "value": "{{account_names}}",
                        },
                    ],
                }
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": complete_plan,
                        }
                    )
                )
                pass_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": request,
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/login final_url=https://example.com/login forms=1 inputs=2；headed 探索已确认 AI 账户管理菜单和账户名称列表。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                no_submit_plan = dict(complete_plan)
                no_submit_plan["steps"] = [
                    step
                    for step in complete_plan["steps"]
                    if not (step.get("action") == "element" and step.get("type") == "click")
                    and step.get("action") != "manual_confirm"
                ]
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": no_submit_plan,
                        }
                    )
                )
                no_submit_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": request,
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/login final_url=https://example.com/login forms=1 inputs=2。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                extraction_only_plan = {
                    "name": "quality account names extraction",
                    "variables": {"target_url": "https://example.com/accounts"},
                    "steps": [
                        {"action": "open_browser", "name": "main", "headed": True},
                        {"action": "navigate", "type": "goto", "browser": "main", "url": "{{target_url}}"},
                        {
                            "action": "extract",
                            "type": "all_texts",
                            "browser": "main",
                            "selector": ".account-name",
                            "save_as": "account_names",
                        },
                        {
                            "action": "write",
                            "type": "text",
                            "path": "AI账户.txt",
                            "value": "{{account_names}}",
                        },
                    ],
                }
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": extraction_only_plan,
                        }
                    )
                )
                extraction_only_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": "把页面里的全部账户名称提取出来并写到 /Users/anminhu/Downloads/AI账户.txt，一行一个。",
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/accounts final_url=https://example.com/accounts inputs=2 buttons=1；headed 探索已确认账户名称列表。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                trailing_manual_plan = dict(extraction_only_plan)
                trailing_manual_plan["steps"] = [
                    *extraction_only_plan["steps"],
                    {"action": "manual_confirm", "browser": "main", "prompt": "最后再确认一次"},
                ]
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": trailing_manual_plan,
                        }
                    )
                )
                trailing_manual_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": "把页面里的全部账户名称提取出来并写到 /Users/anminhu/Downloads/AI账户.txt，一行一个。",
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/accounts final_url=https://example.com/accounts inputs=2 buttons=1；headed 探索已确认账户名称列表。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                headless_complete_plan = dict(complete_plan)
                headless_complete_plan["steps"] = [
                    dict(step, headed=False) if step.get("action") == "open_browser" else step
                    for step in complete_plan["steps"]
                    if step.get("action") != "manual_confirm"
                ]
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": headless_complete_plan,
                        }
                    )
                )
                junk_evidence_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": request,
                            "evidence_summary": "页面看起来差不多。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                weak_evidence_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": request,
                            "evidence_summary": "manual_confirm 等用户确认后继续。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                json.loads(
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "plan.json",
                            "json_value": extraction_only_plan,
                        }
                    )
                )
                credential_stopword_result = json.loads(
                    review_plan_quality_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "user_request": "提取页面中的 password policy 文本和 account name 列表，写到 /Users/anminhu/Downloads/AI账户.txt。",
                            "evidence_summary": "inspect_web_page requested_url=https://example.com/accounts final_url=https://example.com/accounts title=Accounts；headed 探索已确认列表。",
                            "planned_output_path": "/Users/anminhu/Downloads/AI账户.txt",
                        }
                    )
                )
                review_plan_quality_ok = (
                    fail_result.get("ok") is False
                    and fail_result.get("severity") == "fail"
                    and "missing_password_fill" in {issue.get("code") for issue in fail_result.get("issues", [])}
                    and "missing_account_fill" in {issue.get("code") for issue in fail_result.get("issues", [])}
                    and any("AI账户.txt" in str(fact) for fact in fail_result.get("missing_facts", []))
                    and bool(pass_result.get("ok"))
                    and pass_result.get("severity") == "warn"
                    and pass_result.get("next_action") == "run_plan_then_export_local_file"
                    and bool(pass_result.get("plan_signature"))
                    and "已覆盖账号输入" in pass_result.get("covered_facts", [])
                    and "已覆盖输出文件名 AI账户.txt" in pass_result.get("covered_facts", [])
                    and no_submit_result.get("ok") is False
                    and "missing_login_submit_or_handoff" in {issue.get("code") for issue in no_submit_result.get("issues", [])}
                    and extraction_only_result.get("ok") is True
                    and extraction_only_result.get("severity") == "warn"
                    and trailing_manual_result.get("ok") is False
                    and "manual_confirm_without_followup" in {issue.get("code") for issue in trailing_manual_result.get("issues", [])}
                    and "missing_account_fill" not in {issue.get("code") for issue in extraction_only_result.get("issues", [])}
                    and "missing_password_fill" not in {issue.get("code") for issue in extraction_only_result.get("issues", [])}
                    and junk_evidence_result.get("ok") is False
                    and "missing_real_site_evidence" in {issue.get("code") for issue in junk_evidence_result.get("issues", [])}
                    and weak_evidence_result.get("ok") is False
                    and "missing_real_site_evidence" in {issue.get("code") for issue in weak_evidence_result.get("issues", [])}
                    and credential_stopword_result.get("ok") is True
                    and "missing_account_fill" not in {issue.get("code") for issue in credential_stopword_result.get("issues", [])}
                    and "missing_password_fill" not in {issue.get("code") for issue in credential_stopword_result.get("issues", [])}
                    and "raw-account-value" in redaction_text
                    and "raw-password-value" in redaction_text
                )
                review_plan_quality_detail = {
                    "fail_codes": [issue.get("code") for issue in fail_result.get("issues", [])],
                    "fail_missing_facts": fail_result.get("missing_facts", []),
                    "pass_severity": pass_result.get("severity"),
                    "pass_next_action": pass_result.get("next_action"),
                    "pass_covered_facts": pass_result.get("covered_facts", []),
                    "pass_signature": pass_result.get("plan_signature"),
                    "extraction_only_codes": [
                        issue.get("code") for issue in extraction_only_result.get("issues", [])
                    ],
                    "junk_evidence_codes": [issue.get("code") for issue in junk_evidence_result.get("issues", [])],
                    "weak_evidence_codes": [issue.get("code") for issue in weak_evidence_result.get("issues", [])],
                    "credential_stopword_codes": [
                        issue.get("code") for issue in credential_stopword_result.get("issues", [])
                    ],
                    "raw_credential_evidence_kept": "raw-account-value" in redaction_text
                    and "raw-password-value" in redaction_text,
                }
            except Exception as error:
                review_plan_quality_error = str(error)

        run_plan_quality_gate_ok = False
        run_plan_quality_gate_error = ""
        run_plan_quality_gate_detail: dict[str, Any] = {}
        if run_plan_tool is not None:
            try:
                with tempfile.TemporaryDirectory(prefix="ai-tools-run-gate-") as raw_gate_dir:
                    gate_root = Path(raw_gate_dir)
                    (gate_root / "plans").mkdir(parents=True, exist_ok=True)
                    gate_package = gate_root / "plans" / "gate"
                    create_plan_package(gate_package, project_root=gate_root, name="gate")
                    gate_plan_path = gate_package / "plan.json"
                    gate_plan_path.write_text(
                        json.dumps(
                            {
                                "name": "gate",
                                "variables": {},
                                "steps": [{"action": "print", "message": "gate ok"}],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    gated_calls: list[dict[str, Any]] = []
                    gate_state: dict[str, Any] = {}
                    gated_tools = build_langchain_tools(
                        gate_root,
                        after_tool_call=lambda name, args, result: gated_calls.append(
                            {"name": name, "ok": result.get("ok"), "error": result.get("error")}
                        ),
                        quality_gate_provider=lambda: gate_state,
                    )
                    gated_by_name = {tool.name: tool for tool in gated_tools}
                    no_review_result = json.loads(gated_by_name["run_plan"].invoke({"plan_path": str(gate_plan_path)}))
                    review_result = json.loads(
                        gated_by_name["review_plan_quality"].invoke(
                            {
                                "plan_path": str(gate_plan_path),
                                "user_request": "运行一个简单打印 plan",
                            }
                        )
                    )
                    gate_state.update(
                        {
                            "latest_plan_quality_review_plan_path": review_result.get("plan_path"),
                            "latest_plan_quality_review_signature": review_result.get("plan_signature"),
                            "latest_plan_quality_review_ok": "true" if review_result.get("ok") else "false",
                            "latest_plan_quality_review_severity": review_result.get("severity"),
                            "latest_plan_quality_review_next_action": review_result.get("next_action"),
                        }
                    )
                    run_after_review_result = json.loads(gated_by_name["run_plan"].invoke({"plan_path": str(gate_plan_path)}))
                    (gate_package / "config.json").write_text(
                        json.dumps({"flag": "changed"}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    config_stale_result = json.loads(gated_by_name["run_plan"].invoke({"plan_path": str(gate_plan_path)}))
                    gate_plan_path.write_text(
                        json.dumps(
                            {
                                "name": "gate changed",
                                "variables": {},
                                "steps": [{"action": "print", "message": "changed"}],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    stale_review_result = json.loads(gated_by_name["run_plan"].invoke({"plan_path": str(gate_plan_path)}))
                    run_plan_quality_gate_ok = (
                        no_review_result.get("ok") is False
                        and "review_plan_quality" in str(no_review_result.get("error", ""))
                        and bool(review_result.get("ok"))
                        and bool(run_after_review_result.get("ok"))
                        and config_stale_result.get("ok") is False
                        and "复查已失效" in str(config_stale_result.get("error", ""))
                        and stale_review_result.get("ok") is False
                        and "复查已失效" in str(stale_review_result.get("error", ""))
                    )
                    run_plan_quality_gate_detail = {
                        "no_review_error": no_review_result.get("error"),
                        "run_after_review_ok": run_after_review_result.get("ok"),
                        "config_stale_review_error": config_stale_result.get("error"),
                        "stale_review_error": stale_review_result.get("error"),
                        "gated_calls": gated_calls,
                    }
            except Exception as error:
                run_plan_quality_gate_error = str(error)
    checks.append(
        _self_check_result(
            name="progressive_text_tools",
            passed=progressive_tools_ok,
            detail={**progressive_tools_detail, "error": progressive_tools_error},
        )
    )
    checks.append(
        _self_check_result(
            name="grep_missing_root_is_recoverable",
            passed=missing_root_recoverable_ok,
            detail={**missing_root_recoverable_detail, "error": missing_root_recoverable_error},
        )
    )
    checks.append(
        _self_check_result(
            name="write_plan_package_file_tool",
            passed=write_plan_package_file_ok,
            detail={**write_plan_package_file_detail, "error": write_plan_package_file_error},
        )
    )
    checks.append(
        _self_check_result(
            name="inspect_web_page_tool",
            passed=web_inspection_ok,
            detail={**web_inspection_detail, "error": web_inspection_error},
        )
    )
    checks.append(
        _self_check_result(
            name="update_work_plan_tool",
            passed=work_plan_tool_ok,
            detail={**work_plan_tool_detail, "error": work_plan_tool_error},
        )
    )
    checks.append(
        _self_check_result(
            name="export_local_file_tool",
            passed=export_local_file_ok,
            detail={**export_local_file_detail, "error": export_local_file_error},
        )
    )
    checks.append(
        _self_check_result(
            name="schedule_tools_roundtrip",
            passed=schedule_tools_ok,
            detail={**schedule_tools_detail, "error": schedule_tools_error},
        )
    )
    checks.append(
        _self_check_result(
            name="review_plan_quality_tool",
            passed=review_plan_quality_ok,
            detail={**review_plan_quality_detail, "error": review_plan_quality_error},
        )
    )
    checks.append(
        _self_check_result(
            name="run_plan_requires_fresh_quality_review",
            passed=run_plan_quality_gate_ok,
            detail={**run_plan_quality_gate_detail, "error": run_plan_quality_gate_error},
        )
    )

    protected_tool = tool_by_name.get("apply_debug_patch_after_approval")
    protected_rejected = False
    protected_error = ""
    if protected_tool is not None:
        try:
            protected_tool.invoke({"workspace": "not-used", "approved": True})
        except Exception as error:
            protected_rejected = "人工 approve 恢复状态" in str(error)
            protected_error = str(error)
    checks.append(
        _self_check_result(
            name="protected_tool_requires_hitl_resume",
            passed=protected_rejected,
            detail={"error": protected_error},
        )
    )

    failures = [check for check in checks if not check["passed"]]
    return {
        "ok": not failures,
        "check": "langchain_structured_tools",
        "tools": len(tools),
        "captured_calls": captured_calls,
        "checks": checks,
    }


def _self_check_plan_root(project_root: Path) -> Path:
    for plan_root in plan_roots_for_project(project_root):
        if plan_root.exists():
            return plan_root
    fallback = project_root / "plans"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class _self_check_temp_plan_package:
    def __init__(self, plan_root: Path) -> None:
        self.plan_root = plan_root
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="_ai-tools-self-check-", dir=str(self.plan_root)))
        return self.path

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.path is None:
            return
        _remove_self_check_tree_with_retry(self.path)


def _remove_self_check_tree_with_retry(path: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            last_error = error
            time.sleep(0.15 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _self_check_result(
    *,
    name: str,
    passed: bool,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed}
    if detail is not None:
        result["detail"] = detail
    return result
