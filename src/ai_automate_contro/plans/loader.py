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
    raise ValueError("Unsupported document. Expected a plan document with a 'steps' array.")
