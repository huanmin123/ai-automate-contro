from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class DesktopBackendError(RuntimeError):
    pass


class DesktopBackend(Protocol):
    platform_name: str
    backend_name: str

    def probe(self, *, request_permissions: bool = False) -> dict[str, Any]:
        ...

    def list_windows(self, *, include_invisible: bool = False) -> list[dict[str, Any]]:
        ...

    def focus_window(self, query: dict[str, Any]) -> dict[str, Any]:
        ...

    def type_text(self, value: str, *, method: str = "auto", delay_ms: int = 0, preserve_clipboard: bool = True) -> dict[str, Any]:
        ...

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        ...

    def click(self, *, x: int, y: int, button: str = "left", clicks: int = 1, interval_ms: int = 0) -> dict[str, Any]:
        ...

    def screenshot(self, path: Path, *, region: dict[str, Any] | None = None, include_cursor: bool = False) -> dict[str, Any]:
        ...

    def snapshot(self, *, include_windows: bool = True, include_displays: bool = True) -> dict[str, Any]:
        ...

    def wait_window(
        self,
        query: dict[str, Any],
        *,
        state: str = "exists",
        timeout_ms: int = 10_000,
        interval_ms: int = 250,
    ) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...
