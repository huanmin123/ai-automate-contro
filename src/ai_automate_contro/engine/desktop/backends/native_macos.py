from __future__ import annotations

import subprocess
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError
from ai_automate_contro.engine.desktop.backends.native_elements import _normalize_element, _safe_int


def _list_elements_macos(window: dict[str, Any], *, max_depth: int, max_elements: int) -> dict[str, Any]:
    app = str(window.get("app") or "")
    bounds = window.get("bounds") if isinstance(window.get("bounds"), dict) else {}
    if not app:
        raise DesktopBackendError("macOS 控件枚举需要窗口 app 字段。")
    target_window_script = _target_window_script_macos(window)
    normalized_max_depth = max(0, int(max_depth))
    normalized_max_elements = max(1, int(max_elements))
    script = f"""
    set outputLines to {{}}
    set maxElements to {normalized_max_elements}
    set maxDepth to {normalized_max_depth}

    using terms from application "System Events"
      on appendChildren(parentElement, parentPath, depthValue)
        global outputLines, maxElements, maxDepth
        if depthValue is greater than maxDepth then return
        try
          set childElements to UI elements of parentElement
        on error
          return
        end try
        set childCount to count of childElements
        repeat with childIndex from 1 to childCount
          if (count of outputLines) is greater than or equal to maxElements then exit repeat
          try
            set childElement to item childIndex of childElements
            if parentPath is "" then
              set childPath to childIndex as text
              set parentRuntimeId to "macos:window"
            else
              set childPath to parentPath & "." & (childIndex as text)
              set parentRuntimeId to "macos:" & parentPath
            end if
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
            set end of outputLines to (depthValue as text) & tab & ("macos:" & childPath) & tab & childName & tab & childRole & tab & "" & tab & childValue & tab & childEnabled & tab & (item 1 of childPosition) & tab & (item 2 of childPosition) & tab & (item 1 of childSize) & tab & (item 2 of childSize) & tab & parentRuntimeId
            if depthValue is less than maxDepth then
              my appendChildren(childElement, childPath, depthValue + 1)
            end if
          end try
          if (count of outputLines) is greater than or equal to maxElements then exit repeat
        end repeat
      end appendChildren
    end using terms from

    tell application "System Events"
      tell process {_applescript_text(app)}
        set frontmost to true
        {target_window_script}
        set winPosition to position of targetWindow
        set winSize to size of targetWindow
        set end of outputLines to "0" & tab & "macos:window" & tab & (name of targetWindow as text) & tab & "window" & tab & "" & tab & "" & tab & "true" & tab & (item 1 of winPosition) & tab & (item 2 of winPosition) & tab & (item 1 of winSize) & tab & (item 2 of winSize) & tab & ""
        if maxDepth > 0 then my appendChildren(targetWindow, "", 1)
      end tell
    end tell
    set AppleScript's text item delimiters to linefeed
    return outputLines as text
    """
    try:
        completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=15)
    except subprocess.TimeoutExpired as error:
        return {
            "ok": False,
            "elements": [_macos_window_element(window)],
            "count": 1,
            "truncated": True,
            "fallback_used": True,
            "diagnostics": {
                "reason": "macos_accessibility_timeout",
                "timeout_seconds": 15,
                "error": str(error),
            },
        }
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
        if len(elements) >= normalized_max_elements:
            break
    return {
        "ok": True,
        "elements": elements,
        "count": len(elements),
        "truncated": len(elements) >= normalized_max_elements,
    }


def _macos_window_element(window: dict[str, Any]) -> dict[str, Any]:
    bounds = window.get("bounds") if isinstance(window.get("bounds"), dict) else {}
    title = str(window.get("title") or "")
    return _normalize_element(
        {
            "id": "macos:window",
            "runtime_id": "macos:window",
            "name": title,
            "value": "",
            "text": title,
            "automation_id": "",
            "control_type": "window",
            "localized_control_type": "window",
            "role": "window",
            "class_name": "",
            "enabled": True,
            "visible": True,
            "focused": bool(window.get("focused")),
            "bounds": {
                "x": _safe_int(bounds.get("x"), default=0),
                "y": _safe_int(bounds.get("y"), default=0),
                "width": _safe_int(bounds.get("width"), default=0),
                "height": _safe_int(bounds.get("height"), default=0),
            },
            "depth": 0,
            "parent_id": "",
        },
        index=0,
    )


