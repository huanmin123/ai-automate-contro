from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackend


@dataclass
class DesktopSession:
    name: str
    backend: DesktopBackend
    platform: str
    backend_name: str
    permissions: dict[str, Any] = field(default_factory=dict)
    capability_matrix: dict[str, Any] = field(default_factory=dict)
    coordinate_profile: dict[str, Any] = field(default_factory=dict)
    target_candidates: dict[str, Any] = field(default_factory=dict)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    current_window: dict[str, Any] | None = None

    def close(self) -> None:
        self.backend.close()
