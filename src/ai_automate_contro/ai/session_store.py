from __future__ import annotations

import json
import tempfile
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ai_automate_contro.ai.image_attachments import IMAGE_ATTACHMENTS_METADATA_KEY
from ai_automate_contro.ai.terminal_message_utils import message_content_to_text


SESSION_LIST_LIMIT_DEFAULT = 20
SESSION_LIST_LIMIT_MAX = 200
PREVIEW_CHARS = 140
SESSION_INDEX_SCHEMA_VERSION = 1
SESSION_INDEX_FILE_NAME = "index.json"
_SESSION_INDEX_LOCK = threading.Lock()

CONTEXT_STATE_KEYS = (
    "current_plan_path",
    "current_debug_workspace",
    "latest_output_dir",
    "latest_compression_archive_dir",
    "latest_compression_messages_path",
    "latest_compression_summary_path",
    "latest_compression_token_count",
    "latest_compression_message_count",
)


@dataclass(frozen=True)
class AITerminalSessionSummary:
    index: int
    thread_id: str
    checkpoint_id: str
    last_timestamp: str
    checkpoint_count: int
    message_count: int
    image_count: int
    latest_user_preview: str
    latest_assistant_preview: str
    context_state: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "thread_id": self.thread_id,
            "checkpoint_id": self.checkpoint_id,
            "last_timestamp": self.last_timestamp,
            "checkpoint_count": self.checkpoint_count,
            "message_count": self.message_count,
            "image_count": self.image_count,
            "latest_user_preview": self.latest_user_preview,
            "latest_assistant_preview": self.latest_assistant_preview,
            "context_state": self.context_state,
        }


def list_ai_terminal_sessions(
    checkpointer: Any,
    *,
    project_root: str | Path | None = None,
    limit: int = SESSION_LIST_LIMIT_DEFAULT,
) -> list[AITerminalSessionSummary]:
    resolved_limit = _clamp_limit(limit)
    if project_root is None:
        return _list_ai_terminal_sessions_from_checkpoints(checkpointer, limit=resolved_limit)

    with _SESSION_INDEX_LOCK:
        indexed_sessions = _read_session_index(project_root)
        checkpoint_sessions = _list_ai_terminal_sessions_from_checkpoints(checkpointer, limit=SESSION_LIST_LIMIT_MAX)
        if indexed_sessions and not _has_missing_index_entries(indexed_sessions, checkpoint_sessions):
            return _reindex_sessions(indexed_sessions[:resolved_limit])
        if not checkpoint_sessions:
            return _reindex_sessions(indexed_sessions[:resolved_limit])
        merged_sessions = _merge_session_entries(indexed_sessions, checkpoint_sessions)
        _write_session_index(project_root, merged_sessions)
    return _reindex_sessions(merged_sessions[:resolved_limit])


def current_ai_terminal_session(
    checkpointer: Any,
    thread_id: str,
    *,
    project_root: str | Path | None = None,
) -> AITerminalSessionSummary | None:
    if project_root is not None:
        indexed = _session_from_index(project_root, thread_id)
        if indexed is not None:
            return indexed
    summary = _current_ai_terminal_session_from_checkpoint(checkpointer, thread_id)
    if summary is not None and project_root is not None:
        with _SESSION_INDEX_LOCK:
            _write_session_index(project_root, _merge_session_entries(_read_session_index(project_root), [summary]))
    return summary


