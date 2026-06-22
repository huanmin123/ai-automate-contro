from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from ai_automate_contro.ai.file_search import (
    MAX_FILE_SLICE_BYTES,
    MAX_FILE_SLICE_LINES,
    MAX_GREP_LINE_CHARS,
    MAX_GREP_MATCHES,
    assert_ripgrep_available,
    clamp_int,
    truncate_line,
)
from ai_automate_contro.ai.session_compression import redact_image_data_urls, sanitize_thread_id, session_root
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text
from ai_automate_contro.support.paths import path_from_text


CompressionRecallMode = Literal["list", "summary", "messages", "manifest", "search"]


def read_compression_archive_tool(
    project_root: str | Path,
    *,
    thread_id: str,
    mode: CompressionRecallMode = "summary",
    archive_path: str | Path = "",
    pattern: str = "",
    literal: bool = True,
    start_line: int = 1,
    line_count: int = 80,
    max_bytes: int = MAX_FILE_SLICE_BYTES,
    max_matches: int = 50,
    max_archives: int = 20,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    if not thread_id.strip():
        raise ValueError("read_compression_archive 需要当前 thread_id。")
    thread = sanitize_thread_id(thread_id)
    compressions_root = session_root(root, thread) / "compressions"

    if mode == "list":
        return _list_archives(compressions_root, thread_id=thread, max_archives=max_archives)

    archive_dir = _resolve_archive_dir(root, compressions_root, archive_path)
    if mode == "summary":
        return _read_summary(archive_dir, thread_id=thread, start_line=start_line, line_count=line_count, max_bytes=max_bytes)
    if mode == "messages":
        return _read_messages(archive_dir, thread_id=thread, start_line=start_line, line_count=line_count, max_bytes=max_bytes)
    if mode == "manifest":
        return _read_manifest(archive_dir, thread_id=thread)
    if mode == "search":
        return _search_archive(
            archive_dir,
            thread_id=thread,
            pattern=pattern,
            literal=literal,
            max_matches=max_matches,
        )
    raise ValueError(f"不支持的压缩归档读取模式：{mode}")


def _list_archives(compressions_root: Path, *, thread_id: str, max_archives: int) -> dict[str, Any]:
    archives: list[dict[str, Any]] = []
    if compressions_root.exists():
        limit = clamp_int(max_archives, minimum=1, maximum=100)
        archive_dirs = sorted(
            (path for path in compressions_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
            reverse=True,
        )[:limit]
        for archive_dir in archive_dirs:
            manifest = _load_manifest(archive_dir)
            summary_preview = _read_text_preview(archive_dir / "summary.md", max_chars=500)
            archives.append(
                {
                    "archive_dir": str(archive_dir),
                    "messages_path": str(archive_dir / "messages.jsonl"),
                    "summary_path": str(archive_dir / "summary.md"),
                    "manifest_path": str(archive_dir / "manifest.json"),
                    "created_at": manifest.get("created_at"),
                    "reason": manifest.get("reason"),
                    "message_count": manifest.get("message_count"),
                    "token_count": manifest.get("token_count"),
                    "summary_preview": summary_preview,
                }
            )
    return {
        "ok": True,
        "tool": "read_compression_archive",
        "mode": "list",
        "thread_id": thread_id,
        "compressions_root": str(compressions_root),
        "archive_count": len(archives),
        "archives": archives,
    }


def _read_summary(
    archive_dir: Path,
    *,
    thread_id: str,
    start_line: int,
    line_count: int,
    max_bytes: int,
) -> dict[str, Any]:
    summary_path = archive_dir / "summary.md"
    lines, truncated = _read_text_lines(summary_path, start_line=start_line, line_count=line_count, max_bytes=max_bytes)
    return {
        "ok": True,
        "tool": "read_compression_archive",
        "mode": "summary",
        "thread_id": thread_id,
        "archive_dir": str(archive_dir),
        "summary_path": str(summary_path),
        "start_line": max(1, int(start_line)),
        "line_count": len(lines),
        "truncated": truncated,
        "lines": lines,
    }


def _read_messages(
    archive_dir: Path,
    *,
    thread_id: str,
    start_line: int,
    line_count: int,
    max_bytes: int,
) -> dict[str, Any]:
    messages_path = archive_dir / "messages.jsonl"
    raw_lines, truncated = _read_text_lines(
        messages_path,
        start_line=start_line,
        line_count=line_count,
        max_bytes=max_bytes,
    )
    messages = [_message_entry(line["line"], line["text"]) for line in raw_lines]
    return {
        "ok": True,
        "tool": "read_compression_archive",
        "mode": "messages",
        "thread_id": thread_id,
        "archive_dir": str(archive_dir),
        "messages_path": str(messages_path),
        "start_line": max(1, int(start_line)),
        "line_count": len(messages),
        "truncated": truncated,
        "messages": messages,
    }


def _read_manifest(archive_dir: Path, *, thread_id: str) -> dict[str, Any]:
    manifest_path = archive_dir / "manifest.json"
    manifest = _load_manifest(archive_dir)
    if not manifest and not manifest_path.exists():
        raise FileNotFoundError(f"压缩归档 manifest 不存在：{manifest_path}")
    return {
        "ok": True,
        "tool": "read_compression_archive",
        "mode": "manifest",
        "thread_id": thread_id,
        "archive_dir": str(archive_dir),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def _search_archive(
    archive_dir: Path,
    *,
    thread_id: str,
    pattern: str,
    literal: bool,
    max_matches: int,
) -> dict[str, Any]:
    if not pattern:
        raise ValueError("search 模式需要非空 pattern。")
    assert_ripgrep_available()
    resolved_max_matches = clamp_int(max_matches, minimum=1, maximum=MAX_GREP_MATCHES)
    files = [
        path
        for path in (archive_dir / "summary.md", archive_dir / "manifest.json", archive_dir / "messages.jsonl")
        if path.exists() and path.is_file()
    ]
    if not files:
        raise FileNotFoundError(f"压缩归档没有可搜索文件：{archive_dir}")

    args = [
        "rg",
        "--json",
        "--color",
        "never",
        "--max-count",
        str(resolved_max_matches),
    ]
    if literal:
        args.append("-F")
    args.extend(["--", pattern])
    args.extend(str(path) for path in files)

    completed = subprocess.run(
        args,
        cwd=str(archive_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(completed.stderr.strip() or "rg 搜索压缩归档失败。")

    matches: list[dict[str, Any]] = []
    match_count = 0
    truncated = False
    for raw_line in completed.stdout.splitlines():
        if not raw_line:
            continue
        event = json.loads(raw_line)
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        path = path_from_text(str(data.get("path", {}).get("text", ""))).resolve()
        text = str(data.get("lines", {}).get("text", "")).rstrip("\r\n")
        matches.append(
            {
                "path": str(path),
                "file": path.name,
                "line": data.get("line_number"),
                "text": truncate_line(_redact_inline_image_data_urls(text)),
                "submatches": data.get("submatches", []),
            }
        )
        match_count += 1
        if match_count >= resolved_max_matches:
            truncated = True
            break

    return {
        "ok": True,
        "tool": "read_compression_archive",
        "mode": "search",
        "thread_id": thread_id,
        "archive_dir": str(archive_dir),
        "pattern": pattern,
        "literal": literal,
        "match_count": match_count,
        "truncated": truncated,
        "matches": matches,
    }


def _resolve_archive_dir(root: Path, compressions_root: Path, archive_path: str | Path) -> Path:
    if archive_path:
        candidate = path_from_text(archive_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        archive_dir = resolved.parent if resolved.name in {"summary.md", "messages.jsonl", "manifest.json"} else resolved
    else:
        archive_dir = _latest_archive_dir(compressions_root)

    archive_dir = archive_dir.resolve()
    if archive_dir.parent != compressions_root.resolve():
        raise ValueError("压缩归档路径必须位于当前线程的 compressions/<archive>/ 下。")
    if not archive_dir.exists() or not archive_dir.is_dir():
        raise FileNotFoundError(f"压缩归档目录不存在：{archive_dir}")
    return archive_dir


def _latest_archive_dir(compressions_root: Path) -> Path:
    if not compressions_root.exists():
        raise FileNotFoundError(f"当前线程没有压缩归档目录：{compressions_root}")
    archive_dirs = sorted(
        (path for path in compressions_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    if not archive_dirs:
        raise FileNotFoundError(f"当前线程没有压缩归档：{compressions_root}")
    return archive_dirs[0]


def _load_manifest(archive_dir: Path) -> dict[str, Any]:
    manifest_path = archive_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _read_text_preview(path: Path, *, max_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def _read_text_lines(
    path: Path,
    *,
    start_line: int,
    line_count: int,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], bool]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"压缩归档文件不存在：{path}")
    resolved_start_line = max(1, int(start_line))
    resolved_line_count = clamp_int(line_count, minimum=1, maximum=MAX_FILE_SLICE_LINES)
    resolved_max_bytes = clamp_int(max_bytes, minimum=1, maximum=MAX_FILE_SLICE_BYTES)
    end_line = resolved_start_line + resolved_line_count - 1

    lines: list[dict[str, Any]] = []
    used_bytes = 0
    truncated = False
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line_number, raw_line in enumerate(file, start=1):
            if line_number < resolved_start_line:
                continue
            if line_number > end_line:
                break
            text = _redact_inline_image_data_urls(raw_line.rstrip("\r\n"))
            encoded = text.encode("utf-8")
            if used_bytes + len(encoded) > resolved_max_bytes:
                remaining = max(0, resolved_max_bytes - used_bytes)
                text = encoded[:remaining].decode("utf-8", errors="ignore")
                truncated = True
            lines.append({"line": line_number, "text": text})
            used_bytes += len(text.encode("utf-8"))
            if truncated:
                break
    return lines, truncated


def _message_entry(line_number: int, raw_text: str) -> dict[str, Any]:
    try:
        payload = redact_image_data_urls(json.loads(raw_text))
    except json.JSONDecodeError:
        return {"line": line_number, "role": "unknown", "content": raw_text}

    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    content = data.get("content")
    tool_calls = data.get("tool_calls")
    entry: dict[str, Any] = {
        "line": line_number,
        "role": payload.get("type", "unknown") if isinstance(payload, dict) else "unknown",
        "content": message_content_to_text(content).strip(),
    }
    if isinstance(tool_calls, list) and tool_calls:
        entry["tool_calls"] = [
            call.get("name")
            for call in tool_calls
            if isinstance(call, dict) and isinstance(call.get("name"), str)
        ]
    if not entry["content"]:
        entry["raw_preview"] = truncate_line(json.dumps(payload, ensure_ascii=False, default=str))
    elif len(entry["content"]) > MAX_GREP_LINE_CHARS:
        entry["content"] = entry["content"][:MAX_GREP_LINE_CHARS] + "..."
    return entry


def _redact_inline_image_data_urls(text: str) -> str:
    return text
