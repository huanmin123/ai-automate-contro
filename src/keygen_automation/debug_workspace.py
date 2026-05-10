from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from keygen_automation.utils import ensure_directory, make_timestamp, sanitize_name


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


def create_debug_workspace(
    plan_path: str | Path,
    project_root: str | Path,
    *,
    name: str | None = None,
) -> DebugWorkspace:
    resolved_plan_path = _resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent
    workspace_name = f"{make_timestamp()}-{sanitize_name(name or package_dir.name + '-debug')}"
    debug_root = (package_dir / "output" / "debug").resolve()
    workspace_root = _unique_workspace_path(debug_root / workspace_name)

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
                f"- Project root: {Path(project_root).resolve()}",
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
                    "injected_plan": "Diagnostic copy where AI/debug tools may add print/capture/write/manual_confirm steps.",
                    "final_patch": "Only patch.diff should describe changes intended for the original plan package.",
                },
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")
    return workspace


def inject_debug_steps(
    workspace: str | Path,
    *,
    presets: list[str],
    message: str | None = None,
    browser: str | None = None,
    page: str | None = None,
    position: str = "end",
    step: int | None = None,
) -> DebugInjectionResult:
    workspace_root = Path(workspace).resolve()
    manifest = _load_workspace_manifest(workspace_root)
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    plan_path = injected_plan_dir / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"Injected plan does not exist: {plan_path}")

    document = _load_plan_document(plan_path)
    steps = document.setdefault("steps", [])
    if not isinstance(steps, list):
        raise ValueError(f"Injected plan steps must be an array: {plan_path}")

    normalized_presets = [_normalize_preset(preset) for preset in presets]
    injected_steps = [
        _build_debug_step(preset, message=message, browser=browser, page=page)
        for preset in normalized_presets
    ]
    backup_path = _backup_plan(plan_path)
    if position == "start":
        steps[0:0] = injected_steps
    elif position == "end":
        steps.extend(injected_steps)
    elif position in {"before_step", "after_step"}:
        if step is None or step < 1:
            raise ValueError("step must be a 1-based positive integer when position is before_step or after_step.")
        if step > len(steps):
            raise ValueError(f"step {step} is outside the injected plan step range 1..{len(steps)}.")
        insertion_index = step - 1 if position == "before_step" else step
        steps[insertion_index:insertion_index] = injected_steps
    else:
        raise ValueError("position must be 'start', 'end', 'before_step', or 'after_step'.")
    _write_plan_document(plan_path, document)
    _append_injection_note(workspace_root, injected_steps, position=position, step=step)
    return DebugInjectionResult(
        workspace_root=workspace_root,
        plan_path=plan_path,
        injected_steps=injected_steps,
        backup_path=backup_path,
    )


def generate_debug_patch(workspace: str | Path) -> DebugPatchResult:
    workspace_root = Path(workspace).resolve()
    manifest = _load_workspace_manifest(workspace_root)
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    package_dir = Path(manifest["package_dir"]).resolve()
    patch_path = Path(manifest["patch_path"]).resolve()

    changed_files = _collect_changed_files(source_copy_dir, injected_plan_dir)
    patch_text_parts: list[str] = []
    for relative_path in changed_files:
        original_path = source_copy_dir / relative_path
        modified_path = injected_plan_dir / relative_path
        patch_text_parts.append(
            _git_no_index_diff(
                original_path=original_path,
                modified_path=modified_path,
                original_label=f"a/{relative_path}",
                modified_label=f"b/{relative_path}",
                cwd=package_dir,
            )
        )

    patch_path.write_text("".join(patch_text_parts), encoding="utf-8", newline="\n")
    _append_patch_note(workspace_root, changed_files)
    return DebugPatchResult(
        workspace_root=workspace_root,
        patch_path=patch_path,
        changed_files=changed_files,
        applied=False,
    )


def apply_debug_patch(workspace: str | Path, *, yes: bool = False) -> DebugPatchResult:
    if not yes:
        raise ValueError("Applying a debug patch requires explicit confirmation.")
    workspace_root = Path(workspace).resolve()
    manifest = _load_workspace_manifest(workspace_root)
    package_dir = Path(manifest["package_dir"]).resolve()
    patch_path = Path(manifest["patch_path"]).resolve()
    if not patch_path.exists() or patch_path.stat().st_size == 0:
        generate_debug_patch(workspace_root)
    patch_text = patch_path.read_text(encoding="utf-8")
    if not patch_text.strip():
        return DebugPatchResult(
            workspace_root=workspace_root,
            patch_path=patch_path,
            changed_files=[],
            applied=True,
        )

    _run_git_apply(package_dir, patch_path, check_only=True)
    backup_dir = _backup_original_files_before_patch(workspace_root, package_dir, patch_text)
    _run_git_apply(package_dir, patch_path, check_only=False)
    changed_files = _changed_files_from_patch(patch_text)
    _append_apply_note(workspace_root, changed_files, backup_dir=backup_dir)
    return DebugPatchResult(
        workspace_root=workspace_root,
        patch_path=patch_path,
        changed_files=changed_files,
        applied=True,
    )