def resolve_ai_terminal_session(
    checkpointer: Any,
    identifier: str,
    *,
    project_root: str | Path | None = None,
) -> str:
    query = identifier.strip()
    if not query:
        raise ValueError("用法：/resume <thread-id-or-index>")
    if ai_terminal_session_exists(checkpointer, query, project_root=project_root):
        return query

    sessions = list_ai_terminal_sessions(checkpointer, project_root=project_root, limit=SESSION_LIST_LIMIT_MAX)
    if query.isdigit():
        index = int(query)
        if 1 <= index <= len(sessions):
            return sessions[index - 1].thread_id
        raise ValueError(f"session index out of range: {index}")

    lowered = query.lower()
    matches = [summary.thread_id for summary in sessions if lowered in summary.thread_id.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        preview = ", ".join(matches[:5])
        raise ValueError(f"session selector is ambiguous: {query}. Matches: {preview}")
    raise ValueError(f"AI terminal session not found: {query}")


def ai_terminal_session_exists(
    checkpointer: Any,
    thread_id: str,
    *,
    project_root: str | Path | None = None,
) -> bool:
    if project_root is not None and _session_from_index(project_root, thread_id) is not None:
        return True
    with checkpointer.cursor(transaction=False) as cursor:
        cursor.execute(
            "SELECT 1 FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = '' LIMIT 1",
            (thread_id,),
        )
        return cursor.fetchone() is not None


def update_ai_terminal_session_index(
    project_root: str | Path,
    checkpointer: Any,
    thread_id: str,
) -> AITerminalSessionSummary | None:
    summary = _current_ai_terminal_session_from_checkpoint(checkpointer, thread_id)
    if summary is None:
        return None
    with _SESSION_INDEX_LOCK:
        sessions = _merge_session_entries(_read_session_index(project_root), [summary])
        _write_session_index(project_root, sessions)
    return summary


def remove_ai_terminal_session_from_index(project_root: str | Path, thread_id: str) -> None:
    with _SESSION_INDEX_LOCK:
        sessions = [summary for summary in _read_session_index(project_root) if summary.thread_id != thread_id]
        _write_session_index(project_root, sessions)


def session_index_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".keygen" / "ai-terminal-sessions" / SESSION_INDEX_FILE_NAME


def _list_ai_terminal_sessions_from_checkpoints(
    checkpointer: Any,
    *,
    limit: int,
) -> list[AITerminalSessionSummary]:
    rows = _latest_checkpoint_rows(checkpointer, limit)
    summaries: list[AITerminalSessionSummary] = []
    for index, row in enumerate(rows, start=1):
        thread_id = str(row["thread_id"])
        checkpoint_id = str(row["checkpoint_id"])
        checkpoint_tuple = checkpointer.get_tuple(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": checkpoint_id,
                }
            }
        )
        if checkpoint_tuple is None:
            continue
        summaries.append(
            summarize_checkpoint_tuple(
                checkpoint_tuple,
                index=index,
                checkpoint_count=int(row["checkpoint_count"]),
            )
        )
    return summaries


def _current_ai_terminal_session_from_checkpoint(checkpointer: Any, thread_id: str) -> AITerminalSessionSummary | None:
    row = _latest_checkpoint_row_for_thread(checkpointer, thread_id)
    if row is None:
        return None
    checkpoint_tuple = checkpointer.get_tuple(
        {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": str(row["checkpoint_id"]),
            }
        }
    )
    if checkpoint_tuple is None:
        return None
    return summarize_checkpoint_tuple(
        checkpoint_tuple,
        index=0,
        checkpoint_count=int(row["checkpoint_count"]),
    )


def summarize_checkpoint_tuple(
    checkpoint_tuple: Any,
    *,
    index: int,
    checkpoint_count: int,
) -> AITerminalSessionSummary:
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    config = getattr(checkpoint_tuple, "config", {}) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    if not isinstance(values, dict):
        values = {}
    messages = values.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    context_state = {
        key: str(value)
        for key in CONTEXT_STATE_KEYS
        if isinstance((value := values.get(key)), str) and value
    }
    checkpoint_id = str(configurable.get("checkpoint_id") or checkpoint.get("id") or "")
    thread_id = str(configurable.get("thread_id") or "")
    last_timestamp = str(checkpoint.get("ts") or "")
    return AITerminalSessionSummary(
        index=index,
        thread_id=thread_id,
        checkpoint_id=checkpoint_id,
        last_timestamp=last_timestamp,
        checkpoint_count=checkpoint_count,
        message_count=len(messages),
        image_count=count_images_in_messages(messages),
        latest_user_preview=latest_message_preview(messages, HumanMessage),
        latest_assistant_preview=latest_message_preview(messages, AIMessage),
        context_state=context_state,
    )


