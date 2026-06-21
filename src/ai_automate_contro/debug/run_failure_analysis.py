from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.failure_dom import summarize_failure_html
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
    dom_summaries = [
        summarize_failure_html(run_output_dir, html_path)
        for html_path in failure_htmls[:5]
    ]
    hints = build_failure_hints(error=error, failed_step=failed_step, events=events)

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


def build_failure_hints(*, error: str, failed_step: dict[str, Any] | None, events: list[dict[str, Any]]) -> list[str]:
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
