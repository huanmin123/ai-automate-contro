from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


TESSERACT_PATH_ENV = "AI_AUTOMATE_TESSERACT_PATH"
TESSDATA_DIR_ENV = "AI_AUTOMATE_TESSDATA_DIR"


def module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def desktop_dependencies(desktop_config: dict[str, Any] | None = None) -> dict[str, bool]:
    return {
        "Pillow.ImageGrab": module_available("PIL.ImageGrab"),
        "opencv-python": module_available("cv2"),
        "pytesseract": module_available("pytesseract"),
        "tesseract": resolve_tesseract_binary(desktop_config) is not None,
        "tessdata.eng": tesseract_language_available("eng", desktop_config),
        "tessdata.chi_sim": tesseract_language_available("chi_sim", desktop_config),
        "pyautogui": module_available("pyautogui"),
        "pyperclip": module_available("pyperclip"),
    }


def resolve_tesseract_binary(desktop_config: dict[str, Any] | None = None) -> str | None:
    details = tesseract_binary_details(desktop_config)
    path = str(details.get("path") or "")
    return path or None


def tesseract_binary_details(desktop_config: dict[str, Any] | None = None) -> dict[str, Any]:
    ocr_config = normalize_ocr_config(desktop_config)
    configured_path = str(ocr_config.get("tesseract_path") or "").strip()
    if configured_path:
        binary = _resolve_binary_candidate(configured_path)
        return {
            "available": binary is not None,
            "path": binary or "",
            "source": "config.desktop.ocr.tesseract_path",
            "configured_path": configured_path,
            "tessdata_dir": resolve_tessdata_dir(desktop_config) or "",
        }

    env_path = str(os.environ.get(TESSERACT_PATH_ENV) or "").strip()
    if env_path:
        binary = _resolve_binary_candidate(env_path)
        return {
            "available": binary is not None,
            "path": binary or "",
            "source": TESSERACT_PATH_ENV,
            "configured_path": env_path,
            "tessdata_dir": resolve_tessdata_dir(desktop_config) or "",
        }

    path_binary = shutil.which("tesseract")
    if path_binary:
        return {
            "available": True,
            "path": path_binary,
            "source": "PATH",
            "configured_path": "",
            "tessdata_dir": resolve_tessdata_dir(desktop_config) or "",
        }

    registry_binary = _resolve_tesseract_from_windows_registry_path()
    if registry_binary:
        return {
            "available": True,
            "path": registry_binary,
            "source": "windows_registry_path",
            "configured_path": "",
            "tessdata_dir": resolve_tessdata_dir(desktop_config) or "",
        }

    common_binary = _resolve_tesseract_from_common_locations()
    return {
        "available": common_binary is not None,
        "path": common_binary or "",
        "source": "common_install_location" if common_binary else "",
        "configured_path": "",
        "tessdata_dir": resolve_tessdata_dir(desktop_config) or "",
    }


def normalize_ocr_config(desktop_config: dict[str, Any] | None = None) -> dict[str, str]:
    if not isinstance(desktop_config, dict):
        return {}
    raw: dict[str, Any] = desktop_config
    desktop_section = raw.get("desktop")
    if isinstance(desktop_section, dict):
        raw = desktop_section
    ocr_section = raw.get("ocr")
    if isinstance(ocr_section, dict):
        raw = ocr_section
    normalized: dict[str, str] = {}
    for key in ("tesseract_path", "tessdata_dir", "default_language"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def resolve_tessdata_dir(desktop_config: dict[str, Any] | None = None) -> str | None:
    ocr_config = normalize_ocr_config(desktop_config)
    configured_dir = str(ocr_config.get("tessdata_dir") or "").strip()
    if configured_dir:
        return str(Path(configured_dir).expanduser())
    env_dir = str(os.environ.get(TESSDATA_DIR_ENV) or "").strip()
    if env_dir:
        return str(Path(env_dir).expanduser())
    return None


def tesseract_common_options(desktop_config: dict[str, Any] | None = None) -> list[str]:
    tessdata_dir = resolve_tessdata_dir(desktop_config)
    return ["--tessdata-dir", tessdata_dir] if tessdata_dir else []


def tesseract_language_available(language: str, desktop_config: dict[str, Any] | None = None) -> bool:
    binary = resolve_tesseract_binary(desktop_config)
    if not binary:
        return False
    try:
        completed = subprocess.run(
            [binary, "--list-langs", *tesseract_common_options(desktop_config)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return False
    languages = set((completed.stdout + "\n" + completed.stderr).split())
    required_languages = _split_tesseract_languages(language)
    return bool(required_languages) and all(item in languages for item in required_languages)


def _split_tesseract_languages(language: str) -> list[str]:
    return [item.strip() for item in str(language or "").replace(",", "+").split("+") if item.strip()]


def _resolve_binary_candidate(raw_path: str) -> str | None:
    candidate = Path(raw_path).expanduser()
    if candidate.is_dir():
        candidate = candidate / _tesseract_executable_name()
    if candidate.exists() and candidate.is_file():
        return str(candidate.resolve())
    if platform.system() == "Windows" and candidate.suffix == "":
        exe_candidate = candidate.with_suffix(".exe")
        if exe_candidate.exists() and exe_candidate.is_file():
            return str(exe_candidate.resolve())
    found = shutil.which(raw_path)
    return found or None


def _resolve_tesseract_from_windows_registry_path() -> str | None:
    if platform.system() != "Windows":
        return None
    for entry in _windows_registry_path_entries():
        candidate = Path(entry) / _tesseract_executable_name()
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
    return None


def _windows_registry_path_entries() -> list[str]:
    try:
        import winreg
    except Exception:
        return []
    locations = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    entries: list[str] = []
    for hive, subkey in locations:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _value_type = winreg.QueryValueEx(key, "Path")
        except Exception:
            continue
        for raw_entry in str(value or "").split(";"):
            entry = os.path.expandvars(raw_entry.strip().strip('"'))
            if entry:
                entries.append(entry)
    return entries


def _resolve_tesseract_from_common_locations() -> str | None:
    if platform.system() != "Windows":
        return None
    for directory in (
        Path("C:/Program Files/Tesseract-OCR"),
        Path("C:/Program Files (x86)/Tesseract-OCR"),
    ):
        candidate = directory / _tesseract_executable_name()
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
    return None


def _tesseract_executable_name() -> str:
    return "tesseract.exe" if platform.system() == "Windows" else "tesseract"


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
    ocr_available = screenshot_available and bool(deps.get("tesseract")) and bool(deps.get("tessdata.eng"))
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
            "coordinates": {
                "coordinate_profile": True,
                "logical_pixels": True,
                "local_to_screen": True,
                "screen_to_local": True,
            },
            "vision": {
                "image_locator": image_locator_available,
                "template_matching": image_locator_available,
                "ocr": ocr_available,
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
            ocr_available=ocr_available,
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
    ocr_available: bool,
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
    if not ocr_available:
        limitations.append("tesseract_or_eng_tessdata_missing_for_ocr")
    if not clipboard_available:
        limitations.append("pyperclip_missing")
    if platform_name == "macos":
        limitations.append("macos_tcc_permissions_may_require_user_approval")
    return limitations
