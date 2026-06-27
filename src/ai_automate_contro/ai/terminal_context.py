from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from typing_extensions import NotRequired

from ai_automate_contro.plans.packages import resolve_plan_path
from ai_automate_contro.support.paths import path_from_text
from ai_automate_contro.ai.work_plan import (
    format_work_plan_for_context,
    normalize_work_plan_items,
    normalize_work_plan_summary,
)


class AITerminalState(AgentState):
    current_plan_path: NotRequired[str]
    current_debug_workspace: NotRequired[str]
    latest_output_dir: NotRequired[str]
    latest_compression_archive_dir: NotRequired[str]
    latest_compression_messages_path: NotRequired[str]
    latest_compression_summary_path: NotRequired[str]
    latest_compression_token_count: NotRequired[str]
    latest_compression_message_count: NotRequired[str]
    latest_plan_quality_review_plan_path: NotRequired[str]
    latest_plan_quality_review_signature: NotRequired[str]
    latest_plan_quality_review_ok: NotRequired[str]
    latest_plan_quality_review_severity: NotRequired[str]
    latest_plan_quality_review_next_action: NotRequired[str]
    latest_web_inspection_requested_url: NotRequired[str]
    latest_web_inspection_resolved_url: NotRequired[str]
    latest_web_inspection_final_url: NotRequired[str]
    latest_web_inspection_title: NotRequired[str]
    latest_desktop_inspection_platform: NotRequired[str]
    latest_desktop_inspection_backend: NotRequired[str]
    latest_desktop_inspection_capability_limitations: NotRequired[str]
    latest_desktop_inspection_window_count: NotRequired[str]
    latest_desktop_inspection_focused_window: NotRequired[str]
    latest_desktop_inspection_element_match_count: NotRequired[str]
    latest_desktop_failure_status: NotRequired[str]
    latest_desktop_failure_diagnostics_count: NotRequired[str]
    latest_desktop_failure_repair_suggestions: NotRequired[str]
    latest_desktop_failure_state_files: NotRequired[str]
    latest_desktop_failure_screenshots: NotRequired[str]
    work_plan_items: NotRequired[list[dict[str, str]]]
    work_plan_summary: NotRequired[str]


@wrap_model_call(state_schema=AITerminalState, name="AITerminalContextMiddleware")
def inject_ai_terminal_context(
    request: ModelRequest[Any],
    handler: Any,
) -> ModelResponse[Any]:
    context_text = format_ai_terminal_context(request.state)
    if not context_text:
        return handler(request)
    base_content = request.system_message.content if request.system_message is not None else ""
    if isinstance(base_content, list):
        base_content = "\n".join(str(item) for item in base_content)
    system_message = SystemMessage(content=f"{base_content}\n\n{context_text}".strip())
    return handler(request.override(system_message=system_message))


def build_ai_terminal_context_middleware(
    context_state_provider: Callable[[], dict[str, Any]],
) -> Any:
    @wrap_model_call(state_schema=AITerminalState, name="AITerminalContextMiddleware")
    def _inject_runtime_ai_terminal_context(
        request: ModelRequest[Any],
        handler: Any,
    ) -> ModelResponse[Any]:
        state = dict(request.state)
        try:
            state.update(context_state_provider())
        except Exception:
            pass
        context_text = format_ai_terminal_context(state)
        if not context_text:
            return handler(request)
        base_content = request.system_message.content if request.system_message is not None else ""
        if isinstance(base_content, list):
            base_content = "\n".join(str(item) for item in base_content)
        system_message = SystemMessage(content=f"{base_content}\n\n{context_text}".strip())
        return handler(request.override(system_message=system_message))

    return _inject_runtime_ai_terminal_context


