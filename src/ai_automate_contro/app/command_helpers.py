from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import detect_document_type, load_plan
from ai_automate_contro.plans.packages import discover_plan_packages, plan_matches_filter, summarize_plan
from ai_automate_contro.plans.validator import validate_plan_file
from ai_automate_contro.support.paths import path_from_text


def print_validation_result(raw_plan_path: str | Path, project_root: Path) -> int:
    result = validate_plan_file(raw_plan_path, project_root)
    if result.ok:
        print(f"计划校验通过：{result.plan_path}")
        return 0
    for error in result.errors:
        print(f"错误：{error.format()}")
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
            f"| 名称={summary['name']} | 步骤数={summary['steps']}"
        )


def run_plan(
    raw_plan_path: str | Path,
    project_root: Path,
    *,
    run_name: str | None = None,
    output_dir: str | Path | None = None,
    variable_overrides: dict[str, Any] | None = None,
    manual_confirmation_handler: Any | None = None,
    inspection_confirmation_handler: Any | None = None,
    interrupt_checker: Any | None = None,
) -> Any:
    document = load_plan(raw_plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("只能运行 plan 文档。请确认文件是 plan 包入口 plan.json。")
    return execute_plan(
        document,
        project_root,
        plan_path=raw_plan_path,
        run_name=run_name,
        output_dir=output_dir,
        variable_overrides=variable_overrides,
        manual_confirmation_handler=manual_confirmation_handler,
        inspection_confirmation_handler=inspection_confirmation_handler,
        interrupt_checker=interrupt_checker,
    )


def load_tool_arguments(args_json: str, args_file: str | None) -> dict[str, Any]:
    if args_file:
        raw_value = path_from_text(args_file).read_text(encoding="utf-8")
    else:
        raw_value = args_json
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as error:
        repaired_value = _repair_windows_path_backslashes_in_json(raw_value)
        if repaired_value == raw_value:
            raise ValueError(f"工具参数必须是 JSON 对象：{error.msg}") from error
        try:
            value = json.loads(repaired_value)
        except json.JSONDecodeError:
            raise ValueError(f"工具参数必须是 JSON 对象：{error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("工具参数必须是 JSON 对象。")
    return value


def _repair_windows_path_backslashes_in_json(raw_value: str) -> str:
    def repair_string(match: re.Match[str]) -> str:
        content = match.group(1)
        repaired = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", content)
        return f'"{repaired}"'

    return re.sub(r'"((?:[^"\\]|\\.)*)"', repair_string, raw_value)


def print_json(value: Any, *, compact: bool = False) -> None:
    if compact:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))
