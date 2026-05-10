from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import detect_document_type, load_plan
from ai_automate_contro.plans.packages import discover_plan_packages, plan_matches_filter, summarize_plan
from ai_automate_contro.plans.validator import validate_plan_file


def print_validation_result(raw_plan_path: str | Path, project_root: Path) -> int:
    result = validate_plan_file(raw_plan_path, project_root)
    if result.ok:
        print(f"plan valid: {result.plan_path}")
        return 0
    for error in result.errors:
        print(f"ERROR {error.format()}")
    return 1


def print_plan_list(project_root: Path, filter_text: str) -> None:
    normalized_filter = filter_text.lower()
    plans = discover_plan_packages(project_root)
    if normalized_filter:
        plans = [plan_path for plan_path in plans if plan_matches_filter(plan_path, project_root, normalized_filter)]
    for index, plan_path in enumerate(plans, start=1):
        summary = summarize_plan(plan_path, project_root)
        print(
            f"{index:02d}. {summary['relative_path']} "
            f"| name={summary['name']} | steps={summary['steps']}"
        )


def run_plan(
    raw_plan_path: str | Path,
    project_root: Path,
    *,
    run_name: str | None = None,
    output_dir: str | Path | None = None,
    variable_overrides: dict[str, Any] | None = None,
    manual_confirmation_handler: Any | None = None,
) -> Any:
    document = load_plan(raw_plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("Only plan documents can be executed.")
    return execute_plan(
        document,
        project_root,
        plan_path=raw_plan_path,
        run_name=run_name,
        output_dir=output_dir,
        variable_overrides=variable_overrides,
        manual_confirmation_handler=manual_confirmation_handler,
    )


def load_tool_arguments(args_json: str, args_file: str | None) -> dict[str, Any]:
    if args_file:
        raw_value = Path(args_file).read_text(encoding="utf-8")
    else:
        raw_value = args_json
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Tool arguments must be a JSON object: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return value


def print_json(value: Any, *, compact: bool = False) -> None:
    if compact:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))
