from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError
from ai_automate_contro.engine.desktop.backends.native_elements import _normalize_element
from ai_automate_contro.engine.desktop.backends.native_windows_scripts import (
    _WINDOWS_UIA_ACTION_ELEMENT_SCRIPT,
    _WINDOWS_UIA_LIST_ELEMENTS_SCRIPT,
    _WINDOWS_UIA_MENU_ELEMENT_SCRIPT,
    _WINDOWS_UIA_SCROLL_ELEMENT_SCRIPT,
    _WINDOWS_UIA_TABLE_ELEMENT_SCRIPT,
    _WINDOWS_UIA_TREE_ELEMENT_SCRIPT,
)


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


def _table_element_windows(
    hwnd: int,
    locator: dict[str, Any],
    *,
    operation: str,
    runtime_id: str = "",
    row: int = 0,
    column: str = "",
    column_index: int | None = None,
    max_depth: int,
    max_elements: int,
    max_rows: int = 50,
    max_columns: int = 20,
    text_limit: int = 160,
    visible_only: bool = True,
) -> dict[str, Any]:
    return _run_powershell_json(
        _WINDOWS_UIA_TABLE_ELEMENT_SCRIPT,
        {
            "window_id": hwnd,
            "locator": locator,
            "operation": operation,
            "runtime_id": runtime_id,
            "row": max(0, int(row)),
            "column": str(column or ""),
            "column_index": column_index,
            "max_depth": max(0, int(max_depth)),
            "max_elements": max(1, int(max_elements)),
            "max_rows": max(1, int(max_rows)),
            "max_columns": max(1, int(max_columns)),
            "text_limit": max(0, int(text_limit)),
            "visible_only": bool(visible_only),
        },
    )


def _tree_element_windows(
    hwnd: int,
    locator: dict[str, Any],
    *,
    operation: str,
    runtime_id: str = "",
    tree_path: list[str] | None = None,
    max_depth: int,
    max_elements: int,
    max_nodes: int = 200,
    text_limit: int = 160,
) -> dict[str, Any]:
    return _run_powershell_json(
        _WINDOWS_UIA_TREE_ELEMENT_SCRIPT,
        {
            "window_id": hwnd,
            "locator": locator,
            "operation": operation,
            "runtime_id": runtime_id,
            "tree_path": [str(part) for part in (tree_path or [])],
            "max_depth": max(0, int(max_depth)),
            "max_elements": max(1, int(max_elements)),
            "max_nodes": max(1, int(max_nodes)),
            "text_limit": max(0, int(text_limit)),
        },
    )


def _menu_element_windows(
    hwnd: int,
    *,
    menu_path: list[str],
    search_global: bool = False,
    max_depth: int,
    max_elements: int,
) -> dict[str, Any]:
    return _run_powershell_json(
        _WINDOWS_UIA_MENU_ELEMENT_SCRIPT,
        {
            "window_id": hwnd,
            "menu_path": [str(part) for part in menu_path],
            "search_global": bool(search_global),
            "max_depth": max(0, int(max_depth)),
            "max_elements": max(1, int(max_elements)),
        },
    )


def _scroll_element_windows(
    hwnd: int,
    locator: dict[str, Any],
    *,
    runtime_id: str = "",
    amount: int | None = None,
    scroll_to: str = "",
    max_depth: int,
    max_elements: int,
) -> dict[str, Any]:
    return _run_powershell_json(
        _WINDOWS_UIA_SCROLL_ELEMENT_SCRIPT,
        {
            "window_id": hwnd,
            "locator": locator,
            "runtime_id": runtime_id,
            "amount": amount,
            "scroll_to": str(scroll_to or ""),
            "max_depth": max(0, int(max_depth)),
            "max_elements": max(1, int(max_elements)),
        },
    )


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


def _window_from_point_windows(x: int, y: int) -> dict[str, Any]:
    user32 = ctypes.windll.user32
    point = ctypes.wintypes.POINT(int(x), int(y))
    user32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
    user32.WindowFromPoint.restype = ctypes.wintypes.HWND
    user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.wintypes.HWND
    hwnd = user32.WindowFromPoint(point)
    hwnd_int = _hwnd_to_int(hwnd)
    if not hwnd_int:
        return {
            "ok": False,
            "available": True,
            "platform": "windows",
            "backend": "native",
            "point": {"x": int(x), "y": int(y)},
            "reason": "no_window_at_point",
        }
    root_hwnd = user32.GetAncestor(hwnd, 2)
    root_owner_hwnd = user32.GetAncestor(hwnd, 3)
    return {
        "ok": True,
        "available": True,
        "platform": "windows",
        "backend": "native",
        "point": {"x": int(x), "y": int(y)},
        "window": _window_info_windows(hwnd_int),
        "root_window": _window_info_windows(_hwnd_to_int(root_hwnd) or hwnd_int),
        "root_owner_window": _window_info_windows(_hwnd_to_int(root_owner_hwnd) or _hwnd_to_int(root_hwnd) or hwnd_int),
    }


def _window_info_windows(hwnd: int) -> dict[str, Any]:
    user32 = ctypes.windll.user32
    hwnd_int = int(hwnd or 0)
    if not hwnd_int or not user32.IsWindow(hwnd_int):
        return {}
    title_length = user32.GetWindowTextLengthW(hwnd_int)
    title = ""
    if title_length > 0:
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd_int, title_buffer, title_length + 1)
        title = title_buffer.value.strip()
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd_int, class_buffer, 256)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd_int, ctypes.byref(rect))
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd_int, ctypes.byref(pid))
    process_name = _process_name_windows(int(pid.value))
    return {
        "id": hwnd_int,
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
        "visible": bool(user32.IsWindowVisible(hwnd_int)),
        "focused": int(hwnd_int) == int(user32.GetForegroundWindow()),
    }


def _hwnd_to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, ctypes.c_void_p):
        return int(value.value or 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    _raise_window_z_order_windows(hwnd)
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
        _raise_window_z_order_windows(hwnd)
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


def _raise_window_z_order_windows(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    HWND_TOPMOST = ctypes.c_void_p(-1)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)


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
