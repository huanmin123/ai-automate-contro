from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.failure_dom import summarize_failure_html
from ai_automate_contro.engine.desktop.targeting import compact_targeting
from ai_automate_contro.debug.run_artifacts import (
    MAX_RUN_EVENT_LINES,
    MAX_RUN_LOG_LINES,
    MAX_TEXT_ARTIFACT_BYTES,
    clamp_count,
    read_json_if_exists,
    read_jsonl_tail,
    read_text_preview,
    tail_lines,
)
from ai_automate_contro.support.utils import dict_get, first_string


def analyze_latest_run_failure_tool(
    resolve_plan_path: Any,
    resolve_run_output_dir: Any,
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    log_lines: int = 80,
    event_lines: int = 80,
) -> dict[str, Any]:
    resolved_plan_path = resolve_plan_path(plan_path)
    run_output_dir = resolve_run_output_dir(resolved_plan_path, output_dir)
    resolved_log_lines = clamp_count(log_lines, max_count=MAX_RUN_LOG_LINES)
    resolved_event_lines = clamp_count(event_lines, max_count=MAX_RUN_EVENT_LINES)
    state = read_json_if_exists(run_output_dir / "state.json")
    result = read_json_if_exists(run_output_dir / "result.json")
    events = read_jsonl_tail(run_output_dir / "events.jsonl", resolved_event_lines)
    commands = read_jsonl_tail(run_output_dir / "commands.jsonl", resolved_event_lines)
    log_tail = tail_lines(run_output_dir / "run.log", resolved_log_lines) if (run_output_dir / "run.log").exists() else []
    report, report_truncated = read_text_preview(run_output_dir / "report.md", max_bytes=MAX_TEXT_ARTIFACT_BYTES)

    status = first_string(
        dict_get(result, "status"),
        dict_get(state, "status"),
        "<unknown>",
    )
    error = first_string(
        dict_get(result, "error"),
        dict_get(state, "error"),
        last_event_error(events),
        "",
    )
    failed_step = detect_failed_step(events, state)
    plan_context = read_plan_step_context(resolved_plan_path, failed_step)
    warnings = filter_events(events, levels={"WARNING"})
    errors = filter_events(events, levels={"ERROR"})
    failure_screenshots = collect_failure_screenshots(run_output_dir, result)
    failure_htmls = collect_failure_files(run_output_dir, result, result_key="failure_htmls", directory_name="failure-html")
    failure_page_states = collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_page_states",
        directory_name="failure-page-state",
    )
    failure_desktop_screenshots = collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_desktop_screenshots",
        directory_name="failure-desktop-screenshots",
    )
    failure_desktop_states = collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_desktop_states",
        directory_name="failure-desktop-state",
    )
    dom_summaries = [
        summarize_failure_html(run_output_dir, html_path)
        for html_path in failure_htmls[:5]
    ]
    desktop_diagnostics = collect_desktop_diagnostics(failure_desktop_states)
    desktop_repair_suggestions = build_desktop_repair_suggestions(desktop_diagnostics)
    hints = build_failure_hints(
        error=error,
        failed_step=failed_step,
        events=events,
        desktop_diagnostics=desktop_diagnostics,
    )

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
        "failure_desktop_screenshots": failure_desktop_screenshots,
        "failure_desktop_states": failure_desktop_states,
        "desktop_diagnostics": desktop_diagnostics,
        "desktop_repair_suggestions": desktop_repair_suggestions,
        "dom_summaries": [summary for summary in dom_summaries if summary],
        "recent_errors": errors[-10:],
        "recent_warnings": warnings[-10:],
        "commands": commands[-20:],
        "report": report,
        "report_truncated": report_truncated,
        "log_tail": log_tail,
        "events_tail": events[-20:],
        "requested_log_lines": log_lines,
        "requested_event_lines": event_lines,
        "max_log_lines": MAX_RUN_LOG_LINES,
        "max_event_lines": MAX_RUN_EVENT_LINES,
        "next_actions": [
            "修改前先读取失败步骤和相邻 plan 步骤。",
            "注入诊断或提出修复前，先创建调试工作区。",
            "只对调试工作区的 injected-plan/ 做最小修改。",
            "生成 patch.diff 前，先运行并校验 injected-plan。",
        ],
    }


