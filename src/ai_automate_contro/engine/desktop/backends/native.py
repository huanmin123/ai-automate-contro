from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError
from ai_automate_contro.engine.desktop.backends.capabilities import (
    build_capability_matrix,
    desktop_dependencies,
    module_available as _module_available,
)
from ai_automate_contro.engine.desktop.backends.input_driver import (
    click_element_center as _click_element_center,
    paste_text_with_clipboard as _paste_text_with_clipboard,
    require_pyautogui as _require_pyautogui,
    select_element_keyboard_fallback as _select_element_keyboard_fallback,
    set_element_text_keyboard_fallback as _set_element_text_keyboard_fallback,
)
from ai_automate_contro.engine.desktop.coordinates import build_coordinate_profile
from ai_automate_contro.engine.desktop.backends.native_elements import (
    _compact_near_element_matches,
    _diagnostic_element,
    _element_center,
    _element_dump_limitations,
    _element_dump_recommendations,
    _element_matches,
    _element_state_matches,
    _element_text,
    _element_tree,
    _element_type_matches,
    _fallback_scroll_amount,
    _matching_elements,
    _near_matches_for_locator,
    _normalize_table,
    _normalized_action_payload,
    _normalized_table_payload,
    _normalized_tree_payload,
    _optional_int,
    _region_to_bbox,
    _safe_int,
    _select_element,
    _select_option_element,
)
from ai_automate_contro.engine.desktop.backends.native_macos import (
    _action_element_macos,
    _applescript_text,
    _control_window_macos,
    _focus_window_macos,
    _list_elements_macos,
)
from ai_automate_contro.engine.desktop.backends.native_window_matching import (
    _compact_window_candidate,
    _matching_windows,
    _near_window_matches,
    _window_diagnostics,
    _window_matches,
)
from ai_automate_contro.engine.desktop.backends.native_windows import (
    _action_element_windows,
    _control_window_windows,
    _focus_window_windows,
    _list_elements_windows,
    _list_windows_windows,
    _menu_element_windows,
    _raise_window_z_order_windows,
    _scroll_element_windows,
    _table_element_windows,
    _tree_element_windows,
    _window_from_point_windows,
)