def format_sessions_table(sessions: list[AITerminalSessionSummary]) -> str:
    if not sessions:
        return "sessions: <empty>"
    lines = ["#  checkpoints  messages  images  last_timestamp                thread"]
    for summary in sessions:
        last_timestamp = summary.last_timestamp[:25] if summary.last_timestamp else "<unknown>"
        lines.append(
            f"{summary.index:02d} {summary.checkpoint_count:11d} "
            f"{summary.message_count:9d} {summary.image_count:7d} "
            f"{last_timestamp:28s} {summary.thread_id}"
        )
        context = _compact_context_label(summary.context_state)
        if context:
            lines.append(f"   context: {context}")
        if summary.latest_user_preview:
            lines.append(f"   user: {summary.latest_user_preview}")
        if summary.latest_assistant_preview:
            lines.append(f"   assistant: {summary.latest_assistant_preview}")
    return "\n".join(lines)


def _read_session_index(project_root: str | Path) -> list[AITerminalSessionSummary]:
    index_path = session_index_path(project_root)
    if not index_path.exists():
        return []
    try:
        raw_text = index_path.read_text(encoding="utf-8")
    except OSError:
        return []
    payload = _load_json_payload(raw_text)
    if not isinstance(payload, dict) or payload.get("version") != SESSION_INDEX_SCHEMA_VERSION:
        return []
    sessions = payload.get("sessions", [])
    if not isinstance(sessions, list):
        return []
    result: list[AITerminalSessionSummary] = []
    for raw_session in sessions:
        if not isinstance(raw_session, dict):
            continue
        summary = _summary_from_dict(raw_session)
        if summary is not None:
            result.append(summary)
    return _reindex_sessions(_sort_sessions(result))


def _write_session_index(project_root: str | Path, sessions: list[AITerminalSessionSummary]) -> None:
    index_path = session_index_path(project_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SESSION_INDEX_SCHEMA_VERSION,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "sessions": [replace(summary, index=0).to_dict() for summary in _sort_sessions(sessions)],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(index_path.parent), prefix=f".{SESSION_INDEX_FILE_NAME}.", suffix=".tmp") as tmp_file:
        tmp_path = Path(tmp_file.name)
        tmp_file.write(serialized)
        tmp_file.flush()
    tmp_path.replace(index_path)


def _session_from_index(project_root: str | Path, thread_id: str) -> AITerminalSessionSummary | None:
    for summary in _read_session_index(project_root):
        if summary.thread_id == thread_id:
            return replace(summary, index=0)
    return None


def _merge_session_entries(
    existing: list[AITerminalSessionSummary],
    updates: list[AITerminalSessionSummary],
) -> list[AITerminalSessionSummary]:
    sessions_by_thread = {summary.thread_id: replace(summary, index=0) for summary in existing}
    for summary in updates:
        sessions_by_thread[summary.thread_id] = replace(summary, index=0)
    return _sort_sessions(list(sessions_by_thread.values()))


def _has_missing_index_entries(
    indexed_sessions: list[AITerminalSessionSummary],
    checkpoint_sessions: list[AITerminalSessionSummary],
) -> bool:
    indexed_thread_ids = {summary.thread_id for summary in indexed_sessions}
    return any(summary.thread_id not in indexed_thread_ids for summary in checkpoint_sessions)


def _sort_sessions(sessions: list[AITerminalSessionSummary]) -> list[AITerminalSessionSummary]:
    return sorted(sessions, key=lambda summary: (summary.last_timestamp, summary.thread_id), reverse=True)


def _reindex_sessions(sessions: list[AITerminalSessionSummary]) -> list[AITerminalSessionSummary]:
    return [replace(summary, index=index) for index, summary in enumerate(sessions, start=1)]


