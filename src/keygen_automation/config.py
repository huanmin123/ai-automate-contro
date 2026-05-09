from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_config_directory(project_root: Path) -> Path:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_plan_config(project_root: Path, plan_dir: Path) -> dict[str, Any]:
    global_config = _load_json_object(project_root / "plans" / "config.json")
    local_config = _load_json_object(plan_dir / "config.json")
    return _deep_merge(global_config, local_config)


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
