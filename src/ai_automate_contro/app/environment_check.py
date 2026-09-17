from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project, load_runtime_config
from ai_automate_contro.engine.desktop.backends.capabilities import desktop_dependencies
from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.support.playwright_browsers import (
    format_playwright_browser_missing_message,
    is_playwright_browser_missing_error,
    playwright_browser_storage_path,
    playwright_browser_storage_source,
    playwright_version,
)


def self_check_environment(project_root: Path) -> dict[str, Any]:
    checks = [
        _check_python_version(),
        _check_shell(),
        _check_imports(),
        _check_ripgrep(),
        _check_playwright_chromium(),
        _check_runtime_config(project_root),
        _check_ai_config(project_root),
        _check_desktop_dependencies(project_root),
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "install": {
            "project": "python -m pip install -e .",
            "ripgrep": _ripgrep_install_hint(),
            "playwright_chromium": _playwright_install_hint(),
            "desktop_extra": r'python -m pip install -e ".[desktop]"',
            "verify": _self_check_env_command(),
        },
    }


def _self_check_env_command() -> str:
    if platform.system() == "Windows":
        return r"python .\main.py self-check env"
    return "python ./main.py self-check env"


def self_check_runtime_config(project_root: Path) -> dict[str, Any]:
    check = _check_runtime_config(project_root)
    return {
        "ok": check["ok"],
        "checks": [check],
    }


def _check_python_version() -> dict[str, Any]:
    minimum = (3, 11)
    current = sys.version_info
    return _check_result(
        "python",
        current >= minimum,
        version=f"{current.major}.{current.minor}.{current.micro}",
        detail="需要 Python 3.11 或更高版本。",
        fix="安装 Python 3.11+ 后，在当前终端重新运行。",
    )


def _check_shell() -> dict[str, Any]:
    system = platform.system()
    if system != "Windows":
        return _check_result(
            "shell",
            True,
            system=system,
            shell=os.environ.get("SHELL", ""),
            detail="当前系统可使用原生终端运行；PowerShell 7 只在 Windows 作为推荐 shell 检查。",
            fix="",
        )
    return _check_pwsh()


