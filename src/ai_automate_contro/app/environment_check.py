from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project, load_runtime_config
from ai_automate_contro.plans.config import load_plan_config


def self_check_environment(project_root: Path) -> dict[str, Any]:
    checks = [
        _check_python_version(),
        _check_pwsh(),
        _check_imports(),
        _check_ripgrep(),
        _check_playwright_chromium(),
        _check_runtime_config(project_root),
        _check_ai_config(project_root),
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "install": {
            "project": "python -m pip install -e .",
            "ripgrep": "winget install --id BurntSushi.ripgrep.MSVC -e",
            "playwright_chromium": "python -m playwright install chromium",
            "verify": "python .\\main.py self-check env",
        },
    }


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
        fix="安装 Python 3.11+ 后，在 PowerShell 7 中重新运行。",
    )


def _check_pwsh() -> dict[str, Any]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return _check_result(
            "powershell_7",
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
        "powershell_7",
        completed.returncode == 0 and version.startswith("7."),
        version=version,
        detail="本项目支持的交互式 shell 是 PowerShell 7。",
        fix="请从 PowerShell 7 中运行本项目。",
    )


def _check_imports() -> dict[str, Any]:
    modules = {
        "ai_automate_contro": "keygen-openai-account",
        "playwright": "playwright",
        "openai": "openai",
        "jsonschema": "jsonschema",
        "langchain": "langchain",
        "langgraph": "langgraph",
        "langgraph.checkpoint.sqlite": "langgraph-checkpoint-sqlite",
        "langchain_openai": "langchain-openai",
        "pydantic": "pydantic",
        "PIL": "Pillow",
        "prompt_toolkit": "prompt_toolkit",
        "rich": "rich",
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
            fix="winget install --id BurntSushi.ripgrep.MSVC -e",
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
        fix="winget install --id BurntSushi.ripgrep.MSVC -e",
    )


def _check_playwright_chromium() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as error:
        return _check_result(
            "playwright_chromium",
            False,
            detail=str(error),
            fix="python -m playwright install chromium",
        )
    return _check_result(
        "playwright_chromium",
        True,
        detail="Playwright 可以正常启动 Chromium。",
        fix="python -m playwright install chromium",
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
    return _check_result(
        "ai_config",
        bool(model) and (has_api_key or env_ready),
        configured=True,
        ready=bool(model) and (has_api_key or env_ready),
        service="default",
        config_dir=str(ai_config_dir),
        model=str(model) if model else "",
        has_inline_api_key=has_api_key,
        api_key_env=str(api_key_env) if api_key_env else "",
        api_key_env_ready=env_ready,
        detail="AI 配置只做本地检查，不会发送真实模型请求。",
        fix="在配置目录中设置 model，并设置 api_key 或 api_key_env。",
    )


def _distribution_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _check_result(name: str, ok: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, **details}
