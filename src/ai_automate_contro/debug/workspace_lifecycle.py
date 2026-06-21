from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.models import DebugWorkspace
from ai_automate_contro.debug.workspace_paths import resolve_plan_path, unique_workspace_path
from ai_automate_contro.support.paths import path_from_text
from ai_automate_contro.support.utils import ensure_directory, make_timestamp, sanitize_name


def create_debug_workspace(
    plan_path: str | Path,
    project_root: str | Path,
    *,
    name: str | None = None,
) -> DebugWorkspace:
    resolved_plan_path = resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent
    workspace_name = f"{make_timestamp()}-{sanitize_name(name or package_dir.name + '-debug')}"
    debug_root = (package_dir / "output" / "debug").resolve()
    workspace_root = unique_workspace_path(debug_root / workspace_name)

    source_copy_dir = workspace_root / "source-copy"
    injected_plan_dir = workspace_root / "injected-plan"
    ensure_directory(workspace_root)
    _copy_plan_package(package_dir, source_copy_dir)
    _copy_plan_package(package_dir, injected_plan_dir)

    notes_path = workspace_root / "notes.md"
    report_path = workspace_root / "report.md"
    patch_path = workspace_root / "patch.diff"
    manifest_path = workspace_root / "manifest.json"

    notes_path.write_text(
        "\n".join(
            [
                "# Debug Notes",
                "",
                f"- Created at: {datetime.now().isoformat(timespec='seconds')}",
                f"- Project root: {path_from_text(project_root).resolve()}",
                f"- Original plan: {resolved_plan_path}",
                f"- Source copy: {source_copy_dir}",
                f"- Injected plan: {injected_plan_dir}",
                "",
                "Use `injected-plan/` for diagnostic prints, screenshots, HTML captures, variable snapshots, and manual confirmations.",
                "Apply only the final minimal fix back to the original plan package after user confirmation.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        "\n".join(
            [
                "# Debug Report",
                "",
                "## Symptom",
                "",
                "## Investigation",
                "",
                "## Root Cause",
                "",
                "## Patch",
                "",
                "## Verification",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch_path.write_text("", encoding="utf-8")

    workspace = DebugWorkspace(
        name=workspace_root.name,
        root=workspace_root,
        plan_path=resolved_plan_path,
        package_dir=package_dir,
        source_copy_dir=source_copy_dir,
        injected_plan_dir=injected_plan_dir,
        notes_path=notes_path,
        report_path=report_path,
        patch_path=patch_path,
        manifest_path=manifest_path,
    )
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                **workspace.to_dict(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "contract": {
                    "source_copy": "Read-only snapshot of the original plan package without output/.",
                    "injected_plan": "Diagnostic copy where debug utilities may add print/capture/write/manual_confirm steps.",
                    "final_patch": "Only patch.diff should describe changes intended for the original plan package.",
                },
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")
    return workspace


def list_debug_workspaces(plan_path: str | Path) -> list[dict[str, Any]]:
    resolved_plan_path = resolve_plan_path(plan_path)
    debug_root = resolved_plan_path.parent / "output" / "debug"
    if not debug_root.exists():
        return []
    workspaces: list[dict[str, Any]] = []
    for child in debug_root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)
        else:
            manifest = {"name": child.name, "root": str(child.resolve())}
        workspaces.append(manifest)
    return sorted(workspaces, key=lambda item: str(item.get("name", "")).lower(), reverse=True)


def find_debug_workspace(plan_path: str | Path, name: str | None = None) -> dict[str, Any]:
    workspaces = list_debug_workspaces(plan_path)
    if not workspaces:
        raise FileNotFoundError("当前 plan 没有调试工作区。")
    if not name:
        return workspaces[0]
    for workspace in workspaces:
        workspace_name = str(workspace.get("name", ""))
        workspace_root = str(workspace.get("root", ""))
        if workspace_name == name or workspace_root == name or workspace_name.endswith(name):
            return workspace
    raise FileNotFoundError(f"调试工作区不存在：{name}")


def _copy_plan_package(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=_ignore_plan_runtime_files,
    )


def _ignore_plan_runtime_files(_: str, names: list[str]) -> set[str]:
    ignored = {"output", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    return {name for name in names if name in ignored or name.endswith(".pyc") or name.endswith(".pyo")}