def _check_pwsh() -> dict[str, Any]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return _check_result(
            "shell",
            False,
            detail="PATH 中没有找到 PowerShell 7 (pwsh)。",
            fix="安装 PowerShell 7，并从 pwsh 中运行命令。",
        )

    completed = subprocess.run(
        [pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    version = completed.stdout.strip()
    return _check_result(
        "shell",
        completed.returncode == 0 and version.startswith("7."),
        version=version,
        detail="Windows 推荐的交互式 shell 是 PowerShell 7。",
        fix="请从 PowerShell 7 中运行本项目。",
    )


def _check_imports() -> dict[str, Any]:
    modules = {
        "ai_automate_contro": "ai-automate-contro",
        "playwright": "playwright",
        "openai": "openai",
        "anthropic": "anthropic",
        "google.genai": "google-genai",
        "jsonschema": "jsonschema",
        "langchain": "langchain",
        "langgraph": "langgraph",
        "langgraph.checkpoint.sqlite": "langgraph-checkpoint-sqlite",
        "langchain_openai": "langchain-openai",
        "langchain_anthropic": "langchain-anthropic",
        "langchain_google_genai": "langchain-google-genai",
        "pydantic": "pydantic",
        "PIL": "Pillow",
        "rich": "rich",
        "textual": "textual",
    }
    missing = [module for module in modules if importlib.util.find_spec(module) is None]
    versions = {
        package: _distribution_version(package)
        for package in sorted(set(modules.values()))
    }
    return _check_result(
        "python_dependencies",
        not missing,
        missing=missing,
        versions=versions,
        detail="Python 包依赖必须能够正常导入。",
        fix="python -m pip install -e .",
    )


def _check_ripgrep() -> dict[str, Any]:
    rg = shutil.which("rg")
    if rg is None:
        return _check_result(
            "ripgrep",
            False,
            detail="必须安装 ripgrep (rg)。本项目不使用 Windows 内置搜索作为兜底。",
            fix=_ripgrep_install_hint(),
        )

    completed = subprocess.run(
        ["rg", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    version = completed.stdout.splitlines()[0] if completed.stdout.splitlines() else ""
    return _check_result(
        "ripgrep",
        completed.returncode == 0,
        path=rg,
        version=version,
        detail="AI 终端文本搜索只使用 rg。",
        fix=_ripgrep_install_hint(),
    )


def _check_playwright_chromium() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as error:
        fix = (
            format_playwright_browser_missing_message("chromium", error)
            if is_playwright_browser_missing_error(error)
            else _playwright_install_hint()
        )
        return _check_result(
            "playwright_chromium",
            False,
            detail=str(error),
            fix=fix,
            playwright_version=playwright_version(),
            browser_path=str(playwright_browser_storage_path()),
            browser_path_source=playwright_browser_storage_source(),
        )
    return _check_result(
        "playwright_chromium",
        True,
        detail="Playwright 可以正常启动 Chromium。",
        fix=_playwright_install_hint(),
        playwright_version=playwright_version(),
        browser_path=str(playwright_browser_storage_path()),
        browser_path_source=playwright_browser_storage_source(),
    )


def _check_runtime_config(project_root: Path) -> dict[str, Any]:
    try:
        runtime_config = load_runtime_config(project_root)
    except Exception as error:
        return _check_result(
            "runtime_config",
            False,
            detail=str(error),
            fix="修复 plan.config，确保 handbook_path 和 plan_roots 有效。",
        )
    missing_plan_roots = [str(path) for path in runtime_config.plan_roots if not path.exists()]
    return _check_result(
        "runtime_config",
        runtime_config.handbook_path.exists() and not missing_plan_roots,
        project_root=str(runtime_config.project_root),
        handbook_path=str(runtime_config.handbook_path),
        plan_roots=[str(path) for path in runtime_config.plan_roots],
        default_ai_config_dir=str(runtime_config.default_ai_config_dir),
        missing_plan_roots=missing_plan_roots,
        detail="运行时 plan.config 控制 handbook 和 plan 根目录位置。",
        fix="创建 handbook/ 和配置的 plan_roots，或编辑 plan.config。",
    )


def _check_ai_config(project_root: Path) -> dict[str, Any]:
    from ai_automate_contro.ai.service_config import validate_ai_service_config

    try:
        ai_config_dir = default_ai_config_dir_for_project(project_root)
        plan_config = load_plan_config(project_root, ai_config_dir)
    except Exception as error:
        return _check_result(
            "ai_config",
            False,
            detail=str(error),
            fix="修复 plan.config default_ai_config_dir 指向目录下的 config.json。",
        )

    if "ai_services" not in plan_config:
        return _check_result(
            "ai_config",
            True,
            configured=False,
            ready=False,
            config_dir=str(ai_config_dir),
            config_path=str(ai_config_dir / "config.json"),
            detail="AI 服务未配置。plan 模式仍可使用；进入 AI 模式需要 ai_services.default。",
            fix="添加 ai_services.default 后再使用 AI 终端或 ai action。",
        )

    ai_services = plan_config.get("ai_services")
    if not isinstance(ai_services, dict):
        return _check_result(
            "ai_config",
            False,
            config_dir=str(ai_config_dir),
            config_path=str(ai_config_dir / "config.json"),
            detail="config.ai_services 必须是 JSON 对象。",
            fix="在 plan.config default_ai_config_dir 指向目录下的 config.json 中添加 ai_services.default。",
        )

    default_service = ai_services.get("default")
    if not isinstance(default_service, dict):
        return _check_result(
            "ai_config",
            True,
            configured=False,
            ready=False,
            config_dir=str(ai_config_dir),
            config_path=str(ai_config_dir / "config.json"),
            detail="ai_services.default 未配置。",
            fix="添加带 model 和 api_key 或 api_key_env 的 ai_services.default。",
        )

    model = default_service.get("model")
    api_key_env = default_service.get("api_key_env")
    has_api_key = bool(default_service.get("api_key"))
    env_ready = isinstance(api_key_env, str) and bool(os.environ.get(api_key_env))
    config_error = ""
    try:
        validate_ai_service_config(default_service)
    except (TypeError, ValueError) as error:
        config_error = str(error)
    ready = bool(model) and (has_api_key or env_ready) and not config_error
    return _check_result(
        "ai_config",
        ready,
        configured=True,
        ready=ready,
        service="default",
        config_dir=str(ai_config_dir),
        model=str(model) if model else "",
        has_inline_api_key=has_api_key,
        api_key_env=str(api_key_env) if api_key_env else "",
        api_key_env_ready=env_ready,
        protocol=str(default_service.get("protocol") or default_service.get("api") or "openai_chat_completions"),
        config_error=config_error,
        detail=config_error or "AI 配置只做本地检查，不会发送真实模型请求。",
        fix="在配置目录中设置有效的 protocol、model、通用模型参数，并设置 api_key 或 api_key_env。",
    )


def _check_desktop_dependencies(project_root: Path) -> dict[str, Any]:
    try:
        ai_config_dir = default_ai_config_dir_for_project(project_root)
        config = load_plan_config(project_root, ai_config_dir)
    except Exception:
        config = {}
    dependencies = desktop_dependencies(config)
    ready = (
        bool(dependencies.get("pyautogui"))
        and bool(dependencies.get("pyperclip"))
        and bool(dependencies.get("Pillow.ImageGrab"))
        and bool(dependencies.get("opencv-python"))
    )
    return _check_result(
        "desktop_optional_dependencies",
        True,
        ready=ready,
        dependencies=dependencies,
        detail="桌面控制依赖为可选能力诊断；视觉定位只保留 OpenCV 模板匹配。",
        fix='python -m pip install -e ".[desktop]"',
    )


def _distribution_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _check_result(name: str, ok: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, **details}


def _ripgrep_install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ripgrep"
    if system == "Linux":
        return "使用系统包管理器安装 ripgrep，例如 sudo apt install ripgrep 或 sudo dnf install ripgrep。"
    return "winget install --id BurntSushi.ripgrep.MSVC -e"


def _playwright_install_hint() -> str:
    if getattr(sys, "frozen", False):
        executable = ".\\aic.exe" if platform.system() == "Windows" else "./aic"
        return f"{executable} install-browser --browser chromium"
    return "python -m playwright install chromium"
