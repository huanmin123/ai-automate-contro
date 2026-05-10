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
        issues.append(ValidationIssue(str(path), f"invalid JSON: {error.msg}"))
        return None
    except OSError as error:
        issues.append(ValidationIssue(str(path), str(error)))
        return None
    if not isinstance(document, dict):
        issues.append(ValidationIssue(str(path), "plan document must be a JSON object"))
        return None
    return document


def validate_config(project_root: Path, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        load_plan_config(project_root, plan_dir)
    except Exception as error:
        issues.append(ValidationIssue(str(plan_dir / "config.json"), f"invalid merged config: {error}"))
