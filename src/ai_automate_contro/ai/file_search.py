from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ai_automate_contro.app.errors import UserFacingError
from ai_automate_contro.support.paths import path_from_text


MAX_GREP_MATCHES = 100
MAX_GREP_CONTEXT_LINES = 5
MAX_GREP_LINE_CHARS = 1_000
MAX_FILE_SLICE_LINES = 200
MAX_FILE_SLICE_BYTES = 64_000


def ripgrep_install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ripgrep"
    if system == "Linux":
        return "使用系统包管理器安装 ripgrep，例如 sudo apt install ripgrep 或 sudo dnf install ripgrep"
    return "winget install --id BurntSushi.ripgrep.MSVC -e"


RIPGREP_INSTALL_MESSAGE = (
    "AI 终端文本搜索必须安装 ripgrep (rg)。"
    "本项目不使用系统内置搜索兜底。"
    f"安装建议：{ripgrep_install_hint()}。"
    "安装后执行 rg --version 验证。"
    "如果希望助手帮你全局安装，请先明确确认。"
)


def grep_project_text_tool(
    project_root: str | Path,
    *,
    pattern: str,
    root_path: str | Path = ".",
    literal: bool = True,
    include_output: bool = False,
    file_glob: str = "",
    context_lines: int = 0,
    max_matches: int = 50,
) -> dict[str, Any]:
    if not pattern:
        raise ValueError("grep_project_text 需要非空 pattern。")
    assert_ripgrep_available()
    project_root_path = Path(project_root).resolve()
    search_root = resolve_project_path(project_root_path, root_path)
    resolved_context_lines = clamp_int(context_lines, minimum=0, maximum=MAX_GREP_CONTEXT_LINES)
    resolved_max_matches = clamp_int(max_matches, minimum=1, maximum=MAX_GREP_MATCHES)

    args = [
        "rg",
        "--json",
        "--color",
        "never",
        "--max-filesize",
        "1M",
        "--max-count",
        str(resolved_max_matches),
    ]
    if literal:
        args.append("-F")
    if resolved_context_lines:
        args.extend(["--context", str(resolved_context_lines)])
    for glob in default_excluded_globs(include_output=include_output):
        args.extend(["--glob", glob])
    if file_glob:
        args.extend(["--glob", file_glob])
    args.extend(["--", pattern, str(search_root)])

    try:
        completed = subprocess.run(
            args,
            cwd=str(project_root_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except FileNotFoundError as error:
        raise RuntimeError(RIPGREP_INSTALL_MESSAGE) from error
    if completed.returncode not in {0, 1}:
        raise RuntimeError(completed.stderr.strip() or "rg 执行失败。")

    matches: list[dict[str, Any]] = []
    match_count = 0
    truncated = False
    for raw_line in completed.stdout.splitlines():
        if not raw_line:
            continue
        event = json.loads(raw_line)
        event_type = event.get("type")
        if event_type not in {"match", "context"}:
            continue
        data = event.get("data", {})
        path_text = str(data.get("path", {}).get("text", ""))
        path = path_from_text(path_text).resolve()
        line_text = str(data.get("lines", {}).get("text", "")).rstrip("\r\n")
        entry = {
            "type": event_type,
            "path": str(path),
            "relative_path": relative_to_project(project_root_path, path),
            "line": data.get("line_number"),
            "text": truncate_line(line_text),
        }
        if event_type == "match":
            match_count += 1
            entry["submatches"] = data.get("submatches", [])
        matches.append(entry)
        if match_count >= resolved_max_matches:
            truncated = True
            break

    return {
        "ok": True,
        "tool": "rg",
        "root": str(search_root),
        "pattern": pattern,
        "literal": literal,
        "include_output": include_output,
        "file_glob": file_glob,
        "context_lines": resolved_context_lines,
        "requested_max_matches": max_matches,
        "max_matches": MAX_GREP_MATCHES,
        "match_count": match_count,
        "truncated": truncated,
        "matches": matches,
    }


def assert_ripgrep_available() -> None:
    if shutil.which("rg") is None:
        raise UserFacingError(
            "缺少 ripgrep：AI 终端文本搜索需要 rg。",
            fix=(
                "本项目不使用系统内置搜索兜底。\n"
                f"安装建议：{ripgrep_install_hint()}\n"
                "安装后重新打开终端，再执行：rg --version"
            ),
            verify=["rg --version"],
        )


def read_project_file_slice_tool(
    project_root: str | Path,
    *,
    path: str | Path,
    start_line: int = 1,
    line_count: int = 80,
    max_bytes: int = MAX_FILE_SLICE_BYTES,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    file_path = resolve_project_path(project_root_path, path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"文件不存在：{file_path}")

    resolved_start_line = max(1, int(start_line))
    resolved_line_count = clamp_int(line_count, minimum=1, maximum=MAX_FILE_SLICE_LINES)
    resolved_max_bytes = clamp_int(max_bytes, minimum=1, maximum=MAX_FILE_SLICE_BYTES)
    end_line = resolved_start_line + resolved_line_count - 1

    lines: list[dict[str, Any]] = []
    used_bytes = 0
    truncated = False
    with file_path.open("r", encoding="utf-8", errors="replace") as file:
        for line_number, raw_line in enumerate(file, start=1):
            if line_number < resolved_start_line:
                continue
            if line_number > end_line:
                break
            text = raw_line.rstrip("\r\n")
            encoded = text.encode("utf-8")
            if used_bytes + len(encoded) > resolved_max_bytes:
                remaining = max(0, resolved_max_bytes - used_bytes)
                text = encoded[:remaining].decode("utf-8", errors="ignore")
                truncated = True
            lines.append({"line": line_number, "text": text})
            used_bytes += len(text.encode("utf-8"))
            if truncated:
                break

    return {
        "ok": True,
        "path": str(file_path),
        "relative_path": relative_to_project(project_root_path, file_path),
        "start_line": resolved_start_line,
        "requested_line_count": line_count,
        "line_count": len(lines),
        "max_lines": MAX_FILE_SLICE_LINES,
        "requested_max_bytes": max_bytes,
        "max_bytes": MAX_FILE_SLICE_BYTES,
        "truncated": truncated,
        "lines": lines,
    }


def resolve_project_path(project_root: Path, raw_path: str | Path) -> Path:
    candidate = path_from_text(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    if not is_relative_to(resolved, project_root):
        raise ValueError("路径必须位于项目根目录内。")
    if is_forbidden_read_path(resolved.relative_to(project_root)):
        raise ValueError("拒绝读取或搜索缓存、checkpoint、git、pyc 或 egg-info 路径。")
    return resolved


def default_excluded_globs(*, include_output: bool) -> list[str]:
    globs = [
        "!**/.git/**",
        "!**/.keygen/**",
        "!**/__pycache__/**",
        "!**/.pytest_cache/**",
        "!**/.mypy_cache/**",
        "!**/.ruff_cache/**",
        "!**/*.pyc",
        "!**/*.pyo",
        "!**/*.egg-info/**",
    ]
    if not include_output:
        globs.append("!**/output/**")
    return globs


def is_forbidden_read_path(path: Path) -> bool:
    forbidden_parts = {
        ".git",
        ".keygen",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    if any(part in forbidden_parts for part in path.parts):
        return True
    return path.name.endswith(".pyc") or path.name.endswith(".pyo") or ".egg-info" in path.parts


def relative_to_project(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path)


def truncate_line(text: str) -> str:
    if len(text) <= MAX_GREP_LINE_CHARS:
        return text
    return text[:MAX_GREP_LINE_CHARS] + "..."


def clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
