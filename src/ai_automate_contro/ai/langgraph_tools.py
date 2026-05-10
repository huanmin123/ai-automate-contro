from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

from ai_automate_contro.ai.terminal_tools import (
    call_ai_terminal_tool,
    check_ai_terminal_tool_registry,
)
from ai_automate_contro.ai.tool_schemas import TOOL_ARGS_SCHEMAS, TOOL_DESCRIPTIONS


def build_langchain_tools(
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None = None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
) -> list[StructuredTool]:
    _ensure_langchain_tool_registry_consistent()
    return [
        _build_structured_tool(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
        )
        for tool_name in TOOL_ARGS_SCHEMAS
    ]


def _ensure_langchain_tool_registry_consistent() -> None:
    result = check_ai_terminal_tool_registry()
    if not result["ok"]:
        raise RuntimeError("AI terminal tool registry is inconsistent: " + "; ".join(result["errors"]))


def _build_structured_tool(
    tool_name: str,
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
) -> StructuredTool:
    return StructuredTool.from_function(
        func=_make_tool_function(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
        ),
        name=tool_name,
        description=TOOL_DESCRIPTIONS.get(tool_name, tool_name),
        args_schema=TOOL_ARGS_SCHEMAS[tool_name],
    )


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
                raise ValueError("Applying a debug patch requires an active human approve resume.")
        result = call_ai_terminal_tool(
            tool_name,
            project_root,
            kwargs,
            allow_protected=tool_name == "apply_debug_patch_after_approval",
        )
        if after_tool_call is not None:
            after_tool_call(tool_name, kwargs, result)
        return json.dumps(result, ensure_ascii=False, indent=2)

    _tool.__name__ = tool_name
    return _tool


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
            passed=len(tools) == len(TOOL_ARGS_SCHEMAS),
            detail={"tools": len(tools), "schemas": len(TOOL_ARGS_SCHEMAS)},
        )
    )
    checks.append(
        _self_check_result(
            name="structured_tool_names",
            passed=set(tool_by_name) == set(TOOL_ARGS_SCHEMAS),
            detail={
                "missing": sorted(set(TOOL_ARGS_SCHEMAS) - set(tool_by_name)),
                "extra": sorted(set(tool_by_name) - set(TOOL_ARGS_SCHEMAS)),
            },
        )
    )

    schema_mismatches = []
    description_mismatches = []
    arg_mismatches = []
    for tool_name, args_schema in TOOL_ARGS_SCHEMAS.items():
        tool = tool_by_name.get(tool_name)
        if tool is None:
            continue
        if tool.args_schema is not args_schema:
            schema_mismatches.append(tool_name)
        if tool.description != TOOL_DESCRIPTIONS[tool_name]:
            description_mismatches.append(tool_name)
        tool_args = set(tool.args)
        schema_args = set(args_schema.model_fields)
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
            name="tool_descriptions",
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

    validate_plan_tool = tool_by_name.get("validate_plan")
    validate_plan_ok = False
    validate_plan_error = ""
    if validate_plan_tool is not None:
        try:
            raw_result = validate_plan_tool.invoke({"plan_path": str(root / "plans" / "minimal-browser-plan" / "plan.json")})
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

    protected_tool = tool_by_name.get("apply_debug_patch_after_approval")
    protected_rejected = False
    protected_error = ""
    if protected_tool is not None:
        try:
            protected_tool.invoke({"workspace": "not-used", "approved": True})
        except Exception as error:
            protected_rejected = "active human approve resume" in str(error)
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
