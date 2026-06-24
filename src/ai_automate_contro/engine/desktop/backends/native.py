from __future__ import annotations

import ctypes
import ctypes.wintypes
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError


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
        pyautogui_available = _module_available("pyautogui")
        if pyautogui_available:
            permissions["input_control"] = "available_or_not_required"
        return {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "permissions": permissions,
            "dependencies": {
                "Pillow.ImageGrab": _module_available("PIL.ImageGrab"),
                "pyautogui": pyautogui_available,
                "pyperclip": _module_available("pyperclip"),
            },
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
        payload: dict[str, Any] = {
            "platform": self.platform_name,
            "system": platform.system(),
            "backend": self.backend_name,
            "dependencies": {
                "Pillow.ImageGrab": _module_available("PIL.ImageGrab"),
                "pyautogui": _module_available("pyautogui"),
                "pyperclip": _module_available("pyperclip"),
            },
        }
        if include_displays:
            payload["display"] = self._display_info()
        if include_windows:
            try:
                payload["windows"] = self.list_windows()
            except Exception as error:
                payload["windows"] = []
                payload["window_list_error"] = str(error)
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
        while True:
            windows = self.list_windows()
            last_matches = _matching_windows(windows, query)
            if state == "exists" and last_matches:
                return {"ok": True, "state": state, "window": last_matches[0], "matches": last_matches}
            if state == "not_exists" and not last_matches:
                return {"ok": True, "state": state, "window": None, "matches": []}
            if state == "focused" and any(bool(window.get("focused")) for window in last_matches):
                focused = next(window for window in last_matches if bool(window.get("focused")))
                return {"ok": True, "state": state, "window": focused, "matches": last_matches}
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待窗口超时：state={state} query={query} matches={len(last_matches)}")
            time.sleep(max(0.001, interval_ms / 1000))

    def close(self) -> None:
        return None

    def _select_window(self, query: dict[str, Any]) -> dict[str, Any]:
        windows = self.list_windows()
        matches = _matching_windows(windows, query)
        if not matches:
            raise DesktopBackendError(f"未找到匹配窗口：{query}")
        match_index = int(query.get("match_index", 0) or 0)
        if match_index >= len(matches):
            raise DesktopBackendError(f"窗口匹配索引超出范围：match_index={match_index} matches={len(matches)}")
        return dict(matches[match_index])

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


def _focus_window_macos(window: dict[str, Any]) -> None:
    app = str(window.get("app") or "").replace('"', '\\"')
    if not app:
        raise DesktopBackendError("macOS 聚焦窗口需要 app 字段。")
    script = f'tell application "{app}" to activate'
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        raise DesktopBackendError(completed.stderr.strip() or completed.stdout.strip() or "macOS activate failed")


def _matching_windows(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    return [window for window in windows if _window_matches(window, query)]


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


def _require_pyautogui() -> Any:
    try:
        import pyautogui
    except Exception as error:
        raise DesktopBackendError(
            "desktop_input 需要可选依赖 pyautogui。请安装桌面控制依赖后重试：pip install pyautogui pyperclip"
        ) from error
    pyautogui.FAILSAFE = True
    return pyautogui


def _paste_text_with_clipboard(text: str, *, preserve_clipboard: bool) -> None:
    pyautogui = _require_pyautogui()
    try:
        import pyperclip
    except Exception as error:
        raise DesktopBackendError("desktop_input.method=clipboard 需要可选依赖 pyperclip。") from error
    old_text = ""
    if preserve_clipboard:
        try:
            old_text = pyperclip.paste()
        except Exception:
            old_text = ""
    try:
        pyperclip.copy(text)
        paste_key = "command" if platform.system() == "Darwin" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
    finally:
        if preserve_clipboard:
            try:
                pyperclip.copy(old_text)
            except Exception:
                pass


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False