def format_ai_terminal_context(state: dict[str, Any]) -> str:
    lines = ["当前 AI 终端上下文："]
    added = False
    current_plan_path = state.get("current_plan_path")
    if isinstance(current_plan_path, str) and current_plan_path:
        lines.append(f"- current_plan_path: {current_plan_path}")
        added = True
    current_debug_workspace = state.get("current_debug_workspace")
    if isinstance(current_debug_workspace, str) and current_debug_workspace:
        lines.append(f"- current_debug_workspace: {current_debug_workspace}")
        added = True
    latest_output_dir = state.get("latest_output_dir")
    if isinstance(latest_output_dir, str) and latest_output_dir:
        lines.append(f"- latest_output_dir: {latest_output_dir}")
        added = True
    latest_compression_summary_path = state.get("latest_compression_summary_path")
    latest_compression_messages_path = state.get("latest_compression_messages_path")
    latest_compression_archive_dir = state.get("latest_compression_archive_dir")
    if isinstance(latest_compression_summary_path, str) and latest_compression_summary_path:
        lines.append(f"- latest_compression_summary_path: {latest_compression_summary_path}")
        added = True
    if isinstance(latest_compression_messages_path, str) and latest_compression_messages_path:
        lines.append(f"- latest_compression_messages_path: {latest_compression_messages_path}")
        added = True
    if isinstance(latest_compression_archive_dir, str) and latest_compression_archive_dir:
        lines.append(f"- latest_compression_archive_dir: {latest_compression_archive_dir}")
        added = True
    quality_review_plan_path = state.get("latest_plan_quality_review_plan_path")
    quality_review_ok = state.get("latest_plan_quality_review_ok")
    quality_review_severity = state.get("latest_plan_quality_review_severity")
    quality_review_next_action = state.get("latest_plan_quality_review_next_action")
    quality_review_signature = state.get("latest_plan_quality_review_signature")
    if isinstance(quality_review_plan_path, str) and quality_review_plan_path:
        lines.append(f"- latest_plan_quality_review_plan_path: {quality_review_plan_path}")
        added = True
    if isinstance(quality_review_ok, str) and quality_review_ok:
        lines.append(f"- latest_plan_quality_review_ok: {quality_review_ok}")
        added = True
    if isinstance(quality_review_severity, str) and quality_review_severity:
        lines.append(f"- latest_plan_quality_review_severity: {quality_review_severity}")
        added = True
    if isinstance(quality_review_next_action, str) and quality_review_next_action:
        lines.append(f"- latest_plan_quality_review_next_action: {quality_review_next_action}")
        added = True
    if isinstance(quality_review_signature, str) and quality_review_signature:
        lines.append("- latest_plan_quality_review_signature: <recorded>")
        added = True
    web_final_url = state.get("latest_web_inspection_final_url")
    web_requested_url = state.get("latest_web_inspection_requested_url")
    web_title = state.get("latest_web_inspection_title")
    if isinstance(web_requested_url, str) and web_requested_url:
        lines.append(f"- latest_web_inspection_requested_url: {web_requested_url}")
        added = True
    if isinstance(web_final_url, str) and web_final_url:
        lines.append(f"- latest_web_inspection_final_url: {web_final_url}")
        added = True
    if isinstance(web_title, str) and web_title:
        lines.append(f"- latest_web_inspection_title: {web_title}")
        added = True
    desktop_platform = state.get("latest_desktop_inspection_platform")
    desktop_backend = state.get("latest_desktop_inspection_backend")
    desktop_capability_limitations = state.get("latest_desktop_inspection_capability_limitations")
    desktop_window_count = state.get("latest_desktop_inspection_window_count")
    desktop_focused_window = state.get("latest_desktop_inspection_focused_window")
    desktop_element_match_count = state.get("latest_desktop_inspection_element_match_count")
    desktop_failure_status = state.get("latest_desktop_failure_status")
    desktop_failure_diagnostics_count = state.get("latest_desktop_failure_diagnostics_count")
    desktop_failure_repair_suggestions = state.get("latest_desktop_failure_repair_suggestions")
    desktop_failure_state_files = state.get("latest_desktop_failure_state_files")
    desktop_failure_screenshots = state.get("latest_desktop_failure_screenshots")
    if isinstance(desktop_platform, str) and desktop_platform:
        lines.append(f"- latest_desktop_inspection_platform: {desktop_platform}")
        added = True
    if isinstance(desktop_backend, str) and desktop_backend:
        lines.append(f"- latest_desktop_inspection_backend: {desktop_backend}")
        added = True
    if isinstance(desktop_capability_limitations, str) and desktop_capability_limitations:
        lines.append(f"- latest_desktop_inspection_capability_limitations: {desktop_capability_limitations}")
        added = True
    if isinstance(desktop_window_count, str) and desktop_window_count:
        lines.append(f"- latest_desktop_inspection_window_count: {desktop_window_count}")
        added = True
    if isinstance(desktop_focused_window, str) and desktop_focused_window:
        lines.append(f"- latest_desktop_inspection_focused_window: {desktop_focused_window}")
        added = True
    if isinstance(desktop_element_match_count, str) and desktop_element_match_count:
        lines.append(f"- latest_desktop_inspection_element_match_count: {desktop_element_match_count}")
        added = True
    if isinstance(desktop_failure_status, str) and desktop_failure_status:
        lines.append(f"- latest_desktop_failure_status: {desktop_failure_status}")
        added = True
    if isinstance(desktop_failure_diagnostics_count, str) and desktop_failure_diagnostics_count:
        lines.append(f"- latest_desktop_failure_diagnostics_count: {desktop_failure_diagnostics_count}")
        added = True
    if isinstance(desktop_failure_repair_suggestions, str) and desktop_failure_repair_suggestions:
        lines.append(f"- latest_desktop_failure_repair_suggestions: {desktop_failure_repair_suggestions}")
        added = True
    if isinstance(desktop_failure_state_files, str) and desktop_failure_state_files:
        lines.append(f"- latest_desktop_failure_state_files: {desktop_failure_state_files}")
        added = True
    if isinstance(desktop_failure_screenshots, str) and desktop_failure_screenshots:
        lines.append(f"- latest_desktop_failure_screenshots: {desktop_failure_screenshots}")
        added = True
    if not added:
        plan_context = format_work_plan_for_context(
            state.get("work_plan_items"),
            summary=state.get("work_plan_summary", ""),
        )
        if not plan_context:
            return ""
        return plan_context
    plan_context = format_work_plan_for_context(
        state.get("work_plan_items"),
        summary=state.get("work_plan_summary", ""),
    )
    if plan_context:
        lines.extend(["", plan_context])
    lines.append("如果用户没有指定路径，优先使用这些上下文；如果上下文不足，再询问或调用工具确认。需要历史细节时，先读取压缩摘要，再按需读取归档消息文件的相关行段。")
    return "\n".join(lines)


