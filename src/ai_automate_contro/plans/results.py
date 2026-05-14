from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json

from ai_automate_contro.support.paths import path_from_text


@dataclass
class PlanResult:
    run_name: str
    status: str
    plan_path: str | None
    output_dir: str
    started_at: str
    finished_at: str
    error: str | None = None
    failure_screenshots: list[str] = field(default_factory=list)
    failure_htmls: list[str] = field(default_factory=list)
    failure_page_states: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_result_json(result: PlanResult, output_dir: Path) -> Path:
    result_path = output_dir / "result.json"

    with result_path.open("w", encoding="utf-8") as file:
        json.dump(result.to_dict(), file, ensure_ascii=False, indent=2)
    return result_path


def write_report_markdown(result: PlanResult, output_dir: Path) -> Path:
    report_path = output_dir / "report.md"
    lines = [
        "# Run Report",
        "",
        f"- Run name: `{result.run_name}`",
        f"- Status: `{result.status}`",
        f"- Started at: `{result.started_at}`",
        f"- Finished at: `{result.finished_at}`",
    ]
    if result.plan_path:
        lines.append(f"- Plan: `{result.plan_path}`")
    lines.append(f"- Output: `{result.output_dir}`")
    if result.tags:
        lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in result.tags)}")
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])

    lines.extend(["", "## Artifacts", ""])
    for relative_path in _standard_artifact_paths(output_dir):
        lines.append(f"- `{relative_path}`")
    for screenshot in result.failure_screenshots:
        lines.append(f"- Failure screenshot: `{_display_artifact_path(output_dir, screenshot)}`")
    for html in result.failure_htmls:
        lines.append(f"- Failure HTML: `{_display_artifact_path(output_dir, html)}`")
    for page_state in result.failure_page_states:
        lines.append(f"- Failure page state: `{_display_artifact_path(output_dir, page_state)}`")
    for download in _metadata_list(result.metadata, "downloads"):
        lines.append(f"- Download: `{_display_artifact_path(output_dir, download)}`")
    if not lines[-1].startswith("- "):
        lines.append("- <none>")

    last_dialog_message = result.metadata.get("last_dialog_message")
    if last_dialog_message:
        lines.extend(["", "## Last Dialog", "", str(last_dialog_message)])

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _standard_artifact_paths(output_dir: Path) -> list[str]:
    names = ["state.json", "result.json", "report.md", "run.log", "events.jsonl", "commands.jsonl"]
    return [name for name in names if name == "report.md" or (output_dir / name).exists()]


def _metadata_list(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _display_artifact_path(output_dir: Path, raw_path: str) -> str:
    path = path_from_text(raw_path)
    try:
        return str(path.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(path)
