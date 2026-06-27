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


class NativeDesktopBackend:
    backend_name = "native"

    def __init__(self, *, platform_name: str | None = None) -> None:
        self.platform_name = platform_name or _current_platform_name()
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
        dependencies = desktop_dependencies()
        pyautogui_available = dependencies.get("pyautogui", False)
        if pyautogui_available:
            permissions["input_control"] = "available_or_not_required"
        capability_matrix = build_capability_matrix(
            platform_name=self.platform_name,
            backend_name=self.backend_name,
            source="probe",
            permissions=permissions,
            dependencies=dependencies,
            window_list_error=window_error or self.last_window_list_error,
        )
        return {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "permissions": permissions,
            "dependencies": dependencies,
            "capability_matrix": capability_matrix,
            "display": self._display_info(),
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
            "include_cursor": include_cursor,
        }

    def snapshot(self, *, include_windows: bool = True, include_displays: bool = True) -> dict[str, Any]:
        dependencies = desktop_dependencies()
        payload: dict[str, Any] = {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "dependencies": dependencies,
        }
        if include_displays:
            payload["display"] = self._display_info()
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
            if state == "exists" and last_matches:
                return {"ok": True, "state": state, "window": last_matches[0], "matches": last_matches}
            if state == "not_exists" and not last_matches:
                return {"ok": True, "state": state, "window": None, "matches": []}
            if state == "focused" and any(bool(window.get("focused")) for window in last_matches):
                focused = next(window for window in last_matches if bool(window.get("focused")))
                return {"ok": True, "state": state, "window": focused, "matches": last_matches}
            if time.monotonic() >= deadline:
                diagnostics = _window_diagnostics(last_windows, query, last_matches)
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
            return {
                "width": int(user32.GetSystemMetrics(0)),
                "height": int(user32.GetSystemMetrics(1)),
                "virtual_width": int(user32.GetSystemMetrics(78)),
                "virtual_height": int(user32.GetSystemMetrics(79)),
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


_WINDOWS_UIA_LIST_ELEMENTS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object 'System.Collections.Generic.Queue[object]'
$queue.Enqueue([pscustomobject]@{ Element = $root; Depth = 0; Parent = '' })
$result = New-Object System.Collections.ArrayList
while ($queue.Count -gt 0 -and $result.Count -lt $maxElements) {
  $item = $queue.Dequeue()
  $element = $item.Element
  try {
    $current = $element.Current
    $rect = $current.BoundingRectangle
    $runtimeId = ''
    try { $runtimeId = ($element.GetRuntimeId() -join '.') } catch {}
    $value = ''
    try {
      $patternObj = $null
      if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
        $value = [string]$patternObj.Current.Value
      }
    } catch {}
    $controlType = ''
    try {
      $controlType = [string]$current.ControlType.ProgrammaticName
      $controlType = $controlType -replace '^ControlType\.', ''
    } catch {}
    $obj = [ordered]@{
      id = $runtimeId
      runtime_id = $runtimeId
      name = [string]$current.Name
      value = $value
      text = $(if ($value) { $value } else { [string]$current.Name })
      automation_id = [string]$current.AutomationId
      control_type = $controlType
      localized_control_type = [string]$current.LocalizedControlType
      role = $controlType
      class_name = [string]$current.ClassName
      enabled = [bool]$current.IsEnabled
      visible = -not [bool]$current.IsOffscreen
      focused = [bool]$current.HasKeyboardFocus
      bounds = @{
        x = [int][Math]::Round($rect.X)
        y = [int][Math]::Round($rect.Y)
        width = [int][Math]::Round($rect.Width)
        height = [int][Math]::Round($rect.Height)
      }
      depth = [int]$item.Depth
      parent_id = [string]$item.Parent
    }
    [void]$result.Add($obj)
    if ($item.Depth -lt $maxDepth) {
      $child = $walker.GetFirstChild($element)
      while ($null -ne $child) {
        $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = $runtimeId })
        $child = $walker.GetNextSibling($child)
      }
    }
  } catch {}
}
[ordered]@{
  ok = $true
  elements = $result
  count = $result.Count
  truncated = ($queue.Count -gt 0)
} | ConvertTo-Json -Depth 8 -Compress
"""


_WINDOWS_UIA_ACTION_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$locator = $payload.locator
if ($null -eq $locator) { $locator = [pscustomobject]@{} }
$operation = [string]$payload.operation
$value = [string]$payload.value
$runtimeId = [string]$payload.runtime_id
$optionIndex = $null
if ($null -ne $payload.option_index) {
  try { $optionIndex = [int]$payload.option_index } catch { $optionIndex = $null }
}
$matchIndex = 0
try { $matchIndex = [int]$locator.element_match_index } catch {}

function Get-PropText($obj, [string]$name) {
  $prop = $obj.PSObject.Properties[$name]
  if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
  return [string]$prop.Value
}

function Test-RegexValue([string]$pattern, [string]$value) {
  if ([string]::IsNullOrEmpty($pattern)) { return $true }
  try { return [regex]::IsMatch($value, $pattern) } catch { return $false }
}

function Test-TypeMatch($obj, [string]$expected) {
  if ([string]::IsNullOrEmpty($expected)) { return $true }
  $expectedLower = $expected.ToLowerInvariant()
  foreach ($field in @('control_type', 'localized_control_type', 'role')) {
    $candidate = (Get-PropText $obj $field).ToLowerInvariant()
    if ($candidate -eq $expectedLower -or $candidate.Contains($expectedLower)) { return $true }
  }
  return $false
}

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Get-UiaValue([System.Windows.Automation.AutomationElement]$element) {
  try {
    $patternObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
      return [string]$patternObj.Current.Value
    }
  } catch {}
  return ''
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $uiaValue = Get-UiaValue $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = $uiaValue
    text = $(if ($uiaValue) { $uiaValue } else { [string]$current.Name })
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = [int][Math]::Round($rect.X)
      y = [int][Math]::Round($rect.Y)
      width = [int][Math]::Round($rect.Width)
      height = [int][Math]::Round($rect.Height)
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Test-LocatorMatch($obj, $locator) {
  $names = $locator.PSObject.Properties.Name
  if ($names -contains 'element_id' -and (Get-PropText $obj 'id') -ne [string]$locator.element_id) { return $false }
  if ($names -contains 'automation_id' -and (Get-PropText $obj 'automation_id') -ne [string]$locator.automation_id) { return $false }
  if ($names -contains 'name' -and (Get-PropText $obj 'name') -ne [string]$locator.name) { return $false }
  if ($names -contains 'name_contains' -and -not (Get-PropText $obj 'name').Contains([string]$locator.name_contains)) { return $false }
  if ($names -contains 'name_regex' -and -not (Test-RegexValue ([string]$locator.name_regex) (Get-PropText $obj 'name'))) { return $false }
  $elementText = Get-PropText $obj 'text'
  if ($names -contains 'text' -and $elementText -ne [string]$locator.text) { return $false }
  if ($names -contains 'text_contains' -and -not $elementText.Contains([string]$locator.text_contains)) { return $false }
  if ($names -contains 'text_regex' -and -not (Test-RegexValue ([string]$locator.text_regex) $elementText)) { return $false }
  if ($names -contains 'control_type' -and -not (Test-TypeMatch $obj ([string]$locator.control_type))) { return $false }
  if ($names -contains 'role' -and -not (Test-TypeMatch $obj ([string]$locator.role))) { return $false }
  if ($names -contains 'element_class_name') {
    $expected = ([string]$locator.element_class_name).ToLowerInvariant()
    $actual = (Get-PropText $obj 'class_name').ToLowerInvariant()
    if (-not $actual.Contains($expected)) { return $false }
  }
  return $true
}

function Test-OptionMatch($obj, [string]$optionValue, $optionIndex, [int]$matchOrder) {
  if ($null -ne $optionIndex -and $matchOrder -eq [int]$optionIndex) { return $true }
  if ([string]::IsNullOrEmpty($optionValue)) { return $false }
  $name = Get-PropText $obj 'name'
  $text = Get-PropText $obj 'text'
  $valueText = Get-PropText $obj 'value'
  return $name -eq $optionValue -or $text -eq $optionValue -or $valueText -eq $optionValue
}

function Find-OptionElement(
  [System.Windows.Automation.AutomationElement]$rootElement,
  [string]$optionValue,
  $optionIndex,
  [int]$maxDepth,
  [int]$maxElements
) {
  $optionControlTypes = @(
    [System.Windows.Automation.ControlType]::ListItem,
    [System.Windows.Automation.ControlType]::DataItem,
    [System.Windows.Automation.ControlType]::MenuItem,
    [System.Windows.Automation.ControlType]::TreeItem
  )
  $optionWalker = [System.Windows.Automation.TreeWalker]::RawViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $rootElement; Depth = 0; Parent = '' })
  $visited = 0
  $candidateIndex = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
      $visited += 1
      $controlType = $element.Current.ControlType
      $isOptionType = $optionControlTypes -contains $controlType
      if ($isOptionType -and (Test-OptionMatch $obj $optionValue $optionIndex $candidateIndex)) {
        return [pscustomobject]@{ Element = $element; Payload = $obj }
      }
      if ($isOptionType) { $candidateIndex += 1 }
      if ($item.Depth -lt $maxDepth) {
        $child = $optionWalker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
          $child = $optionWalker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object 'System.Collections.Generic.Queue[object]'
$queue.Enqueue([pscustomobject]@{ Element = $root; Depth = 0; Parent = '' })
$selectedElement = $null
$selectedPayload = $null
$matched = 0
$visited = 0
while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
  $item = $queue.Dequeue()
  $element = $item.Element
  try {
    $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
    $visited += 1
    $isRuntimeMatch = -not [string]::IsNullOrEmpty($runtimeId) -and [string]$obj.runtime_id -eq $runtimeId
    if ($isRuntimeMatch -or (Test-LocatorMatch $obj $locator)) {
      if ($isRuntimeMatch -or $matched -eq $matchIndex) {
        $selectedElement = $element
        $selectedPayload = $obj
        break
      }
      $matched += 1
    }
    if ($item.Depth -lt $maxDepth) {
      $child = $walker.GetFirstChild($element)
      while ($null -ne $child) {
        $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
        $child = $walker.GetNextSibling($child)
      }
    }
  } catch {}
}
if ($null -eq $selectedElement) { throw "UIAutomation element not found: locator=$($locator | ConvertTo-Json -Compress)" }

$method = ''
$fallbackRequired = $false
$fallbackError = ''
if ($operation -eq 'invoke') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$patternObj)) {
      $patternObj.Invoke()
      $method = 'uia_invoke_pattern'
    } else {
      $fallbackRequired = $true
      $method = 'bounds_click_fallback'
      $fallbackError = 'InvokePattern unavailable'
    }
  } catch {
    $fallbackRequired = $true
    $method = 'bounds_click_fallback'
    $fallbackError = $_.Exception.Message
  }
} elseif ($operation -eq 'set_text') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
      if ([bool]$patternObj.Current.IsReadOnly) {
        $fallbackRequired = $true
        $method = 'keyboard_clipboard_fallback'
        $fallbackError = 'ValuePattern is read-only'
      } else {
        $patternObj.SetValue($value)
        $method = 'uia_value_pattern'
      }
    } else {
      $fallbackRequired = $true
      $method = 'keyboard_clipboard_fallback'
      $fallbackError = 'ValuePattern unavailable'
    }
  } catch {
    $fallbackRequired = $true
    $method = 'keyboard_clipboard_fallback'
    $fallbackError = $_.Exception.Message
  }
} elseif ($operation -eq 'select') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$patternObj) -and [string]::IsNullOrEmpty($value) -and $null -eq $optionIndex) {
      $patternObj.Select()
      $method = 'uia_selection_item_pattern'
    } else {
      $expandObj = $null
      try {
        if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
          if ($expandObj.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded) {
            $expandObj.Expand()
            Start-Sleep -Milliseconds 150
          }
        }
      } catch {}
      $optionMatch = Find-OptionElement $selectedElement $value $optionIndex ([Math]::Min($maxDepth, 4)) $maxElements
      if ($null -eq $optionMatch) {
        $optionMatch = Find-OptionElement $root $value $optionIndex ([Math]::Min($maxDepth, 6)) $maxElements
      }
      if ($null -eq $optionMatch) {
        $fallbackRequired = $true
        $method = 'bounds_click_fallback'
        $fallbackError = 'Selection option not found'
      } else {
        $selectedPayload = $optionMatch.Payload
        $optionPatternObj = $null
        if ($optionMatch.Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$optionPatternObj)) {
          $optionPatternObj.Select()
          $method = 'uia_selection_item_pattern'
        } else {
          $invokeObj = $null
          if ($optionMatch.Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokeObj)) {
            $invokeObj.Invoke()
            $method = 'uia_invoke_option_pattern'
          } else {
            $fallbackRequired = $true
            $method = 'bounds_click_fallback'
            $fallbackError = 'SelectionItemPattern unavailable'
          }
        }
      }
    }
  } catch {
    $fallbackRequired = $true
    $method = 'bounds_click_fallback'
    $fallbackError = $_.Exception.Message
  }
} else {
  throw "Unsupported UIAutomation operation: $operation"
}

[ordered]@{
  ok = $true
  operation = $operation
  method = $method
  fallback_required = $fallbackRequired
  fallback_error = $fallbackError
  element = $selectedPayload
} | ConvertTo-Json -Depth 8 -Compress
"""


