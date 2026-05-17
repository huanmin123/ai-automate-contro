from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ClientEventKind = Literal[
    "assistant_delta",
    "assistant_done",
    "tool_started",
    "tool_finished",
    "plan_progress",
    "file_changed",
    "diff",
    "artifact",
    "work_plan_updated",
    "activity",
    "system_output",
    "status",
    "context_updated",
    "approval_requested",
    "error",
    "interrupted",
    "exit_requested",
]


@dataclass(frozen=True)
class ClientEvent:
    kind: ClientEventKind
    text: str = ""
    title: str = ""
    data: dict[str, Any] = field(default_factory=dict)
