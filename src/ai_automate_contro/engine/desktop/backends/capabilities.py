from __future__ import annotations

from typing import Any


def module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def desktop_dependencies() -> dict[str, bool]:
    return {
        "Pillow.ImageGrab": module_available("PIL.ImageGrab"),
        "opencv-python": module_available("cv2"),
        "pyautogui": module_available("pyautogui"),
        "pyperclip": module_available("pyperclip"),
    }


def build_capability_matrix(
    *,
    platform_name: str,
    backend_name: str,
    source: str = "runtime",
    permissions: dict[str, Any] | None = None,
    dependencies: dict[str, bool] | None = None,
    window_list_error: str = "",
) -> dict[str, Any]:
    deps = dict(dependencies or desktop_dependencies())
    perms = dict(permissions or {})
    platform_supported = platform_name in {"windows", "macos"}
    windowing_available = platform_supported and not str(window_list_error or "").strip()
    input_available = bool(deps.get("pyautogui"))
    screenshot_available = bool(deps.get("Pillow.ImageGrab"))
    image_locator_available = screenshot_available and bool(deps.get("opencv-python"))
    clipboard_available = bool(deps.get("pyperclip"))
    advanced_semantic_available = windowing_available and platform_name == "windows"
    semantic = {
        "window_list": windowing_available,
        "elements": windowing_available,
        "get_text": windowing_available,
        "get_state": windowing_available,
        "set_text": windowing_available,
        "select": windowing_available,
        "invoke": windowing_available,
        "get_table": advanced_semantic_available,
        "select_cell": advanced_semantic_available,
        "get_tree": advanced_semantic_available,
        "expand_tree": advanced_semantic_available,
        "collapse_tree": advanced_semantic_available,
        "select_tree": advanced_semantic_available,
        "invoke_menu": advanced_semantic_available,
        "scroll_element": advanced_semantic_available,
    }
    input_control = {
        "keyboard": input_available,
        "mouse": input_available,
        "clipboard": clipboard_available,
        "hotkey": input_available,
        "drag": input_available,
        "scroll": input_available,
    }
    screenshot = {
        "full_screen": screenshot_available,
        "region": screenshot_available,
        "annotation": screenshot_available,
    }
    return {
        "schema_version": 1,
        "platform": platform_name,
        "backend": backend_name,
        "source": str(source or "runtime"),
        "capabilities": {
            "semantic": semantic,
            "input": input_control,
            "screenshot": screenshot,
            "vision": {
                "image_locator": image_locator_available,
                "template_matching": image_locator_available,
                "ocr": False,
            },
        },
        "permissions": {
            "accessibility": perms.get("accessibility", "unknown"),
            "screen_recording": perms.get("screen_recording", "unknown"),
            "input_control": perms.get("input_control", "unknown"),
        },
        "dependencies": deps,
        "limitations": _capability_limitations(
            platform_name=platform_name,
            input_available=input_available,
            screenshot_available=screenshot_available,
            image_locator_available=image_locator_available,
            clipboard_available=clipboard_available,
            window_list_error=window_list_error,
        ),
    }


def _capability_limitations(
    *,
    platform_name: str,
    input_available: bool,
    screenshot_available: bool,
    image_locator_available: bool,
    clipboard_available: bool,
    window_list_error: str,
) -> list[str]:
    limitations: list[str] = []
    if platform_name not in {"windows", "macos"}:
        limitations.append(f"unsupported_platform:{platform_name}")
    if window_list_error:
        limitations.append("window_list_unavailable")
    if not input_available:
        limitations.append("pyautogui_missing")
    if not screenshot_available:
        limitations.append("pillow_imagegrab_missing")
    if not image_locator_available:
        limitations.append("opencv_missing_for_image_locator")
    if not clipboard_available:
        limitations.append("pyperclip_missing")
    if platform_name == "macos":
        limitations.append("macos_tcc_permissions_may_require_user_approval")
    return limitations