def _run_powershell_json(script: str, payload: dict[str, Any], *, timeout: int = 15) -> dict[str, Any]:
    stdin = json.dumps(payload, ensure_ascii=False)
    command_script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
        + script
    )
    last_error = ""
    for executable in ("pwsh", "powershell"):
        try:
            completed = subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", command_script],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            last_error = str(error)
            continue
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"PowerShell 桌面控件探测超时：timeout={timeout}s") from error
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0:
            message = stderr.strip() or stdout.strip() or f"{executable} failed"
            raise DesktopBackendError(message)
        try:
            parsed = json.loads(stdout.strip() or "{}")
        except json.JSONDecodeError as error:
            raise DesktopBackendError(f"PowerShell 返回的控件 JSON 无法解析：{stdout[:500]}") from error
        if not isinstance(parsed, dict):
            raise DesktopBackendError("PowerShell 返回的控件 JSON 必须是对象。")
        return parsed
    raise DesktopBackendError(f"未找到 PowerShell，无法使用 Windows UIAutomation：{last_error}")


def _list_elements_windows(hwnd: int, *, max_depth: int, max_elements: int) -> dict[str, Any]:
    payload = _run_powershell_json(
        _WINDOWS_UIA_LIST_ELEMENTS_SCRIPT,
        {"window_id": hwnd, "max_depth": max_depth, "max_elements": max_elements},
    )
    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        elements = []
    return {
        "ok": True,
        "elements": [_normalize_element(element, index=index) for index, element in enumerate(elements) if isinstance(element, dict)],
        "count": len(elements),
        "truncated": bool(payload.get("truncated", False)),
    }