def context_update_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str]:
    update: dict[str, str] = {}
    if tool_name == "update_work_plan":
        return {}
    for key in ("plan_path", "output_dir", "workspace"):
        _capture_context_value(update, key, arguments.get(key))
        _capture_context_value(update, key, result.get(key))

    summary = result.get("summary")
    if isinstance(summary, dict):
        _capture_context_value(update, "plan_path", summary.get("path"))
        _capture_context_value(update, "output_dir", summary.get("latest_output"))

    plan = result.get("plan")
    if isinstance(plan, dict):
        _capture_context_value(update, "plan_path", plan.get("path"))

    workspace = result.get("workspace")
    if isinstance(workspace, dict):
        _capture_context_value(update, "workspace", workspace.get("root"))
        _capture_context_value(update, "plan_path", workspace.get("plan_path"))
    elif isinstance(workspace, str):
        _capture_context_value(update, "workspace", workspace)

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        _capture_context_value(update, "output_dir", nested_result.get("output_dir"))
        _capture_context_value(update, "workspace", nested_result.get("workspace"))

    latest_state = result.get("latest_state")
    if isinstance(latest_state, dict):
        _capture_context_value(update, "output_dir", latest_state.get("output_dir"))

    manifest = result.get("manifest")
    if isinstance(manifest, dict):
        _capture_context_value(update, "workspace", manifest.get("root"))
        _capture_context_value(update, "plan_path", manifest.get("plan_path"))

    if tool_name in {"read_plan_package", "validate_plan", "run_plan"}:
        _capture_context_value(update, "plan_path", arguments.get("plan_path"))
    if tool_name == "review_plan_quality":
        _capture_context_value(update, "plan_path", result.get("plan_path"))
        _capture_context_value(update, "plan_path", arguments.get("plan_path"))
        _capture_context_value(update, "latest_plan_quality_review_plan_path", result.get("plan_path"))
        _capture_context_value(update, "latest_plan_quality_review_signature", result.get("plan_signature"))
        _capture_context_value(update, "latest_plan_quality_review_severity", result.get("severity"))
        _capture_context_value(update, "latest_plan_quality_review_next_action", result.get("next_action"))
        if "ok" in result:
            update["latest_plan_quality_review_ok"] = "true" if bool(result.get("ok")) else "false"
    if tool_name == "inspect_web_page" and result.get("ok") is not False:
        page = result.get("page") if isinstance(result.get("page"), dict) else {}
        _capture_context_value(update, "latest_web_inspection_requested_url", result.get("requested_url"))
        _capture_context_value(update, "latest_web_inspection_resolved_url", result.get("resolved_url"))
        _capture_context_value(update, "latest_web_inspection_final_url", page.get("final_url"))
        _capture_context_value(update, "latest_web_inspection_title", page.get("title"))
    if tool_name == "inspect_desktop" and result.get("ok") is not False:
        _capture_context_value(update, "latest_desktop_inspection_platform", result.get("platform"))
        _capture_context_value(update, "latest_desktop_inspection_backend", result.get("backend"))
        capability_matrix = result.get("capability_matrix") if isinstance(result.get("capability_matrix"), dict) else {}
        limitations = capability_matrix.get("limitations") if isinstance(capability_matrix.get("limitations"), list) else []
        _capture_context_value(
            update,
            "latest_desktop_inspection_capability_limitations",
            ", ".join(str(item) for item in limitations) if limitations else "none",
        )
        if result.get("window_count") not in (None, ""):
            _capture_context_value(update, "latest_desktop_inspection_window_count", str(result.get("window_count")))
        focused_window = _desktop_focused_window_summary(result)
        _capture_context_value(update, "latest_desktop_inspection_focused_window", focused_window)
        elements = result.get("elements") if isinstance(result.get("elements"), dict) else {}
        match_count = elements.get("match_count") if isinstance(elements, dict) else None
        if match_count not in (None, ""):
            _capture_context_value(update, "latest_desktop_inspection_element_match_count", str(match_count))
    if tool_name in {"analyze_latest_run_failure", "prepare_failure_debug_workspace"} and result.get("ok") is not False:
        analysis = result.get("analysis") if tool_name == "prepare_failure_debug_workspace" else result
        if isinstance(analysis, dict):
            _capture_desktop_failure_context(update, analysis)
    if tool_name in {
        "read_debug_workspace",
        "inject_debug_steps",
        "patch_debug_workspace_json",
        "propose_debug_fix",
        "validate_debug_plan",
        "run_debug_plan",
        "generate_debug_patch",
        "apply_debug_patch_after_approval",
    }:
        _capture_context_value(update, "workspace", arguments.get("workspace"))
    return update