def last_event_error(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if str(event.get("level", "")).upper() != "ERROR":
            continue
        fields = event.get("fields", {})
        if isinstance(fields, dict) and fields.get("error"):
            return str(fields["error"])
        if event.get("message"):
            return str(event["message"])
    return ""


def detect_failed_step(events: list[dict[str, Any]], state: Any) -> dict[str, Any] | None:
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
    current_step = dict_get(state, "current_step")
    if isinstance(current_step, dict):
        return dict(current_step)
    return None


def read_plan_step_context(plan_path: Path, failed_step: dict[str, Any] | None) -> dict[str, Any]:
    if not failed_step:
        return {}
    step_number = failed_step.get("step")
    if not isinstance(step_number, int) or step_number <= 0:
        return {}
    document = read_json_if_exists(plan_path)
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


def filter_events(events: list[dict[str, Any]], *, levels: set[str]) -> list[dict[str, Any]]:
    normalized_levels = {level.upper() for level in levels}
    return [
        event
        for event in events
        if str(event.get("level", "")).upper() in normalized_levels
    ]


def collect_failure_screenshots(run_output_dir: Path, result: Any) -> list[str]:
    return collect_failure_files(
        run_output_dir,
        result,
        result_key="failure_screenshots",
        directory_name="failure-screenshots",
    )


def collect_failure_files(run_output_dir: Path, result: Any, *, result_key: str, directory_name: str) -> list[str]:
    files: list[str] = []
    result_files = dict_get(result, result_key)
    if isinstance(result_files, list):
        files.extend(str(item) for item in result_files)
    failure_dir = run_output_dir / directory_name
    if failure_dir.exists():
        files.extend(str(path.resolve()) for path in sorted(failure_dir.glob("*")) if path.is_file())
    return sorted(dict.fromkeys(files))


def collect_desktop_diagnostics(state_paths: list[str]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for raw_path in state_paths[:5]:
        path = Path(raw_path)
        payload = read_json_if_exists(path)
        if not isinstance(payload, dict):
            continue
        diagnostics = dict_get(payload, "diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        window_diagnostics = dict_get(diagnostics, "window")
        if not isinstance(window_diagnostics, dict):
            window_diagnostics = dict_get(payload, "window_diagnostics")
        if not isinstance(window_diagnostics, dict):
            window_diagnostics = {}
        element_diagnostics = dict_get(diagnostics, "element")
        if not isinstance(element_diagnostics, dict):
            element_diagnostics = dict_get(payload, "element_diagnostics")
        if not isinstance(element_diagnostics, dict):
            element_diagnostics = {}
        capability_matrix = dict_get(payload, "capability_matrix")
        if not isinstance(capability_matrix, dict):
            capability_matrix = dict_get(diagnostics, "capability_matrix")
        if not isinstance(capability_matrix, dict):
            capability_matrix = {}
        coordinate_profile = dict_get(payload, "coordinate_profile")
        if not isinstance(coordinate_profile, dict):
            coordinate_profile = dict_get(diagnostics, "coordinate_profile")
        if not isinstance(coordinate_profile, dict):
            coordinate_profile = {}
        target_candidates = dict_get(payload, "target_candidates")
        if not isinstance(target_candidates, dict):
            target_candidates = dict_get(diagnostics, "target_candidates")
        if not isinstance(target_candidates, dict):
            target_candidates = {}
        summaries.append(
            {
                "path": str(path),
                "step": payload.get("step"),
                "action": payload.get("action", ""),
                "step_name": payload.get("step_name", ""),
                "error": payload.get("error", ""),
                "error_type": payload.get("error_type", ""),
                "target": payload.get("target", {}) if isinstance(payload.get("target"), dict) else {},
                "window": summarize_window_diagnostics(window_diagnostics),
                "element": summarize_element_diagnostics(element_diagnostics),
                "target_candidates": compact_targeting(target_candidates),
                "capability_matrix": summarize_capability_matrix(capability_matrix),
                "coordinate_profile": summarize_coordinate_profile(coordinate_profile),
                "screenshot": payload.get("screenshot", ""),
            }
        )
    return summaries


def summarize_coordinate_profile(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    display = payload.get("display") if isinstance(payload.get("display"), dict) else {}
    transforms = payload.get("transforms") if isinstance(payload.get("transforms"), dict) else {}
    return {
        "schema_version": payload.get("schema_version", ""),
        "kind": payload.get("kind", ""),
        "platform": payload.get("platform", ""),
        "backend": payload.get("backend", ""),
        "space": payload.get("space", {}) if isinstance(payload.get("space"), dict) else {},
        "source": {
            "kind": source.get("kind", ""),
            "bounds": source.get("bounds", {}) if isinstance(source.get("bounds"), dict) else {},
            "screen_clickable": source.get("screen_clickable", ""),
        },
        "display": {
            "virtual_bounds": display.get("virtual_bounds", {}) if isinstance(display.get("virtual_bounds"), dict) else {},
            "monitor_count": display.get("monitor_count", ""),
            "scale": display.get("scale", ""),
            "dpi": display.get("dpi", {}) if isinstance(display.get("dpi"), dict) else {},
        },
        "transforms": transforms,
        "warnings": payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else [],
    }


def summarize_capability_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    raw_capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    capabilities = {
        "semantic": _capability_group(payload, raw_capabilities, "semantic"),
        "input": _capability_group(payload, raw_capabilities, "input"),
        "screenshot": _capability_group(payload, raw_capabilities, "screenshot"),
        "coordinates": _capability_group(payload, raw_capabilities, "coordinates"),
        "vision": _capability_group(payload, raw_capabilities, "vision"),
    }
    return {
        "schema_version": payload.get("schema_version", ""),
        "platform": payload.get("platform", ""),
        "backend": payload.get("backend", ""),
        "source": payload.get("source", ""),
        "capabilities": capabilities,
        "permissions": payload.get("permissions", {}) if isinstance(payload.get("permissions"), dict) else {},
        "dependencies": payload.get("dependencies", {}) if isinstance(payload.get("dependencies"), dict) else {},
        "limitations": payload.get("limitations", []) if isinstance(payload.get("limitations"), list) else [],
    }


def _capability_group(payload: dict[str, Any], capabilities: dict[str, Any], group: str) -> dict[str, Any]:
    raw = capabilities.get(group)
    if isinstance(raw, dict):
        return raw
    legacy = payload.get(group)
    return legacy if isinstance(legacy, dict) else {}


def summarize_window_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    query = dict_get(payload, "query")
    matches = dict_get(payload, "matches")
    near_matches = dict_get(payload, "near_matches")
    current_window = dict_get(payload, "current_window")
    return {
        "query": query if isinstance(query, dict) else {},
        "current_window": current_window if isinstance(current_window, dict) else {},
        "total_windows": _safe_int(dict_get(payload, "total_windows")),
        "match_count": _safe_int(dict_get(payload, "match_count")),
        "matches": compact_window_candidates(matches),
        "near_matches": compact_window_near_matches(near_matches),
        "skipped": bool(dict_get(payload, "skipped")),
        "reason": first_string(dict_get(payload, "reason"), ""),
        "error": first_string(dict_get(payload, "error"), ""),
    }


def summarize_element_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    locator = dict_get(payload, "locator")
    window_query = dict_get(payload, "window_query")
    matches = dict_get(payload, "matches")
    near_matches = dict_get(payload, "near_matches")
    selector_hints = dict_get(payload, "selector_hints")
    return {
        "window_query": window_query if isinstance(window_query, dict) else {},
        "locator": locator if isinstance(locator, dict) else {},
        "count": _safe_int(dict_get(payload, "count")),
        "match_count": _safe_int(dict_get(payload, "match_count")),
        "matches": compact_element_candidates(matches),
        "near_matches": compact_element_near_matches(near_matches),
        "selector_hints": selector_hints[:8] if isinstance(selector_hints, list) else [],
        "skipped": bool(dict_get(payload, "skipped")),
        "reason": first_string(dict_get(payload, "reason"), ""),
        "error": first_string(dict_get(payload, "error"), ""),
        "error_type": first_string(dict_get(payload, "error_type"), ""),
    }


def compact_window_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in value[:5]:
        if isinstance(item, dict):
            candidates.append(
                {
                    "title": first_string(item.get("title"), ""),
                    "app": first_string(item.get("app"), ""),
                    "process_name": first_string(item.get("process_name"), ""),
                    "class_name": first_string(item.get("class_name"), ""),
                    "focused": bool(item.get("focused")),
                    "bounds": item.get("bounds", {}) if isinstance(item.get("bounds"), dict) else {},
                }
            )
    return candidates


def compact_window_near_matches(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    matches: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        window = item.get("window") if isinstance(item.get("window"), dict) else {}
        matches.append(
            {
                "score": _safe_int(item.get("score")),
                "matched_fields": item.get("matched_fields", []) if isinstance(item.get("matched_fields"), list) else [],
                "missing_fields": item.get("missing_fields", []) if isinstance(item.get("missing_fields"), list) else [],
                "window": compact_window_candidates([window])[0] if window else {},
            }
        )
    return matches


def compact_element_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in value[:5]:
        if isinstance(item, dict):
            candidates.append(compact_element_candidate(item))
    return candidates


def compact_element_near_matches(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    matches: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        matches.append(
            {
                "score": _safe_int(item.get("score")),
                "matched_fields": item.get("matched_fields", []) if isinstance(item.get("matched_fields"), list) else [],
                "missing_fields": item.get("missing_fields", []) if isinstance(item.get("missing_fields"), list) else [],
                "reasons": item.get("reasons", []) if isinstance(item.get("reasons"), list) else [],
                "element": compact_element_candidate(element) if element else {},
            }
        )
    return matches


def compact_element_candidate(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "automation_id": first_string(element.get("automation_id"), ""),
        "name": first_string(element.get("name"), ""),
        "text": first_string(element.get("text"), ""),
        "value": first_string(element.get("value"), ""),
        "control_type": first_string(element.get("control_type"), ""),
        "role": first_string(element.get("role"), ""),
        "class_name": first_string(element.get("class_name"), first_string(element.get("element_class_name"), "")),
        "bounds": element.get("bounds", {}) if isinstance(element.get("bounds"), dict) else {},
        "selector_hints": element.get("selector_hints", [])[:5] if isinstance(element.get("selector_hints"), list) else [],
    }


def build_desktop_repair_suggestions(diagnostics: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    for item in diagnostics:
        window = item.get("window") if isinstance(item.get("window"), dict) else {}
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        window_query = window.get("query") if isinstance(window.get("query"), dict) else {}
        element_locator = element.get("locator") if isinstance(element.get("locator"), dict) else {}
        window_near_matches = window.get("near_matches") if isinstance(window.get("near_matches"), list) else []
        element_near_matches = element.get("near_matches") if isinstance(element.get("near_matches"), list) else []
        selector_hints = element.get("selector_hints") if isinstance(element.get("selector_hints"), list) else []
        target_candidates = item.get("target_candidates") if isinstance(item.get("target_candidates"), dict) else {}
        first_candidate = {}
        raw_candidates = target_candidates.get("candidates") if isinstance(target_candidates.get("candidates"), list) else []
        if raw_candidates and isinstance(raw_candidates[0], dict):
            first_candidate = raw_candidates[0]
        best_strategy = first_string(
            dict_get(dict_get(target_candidates, "summary"), "best_strategy"),
            dict_get(target_candidates, "best_strategy"),
            dict_get(first_candidate, "strategy"),
            "",
        )
        best_candidate_id = first_string(dict_get(first_candidate, "candidate_id"), dict_get(first_candidate, "id"), "")
        best_confidence = first_string(dict_get(first_candidate, "confidence"), "")
        best_screen_clickable = dict_get(first_candidate, "screen_clickable")
        candidate_count = _safe_int(dict_get(target_candidates, "candidate_count"))
        capability_matrix = item.get("capability_matrix") if isinstance(item.get("capability_matrix"), dict) else {}
        limitations = capability_matrix.get("limitations") if isinstance(capability_matrix.get("limitations"), list) else []
        error_text = first_string(item.get("error"), "").lower()
        if limitations:
            suggestions.append(f"桌面能力限制：先处理 capability_matrix.limitations={limitations!r}。")
        if candidate_count:
            suggestions.append(
                "桌面定位候选已生成：优先查看 diagnostics.target_candidates.best_candidate"
                + (f"，当前最佳策略={best_strategy!r}" if best_strategy else "")
                + (f"，candidate_id={best_candidate_id!r}" if best_candidate_id else "")
                + "。"
            )
        if best_strategy == "semantic_locator" and best_candidate_id:
            suggestions.append(
                "桌面候选可执行：需要真实鼠标事件时优先改用 desktop_input target=candidate，"
                f"传入同一次 target_candidates 和 candidate_id={best_candidate_id!r}；否则直接使用 desktop_element。"
            )
        if best_strategy == "visual_bounds" and best_candidate_id:
            if best_screen_clickable is True and best_confidence in {"high", "medium"}:
                suggestions.append(
                    "视觉候选可作为坐标兜底：使用 desktop_input target=candidate 消费 candidate_id，"
                    "并在后续补 desktop_assert、desktop_wait 或截图验证。"
                )
            else:
                suggestions.append(
                    "视觉候选不可直接点击：置信度不足或 screen_clickable=false，先重新 observe/vision 当前屏幕或加入 manual_confirm。"
                )
        if "point_outside_virtual_screen" in error_text or "输入前安全检查失败" in first_string(item.get("error"), ""):
            suggestions.append("桌面输入前安全检查失败：重新获取 coordinate_profile/target_candidates，避免复用旧 bounds 或跨显示器坐标。")
        if "screen_clickable=false" in error_text or "source_path" in error_text or "离线图片" in first_string(item.get("error"), ""):
            suggestions.append("离线图片或 screen_clickable=false 只能作为证据：改用当前屏幕的 desktop_capture observe/desktop_vision，或人工确认后再点击。")
        if window_query and not window.get("match_count") and window_near_matches:
            top_window = window_near_matches[0].get("window") if isinstance(window_near_matches[0], dict) else {}
            title = first_string(dict_get(top_window, "title"), "")
            app = first_string(dict_get(top_window, "app"), dict_get(top_window, "process_name"), "")
            suggestions.append(
                "桌面窗口未命中：根据 diagnostics.window.near_matches 修正 Window Query"
                + (f"，优先核对 title_contains={title!r}" if title else "")
                + (f" 或 app/process={app!r}" if app else "")
                + "。"
            )
        if element_locator and element_near_matches:
            top_element = element_near_matches[0].get("element") if isinstance(element_near_matches[0], dict) else {}
            hints = top_element.get("selector_hints") if isinstance(top_element, dict) else []
            if not hints:
                hints = selector_hints
            suggestions.append(
                "桌面控件未命中：根据 diagnostics.element.near_matches 修正 Element Locator"
                + (f"，可优先尝试 selector_hints={hints[:3]!r}" if hints else "")
                + "。"
            )
        if element.get("error") and not element_locator:
            suggestions.append("桌面控件诊断缺少 locator：先补充 name/name_contains/automation_id/control_type 等 Element Locator。")
    return list(dict.fromkeys(suggestions))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_failure_hints(
    *,
    error: str,
    failed_step: dict[str, Any] | None,
    events: list[dict[str, Any]],
    desktop_diagnostics: list[dict[str, Any]] | None = None,
) -> list[str]:
    text = " ".join(
        [
            error.lower(),
            json.dumps(failed_step or {}, ensure_ascii=False).lower(),
            " ".join(str(event.get("message", "")).lower() for event in events[-10:]),
        ]
    )
    hints: list[str] = []
    desktop_diagnostics = desktop_diagnostics or []
    if desktop_diagnostics:
        hints.append(
            "Desktop failure evidence is available; inspect desktop_diagnostics and desktop_repair_suggestions before changing the plan."
        )
    if "desktop" in text and ("window" in text or "窗口" in text):
        hints.append("Desktop window query may be wrong; compare failed Window Query with diagnostics.window.near_matches.")
    if "desktop" in text and ("element" in text or "控件" in text):
        hints.append("Desktop element locator may be wrong; compare failed Element Locator with diagnostics.element.near_matches and selector_hints.")
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