def _action_element_macos(
    window: dict[str, Any],
    element: dict[str, Any],
    *,
    operation: str,
    value: str = "",
) -> dict[str, Any]:
    app = str(window.get("app") or "")
    if not app:
        raise DesktopBackendError("macOS 控件操作需要窗口 app 字段。")
    runtime_id = str(element.get("runtime_id") or element.get("id") or "")
    element_path = ""
    if runtime_id.startswith("macos:"):
        element_path = runtime_id.split(":", 1)[1]
    if runtime_id != "macos:window" and not element_path:
        return {
            "ok": True,
            "operation": operation,
            "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
            "fallback_required": True,
            "fallback_error": f"macOS element runtime id is unavailable: {runtime_id}",
        }
    target_window_script = _target_window_script_macos(window)
    if runtime_id == "macos:window":
        target_element_line = "set targetElement to targetWindow"
    elif runtime_id.startswith("macos:flat:"):
        try:
            flat_index = int(runtime_id.split(":", 2)[2])
        except ValueError:
            flat_index = 0
        if flat_index <= 0:
            return {
                "ok": True,
                "operation": operation,
                "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
                "fallback_required": True,
                "fallback_error": f"macOS flat element runtime id is invalid: {runtime_id}",
            }
        target_element_line = f"""
        set allElements to entire contents of targetWindow
        set targetElement to item {flat_index} of allElements
        """
    else:
        path_indexes: list[int] = []
        try:
            path_indexes = [int(part) for part in element_path.split(".") if part]
        except ValueError:
            path_indexes = []
        if not path_indexes or any(index <= 0 for index in path_indexes):
            return {
                "ok": True,
                "operation": operation,
                "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
                "fallback_required": True,
                "fallback_error": f"macOS element runtime path is invalid: {runtime_id}",
            }
        target_lines = ["set targetElement to targetWindow"]
        target_lines.extend(f"set targetElement to UI element {index} of targetElement" for index in path_indexes)
        target_element_line = "\n        ".join(target_lines)
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
        {target_window_script}
        {target_element_line}
        {operation_script}
      end tell
    end tell
    return {_applescript_text(operation)} & tab & methodText & tab & fallbackRequired & tab & fallbackError
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "macOS Accessibility action failed"
        if _is_target_window_selection_error(message):
            raise DesktopBackendError(message)
        return {
            "ok": True,
            "operation": operation,
            "method": "bounds_click_fallback" if operation == "invoke" else "keyboard_clipboard_fallback",
            "fallback_required": True,
            "fallback_error": message,
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
    app = str(window.get("app") or "")
    if not app:
        raise DesktopBackendError("macOS 聚焦窗口需要 app 字段。")
    target_window_script = _target_window_script_macos(window)
    title = str(window.get("title") or "")
    focus_verification_script = ""
    if title:
        focus_verification_script = f"""
        set frontWindowName to ""
        try
          set frontWindowName to name of window 1 as text
        on error frontError
          error "macOS focus verification failed: " & frontError
        end try
        if frontWindowName is not {_applescript_text(title)} then error "macOS focus verification mismatch: " & frontWindowName
        """
    script = f"""
    tell application "System Events"
      tell process {_applescript_text(app)}
        set frontmost to true
        {target_window_script}
        set focusSucceeded to false
        set raiseErrorText to ""
        set mainErrorText to ""
        try
          perform action "AXRaise" of targetWindow
          set focusSucceeded to true
        on error raiseError
          set raiseErrorText to raiseError as text
        end try
        try
          set value of attribute "AXMain" of targetWindow to true
          set focusSucceeded to true
        on error mainError
          set mainErrorText to mainError as text
        end try
        if focusSucceeded is false then error "macOS focus failed: " & raiseErrorText & " | " & mainErrorText
        {focus_verification_script}
      end tell
    end tell
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        raise DesktopBackendError(completed.stderr.strip() or completed.stdout.strip() or "macOS activate failed")


def _control_window_macos(window: dict[str, Any], operation: str) -> None:
    app = str(window.get("app") or "")
    if not app:
        raise DesktopBackendError("macOS 窗口控制需要 app 字段。")
    target_window_script = _target_window_script_macos(window)
    if operation == "close":
        operation_script = """
        set originalTitle to ""
        try
          set originalTitle to name of targetWindow as text
        end try
        set closeErrorText to ""
        try
          if exists (first button of targetWindow whose subrole is "AXCloseButton") then
            try
              perform action "AXPress" of (first button of targetWindow whose subrole is "AXCloseButton")
            on error
              click (first button of targetWindow whose subrole is "AXCloseButton")
            end try
          else
            click button 1 of targetWindow
          end if
        on error closeError
          set closeErrorText to closeError as text
        end try
        if closeErrorText is not "" then
          if originalTitle is "" then error "macOS window close failed: " & closeErrorText
          try
            set targetWindow to first window whose name is originalTitle
            keystroke "w" using command down
          on error fallbackError
            error "macOS window close failed: " & closeErrorText & " | " & fallbackError
          end try
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
        {target_window_script}
        {operation_script}
      end tell
    end tell
    """
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "macOS window control failed"
        raise DesktopBackendError(message)


def _target_window_script_macos(window: dict[str, Any]) -> str:
    title = str(window.get("title") or "")
    window_index = _safe_int(window.get("window_index"), default=0)
    title_guard = ""
    if title:
        title_guard = f"""
        try
          set selectedWindowName to name of targetWindow as text
        on error nameError
          error "selected macOS window title unavailable: " & nameError
        end try
        if selectedWindowName is not {_applescript_text(title)} then error "selected macOS window title mismatch: " & selectedWindowName
        """
    if window_index > 0:
        return f"""
        set targetWindow to window {window_index}
        {title_guard}
        """
    if title:
        return f"set targetWindow to first window whose name is {_applescript_text(title)}"
    return "set targetWindow to window 1"


def _is_target_window_selection_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "selected macos window title mismatch" in normalized
        or "selected macos window title unavailable" in normalized
        or "can't get window" in normalized
        or "can’t get window" in normalized
    )


def _applescript_text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
