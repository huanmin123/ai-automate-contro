from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MAX_OUTPUT_BYTES = 65_536
MAX_OUTPUT_BYTES_CAP = 1_048_576


def run(executor: Any, step: dict[str, Any]) -> None:
    command_args = _build_command_args(step)
    cwd = _resolve_cwd(executor, step)
    stdin = _resolve_stdin(executor, step)
    timeout = max(0.001, float(step.get("timeout_ms", DEFAULT_TIMEOUT_MS)) / 1000)
    encoding = str(step.get("encoding", "utf-8"))
    environment = _build_env(step)

    completed = subprocess.run(
        command_args,
        cwd=str(cwd),
        env=environment,
        input=stdin,
        capture_output=True,
        timeout=timeout,
        check=False,
    )

    stdout_text = completed.stdout.decode(encoding, errors="replace")
    stderr_text = completed.stderr.decode(encoding, errors="replace")
    stdout_path = _write_command_output(executor, step, "stdout_path", completed.stdout)
    stderr_path = _write_command_output(executor, step, "stderr_path", completed.stderr)
    max_output_bytes = min(
        max(1, int(step.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES))),
        MAX_OUTPUT_BYTES_CAP,
    )
    stdout_for_variable, stdout_truncated = _limit_text(stdout_text, max_output_bytes, encoding)
    stderr_for_variable, stderr_truncated = _limit_text(stderr_text, max_output_bytes, encoding)

    payload: dict[str, Any] = {
        "exit_code": completed.returncode,
        "ok": completed.returncode in _expected_exit_codes(step.get("expect_exit_code", 0)),
        "stdout": stdout_for_variable,
        "stderr": stderr_for_variable,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "cwd": str(cwd),
    }
    if str(step.get("stdout_type", "text")).lower() == "json":
        payload["stdout_json"] = json.loads(stdout_text or "null")

    expected = _expected_exit_codes(step.get("expect_exit_code", 0))
    if completed.returncode not in expected:
        raise RuntimeError(f"command exit code assertion failed. expected={sorted(expected)}, actual={completed.returncode}")

    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload

    executor.state.logger.log(
        "info",
        "command finished",
        command=command_args,
        exit_code=completed.returncode,
        ok=payload["ok"],
        cwd=str(cwd),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        save_as=step.get("save_as", ""),
    )


def _build_command_args(step: dict[str, Any]) -> list[str]:
    sources = [field for field in ("argv", "command", "commands") if field in step]
    if len(sources) != 1:
        raise ValueError("command.run 需要 command、commands 或 argv 之一，且只能提供一种。")
    if "argv" in step:
        argv = step["argv"]
        if not isinstance(argv, list) or not argv:
            raise ValueError("command.argv 必须是非空数组。")
        return [str(item) for item in argv]
    command = _select_command_text(step)
    shell_name = str(step.get("shell", "auto")).lower()
    if shell_name == "auto":
        shell_name = "pwsh" if platform.system() == "Windows" else "sh"
    if shell_name == "pwsh":
        return ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    if shell_name == "powershell":
        return ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    if shell_name == "cmd":
        return ["cmd.exe", "/d", "/s", "/c", command]
    if shell_name == "bash":
        return ["bash", "-lc", command]
    if shell_name == "sh":
        return ["sh", "-c", command]
    raise ValueError(f"command.shell 不支持：{shell_name}")


def _select_command_text(step: dict[str, Any]) -> str:
    if "command" in step:
        command = step["command"]
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command.command 必须是非空字符串。")
        return command
    commands = step.get("commands")
    if not isinstance(commands, dict):
        raise ValueError("command.commands 必须是对象。")
    system = platform.system()
    keys = ["windows", "default"] if system == "Windows" else ["macos", "default"] if system == "Darwin" else ["linux", "default"]
    for key in keys:
        value = commands.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise ValueError(f"command.commands 缺少当前平台命令：{', '.join(keys)}")


def _resolve_cwd(executor: Any, step: dict[str, Any]) -> Path:
    package_root = executor._package_root().resolve()
    if "cwd" not in step or step.get("cwd") in (None, ""):
        return package_root
    raw_cwd = str(step["cwd"])
    if is_absolute_path_text(raw_cwd):
        cwd = path_from_text(raw_cwd).resolve()
    else:
        cwd = (package_root / path_from_text(raw_cwd)).resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise FileNotFoundError(f"command.cwd 不存在：{cwd}")
    return cwd


def _resolve_stdin(executor: Any, step: dict[str, Any]) -> bytes | None:
    if "stdin" in step and "stdin_path" in step:
        raise ValueError("command.stdin 和 command.stdin_path 只能提供一种。")
    encoding = str(step.get("encoding", "utf-8"))
    if "stdin" in step:
        return str(step["stdin"]).encode(encoding)
    if "stdin_path" in step:
        path = _resolve_package_input_path(executor, str(step["stdin_path"]))
        return path.read_bytes()
    return None


def _build_env(step: dict[str, Any]) -> dict[str, str] | None:
    raw_env = step.get("env")
    if raw_env in (None, ""):
        return None
    if not isinstance(raw_env, dict):
        raise ValueError("command.env 必须是对象。")
    environment = dict(os.environ)
    for key, value in raw_env.items():
        environment[str(key)] = str(value)
    return environment


def _resolve_package_input_path(executor: Any, raw_path: str) -> Path:
    if is_absolute_path_text(raw_path):
        path = path_from_text(raw_path).resolve()
    else:
        package_root = executor._package_root().resolve()
        path = (package_root / path_from_text(raw_path)).resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"输入文件不存在：{path}")
    return path


def _write_command_output(executor: Any, step: dict[str, Any], field: str, content: bytes) -> str:
    if field not in step:
        return ""
    output_path = executor._resolve_output_path(step[field], category="commands")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return str(output_path)


def _expected_exit_codes(expected: Any) -> set[int]:
    if expected is None:
        return {0}
    if isinstance(expected, int):
        return {expected}
    if isinstance(expected, list):
        return {int(item) for item in expected}
    return {int(expected)}


def _limit_text(text: str, max_bytes: int, encoding: str) -> tuple[str, bool]:
    encoded = text.encode(encoding, errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    limited = encoded[:max_bytes].decode(encoding, errors="replace")
    return limited, True


ACTION_HANDLERS = {
    "command": run,
}
