from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_original_showwarning = warnings.showwarning


def install_langgraph_warning_filter() -> None:
    warnings.showwarning = _showwarning_without_langgraph_allowed_objects_noise


def _showwarning_without_langgraph_allowed_objects_noise(
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: Any | None = None,
    line: str | None = None,
) -> None:
    if "allowed_objects" in str(message):
        return
    _original_showwarning(message, category, filename, lineno, file=file, line=line)


install_langgraph_warning_filter()

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, get_buffer_string, message_to_dict
from langchain_core.messages.modifier import RemoveMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from ai_automate_contro.ai.prompts.session_compression import SUMMARY_PROMPT


MODEL_CONTEXT_TOKEN_LIMIT = 128_000
AUTO_COMPRESS_TRIGGER_TOKENS = MODEL_CONTEXT_TOKEN_LIMIT // 2
POST_COMPRESS_KEEP_TOKENS = MODEL_CONTEXT_TOKEN_LIMIT // 4
MANUAL_COMPRESS_KEEP_MESSAGES = 20


@dataclass(frozen=True)
class CompressionArchive:
    thread_id: str
    archive_dir: Path
    messages_path: Path
    summary_path: Path
    manifest_path: Path
    message_count: int
    token_count: int
    summary: str

    def state_update(self) -> dict[str, str]:
        return {
            "latest_compression_archive_dir": str(self.archive_dir),
            "latest_compression_messages_path": str(self.messages_path),
            "latest_compression_summary_path": str(self.summary_path),
            "latest_compression_token_count": str(self.token_count),
            "latest_compression_message_count": str(self.message_count),
        }


@dataclass(frozen=True)
class CompressionResult:
    archive: CompressionArchive
    messages_to_summarize: list[BaseMessage]
    preserved_messages: list[BaseMessage]

    def state_update(self) -> dict[str, Any]:
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                compression_summary_message(self.archive),
                *self.preserved_messages,
            ],
            **self.archive.state_update(),
        }


class AITerminalSummarizationMiddleware(SummarizationMiddleware):
    def __init__(
        self,
        model: BaseChatModel,
        *,
        project_root: Path,
        thread_id_provider: Callable[[], str],
        trigger: tuple[str, int],
        keep: tuple[str, int],
        summary_prompt: str,
        trim_tokens_to_summarize: int,
    ) -> None:
        super().__init__(
            model=model,
            trigger=trigger,
            keep=keep,
            summary_prompt=summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
        )
        self.project_root = project_root
        self.thread_id_provider = thread_id_provider

    def before_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        messages = state["messages"]
        self._ensure_message_ids(messages)
        total_tokens = self.token_counter(messages)
        if not self._should_summarize(messages, total_tokens):
            return None

        result = self.compress_messages(
            messages,
            reason="auto",
            cutoff_index=self._determine_cutoff_index(messages),
        )
        if result is None:
            return None
        return result.state_update()

    def compress_messages(
        self,
        messages: list[BaseMessage],
        *,
        reason: str,
        keep_messages: int | None = None,
        cutoff_index: int | None = None,
    ) -> CompressionResult | None:
        if cutoff_index is None:
            cutoff_index = self._find_safe_cutoff(messages, keep_messages or MANUAL_COMPRESS_KEEP_MESSAGES)
        if cutoff_index <= 0:
            return None

        messages_to_summarize, preserved_messages = self._partition_messages(messages, cutoff_index)
        summary = self._create_summary_strict(messages_to_summarize)
        archive = archive_messages(
            self.project_root,
            self.thread_id_provider(),
            messages,
            summary=summary,
            reason=reason,
        )
        return CompressionResult(
            archive=archive,
            messages_to_summarize=messages_to_summarize,
            preserved_messages=preserved_messages,
        )

    def _create_summary_strict(self, messages_to_summarize: list[BaseMessage]) -> str:
        if not messages_to_summarize:
            return "No previous conversation history."

        trimmed_messages = self._trim_messages_for_summary(messages_to_summarize)
        if not trimmed_messages:
            return "Previous conversation was too long to summarize."

        formatted_messages = get_buffer_string(trimmed_messages)
        response = self.model.invoke(self.summary_prompt.format(messages=formatted_messages).rstrip())
        return response.text.strip()


def build_summarization_middleware(
    model: BaseChatModel,
    *,
    project_root: Path,
    thread_id_provider: Callable[[], str],
) -> AITerminalSummarizationMiddleware:
    return AITerminalSummarizationMiddleware(
        model=model,
        project_root=project_root,
        thread_id_provider=thread_id_provider,
        trigger=("tokens", AUTO_COMPRESS_TRIGGER_TOKENS),
        keep=("tokens", POST_COMPRESS_KEEP_TOKENS),
        summary_prompt=SUMMARY_PROMPT,
        trim_tokens_to_summarize=16_000,
    )


def make_thread_id(prefix: str = "session") -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def session_root(project_root: Path, thread_id: str) -> Path:
    return project_root / ".keygen" / "ai-terminal-sessions" / sanitize_thread_id(thread_id)


def archive_messages(
    project_root: Path,
    thread_id: str,
    messages: list[BaseMessage],
    *,
    summary: str,
    reason: str,
) -> CompressionArchive:
    token_count = count_ai_terminal_tokens(messages)
    created_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = session_root(project_root, thread_id) / "compressions" / f"{created_at}-{sanitize_thread_id(reason)}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    messages_path = archive_dir / "messages.jsonl"
    summary_path = archive_dir / "summary.md"
    manifest_path = archive_dir / "manifest.json"

    with messages_path.open("w", encoding="utf-8") as file:
        for message in messages:
            payload = redact_image_data_urls(message_to_dict(message))
            file.write(json.dumps(payload, ensure_ascii=False, default=str))
            file.write("\n")

    summary_path.write_text(summary, encoding="utf-8")
    manifest = {
        "thread_id": thread_id,
        "reason": reason,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "message_count": len(messages),
        "token_count": token_count,
        "messages_path": str(messages_path),
        "summary_path": str(summary_path),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return CompressionArchive(
        thread_id=thread_id,
        archive_dir=archive_dir,
        messages_path=messages_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        message_count=len(messages),
        token_count=token_count,
        summary=summary,
    )


def compression_summary_message(archive: CompressionArchive) -> HumanMessage:
    return HumanMessage(
        content=(
            "Here is a compressed summary of the AI terminal conversation to date.\n\n"
            f"{archive.summary}\n\n"
            "Archived full conversation messages are available at:\n"
            f"- messages: {archive.messages_path}\n"
            f"- summary: {archive.summary_path}\n"
            f"- archive_dir: {archive.archive_dir}\n"
        ),
    )


def count_ai_terminal_tokens(messages: list[BaseMessage]) -> int:
    return int(count_tokens_approximately(messages))


def sanitize_thread_id(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    sanitized = sanitized.strip(".-")
    return sanitized or "default"


def redact_image_data_urls(value: Any) -> Any:
    # Compatibility name: project policy keeps image data URLs raw for local debugging.
    return value
