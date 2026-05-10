from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.debug_workspace_io import is_relative_to, read_text_if_exists
from ai_automate_contro.plans.artifacts import list_output_artifacts
from ai_automate_contro.plans.packages import find_latest_run_output


MAX_TEXT_ARTIFACT_BYTES = 256_000
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
    return {
        "ok": report_path.exists(),
        "output_dir": str(output_dir),
        "path": str(report_path),
        "content": read_text_if_exists(report_path),
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
    return {
        "ok": log_path.exists(),
        "output_dir": str(run_output_dir),
        "path": str(log_path),
        "lines": tail_lines(log_path, lines) if log_path.exists() else [],
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
    events: list[Any] = []
    if events_path.exists():
        for line in tail_lines(events_path, lines):
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


def list_output_artifacts_tool(plan_path: str | Path, *, filter_text: str = "", limit: int = 100) -> dict[str, Any]:
    artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
    return {
        "ok": True,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
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
    artifact_path = (output_root / relative_path).resolve()
    if not is_relative_to(artifact_path, output_root):
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


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0:
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]


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
