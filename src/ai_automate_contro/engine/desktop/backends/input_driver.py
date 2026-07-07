from __future__ import annotations

import subprocess
import time
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError
from ai_automate_contro.support.platforms import current_platform_name, normalize_platform_name, primary_modifier_for_platform


MACOS_KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "return": 36,
    "enter": 36,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "tab": 48,
    "space": 49,
    "`": 50,
    "delete": 51,
    "backspace": 51,
    "esc": 53,
    "escape": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}
MACOS_MODIFIER_KEYS = {
    "command": "command down",
    "cmd": "command down",
    "ctrl": "control down",
    "control": "control down",
    "option": "option down",
    "alt": "option down",
    "shift": "shift down",
}
PRIMARY_MODIFIER_ALIASES = {
    "cmd_or_ctrl",
    "command_or_control",
    "control_or_command",
    "mod",
    "primary",
    "shortcut",
}
OPTION_ALT_ALIASES = {"alt_or_option", "option_or_alt"}
COMMON_KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
}


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
        send_hotkey(["primary", "v"])
        time.sleep(0.2)
    finally:
        if preserve_clipboard:
            try:
                pyperclip.copy(old_text)
            except Exception:
                pass


def send_hotkey(keys: list[str]) -> dict[str, Any]:
    platform_name = current_platform_name()
    normalized_keys = _normalize_hotkey_keys(keys, platform_name=platform_name)
    if platform_name == "macos":
        if _send_hotkey_macos(normalized_keys):
            return {"ok": True, "keys": normalized_keys, "method": "macos_system_events"}
    pyautogui = require_pyautogui()
    pyautogui.hotkey(*normalized_keys)
    return {"ok": True, "keys": normalized_keys, "method": "pyautogui"}


def _normalize_hotkey_keys(keys: list[str], *, platform_name: str | None = None) -> list[str]:
    normalized: list[str] = []
    for key in keys:
        raw = str(key or "").strip().lower()
        if not raw:
            continue
        parts = [part.strip() for part in raw.replace("+", " ").split() if part.strip()]
        normalized.extend(_normalize_hotkey_alias(part, platform_name=platform_name) for part in (parts or [raw]))
    if not normalized:
        raise DesktopBackendError("desktop_input.hotkey keys 不能为空。")
    return normalized


def _normalize_hotkey_alias(key: str, *, platform_name: str | None = None) -> str:
    if key in PRIMARY_MODIFIER_ALIASES:
        return primary_modifier_for_platform(platform_name)
    if key in OPTION_ALT_ALIASES:
        selected_platform = normalize_platform_name(platform_name) if platform_name else current_platform_name()
        return "option" if selected_platform == "macos" else "alt"
    return COMMON_KEY_ALIASES.get(key, key)


def _send_hotkey_macos(keys: list[str]) -> bool:
    modifiers: list[str] = []
    key_code: int | None = None
    for key in keys:
        if key in MACOS_MODIFIER_KEYS:
            modifiers.append(MACOS_MODIFIER_KEYS[key])
            continue
        if key not in MACOS_KEY_CODES:
            return False
        if key_code is not None:
            return False
        key_code = MACOS_KEY_CODES[key]
    if key_code is None:
        return False
    using_clause = ""
    if modifiers:
        unique_modifiers = list(dict.fromkeys(modifiers))
        if len(unique_modifiers) == 1:
            using_clause = f" using {unique_modifiers[0]}"
        else:
            using_clause = " using {" + ", ".join(unique_modifiers) + "}"
    script = f'tell application "System Events" to key code {key_code}{using_clause}'
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False, timeout=10)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "macOS hotkey failed"
        raise DesktopBackendError(message)
    time.sleep(0.08)
    return True


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
    time.sleep(0.05)
    send_hotkey(["primary", "a"])
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
