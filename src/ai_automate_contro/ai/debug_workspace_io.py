from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


def read_debug_manifest(workspace_root: Path) -> dict[str, Any]:
    manifest_path = workspace_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"调试工作区缺少 manifest.json：{manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"调试工作区 manifest.json 必须是 JSON 对象：{manifest_path}")
    required = ("source_copy_dir", "injected_plan_dir", "notes_path", "report_path", "patch_path")
    for key in required:
        if key not in manifest:
            raise ValueError(f"调试工作区 manifest.json 缺少 {key}：{manifest_path}")
    return manifest


def read_debug_plan_tree(
    root: Path,
    *,
    read_json_file_overview: Callable[[Path, Path], dict[str, Any]],
    read_plan_file_overview: Callable[[Path, Path], dict[str, Any]],
    read_package_docs: Callable[[Path], list[dict[str, Any]]],
    read_sub_plans: Callable[[Path], list[dict[str, Any]]],
    list_package_files: Callable[[Path, Path], list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "root": str(root),
        "plan": read_plan_file_overview(root / "plan.json", root),
        "config": read_json_file_overview(root / "config.json", root),
        "docs": read_package_docs(root),
        "sub_plans": read_sub_plans(root),
        "resources": list_package_files(root / "resources", root),
    }


def resolve_debug_write_path(manifest: dict[str, Any], *, root: str, relative_path: str) -> Path:
    normalized_root = root.strip().lower()
    if normalized_root == "notes":
        return Path(manifest["notes_path"]).resolve()
    if normalized_root == "report":
        return Path(manifest["report_path"]).resolve()
    if normalized_root != "injected-plan":
        raise ValueError("root 必须是 injected-plan、notes 或 report。")

    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    raw_path = path_from_text(relative_path)
    if is_absolute_path_text(relative_path):
        raise ValueError("relative_path 必须是相对于 injected-plan/ 的路径。")
    if not raw_path.parts:
        raise ValueError("relative_path 不能为空。")
    if is_forbidden_debug_write_path(raw_path):
        raise ValueError(f"拒绝写入禁止的 debug 路径：{relative_path}")
    if not is_allowed_plan_package_write_path(raw_path):
        raise ValueError(
            "injected-plan 下只允许写入 plan.json、config.json、docs/、resources/ 和 sub-plans/。"
        )
    target_path = (injected_plan_dir / raw_path).resolve()
    if not is_relative_to(target_path, injected_plan_dir):
        raise ValueError("relative_path 必须位于 injected-plan/ 内。")
    return target_path


def is_forbidden_debug_write_path(path: Path) -> bool:
    forbidden_parts = {
        "output",
        "__pycache__",
        ".debug-backups",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    return any(part in forbidden_parts for part in path.parts)


def is_allowed_plan_package_write_path(path: Path) -> bool:
    if len(path.parts) == 1 and path.name in {"plan.json", "config.json"}:
        return True
    if path.parts[0] in {"docs", "resources", "sub-plans"}:
        return True
    return False


def read_text_preserve_newlines(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as file:
        return file.read()


def write_text_preserve_newlines(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(content)


def debug_relative_path(manifest: dict[str, Any], path: Path) -> str:
    workspace_root = Path(manifest["root"]).resolve() if manifest.get("root") else path.parent
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path)


def reset_injected_file_to_source(manifest: dict[str, Any], relative_path: str) -> None:
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    raw_path = path_from_text(relative_path)
    if is_absolute_path_text(relative_path) or is_forbidden_debug_write_path(raw_path):
        raise ValueError(f"拒绝重置禁止的 debug 路径：{relative_path}")
    source_path = (source_copy_dir / raw_path).resolve()
    target_path = (injected_plan_dir / raw_path).resolve()
    if not is_relative_to(source_path, source_copy_dir) or not is_relative_to(target_path, injected_plan_dir):
        raise ValueError("debug 重置路径必须位于 source-copy/ 和 injected-plan/ 内。")
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"源 debug 文件不存在：{source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
