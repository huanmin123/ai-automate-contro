from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project, plan_roots_for_project


def load_plan_config(project_root: Path, plan_dir: Path) -> dict[str, Any]:
    collection_config = _load_json_object(_collection_config_path(project_root, plan_dir))
    local_config = _load_json_object(plan_dir / "config.json")
    return _resolve_env_refs(_deep_merge(collection_config, local_config))


def _collection_config_path(project_root: Path, plan_dir: Path) -> Path:
    resolved_project_root = project_root.resolve()
    resolved_plan_dir = plan_dir.resolve()
    for candidate in plan_roots_for_project(resolved_project_root):
        if _is_relative_to(resolved_plan_dir, candidate):
            return candidate / "config.json"
    return default_ai_config_dir_for_project(resolved_project_root) / "config.json"


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"plan config 必须是 JSON 对象：{path}")
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


def _resolve_env_refs(value: Any) -> Any:
    if isinstance(value, dict):
        if _is_env_ref_object(value):
            env_name = str(value.get("env") or value.get("env_var") or "")
            env_value = os.environ.get(env_name)
            if env_value is not None:
                return env_value
            if "default" in value:
                return value["default"]
            return ""
        return {key: _resolve_env_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_refs(item) for item in value]
    if isinstance(value, str):
        env_name = _string_env_ref_name(value)
        if env_name:
            return os.environ.get(env_name, "")
    return value


def _is_env_ref_object(value: dict[str, Any]) -> bool:
    keys = set(value)
    return bool(keys & {"env", "env_var"}) and keys <= {"env", "env_var", "default"}


def _string_env_ref_name(value: str) -> str | None:
    text = value.strip()
    if text.startswith("env:") and len(text) > 4:
        return text[4:]
    if text.startswith("$env:") and len(text) > 5:
        return text[5:]
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        return text[2:-1]
    return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
