from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.plans.validation_models import ValidationIssue


def load_json_document(path: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as file:
            document = json.load(file)
    except JSONDecodeError as error:
        issues.append(ValidationIssue(str(path), f"JSON 无效：{error.msg}"))
        return None
    except OSError as error:
        issues.append(ValidationIssue(str(path), str(error)))
        return None
    if not isinstance(document, dict):
        issues.append(ValidationIssue(str(path), "plan 文档必须是 JSON 对象"))
        return None
    return document


def validate_config(project_root: Path, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        config = load_plan_config(project_root, plan_dir)
    except Exception as error:
        issues.append(ValidationIssue(str(plan_dir / "config.json"), f"合并后的配置无效：{error}"))
        return
    if "variables" in config:
        issues.append(
            ValidationIssue(
                str(plan_dir / "config.json") + ":variables",
                "config.json 不支持 variables；plan 变量请写在 plan.json.variables",
            )
        )
    validate_post_run_inspection_config(config.get("post_run_inspection"), plan_dir, issues)


def validate_post_run_inspection_config(value: Any, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    location = str(plan_dir / "config.json") + ":post_run_inspection"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "post_run_inspection 必须是 JSON 对象"))
        return
    enabled = value.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        issues.append(ValidationIssue(location, "enabled 必须是布尔值"))
    prompt = value.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        issues.append(ValidationIssue(location, "prompt 必须是字符串"))