class NativeDesktopBackend:
    backend_name = "native"

    def __init__(self, *, platform_name: str | None = None, desktop_config: dict[str, Any] | None = None) -> None:
        self.platform_name = platform_name or _current_platform_name()
        self.desktop_config = dict(desktop_config or {})
        self.last_window_list_error = ""

    def probe(self, *, request_permissions: bool = False) -> dict[str, Any]:
        permissions = {
            "accessibility": "unknown",
            "screen_recording": "unknown",
            "input_control": "unknown",
        }
        window_error = ""
        try:
            self.list_windows()
            if self.platform_name == "macos":
                permissions["accessibility"] = "available_or_not_required"
        except Exception as error:
            window_error = str(error)
            if self.platform_name == "macos":
                permissions["accessibility"] = "not_granted_or_unavailable"
        screenshot_error = ""
        if request_permissions:
            try:
                from PIL import ImageGrab

                ImageGrab.grab(bbox=(0, 0, 1, 1))
                permissions["screen_recording"] = "available_or_not_required"
            except Exception as error:
                screenshot_error = str(error)
                permissions["screen_recording"] = "not_granted_or_unavailable"
        dependencies = desktop_dependencies(self.desktop_config)
        pyautogui_available = dependencies.get("pyautogui", False)
        if pyautogui_available:
            permissions["input_control"] = "available_or_not_required"
        display = self._display_info()
        capability_matrix = build_capability_matrix(
            platform_name=self.platform_name,
            backend_name=self.backend_name,
            source="probe",
            permissions=permissions,
            dependencies=dependencies,
            window_list_error=window_error or self.last_window_list_error,
        )
        coordinate_profile = build_coordinate_profile(
            platform=self.platform_name,
            backend=self.backend_name,
            display=display,
            source_kind="screen",
            source_bounds={
                "x": 0,
                "y": 0,
                "width": int(display.get("width", 0) or 0),
                "height": int(display.get("height", 0) or 0),
            },
            coordinate_space={
                "origin": "screen",
                "unit": "logical_px",
                "scale": display.get("scale") if isinstance(display, dict) else None,
            },
        )
        return {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "permissions": permissions,
            "dependencies": dependencies,
            "capability_matrix": capability_matrix,
            "display": display,
            "coordinate_profile": coordinate_profile,
            "window_list_error": window_error or self.last_window_list_error,
        }

    def list_windows(self, *, include_invisible: bool = False) -> list[dict[str, Any]]:
        if self.platform_name == "windows":
            return _list_windows_windows(include_invisible=include_invisible)
        if self.platform_name == "macos":
            return self._list_windows_macos()
        self.last_window_list_error = f"当前平台暂不支持桌面窗口枚举：{self.platform_name}"
        return []

    def diagnose_window(self, query: dict[str, Any]) -> dict[str, Any]:
        windows = self.list_windows()
        matches = _matching_windows(windows, query)
        return _window_diagnostics(windows, query, matches)

    def find_windows(self, query: dict[str, Any], *, include_invisible: bool = False) -> list[dict[str, Any]]:
        windows = self.list_windows(include_invisible=include_invisible)
        return [dict(window) for window in _matching_windows(windows, query)]

    def get_active_window(self) -> dict[str, Any]:
        windows = self.list_windows(include_invisible=True)
        focused = next((window for window in windows if bool(window.get("focused"))), None)
        return dict(focused) if isinstance(focused, dict) else {}

    def window_from_point(self, *, x: int, y: int) -> dict[str, Any]:
        if self.platform_name == "windows":
            return _window_from_point_windows(int(x), int(y))
        return {
            "ok": False,
            "available": False,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "point": {"x": int(x), "y": int(y)},
            "reason": "window_from_point_not_implemented",
        }

    def focus_window(self, query: dict[str, Any]) -> dict[str, Any]:
        window = self._select_window(query)
        if self.platform_name == "windows":
            _focus_window_windows(int(window["id"]))
        elif self.platform_name == "macos":
            _focus_window_macos(window)
        else:
            raise DesktopBackendError(f"当前平台暂不支持窗口聚焦：{self.platform_name}")
        window["focused"] = True
        return window

    def control_window(self, query: dict[str, Any], operation: str) -> dict[str, Any]:
        if operation not in {"close", "minimize", "maximize", "restore"}:
            raise DesktopBackendError(f"不支持的窗口控制操作：{operation}")
        window = self._select_window(query)
        before = dict(window)
        if self.platform_name == "windows":
            _control_window_windows(int(window["id"]), operation)
        elif self.platform_name == "macos":
            _control_window_macos(window, operation)
        else:
            raise DesktopBackendError(f"当前平台暂不支持窗口控制：{self.platform_name}")
        window["operation"] = operation
        if operation == "close":
            window["close_requested"] = True
            window["focused"] = False
        elif operation == "minimize":
            window["minimized"] = True
            window["focused"] = False
        elif operation == "maximize":
            window["maximized"] = True
        elif operation == "restore":
            window["minimized"] = False
        return {
            "ok": True,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "operation": operation,
            "window": window,
            "before": before,
        }

    def list_elements(
        self,
        window_query: dict[str, Any],
        *,
        locator: dict[str, Any] | None = None,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        window = self._select_window(window_query)
        normalized_max_depth = max(0, int(max_depth))
        normalized_max_elements = max(1, int(max_elements))
        if self.platform_name == "windows":
            element_payload = _list_elements_windows(
                int(window["id"]),
                max_depth=normalized_max_depth,
                max_elements=normalized_max_elements,
            )
        elif self.platform_name == "macos":
            element_payload = _list_elements_macos(
                window,
                max_depth=normalized_max_depth,
                max_elements=normalized_max_elements,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持控件枚举：{self.platform_name}")
        elements = list(element_payload.get("elements", [])) if isinstance(element_payload.get("elements"), list) else []
        normalized_locator = dict(locator or {})
        filtered = _matching_elements(elements, normalized_locator) if normalized_locator else elements
        return {
            "ok": True,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "window": window,
            "locator": normalized_locator,
            "elements": filtered,
            "count": len(filtered),
            "total_count": len(elements),
            "truncated": bool(element_payload.get("truncated", False)),
            "max_depth": normalized_max_depth,
            "max_elements": normalized_max_elements,
        }

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
        normalized_max_depth = max(0, int(max_depth))
        normalized_max_elements = max(1, int(max_elements))
        normalized_text_limit = max(0, int(text_limit))
        payload = self.list_elements(
            window_query,
            max_depth=normalized_max_depth,
            max_elements=normalized_max_elements,
        )
        elements = list(payload.get("elements", [])) if isinstance(payload.get("elements"), list) else []
        normalized_locator = dict(locator or {})
        matched_elements = _matching_elements(elements, normalized_locator) if normalized_locator else elements
        matched_ids = {str(element.get("id") or element.get("runtime_id") or "") for element in matched_elements}
        diagnostic_elements = [
            _diagnostic_element(
                element,
                index=index,
                all_elements=elements,
                matched=str(element.get("id") or element.get("runtime_id") or "") in matched_ids,
                include_selector_hints=include_selector_hints,
                text_limit=normalized_text_limit,
            )
            for index, element in enumerate(elements)
        ]
        matched_diagnostics = [element for element in diagnostic_elements if bool(element.get("matched"))]
        selector_hints = (
            [
                {
                    "element_id": element.get("id", ""),
                    "index": element.get("index", 0),
                    "name": element.get("name", ""),
                    "text": element.get("text", ""),
                    "control_type": element.get("control_type", ""),
                    "role": element.get("role", ""),
                    "hints": element.get("selector_hints", []),
                }
                for element in matched_diagnostics
            ]
            if include_selector_hints
            else []
        )
        near_matches = _near_matches_for_locator(diagnostic_elements, normalized_locator) if normalized_locator else []
        return {
            "ok": True,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "window": payload.get("window", {}),
            "locator": normalized_locator,
            "elements": diagnostic_elements,
            "matches": matched_diagnostics,
            "selected_element": matched_diagnostics[0] if matched_diagnostics else None,
            "near_matches": near_matches,
            "tree": _element_tree(diagnostic_elements) if include_tree else [],
            "selector_hints": selector_hints,
            "count": len(diagnostic_elements),
            "match_count": len(matched_diagnostics),
            "total_count": int(payload.get("total_count", len(elements)) or len(elements)),
            "truncated": bool(payload.get("truncated", False)),
            "max_depth": normalized_max_depth,
            "max_elements": normalized_max_elements,
            "include_tree": bool(include_tree),
            "include_selector_hints": bool(include_selector_hints),
            "text_limit": normalized_text_limit,
            "diagnostics": {
                "locator_applied": bool(normalized_locator),
                "ambiguous": bool(normalized_locator) and len(matched_diagnostics) > 1,
                "matched_ids": [str(element.get("id") or element.get("runtime_id") or "") for element in matched_elements],
                "selector_hint_count": sum(
                    len(element.get("selector_hints", []))
                    for element in diagnostic_elements
                    if isinstance(element.get("selector_hints"), list)
                ),
                "enumeration_depth_supported": normalized_max_depth if self.platform_name == "windows" else 1,
                "backend_limitations": _element_dump_limitations(self.platform_name),
                "recommendations": _element_dump_recommendations(
                    locator=normalized_locator,
                    match_count=len(matched_diagnostics),
                    near_matches=near_matches,
                ),
            },
        }

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
        normalized_state = str(state or "exists")
        if normalized_state not in {"exists", "not_exists", "enabled", "disabled", "focused"}:
            raise DesktopBackendError(f"不支持的 desktop_element.state：{normalized_state}")
        deadline = time.monotonic() + max(0.001, int(timeout_ms) / 1000)
        last_payload: dict[str, Any] = {}
        while True:
            payload = self.list_elements(
                window_query,
                locator=locator,
                max_depth=max_depth,
                max_elements=max_elements,
            )
            last_payload = payload
            matches = list(payload.get("elements", [])) if isinstance(payload.get("elements"), list) else []
            element = _select_element(matches, locator) if matches else None
            if _element_state_matches(element, normalized_state):
                return {
                    **payload,
                    "state": normalized_state,
                    "element": element,
                    "matches": matches,
                    "candidates_count": len(matches),
                }
            if time.monotonic() >= deadline:
                diagnostics = self._element_failure_diagnostics(
                    window_query,
                    locator,
                    max_depth=max_depth,
                    max_elements=max_elements,
                )
                raise TimeoutError(
                    f"等待桌面控件超时：state={normalized_state} locator={locator} "
                    f"matches={len(matches)} diagnostics={diagnostics}"
                )
            time.sleep(max(0.001, int(interval_ms) / 1000))

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        x, y = _click_element_center(element, locator=locator)
        return {
            **payload,
            "clicked": True,
            "x": x,
            "y": y,
            "method": "bounds_click",
            "fallback_used": False,
        }

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        action_payload: dict[str, Any]
        if self.platform_name == "windows":
            action_payload = _action_element_windows(
                int(window["id"]),
                locator,
                operation="invoke",
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif self.platform_name == "macos":
            action_payload = _action_element_macos(window, element, operation="invoke", value="")
        else:
            raise DesktopBackendError(f"当前平台暂不支持控件原生 invoke：{self.platform_name}")
        if bool(action_payload.get("fallback_required")):
            x, y = _click_element_center(element, locator=locator)
            return {
                **payload,
                **_normalized_action_payload(action_payload),
                "invoked": True,
                "method": "bounds_click_fallback",
                "fallback_used": True,
                "x": x,
                "y": y,
            }
        return {
            **payload,
            **_normalized_action_payload(action_payload),
            "invoked": True,
            "fallback_used": False,
        }

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
        option_value = str(value or "")
        normalized_option_index = _optional_int(option_index)
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        if (
            self.platform_name == "windows"
            and normalized_option_index is not None
            and (_element_type_matches(element, "combobox") or _element_type_matches(element, "list"))
        ):
            fallback = _select_element_keyboard_fallback(
                element,
                normalized_option_index,
                locator=locator,
            )
            return {
                **payload,
                **fallback,
                "selected": True,
                "value": option_value,
                "option_index": normalized_option_index,
                "fallback_used": True,
            }
        if self.platform_name == "windows":
            action_payload = _action_element_windows(
                int(window["id"]),
                locator,
                operation="select",
                value=option_value,
                option_index=normalized_option_index,
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif self.platform_name == "macos":
            action_payload = self._select_element_macos(
                window,
                element,
                option_value=option_value,
                option_index=normalized_option_index,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持控件选择：{self.platform_name}")
        normalized = _normalized_action_payload(action_payload)
        if bool(action_payload.get("fallback_required")):
            if normalized_option_index is not None and (
                _element_type_matches(element, "combobox") or _element_type_matches(element, "list")
            ):
                fallback = _select_element_keyboard_fallback(
                    element,
                    normalized_option_index,
                    locator=locator,
                )
                return {
                    **payload,
                    **normalized,
                    **fallback,
                    "selected": True,
                    "value": option_value,
                    "option_index": normalized_option_index,
                    "fallback_used": True,
                }
            action_element = normalized.get("action_element") if isinstance(normalized.get("action_element"), dict) else {}
            fallback_element = action_element or element
            x, y = _click_element_center(fallback_element, locator=locator)
            return {
                **payload,
                **normalized,
                "selected": True,
                "value": option_value,
                "option_index": normalized_option_index,
                "method": str(action_payload.get("method") or "bounds_click_fallback"),
                "fallback_used": True,
                "x": x,
                "y": y,
            }
        return {
            **payload,
            **normalized,
            "selected": True,
            "value": option_value,
            "option_index": normalized_option_index,
            "fallback_used": False,
        }

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
        text = str(value)
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        action_payload: dict[str, Any]
        if self.platform_name == "windows":
            action_payload = _action_element_windows(
                int(window["id"]),
                locator,
                operation="set_text",
                value=text,
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif self.platform_name == "macos":
            action_payload = _action_element_macos(window, element, operation="set_text", value=text)
        else:
            raise DesktopBackendError(f"当前平台暂不支持控件原生 set_text：{self.platform_name}")
        if bool(action_payload.get("fallback_required")):
            fallback = _set_element_text_keyboard_fallback(
                element,
                text,
                locator=locator,
                preserve_clipboard=preserve_clipboard,
            )
            return {
                **payload,
                **_normalized_action_payload(action_payload),
                **fallback,
                "set_text": True,
                "length": len(text),
                "fallback_used": True,
            }
        return {
            **payload,
            **_normalized_action_payload(action_payload),
            "set_text": True,
            "length": len(text),
            "fallback_used": False,
        }

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        return {**payload, "text": _element_text(element)}

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        state_payload = {
            "enabled": bool(element.get("enabled", False)) if isinstance(element, dict) else False,
            "visible": bool(element.get("visible", False)) if isinstance(element, dict) else False,
            "focused": bool(element.get("focused", False)) if isinstance(element, dict) else False,
            "bounds": element.get("bounds", {}) if isinstance(element, dict) else {},
        }
        return {**payload, "element_state": state_payload}

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        if self.platform_name == "windows":
            table_payload = _table_element_windows(
                int(window["id"]),
                locator,
                operation="get_table",
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                max_depth=max_depth,
                max_elements=max_elements,
                max_rows=max_rows,
                max_columns=max_columns,
                text_limit=text_limit,
                visible_only=visible_only,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持表格控件读取：{self.platform_name}")
        return {
            **payload,
            **_normalized_table_payload(table_payload),
            "table_read": True,
            "fallback_used": False,
        }

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
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        normalized_column_index = _optional_int(column_index)
        if self.platform_name == "windows":
            action_payload = _table_element_windows(
                int(window["id"]),
                locator,
                operation="select_cell",
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                row=max(0, int(row)),
                column=str(column or ""),
                column_index=normalized_column_index,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持表格单元格选择：{self.platform_name}")
        normalized = _normalized_table_payload(action_payload)
        return {
            **payload,
            **normalized,
            "selected": True,
            "row": max(0, int(row)),
            "column": str(column or ""),
            "column_index": normalized_column_index,
            "fallback_used": bool(action_payload.get("fallback_required", False)),
        }

    def get_tree(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
        max_nodes: int = 200,
        text_limit: int = 160,
    ) -> dict[str, Any]:
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        if self.platform_name == "windows":
            tree_payload = _tree_element_windows(
                int(window["id"]),
                locator,
                operation="get_tree",
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                max_depth=max_depth,
                max_elements=max_elements,
                max_nodes=max_nodes,
                text_limit=text_limit,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持树控件读取：{self.platform_name}")
        return {
            **payload,
            **_normalized_tree_payload(tree_payload),
            "tree_read": True,
            "fallback_used": False,
        }

    def tree_element_action(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        operation: str,
        tree_path: list[str],
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        if operation not in {"expand_tree", "collapse_tree", "select_tree"}:
            raise DesktopBackendError(f"不支持的树控件操作：{operation}")
        normalized_path = [str(part) for part in tree_path]
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        if self.platform_name == "windows":
            action_payload = _tree_element_windows(
                int(window["id"]),
                locator,
                operation=operation,
                runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                tree_path=normalized_path,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持树控件操作：{self.platform_name}")
        normalized = _normalized_tree_payload(action_payload)
        fallback_payload: dict[str, Any] = {}
        fallback_used = bool(action_payload.get("fallback_required", False))
        if operation == "select_tree":
            tree_node = normalized.get("tree_node") if isinstance(normalized.get("tree_node"), dict) else {}
            fallback_element = tree_node or element
            bounds = fallback_element.get("bounds") if isinstance(fallback_element, dict) else {}
            if (
                isinstance(bounds, dict)
                and _safe_int(bounds.get("width"), default=0) > 0
                and _safe_int(bounds.get("height"), default=0) > 0
            ):
                x, y = _click_element_center(fallback_element, locator=locator)
                fallback_method = "bounds_click_fallback" if fallback_used else f"{normalized.get('method', 'uia_select')}+bounds_click"
                fallback_payload = {"method": fallback_method, "x": x, "y": y}
                fallback_used = True
        return {
            **payload,
            **normalized,
            **fallback_payload,
            "tree_path": normalized_path,
            "fallback_used": fallback_used,
        }

    def invoke_menu(
        self,
        window_query: dict[str, Any],
        *,
        locator: dict[str, Any] | None = None,
        menu_path: list[str],
        open_context_menu: bool = False,
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        normalized_path = [str(part) for part in menu_path]
        normalized_locator = locator or {}
        window = self.wait_window(
            window_query,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
        ).get("window")
        if not isinstance(window, dict):
            raise DesktopBackendError(f"未找到匹配菜单窗口：{window_query}")
        context_open: dict[str, Any] = {}
        context_target: dict[str, Any] = {}
        if open_context_menu:
            if not normalized_locator:
                raise DesktopBackendError("desktop_element.invoke_menu open_context_menu 需要 Element Locator")
            target_payload = self.find_element(
                window_query,
                normalized_locator,
                state="exists",
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
            context_target = (
                target_payload.get("element") if isinstance(target_payload.get("element"), dict) else {}
            )
            x, y = _click_element_center(context_target, locator=normalized_locator, button="right")
            time.sleep(0.2)
            context_open = {"ok": True, "x": x, "y": y, "button": "right"}
        if self.platform_name == "windows":
            action_payload = _menu_element_windows(
                int(window["id"]),
                menu_path=normalized_path,
                search_global=bool(open_context_menu),
                max_depth=max_depth,
                max_elements=max_elements,
            )
        else:
            raise DesktopBackendError(f"当前平台暂不支持菜单路径触发：{self.platform_name}")
        normalized = _normalized_action_payload(action_payload)
        menu_item = normalized.pop("action_element", None)
        payload: dict[str, Any] = {
            "ok": True,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "window": window,
            **normalized,
            "invoked": True,
            "menu_path": normalized_path,
            "open_context_menu": bool(open_context_menu),
            "fallback_used": bool(action_payload.get("fallback_required", False)),
        }
        if isinstance(menu_item, dict):
            payload["menu_item"] = menu_item
        if context_open:
            payload["context_open"] = context_open
        if context_target:
            payload["context_target"] = context_target
        return payload

    def scroll_element(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        amount: int | None = None,
        scroll_to: str = "",
        timeout_ms: int = 1_000,
        interval_ms: int = 100,
        max_depth: int = 6,
        max_elements: int = 200,
    ) -> dict[str, Any]:
        payload = self.find_element(
            window_query,
            locator,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        normalized_amount = _optional_int(amount)
        normalized_scroll_to = str(scroll_to or "")
        if normalized_amount == 0:
            raise DesktopBackendError("desktop_element.scroll_element amount 不能为 0")
        action_payload: dict[str, Any] = {}
        if self.platform_name == "windows":
            try:
                action_payload = _scroll_element_windows(
                    int(window["id"]),
                    locator,
                    runtime_id=str(element.get("runtime_id") or element.get("id") or ""),
                    amount=normalized_amount,
                    scroll_to=normalized_scroll_to,
                    max_depth=max_depth,
                    max_elements=max_elements,
                )
            except DesktopBackendError as error:
                action_payload = {
                    "ok": True,
                    "operation": "scroll_element",
                    "method": "mouse_wheel_fallback",
                    "fallback_required": True,
                    "fallback_error": str(error),
                    "element": element,
                }
        else:
            raise DesktopBackendError(f"当前平台暂不支持滚动容器操作：{self.platform_name}")
        normalized = _normalized_action_payload(action_payload)
        scroll_target = normalized.pop("action_element", None)
        if bool(action_payload.get("fallback_required")):
            fallback_amount = _fallback_scroll_amount(normalized_amount, normalized_scroll_to)
            x, y = _element_center(element, locator=locator)
            fallback = self.scroll(x=x, y=y, amount=fallback_amount)
            return {
                **payload,
                **normalized,
                **fallback,
                "method": "mouse_wheel_fallback",
                "scroll_to": normalized_scroll_to,
                "fallback_used": True,
                "scroll_target": scroll_target if isinstance(scroll_target, dict) else element,
            }
        result: dict[str, Any] = {
            **payload,
            **normalized,
            "amount": normalized_amount,
            "scroll_to": normalized_scroll_to,
            "fallback_used": False,
        }
        if isinstance(scroll_target, dict):
            result["scroll_target"] = scroll_target
        return result

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
        normalized_args = [str(arg) for arg in (args or [])]
        command_line = self._launch_command_line(app=app, path=path, command=command, args=normalized_args)
        try:
            process = subprocess.Popen(
                command_line,
                stdout=subprocess.PIPE if wait else subprocess.DEVNULL,
                stderr=subprocess.PIPE if wait else subprocess.DEVNULL,
                text=True,
            )
        except OSError as error:
            raise DesktopBackendError(f"启动桌面 App 失败：{error}") from error
        payload: dict[str, Any] = {
            "ok": True,
            "platform": self.platform_name,
            "backend": self.backend_name,
            "app": app,
            "path": path,
            "command": command,
            "args": normalized_args,
            "command_line": command_line,
            "pid": int(process.pid) if process.pid is not None else None,
            "wait": bool(wait),
        }
        if wait:
            try:
                stdout, stderr = process.communicate(timeout=max(0.001, timeout_ms / 1000))
            except subprocess.TimeoutExpired as error:
                process.kill()
                stdout, stderr = process.communicate(timeout=2)
                raise TimeoutError(f"桌面 App 启动命令等待超时：timeout_ms={timeout_ms}") from error
            payload.update(
                {
                    "exit_code": int(process.returncode or 0),
                    "stdout": _trim_process_text(stdout),
                    "stderr": _trim_process_text(stderr),
                }
            )
        return payload

    def type_text(
        self,
        value: str,
        *,
        method: str = "auto",
        delay_ms: int = 0,
        preserve_clipboard: bool = True,
    ) -> dict[str, Any]:
        pyautogui = _require_pyautogui()
        text = str(value)
        selected_method = method
        if method in {"auto", "type"}:
            pyautogui.write(text, interval=max(0, delay_ms) / 1000)
            selected_method = "type"
        elif method == "clipboard":
            _paste_text_with_clipboard(text, preserve_clipboard=preserve_clipboard)
        else:
            raise DesktopBackendError(f"不支持的 desktop_input.method：{method}")
        return {"ok": True, "method": selected_method, "length": len(text)}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        pyautogui = _require_pyautogui()
        normalized_keys = [str(key).lower() for key in keys]
        pyautogui.hotkey(*normalized_keys)
        return {"ok": True, "keys": normalized_keys}

    def click(
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        interval_ms: int = 0,
    ) -> dict[str, Any]:
        if button not in {"left", "right", "middle"}:
            raise DesktopBackendError(f"不支持的 desktop_input.button：{button}")
        pyautogui = _require_pyautogui()
        normalized_clicks = max(1, int(clicks))
        normalized_interval_ms = max(0, int(interval_ms))
        pyautogui.click(
            x=int(x),
            y=int(y),
            button=button,
            clicks=normalized_clicks,
            interval=normalized_interval_ms / 1000,
        )
        return {
            "ok": True,
            "x": int(x),
            "y": int(y),
            "button": button,
            "clicks": normalized_clicks,
            "interval_ms": normalized_interval_ms,
        }

    def double_click(self, *, x: int, y: int, interval_ms: int = 0) -> dict[str, Any]:
        payload = self.click(x=x, y=y, button="left", clicks=2, interval_ms=interval_ms)
        payload["action"] = "double_click"
        return payload

    def right_click(self, *, x: int, y: int) -> dict[str, Any]:
        payload = self.click(x=x, y=y, button="right", clicks=1, interval_ms=0)
        payload["action"] = "right_click"
        return payload

    def scroll(self, *, x: int, y: int, amount: int) -> dict[str, Any]:
        normalized_amount = int(amount)
        if normalized_amount == 0:
            raise DesktopBackendError("desktop_input.scroll amount 不能为 0")
        pyautogui = _require_pyautogui()
        pyautogui.scroll(normalized_amount, x=int(x), y=int(y))
        return {"ok": True, "x": int(x), "y": int(y), "amount": normalized_amount}

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
        if button not in {"left", "right", "middle"}:
            raise DesktopBackendError(f"不支持的 desktop_input.button：{button}")
        pyautogui = _require_pyautogui()
        normalized_duration_ms = max(0, int(duration_ms))
        pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.dragTo(
            int(end_x),
            int(end_y),
            duration=normalized_duration_ms / 1000,
            button=button,
        )
        return {
            "ok": True,
            "start_x": int(start_x),
            "start_y": int(start_y),
            "end_x": int(end_x),
            "end_y": int(end_y),
            "button": button,
            "duration_ms": normalized_duration_ms,
        }

    def screenshot(
        self,
        path: Path,
        *,
        region: dict[str, Any] | None = None,
        include_cursor: bool = False,
    ) -> dict[str, Any]:
        try:
            from PIL import ImageGrab
        except Exception as error:
            raise DesktopBackendError("desktop_capture.screenshot 需要 Pillow ImageGrab。") from error

        bbox = _region_to_bbox(region)
        image = ImageGrab.grab(bbox=bbox)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return {
            "ok": True,
            "path": str(path),
            "width": image.width,
            "height": image.height,
            "region": region or {},
            "include_cursor": False,
            "include_cursor_requested": bool(include_cursor),
            "cursor_included": False,
        }

    def snapshot(self, *, include_windows: bool = True, include_displays: bool = True) -> dict[str, Any]:
        dependencies = desktop_dependencies(self.desktop_config)
        payload: dict[str, Any] = {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "dependencies": dependencies,
        }
        display = self._display_info() if include_displays else {}
        if include_displays:
            payload["display"] = display
        if include_windows:
            try:
                payload["windows"] = self.list_windows()
            except Exception as error:
                payload["windows"] = []
                payload["window_list_error"] = str(error)
        payload["capability_matrix"] = build_capability_matrix(
            platform_name=self.platform_name,
            backend_name=self.backend_name,
            source="snapshot",
            permissions={},
            dependencies=dependencies,
            window_list_error=str(payload.get("window_list_error") or self.last_window_list_error or ""),
        )
        payload["coordinate_profile"] = build_coordinate_profile(
            platform=self.platform_name,
            backend=self.backend_name,
            display=display,
            source_kind="screen",
            source_bounds={
                "x": 0,
                "y": 0,
                "width": int(display.get("width", 0) or 0) if isinstance(display, dict) else 0,
                "height": int(display.get("height", 0) or 0) if isinstance(display, dict) else 0,
            },
            coordinate_space={
                "origin": "screen",
                "unit": "logical_px",
                "scale": display.get("scale") if isinstance(display, dict) else None,
            },
        )
        return payload

    def wait_window(
        self,
        query: dict[str, Any],
        *,
        state: str = "exists",
        timeout_ms: int = 10_000,
        interval_ms: int = 250,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.001, timeout_ms / 1000)
        last_matches: list[dict[str, Any]] = []
        last_windows: list[dict[str, Any]] = []
        while True:
            windows = self.list_windows()
            last_windows = windows
            last_matches = _matching_windows(windows, query)
            match_index = int(query.get("match_index", 0) or 0)
            selected = last_matches[match_index] if 0 <= match_index < len(last_matches) else None
            if state == "exists" and selected is not None:
                return {"ok": True, "state": state, "window": selected, "matches": last_matches}
            if state == "not_exists" and selected is None:
                return {"ok": True, "state": state, "window": None, "matches": last_matches}
            if state == "focused" and selected is not None and bool(selected.get("focused")):
                return {"ok": True, "state": state, "window": selected, "matches": last_matches}
            if time.monotonic() >= deadline:
                diagnostics = _window_diagnostics(last_windows, query, last_matches)
                diagnostics["match_index"] = match_index
                raise TimeoutError(
                    f"等待窗口超时：state={state} query={query} "
                    f"matches={len(last_matches)} diagnostics={diagnostics}"
                )
            time.sleep(max(0.001, interval_ms / 1000))

    def close(self) -> None:
        return None

    def _select_element_macos(
        self,
        window: dict[str, Any],
        element: dict[str, Any],
        *,
        option_value: str,
        option_index: int | None,
        max_depth: int,
        max_elements: int,
    ) -> dict[str, Any]:
        option_element: dict[str, Any] = {}
        if option_value or option_index is not None:
            elements_payload = _list_elements_macos(
                window,
                max_depth=max_depth,
                max_elements=max_elements,
            )
            elements = elements_payload.get("elements") if isinstance(elements_payload.get("elements"), list) else []
            option_element = _select_option_element(elements, option_value=option_value, option_index=option_index)
        if option_element:
            return {
                "ok": True,
                "operation": "select",
                "method": "bounds_click_fallback",
                "fallback_required": True,
                "fallback_error": "macOS AX selection uses option bounds click fallback.",
                "element": option_element,
            }
        action_payload = _action_element_macos(window, element, operation="select", value=option_value)
        if action_payload.get("method"):
            return action_payload
        return {
            "ok": True,
            "operation": "select",
            "method": "bounds_click_fallback",
            "fallback_required": True,
            "fallback_error": "macOS option was not found in AX element list.",
            "element": element,
        }

    def _launch_command_line(
        self,
        *,
        app: str,
        path: str,
        command: str,
        args: list[str],
    ) -> list[str]:
        if command:
            return [command, *args]
        if self.platform_name == "macos":
            if app:
                return ["open", "-a", app, *args]
            if path:
                return ["open", path, *args]
        executable = path or app
        if not executable:
            raise DesktopBackendError("desktop_app.launch 需要 app、path 或 command 之一。")
        return [executable, *args]

    def _select_window(self, query: dict[str, Any]) -> dict[str, Any]:
        windows = self.list_windows()
        matches = _matching_windows(windows, query)
        if not matches:
            raise DesktopBackendError(f"未找到匹配窗口：{query} diagnostics={_window_diagnostics(windows, query, matches)}")
        match_index = int(query.get("match_index", 0) or 0)
        if match_index >= len(matches):
            raise DesktopBackendError(
                f"窗口匹配索引超出范围：match_index={match_index} matches={len(matches)} "
                f"diagnostics={_window_diagnostics(windows, query, matches)}"
            )
        return dict(matches[match_index])

    def _element_failure_diagnostics(
        self,
        window_query: dict[str, Any],
        locator: dict[str, Any],
        *,
        max_depth: int,
        max_elements: int,
    ) -> dict[str, Any]:
        try:
            dump = self.dump_elements(
                window_query,
                locator=locator,
                max_depth=max_depth,
                max_elements=min(max(1, int(max_elements)), 120),
                include_tree=False,
                include_selector_hints=True,
                text_limit=120,
            )
        except Exception as error:
            return {
                "ok": False,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        diagnostics = dump.get("diagnostics") if isinstance(dump.get("diagnostics"), dict) else {}
        return {
            "ok": bool(dump.get("ok")),
            "window": _compact_window_candidate(dump.get("window", {})) if isinstance(dump.get("window"), dict) else {},
            "locator": dict(locator),
            "total_count": int(dump.get("total_count", 0) or 0),
            "match_count": int(dump.get("match_count", 0) or 0),
            "near_matches": _compact_near_element_matches(dump.get("near_matches", [])),
            "recommendations": list(diagnostics.get("recommendations", []))[:5]
            if isinstance(diagnostics.get("recommendations"), list)
            else [],
        }

    def _list_windows_macos(self) -> list[dict[str, Any]]:
        script = """
        set rows to {}
        tell application "System Events"
          repeat with proc in application processes
            if background only of proc is false then
              set procName to name of proc
              set procFrontmost to frontmost of proc
              repeat with win in windows of proc
                set winName to name of win
                set winPosition to position of win
                set winSize to size of win
                set winX to item 1 of winPosition
                set winY to item 2 of winPosition
                set winWidth to item 1 of winSize
                set winHeight to item 2 of winSize
                set end of rows to procName & tab & winName & tab & procFrontmost & tab & winX & tab & winY & tab & winWidth & tab & winHeight
              end repeat
            end if
          end repeat
        end tell
        set AppleScript's text item delimiters to linefeed
        return rows as text
        """
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if completed.returncode != 0:
            self.last_window_list_error = completed.stderr.strip() or completed.stdout.strip()
            return []
        windows: list[dict[str, Any]] = []
        for index, line in enumerate(completed.stdout.splitlines()):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            app = parts[0].strip()
            title = parts[1].strip()
            focused = len(parts) >= 3 and parts[2].strip().lower() == "true"
            bounds: dict[str, int] = {}
            if len(parts) >= 7:
                try:
                    bounds = {
                        "x": int(float(parts[3].strip())),
                        "y": int(float(parts[4].strip())),
                        "width": int(float(parts[5].strip())),
                        "height": int(float(parts[6].strip())),
                    }
                except ValueError:
                    bounds = {}
            windows.append(
                {
                    "id": f"{app}:{index}",
                    "title": title,
                    "app": app,
                    "process_name": app,
                    "class_name": "",
                    "pid": None,
                    "bounds": bounds,
                    "visible": True,
                    "focused": focused,
                }
            )
        self.last_window_list_error = ""
        return windows

    def _display_info(self) -> dict[str, Any]:
        if self.platform_name == "windows":
            user32 = ctypes.windll.user32
            dpi = 0
            try:
                dpi = int(user32.GetDpiForSystem())
            except Exception:
                dpi = 0
            scale = round(dpi / 96, 4) if dpi > 0 else None
            return {
                "width": int(user32.GetSystemMetrics(0)),
                "height": int(user32.GetSystemMetrics(1)),
                "virtual_x": int(user32.GetSystemMetrics(76)),
                "virtual_y": int(user32.GetSystemMetrics(77)),
                "virtual_width": int(user32.GetSystemMetrics(78)),
                "virtual_height": int(user32.GetSystemMetrics(79)),
                "monitor_count": int(user32.GetSystemMetrics(80)),
                "dpi": {"x": dpi, "y": dpi} if dpi > 0 else {},
                "scale": scale,
            }
        try:
            import pyautogui

            size = pyautogui.size()
            return {"width": int(size.width), "height": int(size.height)}
        except Exception as error:
            return {"error": str(error)}


def _current_platform_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return system.lower() or "unknown"


def _trim_process_text(value: str | None, *, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"



















