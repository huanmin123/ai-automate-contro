from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DebugWorkspace:
    name: str
    root: Path
    plan_path: Path
    package_dir: Path
    source_copy_dir: Path
    injected_plan_dir: Path
    notes_path: Path
    report_path: Path
    patch_path: Path
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "plan_path": str(self.plan_path),
            "package_dir": str(self.package_dir),
            "source_copy_dir": str(self.source_copy_dir),
            "injected_plan_dir": str(self.injected_plan_dir),
            "notes_path": str(self.notes_path),
            "report_path": str(self.report_path),
            "patch_path": str(self.patch_path),
            "manifest_path": str(self.manifest_path),
        }


@dataclass(frozen=True)
class DebugInjectionResult:
    workspace_root: Path
    plan_path: Path
    injected_steps: list[dict[str, Any]]
    backup_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "plan_path": str(self.plan_path),
            "injected_steps": self.injected_steps,
            "backup_path": str(self.backup_path),
        }


@dataclass(frozen=True)
class DebugPatchResult:
    workspace_root: Path
    patch_path: Path
    changed_files: list[str]
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "patch_path": str(self.patch_path),
            "changed_files": self.changed_files,
            "applied": self.applied,
        }