def _action_element_windows(
    hwnd: int,
    locator: dict[str, Any],
    *,
    operation: str,
    value: str = "",
    option_index: int | None = None,
    runtime_id: str = "",
    max_depth: int,
    max_elements: int,
) -> dict[str, Any]:
    return _run_powershell_json(
        _WINDOWS_UIA_ACTION_ELEMENT_SCRIPT,
        {
            "window_id": hwnd,
            "locator": locator,
            "operation": operation,
            "value": value,
            "option_index": option_index,
            "runtime_id": runtime_id,
            "max_depth": max(0, int(max_depth)),
            "max_elements": max(1, int(max_elements)),
        },
    )


def _list_elements_macos(window: dict[str, Any], *, max_depth: int, max_elements: int) -> dict[str, Any]:
    app = str(window.get("app") or "")
    title = str(window.get("title") or "")
    bounds = window.get("bounds") if isinstance(window.get("bounds"), dict) else {}
    if not app:
        raise DesktopBackendError("macOS 控件枚举需要窗口 app 字段。")
    target_line = (
        f"set targetWindow to first window whose name is {_applescript_text(title)}"
        if title
        else "set targetWindow to window 1"
    )
    script = f"""
    set rows to {{}}
    tell application "System Events"
      tell process {_applescript_text(app)}
        set frontmost to true
        {target_line}
        set winPosition to position of targetWindow
        set winSize to size of targetWindow
        set end of rows to "0" & tab & "macos:window" & tab & (name of targetWindow as text) & tab & "window" & tab & "" & tab & "" & tab & "true" & tab & (item 1 of winPosition) & tab & (item 2 of winPosition) & tab & (item 1 of winSize) & tab & (item 2 of winSize) & tab & ""
        if {int(max_depth)} > 0 then
          set childIndex to 0
          repeat with childElement in UI elements of targetWindow
            if childIndex is greater than or equal to {int(max_elements) - 1} then exit repeat
            set childIndex to childIndex + 1
            set childName to ""
            set childRole to ""
            set childValue to ""
            set childEnabled to "true"
            set childPosition to {{0, 0}}
            set childSize to {{0, 0}}
            try
              set childName to name of childElement as text
            end try
            try
              set childRole to role of childElement as text
            end try
            try
              set childValue to value of childElement as text
            end try
            try
              set childEnabled to enabled of childElement as text
            end try
            try
              set childPosition to position of childElement
              set childSize to size of childElement
            end try
            set end of rows to "1" & tab & ("macos:" & childIndex) & tab & childName & tab & childRole & tab & "" & tab & childValue & tab & childEnabled & tab & (item 1 of childPosition) & tab & (item 2 of childPosition) & tab & (item 1 of childSize) & tab & (item 2 of childSize) & tab & "macos:window"
          end repeat
        end if
      end tell
    end tell
    set AppleScript's text item delimiters to linefeed
    return rows as text
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=15)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "macOS Accessibility 控件枚举失败"
        raise DesktopBackendError(message)
    elements: list[dict[str, Any]] = []
    for index, line in enumerate(completed.stdout.splitlines()):
        parts = line.split("\t")
        if len(parts) < 11:
            continue
        depth = _safe_int(parts[0], default=0)
        element_id = parts[1].strip() or f"macos:{index}"
        name = parts[2].strip()
        role = parts[3].strip()
        value = parts[5].strip()
        enabled = parts[6].strip().lower() != "false"
        element_bounds = {
            "x": _safe_int(parts[7], default=int(bounds.get("x", 0) or 0)),
            "y": _safe_int(parts[8], default=int(bounds.get("y", 0) or 0)),
            "width": _safe_int(parts[9], default=int(bounds.get("width", 0) or 0)),
            "height": _safe_int(parts[10], default=int(bounds.get("height", 0) or 0)),
        }
        parent_id = parts[11].strip() if len(parts) >= 12 else ""
        elements.append(
            _normalize_element(
                {
                    "id": element_id,
                    "runtime_id": element_id,
                    "name": name,
                    "value": value,
                    "text": value or name,
                    "automation_id": "",
                    "control_type": role,
                    "localized_control_type": role,
                    "role": role,
                    "class_name": "",
                    "enabled": enabled,
                    "visible": True,
                    "focused": bool(window.get("focused")) if depth == 0 else False,
                    "bounds": element_bounds,
                    "depth": depth,
                    "parent_id": parent_id,
                },
                index=index,
            )
        )
        if len(elements) >= max_elements:
            break
    return {"ok": True, "elements": elements, "count": len(elements), "truncated": len(elements) >= max_elements}


def _action_element_macos(
    window: dict[str, Any],
    element: dict[str, Any],
    *,
    operation: str,
    value: str = "",
) -> dict[str, Any]:
    app = str(window.get("app") or "")
    title = str(window.get("title") or "")
    if not app:
        raise DesktopBackendError("macOS 控件操作需要窗口 app 字段。")
    runtime_id = str(element.get("runtime_id") or element.get("id") or "")
    element_index: int | None = None
    if runtime_id.startswith("macos:"):
        try:
            element_index = int(runtime_id.split(":", 1)[1])
        except ValueError:
            element_index = None
    if element_index is None:
        return {
            "ok": True,
            "operation": operation,
            "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
            "fallback_required": True,
            "fallback_error": f"macOS element runtime id is unavailable: {runtime_id}",
        }
    target_line = (
        f"set targetWindow to first window whose name is {_applescript_text(title)}"
        if title
        else "set targetWindow to window 1"
    )
    if element_index <= 0:
        target_element_line = "set targetElement to targetWindow"
    else:
        target_element_line = f"set targetElement to UI element {element_index} of targetWindow"
    if operation == "invoke":
        operation_script = """
        try
          perform action "AXPress" of targetElement
          set methodText to "ax_press"
        on error pressError
          try
            click targetElement
            set methodText to "ax_click"
          on error clickError
            set fallbackRequired to "true"
            set methodText to "bounds_click_fallback"
            set fallbackError to pressError & " | " & clickError
          end try
        end try
        """
    elif operation == "select":
        operation_script = """
        try
          perform action "AXPress" of targetElement
          set methodText to "ax_press"
        on error pressError
          try
            click targetElement
            set methodText to "ax_click"
          on error clickError
            set fallbackRequired to "true"
            set methodText to "bounds_click_fallback"
            set fallbackError to pressError & " | " & clickError
          end try
        end try
        """
    elif operation == "set_text":
        operation_script = f"""
        try
          set value of targetElement to {_applescript_text(value)}
          set methodText to "ax_set_value"
        on error setError
          try
            set focused of targetElement to true
          end try
          set fallbackRequired to "true"
          set methodText to "keyboard_clipboard_fallback"
          set fallbackError to setError
        end try
        """
    else:
        raise DesktopBackendError(f"不支持的 macOS 控件操作：{operation}")
    script = f"""
    set fallbackRequired to "false"
    set fallbackError to ""
    set methodText to ""
    tell application "System Events"
      tell process {_applescript_text(app)}
        set frontmost to true
        {target_line}
        {target_element_line}
        {operation_script}
      end tell
    end tell
    return {_applescript_text(operation)} & tab & methodText & tab & fallbackRequired & tab & fallbackError
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        return {
            "ok": True,
            "operation": operation,
            "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
            "fallback_required": True,
            "fallback_error": completed.stderr.strip() or completed.stdout.strip() or "macOS Accessibility action failed",
        }
    parts = (completed.stdout.strip() or "").split("\t")
    fallback_required = len(parts) >= 3 and parts[2].strip().lower() == "true"
    return {
        "ok": True,
        "operation": parts[0].strip() if parts else operation,
        "method": parts[1].strip() if len(parts) >= 2 else "",
        "fallback_required": fallback_required,
        "fallback_error": parts[3].strip() if len(parts) >= 4 else "",
    }


