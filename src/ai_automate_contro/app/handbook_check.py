from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ai_automate_contro.app.runtime_config import handbook_path_for_project


EXPECTED_ACTION_DIRS = {"browser", "common", "desktop"}

OLD_ACTION_PATH_RE = re.compile(
    r"handbook/actions/(?!browser/|common/|desktop/|README\.md|<action>\.md)([^\s)`'\"]+)"
)
OLD_MARKDOWN_ACTION_LINK_RE = re.compile(
    r"\]\((?:\./|\.\./)?actions/(?!browser/|common/|desktop/|README\.md)([^)]+)\)"
)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s+(\S+)")
EXTERNAL_LINK_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
DEV_NOISE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("source_path", re.compile(r"src[/\\]ai_automate_contro")),
    ("test_plan_path", re.compile(r"\btest-plans\b")),
    ("python_main_command", re.compile(r"python\s+\.(?:\\|/)main\.py")),
    ("python_cplan_command", re.compile(r"python\s+\.(?:\\|/)cplan\.py")),
    ("self_check_command", re.compile(r"\bself-check\b")),
    ("pytest_command", re.compile(r"\bpytest\b|python\s+-m\s+pytest")),
    ("typecheck_command", re.compile(r"\b(?:ruff|mypy|coverage run)\b")),
    ("git_workflow", re.compile(r"\bgit\s+(?:add|commit|status|push)\b")),
    ("local_state_path", re.compile(r"\.keygen")),
    ("development_note", re.compile(r"回归|自检|内部架构|开发规范|提交前|变更分组|测试环境")),
)


def self_check_handbook_hygiene(project_root: str | Path) -> dict[str, Any]:
    handbook_path = handbook_path_for_project(project_root)
    checks = [
        _check_action_dirs(handbook_path),
        _check_old_action_paths(handbook_path),
        _check_markdown_links(handbook_path),
        _check_development_noise(handbook_path),
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "check": "handbook_hygiene",
        "handbook_path": str(handbook_path),
        "checks": checks,
    }


def _check_action_dirs(handbook_path: Path) -> dict[str, Any]:
    actions_path = handbook_path / "actions"
    existing = {
        path.name
        for path in actions_path.iterdir()
        if path.is_dir()
    } if actions_path.exists() else set()
    missing = sorted(EXPECTED_ACTION_DIRS - existing)
    unexpected = sorted(existing - EXPECTED_ACTION_DIRS)
    legacy_desktop_actions = handbook_path / "desktop" / "actions"
    issues = []
    for name in missing:
        issues.append(_issue("missing_action_dir", actions_path / name, 0, f"缺少 action 分类目录：{name}"))
    for name in unexpected:
        issues.append(_issue("unexpected_action_dir", actions_path / name, 0, f"handbook/actions 只能保留 browser/common/desktop：{name}"))
    if legacy_desktop_actions.exists():
        issues.append(_issue("legacy_desktop_actions_dir", legacy_desktop_actions, 0, "旧 desktop/actions 目录不应作为 AI 手册入口"))
    return {
        "name": "handbook_action_dirs_are_isolated",
        "ok": not issues,
        "expected": sorted(EXPECTED_ACTION_DIRS),
        "existing": sorted(existing),
        "issues": issues,
    }


def _check_old_action_paths(handbook_path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for path in _markdown_files(handbook_path):
        for line_number, line in _iter_lines(path):
            if "handbook/actions/<action>.md" in line:
                continue
            if OLD_ACTION_PATH_RE.search(line) or OLD_MARKDOWN_ACTION_LINK_RE.search(line):
                issues.append(_issue("old_action_path", path, line_number, line.strip()))
    return {
        "name": "handbook_has_no_old_flat_action_paths",
        "ok": not issues,
        "issues": issues,
    }


def _check_markdown_links(handbook_path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    resolved_handbook = handbook_path.resolve()
    for path in _markdown_files(handbook_path):
        in_fence = False
        for line_number, line in _iter_lines(path):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for target in _extract_link_targets(line):
                if _should_skip_link_target(target):
                    continue
                target_path = re.split(r"[?#]", target, maxsplit=1)[0]
                if not target_path:
                    continue
                resolved_target = (path.parent / target_path).resolve()
                if not _is_relative_to(resolved_target, resolved_handbook):
                    issues.append(_issue("outside_handbook_link", path, line_number, target))
                elif not resolved_target.exists():
                    issues.append(_issue("broken_markdown_link", path, line_number, target))
    return {
        "name": "handbook_markdown_links_are_valid",
        "ok": not issues,
        "issues": issues,
    }


def _check_development_noise(handbook_path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for path in _markdown_files(handbook_path):
        for line_number, line in _iter_lines(path):
            for rule, pattern in DEV_NOISE_PATTERNS:
                if pattern.search(line):
                    issues.append(_issue(rule, path, line_number, line.strip()))
                    break
    return {
        "name": "handbook_has_no_development_noise",
        "ok": not issues,
        "issues": issues,
    }


def _markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def _iter_lines(path: Path) -> list[tuple[int, str]]:
    return [
        (index, line)
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1)
    ]


def _extract_link_targets(line: str) -> list[str]:
    plain_line = _strip_inline_code(line)
    targets = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(plain_line)]
    reference_match = REFERENCE_LINK_RE.match(plain_line)
    if reference_match:
        targets.append(reference_match.group(1))
    return [_link_target(target) for target in targets]


def _strip_inline_code(line: str) -> str:
    result: list[str] = []
    in_code = False
    for char in line:
        if char == "`":
            in_code = not in_code
            result.append(" ")
        elif in_code:
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        title_match = re.search(r"\s+['\"]", target)
        if title_match:
            target = target[: title_match.start()]
    return unquote(target.strip())


def _should_skip_link_target(target: str) -> bool:
    return (
        not target
        or target.startswith("#")
        or target.startswith("//")
        or EXTERNAL_LINK_RE.match(target) is not None
        or "{{" in target
        or "<" in target
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _issue(rule: str, path: Path, line: int, text: str) -> dict[str, Any]:
    return {
        "rule": rule,
        "path": str(path),
        "line": line,
        "text": text[:500],
    }