def work_plan_update_from_tool_result(
    tool_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if tool_name != "update_work_plan" or not isinstance(result, dict) or result.get("ok") is False:
        return {}
    return {
        "work_plan_items": normalize_work_plan_items(result.get("items")),
        "work_plan_summary": normalize_work_plan_summary(result.get("summary", "")),
    }


def _capture_context_value(update: dict[str, str], key: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if key == "plan_path":
        update["current_plan_path"] = str(resolve_plan_path(value))
        return
    if key == "workspace":
        update["current_debug_workspace"] = str(path_from_text(value).resolve())
        return
    if key == "output_dir":
        update["latest_output_dir"] = str(path_from_text(value).resolve())
        return
    if (
        key.startswith("latest_plan_quality_review_")
        or key.startswith("latest_web_inspection_")
        or key.startswith("latest_desktop_inspection_")
        or key.startswith("latest_desktop_failure_")
    ):
        update[key] = str(value)


def _desktop_focused_window_summary(result: dict[str, Any]) -> str:
    windows = result.get("windows") if isinstance(result.get("windows"), list) else []
    focused = next((window for window in windows if isinstance(window, dict) and bool(window.get("focused"))), None)
    if not isinstance(focused, dict):
        focused = windows[0] if windows and isinstance(windows[0], dict) else {}
    if not focused:
        return ""
    title = str(focused.get("title") or "")
    app = str(focused.get("app") or focused.get("process_name") or "")
    window_id = str(focused.get("id") or "")
    parts = [part for part in (f"id={window_id}" if window_id else "", f"title={title}" if title else "", f"app={app}" if app else "") if part]
    return ", ".join(parts)


def _capture_desktop_failure_context(update: dict[str, str], analysis: dict[str, Any]) -> None:
    diagnostics = analysis.get("desktop_diagnostics") if isinstance(analysis.get("desktop_diagnostics"), list) else []
    suggestions = (
        analysis.get("desktop_repair_suggestions")
        if isinstance(analysis.get("desktop_repair_suggestions"), list)
        else []
    )
    state_files = (
        analysis.get("failure_desktop_states")
        if isinstance(analysis.get("failure_desktop_states"), list)
        else []
    )
    screenshots = (
        analysis.get("failure_desktop_screenshots")
        if isinstance(analysis.get("failure_desktop_screenshots"), list)
        else []
    )
    if diagnostics or suggestions or state_files or screenshots:
        _capture_context_value(update, "latest_desktop_failure_status", str(analysis.get("status", "")))
        _capture_context_value(update, "latest_desktop_failure_diagnostics_count", str(len(diagnostics)))
        if suggestions:
            _capture_context_value(update, "latest_desktop_failure_repair_suggestions", " | ".join(str(item) for item in suggestions[:3]))
        if state_files:
            _capture_context_value(update, "latest_desktop_failure_state_files", " | ".join(str(item) for item in state_files[:3]))
        if screenshots:
            _capture_context_value(update, "latest_desktop_failure_screenshots", " | ".join(str(item) for item in screenshots[:3]))
