from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_automate_contro.support.paths import path_from_text


CONFIG_FILE_NAME = "plan.config"


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path
    handbook_path: Path
    plan_roots: tuple[Path, ...]
    default_ai_config_dir: Path


def load_runtime_config(project_root: str | Path) -> RuntimeConfig:
    root = Path(project_root).resolve()
    config_path = root / CONFIG_FILE_NAME
    raw_config = _read_config(config_path)

    handbook_path = _resolve_config_path(root, raw_config.get("handbook_path", "handbook"))
    plan_roots = _resolve_plan_roots(root, raw_config)
    default_ai_config_dir = _resolve_config_path(
        root,
        raw_config.get("default_ai_config_dir", _default_ai_config_dir(root, plan_roots)),
    )

    return RuntimeConfig(
        project_root=root,
        handbook_path=handbook_path,
        plan_roots=tuple(plan_roots),
        default_ai_config_dir=default_ai_config_dir,
    )


def plan_roots_for_project(project_root: str | Path) -> tuple[Path, ...]:
    return load_runtime_config(project_root).plan_roots


def default_ai_config_dir_for_project(project_root: str | Path) -> Path:
    return load_runtime_config(project_root).default_ai_config_dir


def handbook_path_for_project(project_root: str | Path) -> Path:
    return load_runtime_config(project_root).handbook_path


def has_runtime_config(project_root: str | Path) -> bool:
    return (Path(project_root).resolve() / CONFIG_FILE_NAME).exists()


def _read_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG_FILE_NAME} 必须是 JSON 对象：{config_path}")
    return data


def _resolve_plan_roots(root: Path, raw_config: dict[str, Any]) -> list[Path]:
    raw_plan_roots = raw_config.get("plan_roots")
    if raw_plan_roots is None:
        return [root / "plans", root / "test-plans"]
    if not isinstance(raw_plan_roots, list):
        raise ValueError("plan.config 字段 plan_roots 必须是数组。")
    plan_roots: list[Path] = []
    for raw_path in raw_plan_roots:
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("plan.config 字段 plan_roots 的每一项都必须是非空字符串。")
        plan_roots.append(_resolve_config_path(root, raw_path))
    return plan_roots


def _default_ai_config_dir(root: Path, plan_roots: list[Path]) -> str:
    for plan_root in plan_roots:
        if plan_root.name == "test-plans":
            return str(plan_root)
    return "plans"


def _resolve_config_path(root: Path, raw_path: str | Path) -> Path:
    path = path_from_text(raw_path)
    if not path.is_absolute():
        path = root / path
    return path.resolve()
