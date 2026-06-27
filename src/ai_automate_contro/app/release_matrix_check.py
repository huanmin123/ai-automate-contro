from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def self_check_release_matrix(
    project_root: str | Path,
    *,
    include_real_ai: bool = False,
    api_key_file: str = "",
    model: str = "gpt-5.5",
    timeout_seconds: int = 240,
    max_attempts: int = 5,
    retry_delay_seconds: float = 3.0,
    step_timeout_seconds: int = 900,
    require_desktop_vision: bool = False,
    only: list[str] | None = None,
    list_steps: bool = False,
    fail_fast: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    commands = _deterministic_commands(root, require_desktop_vision=require_desktop_vision)
    if include_real_ai:
        commands.extend(
            _real_ai_commands(
                root,
                api_key_file=api_key_file,
                model=model,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                retry_delay_seconds=retry_delay_seconds,
            )
        )
    available_steps = [_step_summary(item) for item in commands]
    unknown_steps = _unknown_step_names(commands, only)
    if unknown_steps:
        return {
            "ok": False,
            "check": "release_matrix",
            "project_root": str(root),
            "include_real_ai": include_real_ai,
            "require_desktop_vision": require_desktop_vision,
            "available_steps": available_steps,
            "unknown_steps": unknown_steps,
            "results": [],
        }
    selected_commands = _filter_commands(commands, only)
    if list_steps:
        return {
            "ok": True,
            "check": "release_matrix",
            "project_root": str(root),
            "include_real_ai": include_real_ai,
            "require_desktop_vision": require_desktop_vision,
            "available_steps": available_steps,
            "selected_steps": [_step_summary(item) for item in selected_commands],
            "results": [],
        }
    results: list[dict[str, Any]] = []
    for item in selected_commands:
        result = _run_step(root, item["name"], item["command"], timeout_seconds=step_timeout_seconds)
        results.append(result)
        if fail_fast and not result["ok"]:
            break
    return {
        "ok": all(result["ok"] for result in results),
        "check": "release_matrix",
        "project_root": str(root),
        "include_real_ai": include_real_ai,
        "require_desktop_vision": require_desktop_vision,
        "fail_fast": fail_fast,
        "available_steps": available_steps,
        "selected_steps": [_step_summary(item) for item in selected_commands],
        "results": results,
    }


def _deterministic_commands(project_root: Path, *, require_desktop_vision: bool = False) -> list[dict[str, Any]]:
    desktop_components_command = [_python(), "cplan.py", "self-check", "desktop-components"]
    if require_desktop_vision:
        desktop_components_command.append("--require-vision")
    return [
        {"name": "compileall", "command": [_python(), "-m", "compileall", "-q", "src", "main.py", "cplan.py"]},
        {"name": "tool_check", "command": [_python(), "main.py", "tool", "check"]},
        {"name": "handbook", "command": [_python(), "cplan.py", "self-check", "handbook"]},
        {"name": "workspace_clean", "command": [_python(), "cplan.py", "self-check", "workspace-clean"]},
        {"name": "ai_tools", "command": [_python(), "main.py", "self-check", "ai-tools"]},
        {"name": "ai_terminal", "command": [_python(), "main.py", "self-check", "ai-terminal"]},
        {"name": "ai_plan_generation", "command": [_python(), "main.py", "self-check", "ai-plan-generation"]},
        {"name": "desktop_components", "command": desktop_components_command},
        {"name": "desktop_real_app", "command": [_python(), "cplan.py", "self-check", "desktop-real-app"]},
        {"name": "ai_desktop_loop", "command": [_python(), "main.py", "self-check", "ai-desktop-loop"]},
    ]


def _real_ai_commands(
    project_root: Path,
    *,
    api_key_file: str,
    model: str,
    timeout_seconds: int,
    max_attempts: int,
    retry_delay_seconds: float,
) -> list[dict[str, Any]]:
    common = [
        "--api-key-file",
        api_key_file,
        "--model",
        model,
        "--timeout-seconds",
        str(timeout_seconds),
        "--max-attempts",
        str(max_attempts),
        "--retry-delay-seconds",
        str(retry_delay_seconds),
    ]
    return [
        {
            "name": "ai_real_execution_line",
            "command": [_python(), "main.py", "self-check", "ai-real-execution-line", *common],
        },
        {
            "name": "ai_real_desktop_loop",
            "command": [_python(), "main.py", "self-check", "ai-real-desktop-loop", *common],
        },
    ]


def _run_step(project_root: Path, name: str, command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, int(timeout_seconds or 900)),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "elapsed_ms": elapsed_ms,
            "command": _display_command(command),
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "ok": False,
            "returncode": None,
            "elapsed_ms": elapsed_ms,
            "command": _display_command(command),
            "error": f"step timed out after {timeout_seconds}s",
            "stdout_tail": _tail(error.stdout or ""),
            "stderr_tail": _tail(error.stderr or ""),
        }


def _filter_commands(commands: list[dict[str, Any]], only: list[str] | None) -> list[dict[str, Any]]:
    selected = _requested_step_names(only)
    if not selected:
        return commands
    selected_set = set(selected)
    return [item for item in commands if item["name"] in selected_set]


def _unknown_step_names(commands: list[dict[str, Any]], only: list[str] | None) -> list[str]:
    available = {item["name"] for item in commands}
    return sorted(name for name in _requested_step_names(only) if name not in available)


def _requested_step_names(only: list[str] | None) -> list[str]:
    names: list[str] = []
    for raw_item in only or []:
        for raw_name in str(raw_item or "").split(","):
            name = raw_name.strip()
            if name and name not in names:
                names.append(name)
    return names


def _step_summary(item: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(item["name"]),
        "command": _display_command(item["command"]),
    }


def _python() -> str:
    return sys.executable


def _display_command(command: list[str]) -> str:
    display = ["python" if item == sys.executable else item for item in command]
    return " ".join(display)


def _tail(text: str, *, max_lines: int = 30, max_chars: int = 4000) -> str:
    lines = str(text or "").splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail
