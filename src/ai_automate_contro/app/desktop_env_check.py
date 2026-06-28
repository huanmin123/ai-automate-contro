from __future__ import annotations

import importlib
import importlib.metadata
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project
from ai_automate_contro.engine.desktop.backends.capabilities import (
    desktop_dependencies,
    tesseract_binary_details,
)
from ai_automate_contro.engine.desktop.backends.native import NativeDesktopBackend
from ai_automate_contro.plans.config import load_plan_config


def self_check_desktop_env(
    project_root: str | Path,
    *,
    require_input: bool = False,
    require_vision: bool = False,
    require_ocr: bool = False,
    require_ocr_zh: bool = False,
    request_permissions: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    desktop_config = _desktop_config(root)
    platform_name = _desktop_platform_name()
    dependencies = desktop_dependencies(desktop_config)
    module_check = _python_module_check()
    shell_check = _shell_check()
    tesseract_check = _tesseract_check(desktop_config, dependencies)
    probe_check = _backend_probe_check(
        platform_name,
        desktop_config=desktop_config,
        request_permissions=bool(request_permissions),
    )
    capability_matrix = (
        probe_check.get("probe", {}).get("capability_matrix")
        if isinstance(probe_check.get("probe"), dict)
        and isinstance(probe_check.get("probe", {}).get("capability_matrix"), dict)
        else {}
    )
    required = _required_checks(
        platform_name=platform_name,
        dependencies=dependencies,
        shell_check=shell_check,
        probe_check=probe_check,
        require_input=bool(require_input),
        require_vision=bool(require_vision),
        require_ocr=bool(require_ocr),
        require_ocr_zh=bool(require_ocr_zh),
    )
    checks = [
        _platform_check(platform_name),
        shell_check,
        module_check,
        tesseract_check,
        probe_check,
        {
            "name": "desktop_capability_matrix",
            "ok": True,
            "capability_matrix": capability_matrix,
            "limitations": (
                capability_matrix.get("limitations", [])
                if isinstance(capability_matrix.get("limitations"), list)
                else []
            ),
        },
        required,
    ]
    return {
        "ok": bool(required.get("ok", True)),
        "check": "desktop_env",
        "project_root": str(root),
        "platform": platform.system(),
        "desktop_platform": platform_name,
        "request_permissions": bool(request_permissions),
        "require_input": bool(require_input),
        "require_vision": bool(require_vision),
        "require_ocr": bool(require_ocr),
        "require_ocr_zh": bool(require_ocr_zh),
        "ready": {
            "input": _input_ready(dependencies),
            "vision": _vision_ready(dependencies),
            "ocr": _ocr_ready(dependencies),
            "ocr_zh": _ocr_zh_ready(dependencies),
        },
        "dependencies": dependencies,
        "checks": checks,
        "commands": {
            "run": _cplan_command("desktop-env"),
            "run_require_input": _cplan_command("desktop-env", "--require-input"),
            "run_require_vision": _cplan_command("desktop-env", "--require-vision"),
            "run_require_ocr": _cplan_command("desktop-env", "--require-ocr"),
            "run_require_ocr_zh": _cplan_command("desktop-env", "--require-ocr-zh"),
            "install_desktop_extra": 'python -m pip install -e ".[desktop]"',
        },
    }


def _desktop_config(project_root: Path) -> dict[str, Any]:
    try:
        config_dir = default_ai_config_dir_for_project(project_root)
        config = load_plan_config(project_root, config_dir)
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _desktop_platform_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return system.lower() or "unknown"


def _platform_check(platform_name: str) -> dict[str, Any]:
    supported = platform_name in {"windows", "macos"}
    return {
        "name": "desktop_platform",
        "ok": True,
        "supported": supported,
        "platform": platform.system(),
        "desktop_platform": platform_name,
        "reason": "" if supported else f"desktop runtime currently supports Windows/macOS, current={platform.system()}",
    }


def _shell_check() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "name": "windows_pwsh",
            "ok": True,
            "skipped": True,
            "reason": "PowerShell 7 is only checked on Windows.",
        }
    pwsh = shutil.which("pwsh")
    if not pwsh:
        return {
            "name": "windows_pwsh",
            "ok": True,
            "ready": False,
            "path": "",
            "version": "",
            "fix": "Install PowerShell 7 and run desktop regressions from pwsh.",
        }
    completed = subprocess.run(
        [pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    version = completed.stdout.strip()
    return {
        "name": "windows_pwsh",
        "ok": True,
        "ready": completed.returncode == 0 and version.startswith("7."),
        "path": pwsh,
        "version": version,
        "returncode": completed.returncode,
    }


def _python_module_check() -> dict[str, Any]:
    modules = {
        "pyautogui": "pyautogui",
        "pyperclip": "pyperclip",
        "PIL.ImageGrab": "Pillow",
        "cv2": "opencv-python",
        "mss": "mss",
    }
    if platform.system() == "Windows":
        modules["pywinauto"] = "pywinauto"
    availability = {module: _module_available(module) for module in modules}
    versions = {
        package: _package_version(package)
        for package in sorted(set(modules.values()))
    }
    return {
        "name": "desktop_python_modules",
        "ok": True,
        "availability": availability,
        "versions": versions,
        "missing": [module for module, available in availability.items() if not available],
    }


def _tesseract_check(desktop_config: dict[str, Any], dependencies: dict[str, bool]) -> dict[str, Any]:
    return {
        "name": "desktop_tesseract",
        "ok": True,
        "ready": bool(dependencies.get("tesseract")) and bool(dependencies.get("tessdata.eng")),
        "zh_ready": bool(dependencies.get("tesseract")) and bool(dependencies.get("tessdata.chi_sim")),
        "details": tesseract_binary_details(desktop_config),
        "languages": {
            "eng": bool(dependencies.get("tessdata.eng")),
            "chi_sim": bool(dependencies.get("tessdata.chi_sim")),
        },
    }


def _backend_probe_check(
    platform_name: str,
    *,
    desktop_config: dict[str, Any],
    request_permissions: bool,
) -> dict[str, Any]:
    if platform_name not in {"windows", "macos"}:
        return {
            "name": "desktop_native_probe",
            "ok": True,
            "skipped": True,
            "reason": f"unsupported desktop platform: {platform_name}",
        }
    try:
        backend = NativeDesktopBackend(platform_name=platform_name, desktop_config=desktop_config)
        probe = backend.probe(request_permissions=bool(request_permissions))
    except Exception as error:
        return {
            "name": "desktop_native_probe",
            "ok": True,
            "ready": False,
            "error": str(error),
            "error_type": type(error).__name__,
        }
    return {
        "name": "desktop_native_probe",
        "ok": True,
        "ready": True,
        "probe": probe,
        "window_list_error": str(probe.get("window_list_error") or "") if isinstance(probe, dict) else "",
    }


def _required_checks(
    *,
    platform_name: str,
    dependencies: dict[str, bool],
    shell_check: dict[str, Any],
    probe_check: dict[str, Any],
    require_input: bool,
    require_vision: bool,
    require_ocr: bool,
    require_ocr_zh: bool,
) -> dict[str, Any]:
    issues: list[str] = []
    strict = any((require_input, require_vision, require_ocr, require_ocr_zh))
    if platform_name not in {"windows", "macos"} and any((require_input, require_vision, require_ocr, require_ocr_zh)):
        issues.append(f"unsupported desktop platform: {platform_name}")
    if strict and platform_name == "windows" and not bool(shell_check.get("ready")):
        issues.append("Windows desktop regressions require PowerShell 7 (`pwsh`) to be available.")
    if strict and platform_name in {"windows", "macos"} and not bool(probe_check.get("ready")):
        error = str(probe_check.get("error") or probe_check.get("window_list_error") or "").strip()
        suffix = f" Reason: {error}" if error else ""
        issues.append(f"desktop native backend probe must be ready in strict desktop-env mode.{suffix}")
    if require_input and not _input_ready(dependencies):
        issues.append("desktop input requires pyautogui and pyperclip.")
    if require_vision and not _vision_ready(dependencies):
        issues.append("desktop vision requires Pillow.ImageGrab and opencv-python.")
    if require_ocr and not _ocr_ready(dependencies):
        issues.append("desktop OCR requires Pillow.ImageGrab, tesseract, and tessdata.eng.")
    if require_ocr_zh and not _ocr_zh_ready(dependencies):
        issues.append("desktop Chinese OCR requires Pillow.ImageGrab, tesseract, and tessdata.chi_sim.")
    return {
        "name": "desktop_required_capabilities",
        "ok": not issues,
        "issues": issues,
        "requirements": {
            "backend_probe": strict and platform_name in {"windows", "macos"},
            "windows_pwsh": strict and platform_name == "windows",
            "input": require_input,
            "vision": require_vision,
            "ocr": require_ocr,
            "ocr_zh": require_ocr_zh,
        },
    }


def _input_ready(dependencies: dict[str, bool]) -> bool:
    return bool(dependencies.get("pyautogui")) and bool(dependencies.get("pyperclip"))


def _vision_ready(dependencies: dict[str, bool]) -> bool:
    return bool(dependencies.get("Pillow.ImageGrab")) and bool(dependencies.get("opencv-python"))


def _ocr_ready(dependencies: dict[str, bool]) -> bool:
    return bool(dependencies.get("Pillow.ImageGrab")) and bool(dependencies.get("tesseract")) and bool(dependencies.get("tessdata.eng"))


def _ocr_zh_ready(dependencies: dict[str, bool]) -> bool:
    return bool(dependencies.get("Pillow.ImageGrab")) and bool(dependencies.get("tesseract")) and bool(dependencies.get("tessdata.chi_sim"))


def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception:
        return False
    return True


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _cplan_command(command: str, *args: str) -> str:
    prefix = "python .\\cplan.py self-check" if platform.system() == "Windows" else "python ./cplan.py self-check"
    suffix = " ".join(str(arg) for arg in args if arg)
    return f"{prefix} {command}{(' ' + suffix) if suffix else ''}"
