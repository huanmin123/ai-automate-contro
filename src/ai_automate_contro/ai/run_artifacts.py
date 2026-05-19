from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.debug_workspace_io import is_relative_to
from ai_automate_contro.plans.artifacts import list_output_artifacts
from ai_automate_contro.plans.packages import find_latest_run_output
from ai_automate_contro.support.paths import path_from_text


MAX_TEXT_ARTIFACT_BYTES = 64_000
MAX_RUN_LOG_LINES = 200
MAX_RUN_EVENT_LINES = 200
MAX_OUTPUT_ARTIFACTS = 200
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


def read_latest_run_state_tool(resolve_plan_path: Any, plan_path: str | Path) -> dict[str, Any]:
    resolved_plan_path = resolve_plan_path(plan_path)
    output_dir = find_latest_run_output(resolved_plan_path.parent)
    if output_dir is None:
        return {"ok": True, "output_dir": "", "state": None}
    state_path = output_dir / "state.json"
    state = read_json_if_exists(state_path)
    return {
        "ok": True,
        "output_dir": str(output_dir),
        "state": state,
    }


def read_latest_run_report_tool(resolve_plan_path: Any, plan_path: str | Path) -> dict[str, Any]:
    resolved_plan_path = resolve_plan_path(plan_path)
    output_dir = find_latest_run_output(resolved_plan_path.parent)
    if output_dir is None:
        return {"ok": True, "output_dir": "", "path": "", "content": ""}
    report_path = output_dir / "report.md"
    content, truncated = read_text_preview(report_path, max_bytes=MAX_TEXT_ARTIFACT_BYTES)
    return {
        "ok": report_path.exists(),
        "output_dir": str(output_dir),
        "path": str(report_path),
        "content": content,
        "truncated": truncated,
    }


def read_run_log_tool(
    resolve_run_output_dir: Any,
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 80,
) -> dict[str, Any]:
    run_output_dir = resolve_run_output_dir(plan_path, output_dir)
    log_path = run_output_dir / "run.log"
    resolved_lines = clamp_count(lines, max_count=MAX_RUN_LOG_LINES)
    return {
        "ok": log_path.exists(),
        "output_dir": str(run_output_dir),
        "path": str(log_path),
        "lines": tail_lines(log_path, resolved_lines) if log_path.exists() else [],
        "requested_lines": lines,
        "max_lines": MAX_RUN_LOG_LINES,
    }


def read_run_events_tool(
    resolve_run_output_dir: Any,
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    lines: int = 40,
) -> dict[str, Any]:
    run_output_dir = resolve_run_output_dir(plan_path, output_dir)
    events_path = run_output_dir / "events.jsonl"
    resolved_lines = clamp_count(lines, max_count=MAX_RUN_EVENT_LINES)
    events: list[Any] = []
    if events_path.exists():
        for line in tail_lines(events_path, resolved_lines):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"raw": line})
    return {
        "ok": events_path.exists(),
        "output_dir": str(run_output_dir),
        "path": str(events_path),
        "events": events,
        "requested_lines": lines,
        "max_lines": MAX_RUN_EVENT_LINES,
    }


def list_output_artifacts_tool(plan_path: str | Path, *, filter_text: str = "", limit: int = 100) -> dict[str, Any]:
    resolved_limit = clamp_count(limit, max_count=MAX_OUTPUT_ARTIFACTS)
    artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=resolved_limit)
    return {
        "ok": True,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
        "requested_limit": limit,
        "max_limit": MAX_OUTPUT_ARTIFACTS,
    }


def read_output_artifact_tool(
    resolve_plan_path: Any,
    plan_path: str | Path,
    relative_path: str | Path,
    *,
    max_bytes: int = MAX_TEXT_ARTIFACT_BYTES,
) -> dict[str, Any]:
    resolved_plan_path = resolve_plan_path(plan_path)
    output_root = (resolved_plan_path.parent / "output").resolve()
    artifact_path = (output_root / path_from_text(relative_path)).resolve()
    if not is_relative_to(artifact_path, output_root):
        raise ValueError("产物路径必须位于当前 plan output 目录内。")
    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(f"产物不存在：{artifact_path}")
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
    resolved_max_bytes = max(0, min(int(max_bytes), MAX_TEXT_ARTIFACT_BYTES))
    content, truncated = read_text_preview(artifact_path, max_bytes=resolved_max_bytes)
    lines = content.splitlines()
    payload["truncated"] = truncated
    payload["requested_max_bytes"] = max_bytes
    payload["max_bytes"] = MAX_TEXT_ARTIFACT_BYTES
    payload["content"] = content
    payload["line_count"] = len(lines)
    payload["non_empty_line_count"] = len([line for line in lines if line.strip()])
    payload["content_complete"] = not truncated
    return payload


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0:
        return []
    block_size = 8192
    data = b""
    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        while position > 0 and data.count(b"\n") <= count:
            read_size = min(block_size, position)
            position -= read_size
            file.seek(position)
            data = file.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-count:]


def read_text_preview(path: Path, *, max_bytes: int) -> tuple[str, bool]:
    if not path.exists():
        return "", False
    with path.open("rb") as file:
        data = file.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace"), truncated


def clamp_count(count: int, *, max_count: int) -> int:
    return max(0, min(int(count), max_count))


def read_jsonl_tail(path: Path, count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in tail_lines(path, count):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = {"raw": line}
        if isinstance(value, dict):
            events.append(value)
        else:
            events.append({"value": value})
    return events
