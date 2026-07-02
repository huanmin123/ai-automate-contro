from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from ai_automate_contro.ai.terminal_tool_registry import (
    AI_TERMINAL_TOOL_SPECS,
    call_ai_terminal_tool,
    check_ai_terminal_tool_registry,
)
from ai_automate_contro.ai.plan_quality import compute_plan_signature, review_plan_quality_tool as review_plan_quality_direct
from ai_automate_contro.ai.plan_tools import resolve_plan_path


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


from ai_automate_contro.ai.self_checks.langgraph_tools import self_check_langchain_tools


__all__ = ["build_langchain_tools", "self_check_langchain_tools"]