def list_debug_workspaces(plan_path: str | Path) -> list[dict[str, Any]]:
    resolved_plan_path = _resolve_plan_path(plan_path)
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
        raise FileNotFoundError("No debug workspace found for current plan.")
    if not name:
        return workspaces[0]
    for workspace in workspaces:
        workspace_name = str(workspace.get("name", ""))
        workspace_root = str(workspace.get("root", ""))
        if workspace_name == name or workspace_root == name or workspace_name.endswith(name):
            return workspace
    raise FileNotFoundError(f"Debug workspace not found: {name}")


def _resolve_plan_path(plan_path: str | Path) -> Path:
    resolved_path = Path(plan_path).resolve()
    if resolved_path.is_dir():
        resolved_path = resolved_path / "plan.json"
    if not resolved_path.exists():
        raise FileNotFoundError(f"Plan file does not exist: {resolved_path}")
    if resolved_path.name != "plan.json":
        raise ValueError(f"Debug workspace can only be created for a package entry plan.json: {resolved_path}")
    return resolved_path


def _load_workspace_manifest(workspace_root: Path) -> dict[str, Any]:
    manifest_path = workspace_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Debug workspace manifest not found: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"Debug workspace manifest must be a JSON object: {manifest_path}")
    if "injected_plan_dir" not in manifest:
        raise ValueError(f"Debug workspace manifest missing injected_plan_dir: {manifest_path}")
    return manifest


def _load_plan_document(plan_path: Path) -> dict[str, Any]:
    with plan_path.open("r", encoding="utf-8") as file:
        document = json.load(file)
    if not isinstance(document, dict):
        raise ValueError(f"Plan document must be a JSON object: {plan_path}")
    return document


