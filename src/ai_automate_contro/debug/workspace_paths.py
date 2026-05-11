from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_plan_path(plan_path: str | Path) -> Path:
    resolved_path = Path(plan_path).resolve()
    if resolved_path.is_dir():
        resolved_path = resolved_path / "plan.json"
    if not resolved_path.exists():
        raise FileNotFoundError(f"plan 文件不存在：{resolved_path}")
    if resolved_path.name != "plan.json":
        raise ValueError(f"debug workspace 只能基于 plan 包入口 plan.json 创建：{resolved_path}")
    return resolved_path


def load_workspace_manifest(workspace_root: Path) -> dict[str, Any]:
    manifest_path = workspace_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"debug workspace 缺少 manifest.json：{manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"debug workspace manifest.json 必须是 JSON 对象：{manifest_path}")
    if "injected_plan_dir" not in manifest:
        raise ValueError(f"debug workspace manifest.json 缺少 injected_plan_dir：{manifest_path}")
    return manifest


def unique_workspace_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{index:02d}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法分配唯一 debug workspace 路径：{path.parent}")
