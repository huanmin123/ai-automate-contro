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

    def diagnose_window(self, query: dict[str, Any]) -> dict[str, Any]:
        ...

    def focus_window(self, query: dict[str, Any]) -> dict[str, Any]:
        ...

    def control_window(self, query: dict[str, Any], operation: str) -> dict[str, Any]:
        ...

    def list_elements(
        self,
        window_query: dict[str, Any],
        *,
        locator: dict[str, Any] | None = None,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def dump_elements(
        self,
        window_query: dict[str, Any],
        *,
        locator: dict[str, Any] | None = None,
        max_depth: int = 6,
        max_elements: int = 200,
        include_tree: bool = True,
        include_selector_hints: bool = True,
        text_limit: int = 160,
    ) -> dict[str, Any]:
        ...

    def find_element(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        state: str = "exists",
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def click_element(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def invoke_element(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def select_element(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        value: str = "",
        *,
        option_index: int | None = None,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def set_element_text(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        value: str,
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
        preserve_clipboard: bool = True,
    ) -> dict[str, Any]:
        ...

    def get_element_text(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def get_element_state(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def get_table(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
        max_rows: int = 50,
        max_columns: int = 20,
        text_limit: int = 160,
        visible_only: bool = True,
    ) -> dict[str, Any]:
        ...

    def select_table_cell(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        row: int,
        column: str = "",
        column_index: int | None = None,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        ...

    def launch_app(
        self,
        *,
        app: str = "",
        path: str = "",
        command: str = "",
        args: list[str] | None = None,
        wait: bool = False,
        timeout_ms: int = 10_000,
    ) -> dict[str, Any]:
        ...

    def type_text(self, value: str, *, method: str = "auto", delay_ms: int = 0, preserve_clipboard: bool = True) -> dict[str, Any]:
        ...

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        ...

    def click(self, *, x: int, y: int, button: str = "left", clicks: int = 1, interval_ms: int = 0) -> dict[str, Any]:
        ...

    def double_click(self, *, x: int, y: int, interval_ms: int = 0) -> dict[str, Any]:
        ...

    def right_click(self, *, x: int, y: int) -> dict[str, Any]:
        ...

    def scroll(self, *, x: int, y: int, amount: int) -> dict[str, Any]:
        ...

    def drag(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
        duration_ms: int = 0,
    ) -> dict[str, Any]:
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