def _normalize_element(element: dict[str, Any], *, index: int) -> dict[str, Any]:
    bounds = element.get("bounds") if isinstance(element.get("bounds"), dict) else {}
    normalized_bounds = {
        "x": _safe_int(bounds.get("x"), default=0),
        "y": _safe_int(bounds.get("y"), default=0),
        "width": _safe_int(bounds.get("width"), default=0),
        "height": _safe_int(bounds.get("height"), default=0),
    }
    element_id = str(element.get("id") or element.get("runtime_id") or f"element:{index}")
    return {
        "id": element_id,
        "runtime_id": str(element.get("runtime_id") or element_id),
        "name": str(element.get("name") or ""),
        "value": str(element.get("value") or ""),
        "text": str(element.get("text") or element.get("value") or element.get("name") or ""),
        "automation_id": str(element.get("automation_id") or ""),
        "control_type": str(element.get("control_type") or ""),
        "localized_control_type": str(element.get("localized_control_type") or ""),
        "role": str(element.get("role") or element.get("control_type") or ""),
        "class_name": str(element.get("class_name") or ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": normalized_bounds,
        "depth": _safe_int(element.get("depth"), default=0),
        "parent_id": str(element.get("parent_id") or ""),
    }


def _matching_elements(elements: list[dict[str, Any]], locator: dict[str, Any]) -> list[dict[str, Any]]:
    return [element for element in elements if _element_matches(element, locator)]


def _select_option_element(
    elements: list[dict[str, Any]],
    *,
    option_value: str,
    option_index: int | None,
) -> dict[str, Any]:
    candidates = [
        element
        for element in elements
        if _element_type_matches_any(element, {"listitem", "dataitem", "menuitem", "treeitem", "text"})
    ]
    if option_index is not None and 0 <= option_index < len(candidates):
        return dict(candidates[option_index])
    if option_value:
        for element in candidates:
            if option_value in {str(element.get("name") or ""), str(element.get("text") or ""), str(element.get("value") or "")}:
                return dict(element)
    return {}


def _element_type_matches_any(element: dict[str, Any], expected_values: set[str]) -> bool:
    candidates = (
        str(element.get("control_type", "")),
        str(element.get("localized_control_type", "")),
        str(element.get("role", "")),
    )
    return any(candidate.lower() in expected_values for candidate in candidates if candidate)


def _diagnostic_element(
    element: dict[str, Any],
    *,
    index: int,
    all_elements: list[dict[str, Any]],
    matched: bool,
    include_selector_hints: bool,
    text_limit: int,
) -> dict[str, Any]:
    text = _limit_text(_element_text(element), text_limit)
    diagnostic = {
        "index": index,
        "id": str(element.get("id") or ""),
        "runtime_id": str(element.get("runtime_id") or ""),
        "parent_id": str(element.get("parent_id") or ""),
        "depth": _safe_int(element.get("depth"), default=0),
        "name": _limit_text(str(element.get("name") or ""), text_limit),
        "value": _limit_text(str(element.get("value") or ""), text_limit),
        "text": text,
        "automation_id": str(element.get("automation_id") or ""),
        "control_type": str(element.get("control_type") or ""),
        "localized_control_type": str(element.get("localized_control_type") or ""),
        "role": str(element.get("role") or ""),
        "class_name": str(element.get("class_name") or ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": element.get("bounds") if isinstance(element.get("bounds"), dict) else {},
        "matched": bool(matched),
    }
    if include_selector_hints:
        diagnostic["selector_hints"] = _selector_hints_for_element(element, all_elements)
    return diagnostic


def _selector_hints_for_element(element: dict[str, Any], all_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    automation_id = str(element.get("automation_id") or "")
    name = str(element.get("name") or "")
    text = _element_text(element)
    control_type = str(element.get("control_type") or "")
    role = str(element.get("role") or control_type or "")
    class_name = str(element.get("class_name") or "")
    element_id = str(element.get("id") or "")

    if automation_id:
        candidates.append({"locator": {"automation_id": automation_id}, "stability": "high"})
        if control_type:
            candidates.append({"locator": {"automation_id": automation_id, "control_type": control_type}, "stability": "high"})
    if name:
        locator = {"name": name}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "medium"})
    if text and text != name:
        locator = {"text": text}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "medium"})
    if role and role != control_type:
        candidates.append({"locator": {"role": role, "name": name} if name else {"role": role}, "stability": "medium"})
    if class_name:
        locator = {"element_class_name": class_name}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "low"})
    if element_id:
        candidates.append({"locator": {"element_id": element_id}, "stability": "session"})

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        locator = candidate.get("locator") if isinstance(candidate.get("locator"), dict) else {}
        if not locator:
            continue
        key = json.dumps(locator, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        matches = _matching_elements(all_elements, locator)
        enriched = {
            **candidate,
            "match_count": len(matches),
            "unique": len(matches) == 1,
        }
        unique.append(enriched)
    unique.sort(key=lambda item: (_stability_rank(str(item.get("stability") or "")), 0 if item.get("unique") else 1, int(item.get("match_count", 0))))
    return unique[:8]


def _near_matches_for_locator(elements: list[dict[str, Any]], locator: dict[str, Any]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for element in elements:
        score, matched_fields, missing_fields, reasons = _locator_match_score(element, locator)
        if score <= 0:
            continue
        scored.append(
            {
                "score": score,
                "matched_fields": matched_fields,
                "missing_fields": missing_fields,
                "reasons": reasons,
                "element": _near_match_element(element),
            }
        )
    scored.sort(key=lambda item: (-int(item.get("score", 0)), len(item.get("missing_fields", []))))
    return scored[:8]


def _locator_match_score(element: dict[str, Any], locator: dict[str, Any]) -> tuple[int, list[str], list[str], list[str]]:
    checks: list[tuple[str, bool, str]] = []
    if "element_id" in locator:
        checks.append(("element_id", str(element.get("id")) == str(locator.get("element_id")), "element_id differs"))
    if "automation_id" in locator:
        checks.append(
            ("automation_id", str(element.get("automation_id")) == str(locator.get("automation_id")), "automation_id differs")
        )
    if "name" in locator:
        checks.append(("name", str(element.get("name", "")) == str(locator.get("name")), "name differs"))
    if "name_contains" in locator:
        checks.append(
            ("name_contains", str(locator.get("name_contains")) in str(element.get("name", "")), "name does not contain expected text")
        )
    if "name_regex" in locator:
        checks.append(
            ("name_regex", _regex_matches(str(locator.get("name_regex")), str(element.get("name", ""))), "name_regex does not match")
        )
    element_text = _element_text(element)
    if "text" in locator:
        checks.append(("text", element_text == str(locator.get("text")), "text differs"))
    if "text_contains" in locator:
        checks.append(("text_contains", str(locator.get("text_contains")) in element_text, "text does not contain expected text"))
    if "text_regex" in locator:
        checks.append(("text_regex", _regex_matches(str(locator.get("text_regex")), element_text), "text_regex does not match"))
    if "control_type" in locator:
        checks.append(
            ("control_type", _element_type_matches(element, str(locator.get("control_type"))), "control_type differs")
        )
    if "role" in locator:
        checks.append(("role", _element_type_matches(element, str(locator.get("role"))), "role differs"))
    if "element_class_name" in locator:
        expected = str(locator.get("element_class_name")).lower()
        checks.append(
            (
                "element_class_name",
                expected in str(element.get("class_name", "")).lower(),
                "element_class_name differs",
            )
        )
    matched_fields = [field for field, ok, _reason in checks if ok]
    missing_fields = [field for field, ok, _reason in checks if not ok]
    reasons = [reason for _field, ok, reason in checks if not ok]
    score = len(matched_fields) * 10 - len(missing_fields) * 2
    if not checks and "element_match_index" in locator:
        score = 1
        reasons.append("element_match_index alone is not a stable selector")
    return score, matched_fields, missing_fields, reasons


def _near_match_element(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": element.get("index", 0),
        "id": element.get("id", ""),
        "name": element.get("name", ""),
        "text": element.get("text", ""),
        "automation_id": element.get("automation_id", ""),
        "control_type": element.get("control_type", ""),
        "role": element.get("role", ""),
        "class_name": element.get("class_name", ""),
        "bounds": element.get("bounds", {}),
        "selector_hints": element.get("selector_hints", []),
    }


def _element_dump_limitations(platform_name: str) -> list[str]:
    if platform_name == "macos":
        return [
            "macOS native backend currently enumerates the target window and its direct UI elements.",
            "Accessibility permission is required for AX element data.",
        ]
    if platform_name == "windows":
        return [
            "Windows runtime_id is only stable within the current UIA session; prefer automation_id/name/control_type hints.",
        ]
    return [f"Desktop element dump is not specialized for platform={platform_name}."]


def _element_dump_recommendations(
    *,
    locator: dict[str, Any],
    match_count: int,
    near_matches: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    if not locator:
        recommendations.append("Use selector_hints from a unique target element to build a stable Element Locator.")
        recommendations.append("Prefer automation_id + control_type when available; use element_id only for same-session debugging.")
        return recommendations
    if match_count == 0:
        recommendations.append("No exact element matched the locator; inspect near_matches for the closest controls.")
        if near_matches:
            recommendations.append("Start from the first near_match.selector_hints entry marked unique=true.")
    elif match_count > 1:
        recommendations.append("Locator is ambiguous; add automation_id, control_type, role, name, or text to make it unique.")
    else:
        recommendations.append("Locator matched one element; prefer a selector_hints entry with stability=high or unique=true.")
    if set(locator.keys()) <= {"element_match_index"}:
        recommendations.append("element_match_index alone is order-dependent and should not be used as a durable selector.")
    return recommendations


def _element_tree(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for element in elements:
        element_id = str(element.get("id") or element.get("runtime_id") or f"element:{element.get('index', len(nodes_by_id))}")
        node = {
            "id": element_id,
            "index": element.get("index", 0),
            "name": element.get("name", ""),
            "text": element.get("text", ""),
            "control_type": element.get("control_type", ""),
            "role": element.get("role", ""),
            "automation_id": element.get("automation_id", ""),
            "bounds": element.get("bounds", {}),
            "matched": bool(element.get("matched", False)),
            "children": [],
        }
        nodes_by_id[element_id] = node
    for element in elements:
        element_id = str(element.get("id") or element.get("runtime_id") or "")
        node = nodes_by_id.get(element_id)
        if node is None:
            continue
        parent_id = str(element.get("parent_id") or "")
        parent = nodes_by_id.get(parent_id)
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def _select_element(elements: list[dict[str, Any]], locator: dict[str, Any]) -> dict[str, Any] | None:
    match_index = int(locator.get("element_match_index", 0) or 0)
    if not elements:
        return None
    if match_index >= len(elements):
        return None
    return dict(elements[match_index])


def _element_matches(element: dict[str, Any], locator: dict[str, Any]) -> bool:
    if "element_id" in locator and str(element.get("id")) != str(locator.get("element_id")):
        return False
    if "automation_id" in locator and str(element.get("automation_id")) != str(locator.get("automation_id")):
        return False
    if "name" in locator and str(element.get("name", "")) != str(locator.get("name")):
        return False
    if "name_contains" in locator and str(locator.get("name_contains")) not in str(element.get("name", "")):
        return False
    if "name_regex" in locator and not _regex_matches(str(locator.get("name_regex")), str(element.get("name", ""))):
        return False
    element_text = _element_text(element)
    if "text" in locator and element_text != str(locator.get("text")):
        return False
    if "text_contains" in locator and str(locator.get("text_contains")) not in element_text:
        return False
    if "text_regex" in locator and not _regex_matches(str(locator.get("text_regex")), element_text):
        return False
    if "control_type" in locator and not _element_type_matches(element, str(locator.get("control_type"))):
        return False
    if "role" in locator and not _element_type_matches(element, str(locator.get("role"))):
        return False
    if "element_class_name" in locator:
        expected = str(locator.get("element_class_name")).lower()
        if expected not in str(element.get("class_name", "")).lower():
            return False
    return True


def _element_type_matches(element: dict[str, Any], expected: str) -> bool:
    expected_text = expected.lower()
    candidates = (
        str(element.get("control_type", "")),
        str(element.get("localized_control_type", "")),
        str(element.get("role", "")),
    )
    return any(candidate.lower() == expected_text or expected_text in candidate.lower() for candidate in candidates)


def _element_state_matches(element: dict[str, Any] | None, state: str) -> bool:
    if state == "not_exists":
        return element is None
    if element is None:
        return False
    if state == "exists":
        return True
    if state == "enabled":
        return bool(element.get("enabled"))
    if state == "disabled":
        return not bool(element.get("enabled", True))
    if state == "focused":
        return bool(element.get("focused"))
    return False


def _element_text(element: dict[str, Any]) -> str:
    for field in ("text", "value", "name"):
        value = str(element.get(field) or "")
        if value:
            return value
    return ""


def _regex_matches(pattern: str, value: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


def _limit_text(value: str, limit: int) -> str:
    text = str(value or "")
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _stability_rank(value: str) -> int:
    ranks = {"high": 0, "medium": 1, "low": 2, "session": 3}
    return ranks.get(value, 9)


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _list_windows_windows(*, include_invisible: bool) -> list[dict[str, Any]]:
    user32 = ctypes.windll.user32
    foreground = user32.GetForegroundWindow()
    windows: list[dict[str, Any]] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not include_invisible and not user32.IsWindowVisible(hwnd):
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        title = title_buffer.value.strip()
        if not title:
            return True
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = _process_name_windows(int(pid.value))
        windows.append(
            {
                "id": int(hwnd),
                "title": title,
                "app": process_name,
                "process_name": process_name,
                "class_name": class_buffer.value,
                "pid": int(pid.value),
                "bounds": {
                    "x": int(rect.left),
                    "y": int(rect.top),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                },
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "focused": int(hwnd) == int(foreground),
            }
        )
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return windows


def _process_name_windows(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(4096)
        size = ctypes.c_ulong(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _focus_window_windows(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    if user32.SetForegroundWindow(hwnd) or int(user32.GetForegroundWindow()) == int(hwnd):
        return

    current_thread = int(kernel32.GetCurrentThreadId())
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    foreground = user32.GetForegroundWindow()
    foreground_thread = int(user32.GetWindowThreadProcessId(foreground, None)) if foreground else 0
    attached_threads: list[int] = []
    for thread_id in {target_thread, foreground_thread}:
        if thread_id and thread_id != current_thread and user32.AttachThreadInput(current_thread, thread_id, True):
            attached_threads.append(thread_id)
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        if user32.SetForegroundWindow(hwnd):
            return
        time.sleep(0.05)
        if int(user32.GetForegroundWindow()) == int(hwnd):
            return
    finally:
        for thread_id in attached_threads:
            user32.AttachThreadInput(current_thread, thread_id, False)
    if int(user32.GetForegroundWindow()) != int(hwnd):
        raise DesktopBackendError(f"SetForegroundWindow 失败：window_id={hwnd}")


def _control_window_windows(hwnd: int, operation: str) -> None:
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        raise DesktopBackendError(f"窗口不存在：window_id={hwnd}")
    if operation == "close":
        WM_CLOSE = 0x0010
        if not user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            raise DesktopBackendError(f"PostMessageW(WM_CLOSE) 失败：window_id={hwnd}")
        return
    show_commands = {
        "minimize": 6,
        "maximize": 3,
        "restore": 9,
    }
    command = show_commands.get(operation)
    if command is None:
        raise DesktopBackendError(f"不支持的 Windows 窗口控制操作：{operation}")
    user32.ShowWindow(hwnd, command)


def _focus_window_macos(window: dict[str, Any]) -> None:
    app = str(window.get("app") or "").replace('"', '\\"')
    if not app:
        raise DesktopBackendError("macOS 聚焦窗口需要 app 字段。")
    script = f'tell application "{app}" to activate'
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        raise DesktopBackendError(completed.stderr.strip() or completed.stdout.strip() or "macOS activate failed")


def _control_window_macos(window: dict[str, Any], operation: str) -> None:
    app = str(window.get("app") or "")
    title = str(window.get("title") or "")
    if not app:
        raise DesktopBackendError("macOS 窗口控制需要 app 字段。")
    target_line = (
        f"set targetWindow to first window whose name is {_applescript_text(title)}"
        if title
        else "set targetWindow to window 1"
    )
    if operation == "close":
        operation_script = """
        if exists (first button of targetWindow whose subrole is "AXCloseButton") then
          click (first button of targetWindow whose subrole is "AXCloseButton")
        else
          click button 1 of targetWindow
        end if
        """
    elif operation == "minimize":
        operation_script = 'set value of attribute "AXMinimized" of targetWindow to true'
    elif operation == "restore":
        operation_script = 'set value of attribute "AXMinimized" of targetWindow to false'
    elif operation == "maximize":
        operation_script = """
        if exists (first button of targetWindow whose subrole is "AXZoomButton") then
          click (first button of targetWindow whose subrole is "AXZoomButton")
        else
          perform action "AXZoomWindow" of targetWindow
        end if
        """
    else:
        raise DesktopBackendError(f"不支持的 macOS 窗口控制操作：{operation}")
    script = f"""
    tell application "System Events"
      tell process {_applescript_text(app)}
        set frontmost to true
        {target_line}
        {operation_script}
      end tell
    end tell
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "macOS window control failed"
        raise DesktopBackendError(message)


def _applescript_text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _matching_windows(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    return [window for window in windows if _window_matches(window, query)]


def _window_diagnostics(
    windows: list[dict[str, Any]],
    query: dict[str, Any],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query": dict(query),
        "total_windows": len(windows),
        "match_count": len(matches),
        "matches": [_compact_window_candidate(window) for window in matches[:5]],
        "near_matches": _near_window_matches(windows, query),
    }


def _near_window_matches(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for window in windows:
        score, matched_fields, missing_fields = _window_match_score(window, query)
        scored.append(
            {
                "score": score,
                "matched_fields": matched_fields,
                "missing_fields": missing_fields,
                "window": _compact_window_candidate(window),
            }
        )
    scored.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            len(item.get("missing_fields", [])),
            not bool(item.get("window", {}).get("focused")),
        )
    )
    return scored[:5]


def _window_match_score(window: dict[str, Any], query: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    checks: list[tuple[str, bool]] = []
    if "window_id" in query:
        checks.append(("window_id", str(window.get("id")) == str(query.get("window_id"))))
    if "title" in query:
        checks.append(("title", str(window.get("title", "")) == str(query.get("title"))))
    if "title_contains" in query:
        checks.append(("title_contains", str(query.get("title_contains")) in str(window.get("title", ""))))
    if "title_regex" in query:
        checks.append(("title_regex", _regex_matches(str(query.get("title_regex")), str(window.get("title", "")))))
    for query_field, window_field in (
        ("app", "app"),
        ("process", "process_name"),
        ("process_name", "process_name"),
        ("class_name", "class_name"),
    ):
        if query_field in query:
            checks.append(
                (
                    query_field,
                    str(query.get(query_field)).lower() in str(window.get(window_field, "")).lower(),
                )
            )
    matched_fields = [field for field, ok in checks if ok]
    missing_fields = [field for field, ok in checks if not ok]
    score = len(matched_fields) * 10 - len(missing_fields) * 2
    if bool(window.get("focused")):
        score += 1
    return score, matched_fields, missing_fields


def _compact_window_candidate(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": window.get("id", ""),
        "title": _limit_text(str(window.get("title", "")), 120),
        "app": window.get("app", ""),
        "process_name": window.get("process_name", ""),
        "class_name": window.get("class_name", ""),
        "focused": bool(window.get("focused")),
        "visible": bool(window.get("visible", True)),
        "bounds": window.get("bounds", {}),
    }


def _compact_near_element_matches(raw_near_matches: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_near_matches, list):
        return []
    compacted: list[dict[str, Any]] = []
    for item in raw_near_matches[:5]:
        if not isinstance(item, dict):
            continue
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        selector_hints = element.get("selector_hints", []) if isinstance(element, dict) else []
        compacted.append(
            {
                "score": item.get("score", 0),
                "matched_fields": item.get("matched_fields", []),
                "missing_fields": item.get("missing_fields", []),
                "reasons": item.get("reasons", []),
                "element": {
                    **_near_match_element(element),
                    "selector_hints": selector_hints[:3] if isinstance(selector_hints, list) else [],
                },
            }
        )
    return compacted


def _window_matches(window: dict[str, Any], query: dict[str, Any]) -> bool:
    if "window_id" in query and str(window.get("id")) != str(query.get("window_id")):
        return False
    if "title" in query and str(window.get("title", "")) != str(query.get("title")):
        return False
    if "title_contains" in query and str(query.get("title_contains")) not in str(window.get("title", "")):
        return False
    if "title_regex" in query and not re.search(str(query.get("title_regex")), str(window.get("title", ""))):
        return False
    for query_field, window_field in (
        ("app", "app"),
        ("process", "process_name"),
        ("process_name", "process_name"),
        ("class_name", "class_name"),
    ):
        if query_field in query and str(query.get(query_field)).lower() not in str(window.get(window_field, "")).lower():
            return False
    return True


def _region_to_bbox(region: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not region:
        return None
    x = int(region["x"])
    y = int(region["y"])
    width = int(region["width"])
    height = int(region["height"])
    return (x, y, x + width, y + height)


def _normalized_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": str(payload.get("operation") or ""),
        "method": str(payload.get("method") or ""),
        "fallback_required": bool(payload.get("fallback_required", False)),
    }
    if payload.get("fallback_error") not in (None, ""):
        result["fallback_error"] = str(payload.get("fallback_error"))
    native_element = payload.get("element")
    if isinstance(native_element, dict):
        result["action_element"] = _normalize_element(native_element, index=0)
    return result
