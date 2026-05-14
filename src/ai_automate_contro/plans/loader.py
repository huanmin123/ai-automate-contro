from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.support.paths import format_missing_path_message, path_from_text


def load_plan(plan_path: str | Path) -> dict[str, Any]:
    path = path_from_text(plan_path).resolve()
    if not path.exists():
        raise FileNotFoundError(format_missing_path_message(plan_path, path, label="plan 文件"))
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def detect_document_type(document: dict[str, Any]) -> str:
    if "steps" in document:
        return "plan"
    raise ValueError("不支持的文档类型。请使用包含 steps 数组的 plan 文档。")
