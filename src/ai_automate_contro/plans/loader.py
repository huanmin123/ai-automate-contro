from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_plan(plan_path: str | Path) -> dict[str, Any]:
    path = Path(plan_path).resolve()
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def detect_document_type(document: dict[str, Any]) -> str:
    if "steps" in document:
        return "plan"
    raise ValueError("不支持的文档类型。请使用包含 steps 数组的 plan 文档。")
