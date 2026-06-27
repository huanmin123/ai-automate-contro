from __future__ import annotations

import platform
import time
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError


def require_pyautogui() -> Any:
    try:
        import pyautogui
    except Exception as error:
        raise DesktopBackendError(
            "desktop_input 需要可选依赖 pyautogui。请安装桌面控制依赖后重试：pip install pyautogui pyperclip"
        ) from error
    pyautogui.FAILSAFE = True
    return pyautogui


def paste_text_with_clipboard(text: str, *, preserve_clipboard: bool) -> None:
    pyautogui = require_pyautogui()
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
        time.sleep(0.1)
    finally:
        if preserve_clipboard:
            try:
                pyperclip.copy(old_text)
            except Exception:
                pass


def click_element_center(element: dict[str, Any], *, locator: dict[str, Any], button: str = "left") -> tuple[int, int]:
    bounds = element.get("bounds") if isinstance(element, dict) else None
    if not isinstance(bounds, dict):
        raise DesktopBackendError(f"控件缺少 bounds，无法点击：locator={locator}")
    width = int(bounds.get("width", 0) or 0)
    height = int(bounds.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        raise DesktopBackendError(f"控件 bounds 无效，无法点击：bounds={bounds}")
    x = int(bounds.get("x", 0) or 0) + width // 2
    y = int(bounds.get("y", 0) or 0) + height // 2
    pyautogui = require_pyautogui()
    pyautogui.click(x=x, y=y, button=button)
    return x, y


def set_element_text_keyboard_fallback(
    element: dict[str, Any],
    text: str,
    *,
    locator: dict[str, Any],
    preserve_clipboard: bool,
) -> dict[str, Any]:
    x, y = click_element_center(element, locator=locator)
    pyautogui = require_pyautogui()
    select_key = "command" if platform.system() == "Darwin" else "ctrl"
    time.sleep(0.05)
    pyautogui.hotkey(select_key, "a")
    paste_text_with_clipboard(text, preserve_clipboard=preserve_clipboard)
    return {
        "method": "keyboard_clipboard_fallback",
        "x": x,
        "y": y,
        "preserve_clipboard": bool(preserve_clipboard),
    }


def select_element_keyboard_fallback(
    element: dict[str, Any],
    option_index: int,
    *,
    locator: dict[str, Any],
) -> dict[str, Any]:
    x, y = click_element_center(element, locator=locator)
    pyautogui = require_pyautogui()
    time.sleep(0.05)
    pyautogui.press("home")
    for _ in range(max(0, int(option_index))):
        pyautogui.press("down")
    pyautogui.press("enter")
    return {
        "method": "keyboard_select_fallback",
        "x": x,
        "y": y,
    }
