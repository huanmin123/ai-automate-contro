from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import playwright
from playwright._impl._driver import compute_driver_executable, get_driver_env


SUPPORTED_PLAYWRIGHT_BROWSERS = ("chromium", "firefox", "webkit")


def install_playwright_browser(
    browser: str = "chromium",
    *,
    force: bool = False,
    capture_output: bool = False,
) -> dict[str, Any]:
    browser_name = _normalize_browser_name(browser)
    driver_executable, driver_cli = compute_driver_executable()
    command = [driver_executable, driver_cli, "install"]
    if force:
        command.append("--force")
    command.append(browser_name)

    env = _driver_env_for_current_runtime()
    completed = subprocess.run(
        command,
        env=env,
        capture_output=capture_output,
        text=True if capture_output else None,
        encoding="utf-8" if capture_output else None,
        errors="replace" if capture_output else None,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "browser": browser_name,
        "playwright_version": playwright_version(),
        "browser_path": str(playwright_browser_storage_path(env)),
        "browser_path_source": playwright_browser_storage_source(env),
        "command": _display_install_command(browser_name),
        "stdout": completed.stdout if capture_output else "",
        "stderr": completed.stderr if capture_output else "",
    }


def playwright_version() -> str:
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return ""


def playwright_browser_storage_path(env: dict[str, str] | None = None) -> Path:
    env_values = env if env is not None else os.environ
    raw_path = env_values.get("PLAYWRIGHT_BROWSERS_PATH")
    if raw_path == "0":
        return _local_browser_path()
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return _local_browser_path()
    return _default_browser_cache_path()


def playwright_browser_storage_source(env: dict[str, str] | None = None) -> str:
    env_values = env if env is not None else os.environ
    raw_path = env_values.get("PLAYWRIGHT_BROWSERS_PATH")
    if raw_path == "0":
        return "PLAYWRIGHT_BROWSERS_PATH=0"
    if raw_path:
        return "PLAYWRIGHT_BROWSERS_PATH"
    if getattr(sys, "frozen", False):
        return "packaged_default"
    return "playwright_default_cache"


def is_playwright_browser_missing_error(error: BaseException) -> bool:
    text = str(error)
    lowered = text.lower()
    return (
        "executable doesn't exist" in lowered
        and (
            "playwright install" in lowered
            or "looks like playwright was just installed" in lowered
            or "please run the following command to download new browsers" in lowered
        )
    )


def format_playwright_browser_missing_message(browser: str, error: BaseException | None = None) -> str:
    browser_name = _normalize_browser_name(browser)
    version = playwright_version() or "unknown"
    install_command = _display_install_command(browser_name)
    storage_path = playwright_browser_storage_path()
    lines = [
        f"未找到 Playwright {browser_name} 浏览器。",
        f"当前程序使用 playwright=={version}，需要安装与该版本匹配的浏览器二进制。",
        "",
        "处理办法：",
        f"  {install_command}",
        "",
        "如果要把浏览器安装到自定义目录，请在安装和运行 plan 时使用同一个 PLAYWRIGHT_BROWSERS_PATH。",
    ]
    if platform.system() == "Windows":
        lines.extend(
            [
                '  $env:PLAYWRIGHT_BROWSERS_PATH = "D:\\playwright-browsers"',
                f"  {install_command}",
            ]
        )
    else:
        lines.extend(
            [
                '  export PLAYWRIGHT_BROWSERS_PATH="$HOME/playwright-browsers"',
                f"  {install_command}",
            ]
        )
    lines.extend(
        [
            "",
            f"当前浏览器目录：{storage_path}",
            f"目录来源：{playwright_browser_storage_source()}",
        ]
    )
    if error is not None:
        raw_error = str(error).strip()
        if raw_error:
            lines.extend(["", "Playwright 原始错误：", raw_error])
    return "\n".join(lines)


def _driver_env_for_current_runtime() -> dict[str, str]:
    env = get_driver_env()
    if getattr(sys, "frozen", False):
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    return env


def _display_install_command(browser: str) -> str:
    executable = Path(sys.argv[0] or "").name
    if not executable:
        executable = "aic.exe" if platform.system() == "Windows" else "aic"
    if not getattr(sys, "frozen", False) and executable.endswith(".py"):
        script = f".\\{executable}" if platform.system() == "Windows" else f"./{executable}"
        return f"python {script} install-browser --browser {browser}"
    prefix = ".\\" if platform.system() == "Windows" else "./"
    return f"{prefix}{executable} install-browser --browser {browser}"


def _normalize_browser_name(browser: str) -> str:
    browser_name = str(browser or "chromium").strip().lower()
    if browser_name not in SUPPORTED_PLAYWRIGHT_BROWSERS:
        supported = ", ".join(SUPPORTED_PLAYWRIGHT_BROWSERS)
        raise ValueError(f"不支持的 Playwright browser：{browser_name}；可选值：{supported}")
    return browser_name


def _local_browser_path() -> Path:
    return Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"


def _default_browser_cache_path() -> Path:
    system = platform.system()
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).resolve() / "ms-playwright"
        return Path.home() / "AppData" / "Local" / "ms-playwright"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser().resolve() / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"
