from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_IGNORE_PATTERNS = {
    ".keygen/",
    "plans/**/output/",
    "test-plans/**/output/",
    "plans/**/profiles/",
    "test-plans/**/profiles/",
    "*.log",
    "__pycache__/",
    "*.py[cod]",
    ".env",
    ".env.*",
    "config/",
    "local/",
    "*.local.json",
    "*.secret.json",
    "*.secrets.json",
}

TRACKED_LOCAL_PATTERNS = (
    ".keygen/*",
    "plans/*/output/*",
    "plans/**/output/*",
    "test-plans/*/output/*",
    "test-plans/**/output/*",
    "plans/*/profiles/*",
    "plans/**/profiles/*",
    "test-plans/*/profiles/*",
    "test-plans/**/profiles/*",
    "output/*",
    "*.log",
    "*.pyc",
    "*.pyo",
    "*/__pycache__/*",
    "**/__pycache__/*",
    ".env",
    ".env.*",
    "config/*",
    "local/*",
    "*.local.json",
    "*.secret.json",
    "*.secrets.json",
    "storage-state*.json",
    "downloads/*",
)

IGNORE_PROBE_PATHS = (
    ".keygen/workspace-clean-probe.log",
    "plans/workspace-clean-probe/output/result.json",
    "test-plans/workspace-clean-probe/output/result.json",
    "plans/workspace-clean-probe/profiles/browser/Default/Cookies",
    "test-plans/workspace-clean-probe/profiles/browser/Default/Cookies",
    "debug.log",
    "__pycache__/probe.pyc",
    ".env",
    "config/local.json",
    "local/database-services.json",
)


def self_check_workspace_clean(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    git_check = _run_git(root, "rev-parse", "--show-toplevel")
    if git_check["returncode"] != 0:
        return {
            "ok": False,
            "check": "workspace_clean",
            "project_root": str(root),
            "checks": [
                {
                    "name": "git_repository",
                    "ok": False,
                    "detail": git_check["stderr"] or git_check["stdout"] or "not a git repository",
                }
            ],
        }

    tracked_files = _git_lines(root, "ls-files")
    tracked_local_artifacts = [
        path for path in tracked_files if _matches_any(path, TRACKED_LOCAL_PATTERNS)
    ]
    missing_ignore_patterns = _missing_ignore_patterns(root)
    untracked_review = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    ignored_preview = _git_lines(root, "status", "--ignored", "--short", ".keygen", "plans", "test-plans")[:50]
    unignored_probe_paths = _unignored_probe_paths(root)
    checks = [
        {
            "name": "required_gitignore_patterns_present",
            "ok": not missing_ignore_patterns,
            "missing": missing_ignore_patterns,
        },
        {
            "name": "ignore_rules_cover_local_artifacts",
            "ok": not unignored_probe_paths,
            "unignored": unignored_probe_paths,
        },
        {
            "name": "no_tracked_local_artifacts",
            "ok": not tracked_local_artifacts,
            "tracked": tracked_local_artifacts[:200],
            "tracked_count": len(tracked_local_artifacts),
        },
        {
            "name": "untracked_source_review",
            "ok": True,
            "untracked_not_ignored": untracked_review[:200],
            "untracked_not_ignored_count": len(untracked_review),
            "detail": "仅提示未跟踪且未被忽略的源码/文档文件；是否提交由维护者决定。",
        },
        {
            "name": "ignored_runtime_outputs_preview",
            "ok": True,
            "preview": ignored_preview,
            "detail": "这些 ignored 条目不会进入常规提交。",
        },
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "check": "workspace_clean",
        "project_root": str(root),
        "checks": checks,
    }


def _missing_ignore_patterns(project_root: Path) -> list[str]:
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return sorted(REQUIRED_IGNORE_PATTERNS)
    lines = {
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return sorted(pattern for pattern in REQUIRED_IGNORE_PATTERNS if pattern not in lines)


def _unignored_probe_paths(project_root: Path) -> list[str]:
    unignored: list[str] = []
    for path in IGNORE_PROBE_PATHS:
        result = _run_git(project_root, "check-ignore", path)
        if result["returncode"] != 0:
            unignored.append(path)
    return unignored


def _git_lines(project_root: Path, *args: str) -> list[str]:
    result = _run_git(project_root, *args)
    if result["returncode"] != 0:
        return []
    return [line.strip() for line in result["stdout"].splitlines() if line.strip()]


def _run_git(project_root: Path, *args: str, input_text: str | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(project_root),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)