def _summary_from_dict(value: dict[str, Any]) -> AITerminalSessionSummary | None:
    thread_id = str(value.get("thread_id") or "")
    if not thread_id:
        return None
    context_state = value.get("context_state")
    if not isinstance(context_state, dict):
        context_state = {}
    return AITerminalSessionSummary(
        index=0,
        thread_id=thread_id,
        checkpoint_id=str(value.get("checkpoint_id") or ""),
        last_timestamp=str(value.get("last_timestamp") or ""),
        checkpoint_count=_safe_int(value.get("checkpoint_count")),
        message_count=_safe_int(value.get("message_count")),
        image_count=_safe_int(value.get("image_count")),
        latest_user_preview=str(value.get("latest_user_preview") or ""),
        latest_assistant_preview=str(value.get("latest_assistant_preview") or ""),
        context_state={str(key): str(item) for key, item in context_state.items() if item},
    )


def _load_json_payload(raw_text: str) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        text = raw_text.lstrip()
        if not text:
            return None
        try:
            value, _ = decoder.raw_decode(text)
            return value
        except json.JSONDecodeError:
            return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def latest_message_preview(messages: list[BaseMessage], message_type: type[BaseMessage]) -> str:
    for message in reversed(messages):
        if not isinstance(message, message_type):
            continue
        if isinstance(message, AIMessage) and message.tool_calls:
            continue
        content = getattr(message, "content", "")
        text = message_content_to_text(content).strip()
        if not text and count_images_in_message(message):
            text = "<image>"
        return _truncate_preview(_collapse_text(text))
    return ""


def count_images_in_messages(messages: list[BaseMessage]) -> int:
    return sum(count_images_in_message(message) for message in messages)


def count_images_in_message(message: BaseMessage) -> int:
    return count_images_in_content(getattr(message, "content", None)) + count_images_in_metadata(
        getattr(message, "additional_kwargs", {})
    )


def count_images_in_content(content: Any) -> int:
    if not isinstance(content, list):
        return 0
    count = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in {"image_url", "input_image"} or item.get("image_url"):
            count += 1
    return count


def count_images_in_metadata(additional_kwargs: Any) -> int:
    if not isinstance(additional_kwargs, dict):
        return 0
    attachments = additional_kwargs.get(IMAGE_ATTACHMENTS_METADATA_KEY)
    if not isinstance(attachments, list):
        return 0
    return len([item for item in attachments if isinstance(item, dict)])


def _latest_checkpoint_rows(checkpointer: Any, limit: int) -> list[dict[str, Any]]:
    with checkpointer.cursor(transaction=False) as cursor:
        cursor.execute(
            """
            SELECT thread_id, MAX(checkpoint_id) AS checkpoint_id, COUNT(*) AS checkpoint_count
            FROM checkpoints
            WHERE checkpoint_ns = ''
            GROUP BY thread_id
            ORDER BY checkpoint_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "thread_id": row[0],
                "checkpoint_id": row[1],
                "checkpoint_count": row[2],
            }
            for row in cursor.fetchall()
        ]


def _latest_checkpoint_row_for_thread(checkpointer: Any, thread_id: str) -> dict[str, Any] | None:
    with checkpointer.cursor(transaction=False) as cursor:
        cursor.execute(
            """
            SELECT thread_id, MAX(checkpoint_id) AS checkpoint_id, COUNT(*) AS checkpoint_count
            FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = ''
            GROUP BY thread_id
            """,
            (thread_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return {
        "thread_id": row[0],
        "checkpoint_id": row[1],
        "checkpoint_count": row[2],
    }


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), SESSION_LIST_LIMIT_MAX))


def _compact_context_label(context_state: dict[str, str]) -> str:
    for key in ("current_plan_path", "current_debug_workspace", "latest_output_dir", "latest_compression_summary_path"):
        value = context_state.get(key)
        if value:
            return f"{key}={_truncate_preview(value, chars=180)}"
    return ""


def _collapse_text(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split())


def _truncate_preview(text: str, *, chars: int = PREVIEW_CHARS) -> str:
    if len(text) <= chars:
        return text
    return text[: chars - 3] + "..."
