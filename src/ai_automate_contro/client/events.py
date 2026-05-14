from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ClientEventKind = Literal[
    "assistant_delta",
    "assistant_done",
    "tool_started",
    "tool_finished",
    "terminal_output",
    "status",
    "approval_requested",
    "error",
    "exit_requested",
]


@dataclass(frozen=True)
class ClientEvent:
    kind: ClientEventKind
    text: str = ""
    title: str = ""
    data: dict[str, Any] = field(default_factory=dict)