def _write_plan_document(plan_path: Path, document: dict[str, Any]) -> None:
    with plan_path.open("w", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _backup_plan(plan_path: Path) -> Path:
    backup_dir = ensure_directory(plan_path.parent / ".debug-backups")
    backup_path = backup_dir / f"{make_timestamp()}-plan.json"
    shutil.copy2(plan_path, backup_path)
    return backup_path


def _normalize_preset(preset: str) -> str:
    value = preset.strip().lower()
    aliases = {
        "var": "variables",
        "vars": "variables",
        "variable": "variables",
        "confirm": "manual_confirm",
        "manual": "manual_confirm",
        "screen": "screenshot",
        "capture": "screenshot",
    }
    value = aliases.get(value, value)
    supported = {"print", "variables", "manual_confirm", "screenshot", "html"}
    if value not in supported:
        raise ValueError(f"Unsupported debug injection preset: {preset}")
    return value


def _build_debug_step(
    preset: str,
    *,
    message: str | None,
    browser: str | None,
    page: str | None,
) -> dict[str, Any]:
    if preset == "print":
        return {
            "action": "print",
            "message": message or "[debug] checkpoint reached",
        }
    if preset == "variables":
        return {
            "action": "write",
            "type": "variables",
            "path": f"debug/variables-{make_timestamp()}.json",
        }
    if preset == "manual_confirm":
        return {
            "action": "manual_confirm",
            "prompt": message or "Debug checkpoint reached. Finish manual checks, then continue.",
        }
    if preset == "screenshot":
        _require_browser_for_preset(preset, browser)
        step: dict[str, Any] = {
            "action": "capture",
            "type": "screenshot",
            "browser": browser,
            "path": f"debug/screenshots/screenshot-{make_timestamp()}.png",
            "full_page": True,
        }
        if page:
            step["page"] = page
        return step
    if preset == "html":
        _require_browser_for_preset(preset, browser)
        step = {
            "action": "capture",
            "type": "html",
            "browser": browser,
            "path": f"debug/html/page-{make_timestamp()}.html",
        }
        if page:
            step["page"] = page
        return step
    raise ValueError(f"Unsupported debug injection preset: {preset}")


def _require_browser_for_preset(preset: str, browser: str | None) -> None:
    if not browser:
        raise ValueError(f"Debug preset '{preset}' requires --browser <name>.")


def _append_injection_note(
    workspace_root: Path,
    injected_steps: list[dict[str, Any]],
    *,
    position: str,
    step: int | None,
) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Injection\n\n")
        file.write(f"- Time: {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"- Position: {position}\n")
        if step is not None:
            file.write(f"- Anchor step: {step}\n")
        file.write("- Steps:\n\n")
        file.write("```json\n")
        json.dump(injected_steps, file, ensure_ascii=False, indent=2)
        file.write("\n```\n")


def _collect_changed_files(source_copy_dir: Path, injected_plan_dir: Path) -> list[str]:
    source_files = _collect_comparable_files(source_copy_dir)
    injected_files = _collect_comparable_files(injected_plan_dir)
    relative_paths = sorted(source_files | injected_files)
    changed_files: list[str] = []
    for relative_path in relative_paths:
        original_path = source_copy_dir / relative_path
        modified_path = injected_plan_dir / relative_path
        if not original_path.exists() or not modified_path.exists():
            changed_files.append(relative_path)
            continue
        if original_path.read_bytes() != modified_path.read_bytes():
            changed_files.append(relative_path)
    return changed_files


def _collect_comparable_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root)
        if _is_ignored_debug_relative_path(relative_path):
            continue
        files.add(relative_path.as_posix())
    return files


def _is_ignored_debug_relative_path(relative_path: Path) -> bool:
    ignored_parts = {"output", "__pycache__", ".debug-backups", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    if any(part in ignored_parts for part in relative_path.parts):
        return True
    name = relative_path.name
    return name.endswith(".pyc") or name.endswith(".pyo")


def _git_no_index_diff(
    *,
    original_path: Path,
    modified_path: Path,
    original_label: str,
    modified_label: str,
    cwd: Path,
) -> str:
    args = [
        "git",
        "diff",
        "--no-index",
        "--",
        str(original_path),
        str(modified_path),
    ]
    completed = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    if completed.returncode not in {0, 1}:
        raise RuntimeError(completed.stderr.strip() or "git diff failed")
    diff_text = completed.stdout
    if not diff_text:
        return ""
    diff_text = _normalize_diff_headers(diff_text, original_label=original_label, modified_label=modified_label)
    return diff_text


def _normalize_diff_headers(diff_text: str, *, original_label: str, modified_label: str) -> str:
    lines = diff_text.splitlines()
    normalized: list[str] = []
    for line in lines:
        if line.startswith("diff --git "):
            normalized.append(f"diff --git {original_label} {modified_label}")
            continue
        if line.startswith("--- "):
            normalized.append(f"--- {original_label}")
            continue
        if line.startswith("+++ "):
            normalized.append(f"+++ {modified_label}")
            continue
        normalized.append(line)
    return "\n".join(normalized) + "\n"


def _run_git_apply(package_dir: Path, patch_path: Path, *, check_only: bool) -> None:
    repo_root = _git_repo_root(package_dir)
    package_prefix = package_dir.resolve().relative_to(repo_root).as_posix()
    args = ["git", "apply"]
    if check_only:
        args.append("--check")
    if package_prefix:
        args.append(f"--directory={package_prefix}")
    args.append(str(patch_path))
    completed = subprocess.run(args, cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git apply failed"
        raise RuntimeError(detail)


def _git_repo_root(path: Path) -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(path),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to find git repository root.")
    return Path(completed.stdout.strip()).resolve()


def _backup_original_files_before_patch(workspace_root: Path, package_dir: Path, patch_text: str) -> Path:
    backup_dir = ensure_directory(workspace_root / "original-backups" / make_timestamp())
    for relative_path in _changed_files_from_patch(patch_text):
        source_path = package_dir / relative_path
        target_path = backup_dir / relative_path
        if source_path.exists() and source_path.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
    return backup_dir


def _changed_files_from_patch(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if not line.startswith("+++ b/"):
            continue
        relative_path = line.removeprefix("+++ b/")
        if relative_path != "/dev/null":
            files.append(relative_path)
    return sorted(dict.fromkeys(files))


def _append_patch_note(workspace_root: Path, changed_files: list[str]) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Patch Generated\n\n")
        file.write(f"- Time: {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"- Changed files: {', '.join(changed_files) if changed_files else '<none>'}\n")


def _append_apply_note(workspace_root: Path, changed_files: list[str], *, backup_dir: Path) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Patch Applied\n\n")
        file.write(f"- Time: {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"- Changed files: {', '.join(changed_files) if changed_files else '<none>'}\n")
        file.write(f"- Original backup: {backup_dir}\n")


def _copy_plan_package(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=_ignore_plan_runtime_files,
    )


def _ignore_plan_runtime_files(_: str, names: list[str]) -> set[str]:
    ignored = {"output", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    return {name for name in names if name in ignored or name.endswith(".pyc") or name.endswith(".pyo")}


def _unique_workspace_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{index:02d}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to allocate a unique debug workspace path under: {path.parent}")
