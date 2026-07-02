from __future__ import annotations

import subprocess
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError
from ai_automate_contro.engine.desktop.backends.native_elements import _normalize_element, _safe_int


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
