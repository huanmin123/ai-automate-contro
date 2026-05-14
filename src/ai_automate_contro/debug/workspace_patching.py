from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ai_automate_contro.debug.models import DebugPatchResult
from ai_automate_contro.debug.workspace_paths import load_workspace_manifest
from ai_automate_contro.support.paths import path_from_text
from ai_automate_contro.support.utils import ensure_directory, make_timestamp


def generate_debug_patch(workspace: str | Path) -> DebugPatchResult:
    workspace_root = path_from_text(workspace).resolve()
    manifest = load_workspace_manifest(workspace_root)
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
                original_path=original_path if original_path.exists() else None,
                modified_path=modified_path if modified_path.exists() else None,
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
        raise ValueError("应用 debug patch 需要显式确认：请加 --yes。")
    workspace_root = path_from_text(workspace).resolve()
    manifest = load_workspace_manifest(workspace_root)
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
    original_path: Path | None,
    modified_path: Path | None,
    original_label: str,
    modified_label: str,
    cwd: Path,
) -> str:
    if original_path is None and modified_path is None:
        return ""
    if original_path is None:
        return _new_file_diff(modified_path, modified_label=modified_label)
    if modified_path is None:
        return _deleted_file_diff(original_path, original_label=original_label, modified_label=modified_label)

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
    return _normalize_diff_headers(diff_text, original_label=original_label, modified_label=modified_label)


def _new_file_diff(path: Path, *, modified_label: str) -> str:
    content = path.read_text(encoding="utf-8", errors="surrogateescape")
    content_lines = content.splitlines()
    lines = [
        f"diff --git a/{modified_label.removeprefix('b/')} {modified_label}",
        "new file mode 100644",
        "index 0000000..0000000",
    ]
    if content:
        lines.extend(
            [
                "--- /dev/null",
                f"+++ {modified_label}",
                f"@@ -0,0 +1,{len(content_lines)} @@",
            ]
        )
        lines.extend(f"+{line}" for line in content_lines)
        if not content.endswith("\n"):
            lines.append("\\ No newline at end of file")
    return "\n".join(lines) + "\n"


def _deleted_file_diff(path: Path, *, original_label: str, modified_label: str) -> str:
    content = path.read_text(encoding="utf-8", errors="surrogateescape")
    content_lines = content.splitlines()
    lines = [
        f"diff --git {original_label} {modified_label}",
        "deleted file mode 100644",
        "index 0000000..0000000",
    ]
    if content:
        lines.extend(
            [
                f"--- {original_label}",
                "+++ /dev/null",
                f"@@ -1,{len(content_lines)} +0,0 @@",
            ]
        )
        lines.extend(f"-{line}" for line in content_lines)
        if not content.endswith("\n"):
            lines.append("\\ No newline at end of file")
    return "\n".join(lines) + "\n"


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
