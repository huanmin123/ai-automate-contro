from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

from ai_automate_contro.app.runtime_config import plan_roots_for_project
from ai_automate_contro.ai.terminal_tool_registry import (
    AI_TERMINAL_TOOL_SPECS,
    call_ai_terminal_tool,
    check_ai_terminal_tool_registry,
)
from ai_automate_contro.plans.packages import create_plan_package


def build_langchain_tools(
    project_root: Path,
    *,
    latest_user_approved: Callable[[], bool] | None = None,
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    thread_id_provider: Callable[[], str] | None = None,
) -> list[StructuredTool]:
    _ensure_langchain_tool_registry_consistent()
    return [
        _build_structured_tool(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
            thread_id_provider=thread_id_provider,
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
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
    thread_id_provider: Callable[[], str] | None,
) -> StructuredTool:
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    return StructuredTool.from_function(
        func=_make_tool_function(
            tool_name,
            project_root,
            latest_user_approved=latest_user_approved,
            after_tool_call=after_tool_call,
            thread_id_provider=thread_id_provider,
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
    after_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None,
    thread_id_provider: Callable[[], str] | None,
) -> Callable[..., str]:
    def _tool(**kwargs: Any) -> str:
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
        progressive_tools_ok = False
        progressive_tools_error = ""
        progressive_tools_detail: dict[str, Any] = {}
        if read_plan_package_tool is not None and grep_project_text_tool is not None and read_project_file_slice_tool is not None:
            try:
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
                )
                progressive_tools_detail = {
                    "package_is_metadata": package_is_metadata,
                    "grep_matches": grep_result.get("match_count", 0),
                    "slice_lines": slice_result.get("line_count", 0),
                }
            except Exception as error:
                progressive_tools_error = str(error)

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
                try:
                    write_plan_package_file_tool.invoke(
                        {
                            "plan_path": str(plan_path),
                            "relative_path": "output/forbidden.txt",
                            "content": "no",
                        }
                    )
                except Exception as error:
                    forbidden_error = str(error)
                    forbidden_rejected = (
                        "允许写入的目标" in forbidden_error
                        or "拒绝写入" in forbidden_error
                        or "Allowed write targets" in forbidden_error
                        or "Refusing to write" in forbidden_error
                    )
                write_plan_package_file_ok = (
                    bool(write_result.get("ok"))
                    and (package_dir / "docs" / "AI_TOOLS_SELF_CHECK.md").exists()
                    and forbidden_rejected
                )
                write_plan_package_file_detail = {
                    "relative_path": write_result.get("relative_path"),
                    "forbidden_error": forbidden_error,
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
    checks.append(
        _self_check_result(
            name="progressive_text_tools",
            passed=progressive_tools_ok,
            detail={**progressive_tools_detail, "error": progressive_tools_error},
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
