from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_plan_config(project_root: Path, plan_dir: Path) -> dict[str, Any]:
    collection_config = _load_json_object(_collection_config_path(project_root, plan_dir))
    local_config = _load_json_object(plan_dir / "config.json")
    return _deep_merge(collection_config, local_config)


def _collection_config_path(project_root: Path, plan_dir: Path) -> Path:
    resolved_project_root = project_root.resolve()
    resolved_plan_dir = plan_dir.resolve()
    candidates = [
        resolved_project_root / "test-plans",
        resolved_project_root / "plans",
    ]
    for candidate in candidates:
        if _is_relative_to(resolved_plan_dir, candidate):
            return candidate / "config.json"
    return resolved_project_root / "plans" / "config.json"


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Plan config must be a JSON object: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
