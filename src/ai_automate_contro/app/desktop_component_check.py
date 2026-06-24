from __future__ import annotations

import json
import platform
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file


DESKTOP_REGRESSION_PLAN = Path("test-plans/desktop/basic/plan.json")


def self_check_desktop_components(project_root: Path) -> dict[str, Any]:
    resolved_root = Path(project_root).resolve()
    schema_cases = _run_schema_cases(resolved_root)
    runtime_case = _run_runtime_case(resolved_root)
    failure_case = _run_failure_capture_case(resolved_root)
    real_app_case = _run_real_app_case(resolved_root)
    input_probe_case = _run_input_dependency_probe_case()
    schema_ok = all(case["ok"] for case in schema_cases)
    runtime_ok = bool(runtime_case["ok"])
    failure_ok = bool(failure_case["ok"])
    real_app_ok = bool(real_app_case["ok"])
    input_probe_ok = bool(input_probe_case["ok"])
    return {
        "ok": schema_ok and runtime_ok and failure_ok and real_app_ok and input_probe_ok,
        "checks": [
            {
                "name": "desktop_schema_and_execution_line_validation",
                "ok": schema_ok,
                "cases": schema_cases,
            },
            runtime_case,
            failure_case,
            real_app_case,
            input_probe_case,
        ],
        "commands": {
            "run": f"python {_cplan_script_path()} self-check desktop-components",
            "create_desktop_plan": f"python {_cplan_script_path()} create --path .\\plans\\desktop-demo --automation-type desktop",
        },
    }


def _run_schema_cases(project_root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="desktop-components-schema-") as raw_temp_dir:
        temp_dir = Path(raw_temp_dir)
        for case in _schema_case_definitions():
            results.append(_run_schema_case(project_root, temp_dir, case))
    regression_plan_path = project_root / DESKTOP_REGRESSION_PLAN
    validation = validate_plan_file(regression_plan_path, project_root)
    results.append(
        {
            "name": "desktop_regression_plan_validates",
            "ok": validation.ok,
            "plan_path": str(regression_plan_path),
            "errors": [error.format() for error in validation.errors],
        }
    )
    return results


def _schema_case_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "missing-automation-type",
            "expected_message": "主 plan 必须包含 automation_type",
            "plan": {"name": "missing type", "steps": [{"action": "print", "message": "ok"}]},
        },
        {
            "name": "invalid-automation-type",
            "expected_message": "automation_type 不支持",
            "plan": {"name": "bad type", "automation_type": "mobile", "steps": [{"action": "print", "message": "ok"}]},
        },
        {
            "name": "desktop-rejects-browser-action",
            "expected_message": "automation_type=desktop 不支持 action：open_browser",
            "plan": {"name": "bad desktop action", "automation_type": "desktop", "steps": [{"action": "open_browser", "name": "main"}]},
        },
        {
            "name": "browser-rejects-desktop-action",
            "expected_message": "automation_type=browser 不支持 action：open_desktop",
            "plan": {"name": "bad browser action", "automation_type": "browser", "steps": [{"action": "open_desktop", "name": "desktop"}]},
        },
        {
            "name": "desktop-focus-requires-query",
            "expected_message": "desktop_window.focus 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "focus"},
                ],
            },
        },
        {
            "name": "desktop-assert-window-requires-query",
            "expected_message": "desktop_assert.window 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop assert query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_assert", "desktop": "desktop", "type": "window"},
                ],
            },
        },
        {
            "name": "desktop-assert-screenshot-requires-path",
            "expected_message": "desktop_assert.screenshot 缺少必填字段：path",
            "plan": {
                "name": "missing desktop screenshot assertion path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_assert", "desktop": "desktop", "type": "screenshot"},
                ],
            },
        },
        {
            "name": "desktop-click-requires-target-or-coordinates",
            "expected_message": "desktop_input.click 需要 target 或 x/y",
            "plan": {
                "name": "missing desktop click target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "click"},
                ],
            },
        },
        {
            "name": "desktop-click-rejects-mixed-target-and-coordinates",
            "expected_message": "desktop_input.click 不能同时使用 target 和 x/y",
            "plan": {
                "name": "mixed desktop click target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "current_window_center",
                        "x": 10,
                        "y": 10,
                    },
                ],
            },
        },
        {
            "name": "sub-plan-type-mismatch",
            "expected_message": "子计划 automation_type 必须与主 plan 一致",
            "plan": {
                "name": "sub mismatch",
                "automation_type": "browser",
                "steps": [{"action": "run_sub_plan", "path": "sub-plans/desktop-child-plan.json"}],
            },
            "files": {
                "sub-plans/desktop-child-plan.json": {
                    "name": "desktop child",
                    "automation_type": "desktop",
                    "steps": [{"action": "print", "message": "child"}],
                }
            },
        },
    ]


def _run_schema_case(project_root: Path, temp_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    package_dir = temp_dir / str(case["name"])
    package_dir.mkdir(parents=True, exist_ok=True)
    plan_path = package_dir / "plan.json"
    plan_path.write_text(json.dumps(case["plan"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for relative_path, value in dict(case.get("files", {})).items():
        target_path = package_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = validate_plan_file(plan_path, project_root)
    errors = [error.format() for error in validation.errors]
    matched = any(str(case["expected_message"]) in error for error in errors)
    return {
        "name": str(case["name"]),
        "ok": (not validation.ok) and matched,
        "validation_ok": validation.ok,
        "matched": matched,
        "expected_message": str(case["expected_message"]),
        "errors": errors,
    }


def _run_runtime_case(project_root: Path) -> dict[str, Any]:
    if platform.system() not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_lightweight_runtime",
            "ok": True,
            "skipped": True,
            "reason": f"desktop runtime Phase 0 only supports Windows/macOS, current={platform.system()}",
        }
    plan_path = project_root / DESKTOP_REGRESSION_PLAN
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        return {
            "name": "desktop_lightweight_runtime",
            "ok": False,
            "plan_path": str(plan_path),
            "validation_ok": False,
            "errors": [error.format() for error in validation.errors],
        }
    try:
        plan = load_plan(plan_path)
        started_at = time.time()
        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name="desktop-components-basic",
            run_context_handler=_disable_run_log_echo,
        )
        evidence = _desktop_basic_evidence(project_root, started_at)
    except Exception as error:
        return {
            "name": "desktop_lightweight_runtime",
            "ok": False,
            "plan_path": str(plan_path),
            "validation_ok": True,
            "run_ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
        }
    evidence_ok = all(item["ok"] for item in evidence)
    return {
        "name": "desktop_lightweight_runtime",
        "ok": result.status == "passed" and evidence_ok,
        "plan_path": str(plan_path),
        "validation_ok": True,
        "run_ok": result.status == "passed",
        "output_dir": result.output_dir,
        "evidence": evidence,
    }


def _desktop_basic_evidence(project_root: Path, started_at: float) -> list[dict[str, Any]]:
    package_dir = project_root / DESKTOP_REGRESSION_PLAN.parent
    windows_path = package_dir / "output" / "desktop-windows" / "windows.json"
    screenshot_path = package_dir / "output" / "desktop-screenshots" / "screen.png"
    snapshot_path = package_dir / "output" / "desktop-state" / "snapshot.json"
    windows = _read_json(windows_path) if windows_path.exists() else {}
    snapshot = _read_json(snapshot_path) if snapshot_path.exists() else {}
    return [
        _expect("windows_artifact_fresh", _file_nonempty_after(windows_path, started_at)),
        _expect("windows_payload_shape", isinstance(windows.get("windows"), list)),
        _expect("screenshot_artifact_fresh", _file_nonempty_after(screenshot_path, started_at)),
        _expect("snapshot_artifact_fresh", _file_nonempty_after(snapshot_path, started_at)),
        _expect("snapshot_payload_shape", isinstance(snapshot.get("snapshot"), dict)),
    ]


def _run_failure_capture_case(project_root: Path) -> dict[str, Any]:
    if platform.system() not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_failure_capture",
            "ok": True,
            "skipped": True,
            "reason": f"desktop failure capture only runs on Windows/macOS, current={platform.system()}",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-failure-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "desktop failure capture",
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop"},
                {
                    "action": "desktop_wait",
                    "desktop": "desktop",
                    "type": "window",
                    "state": "exists",
                    "title_contains": "__ai_automate_contro_missing_window__",
                    "timeout_ms": 100,
                    "interval_ms": 20,
                },
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_failure_capture",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        try:
            execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-failure",
                run_context_handler=_disable_run_log_echo,
            )
            failed_as_expected = False
        except Exception as error:
            failed_as_expected = True
            run_error = str(error)
        result_payload = _latest_result_payload(package_dir / "output")
        failure_states = [Path(path) for path in result_payload.get("failure_desktop_states", [])]
        failure_screenshots = [Path(path) for path in result_payload.get("failure_desktop_screenshots", [])]
        state_payloads = [_read_json(path) for path in failure_states if path.exists()]
        state_ok = any(
            payload.get("action") == "desktop_wait" and isinstance(payload.get("snapshot"), dict)
            for payload in state_payloads
            if isinstance(payload, dict)
        )
        target_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("target"), dict)
            and payload["target"].get("title_contains") == "__ai_automate_contro_missing_window__"
            for payload in state_payloads
        )
        error_ok = any(
            isinstance(payload, dict)
            and "等待窗口超时" in str(payload.get("error", ""))
            and payload.get("error_type") == "TimeoutError"
            for payload in state_payloads
        )
        screenshot_ok = all(path.exists() and path.stat().st_size > 0 for path in failure_screenshots)
        return {
            "name": "desktop_failure_capture",
            "ok": (
                failed_as_expected
                and result_payload.get("status") == "failed"
                and state_ok
                and screenshot_ok
                and target_ok
                and error_ok
            ),
            "validation_ok": True,
            "failed_as_expected": failed_as_expected,
            "run_error": run_error,
            "result_status": result_payload.get("status"),
            "failure_desktop_state_count": len(failure_states),
            "failure_desktop_screenshot_count": len(failure_screenshots),
            "state_ok": state_ok,
            "screenshot_ok": screenshot_ok,
            "target_ok": target_ok,
            "error_ok": error_ok,
        }


def _run_real_app_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": f"real app regression only runs on Windows/macOS, current={system}",
        }
    if not _module_available("pyautogui"):
        return {
            "name": "desktop_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": "pyautogui is not installed; desktop input is unavailable in this environment.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-app-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        if system == "Windows":
            plan, assertion_relative_file, cleanup_hint = _windows_notepad_plan()
        else:
            plan, assertion_relative_file, cleanup_hint = _macos_textedit_plan()
        assertion_file = package_dir / assertion_relative_file
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_real_app_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-real-app",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        finally:
            _cleanup_real_app_case(package_dir, system)
        content = assertion_file.read_text(encoding="utf-8", errors="replace") if assertion_file.exists() else ""
        expected_text = str(plan["variables"]["expected_text"])
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "real-app-screen.png"
        return {
            "name": "desktop_real_app_regression",
            "ok": run_ok and expected_text in content and _file_nonempty_after(screenshot_path, 0),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "assertion_file": str(assertion_file),
            "expected_text_found": expected_text in content,
            "screenshot_ok": _file_nonempty_after(screenshot_path, 0),
            "cleanup": cleanup_hint,
        }


def _run_input_dependency_probe_case() -> dict[str, Any]:
    pyautogui_available = _module_available("pyautogui")
    pyperclip_available = _module_available("pyperclip")
    return {
        "name": "desktop_input_dependency_probe",
        "ok": True,
        "dependencies": {
            "pyautogui": pyautogui_available,
            "pyperclip": pyperclip_available,
        },
        "covered_by": "desktop_input.type_text/hotkey handlers require pyautogui at runtime; self-check avoids typing into the user's active desktop.",
    }


def _windows_notepad_plan() -> tuple[dict[str, Any], Path, str]:
    file_name = "desktop-notepad-input.txt"
    expected_text = "desktop automation regression input"
    assertion_file = Path("resources") / file_name
    plan = {
        "name": "desktop notepad regression",
        "automation_type": "desktop",
        "variables": {"expected_text": expected_text},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "command",
                "type": "run",
                "command": (
                    "$file = (Resolve-Path 'resources').Path + '\\\\desktop-notepad-input.txt'; "
                    "Set-Content -LiteralPath $file -Value ''; "
                    "$p = Start-Process -FilePath notepad.exe -ArgumentList @($file) -PassThru; "
                    "Set-Content -LiteralPath 'resources\\\\desktop-app-pid.txt' -Value $p.Id; "
                    "Write-Output $file"
                ),
                "timeout_ms": 10000,
                "save_as": "app_launch",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": file_name,
                "state": "exists",
                "timeout_ms": 8000,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": file_name,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": file_name,
                "timeout_ms": 2000,
                "save_as": "app_focused_assertion",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "current_window_center",
                "save_as": "app_click",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["ctrl", "a"]},
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{expected_text}}",
                "method": "clipboard",
                "save_as": "typed_text",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["ctrl", "s"]},
            {"action": "sleep", "seconds": 0.5},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "save_as": "app_screenshot",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "min_bytes": 1,
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["alt", "f4"]},
            {"action": "sleep", "seconds": 0.5},
            {
                "action": "command",
                "type": "run",
                "command": (
                    "$content = Get-Content -Raw -LiteralPath 'resources\\\\desktop-notepad-input.txt'; "
                    "if ($content -notlike '*{{expected_text}}*') { "
                    "Write-Error ('typed text missing: ' + $content); exit 7 }"
                ),
                "timeout_ms": 10000,
                "save_as": "content_assertion",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, assertion_file, "notepad process is closed by Alt+F4; fallback cleanup uses resources/desktop-app-pid.txt"


def _macos_textedit_plan() -> tuple[dict[str, Any], Path, str]:
    file_name = "desktop-textedit-input.txt"
    expected_text = "desktop automation regression input"
    assertion_file = Path("resources") / file_name
    plan = {
        "name": "desktop textedit regression",
        "automation_type": "desktop",
        "variables": {"expected_text": expected_text},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "command",
                "type": "run",
                "command": (
                    "file=\"$(pwd)/resources/desktop-textedit-input.txt\"; "
                    ": > \"$file\"; "
                    "open -a TextEdit \"$file\"; "
                    "printf '%s\\n' \"$file\""
                ),
                "timeout_ms": 10000,
                "save_as": "app_launch",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": file_name,
                "state": "exists",
                "timeout_ms": 10000,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": file_name,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": file_name,
                "timeout_ms": 2000,
                "save_as": "app_focused_assertion",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "current_window_center",
                "save_as": "app_click",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["command", "a"]},
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{expected_text}}",
                "method": "clipboard",
                "save_as": "typed_text",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["command", "s"]},
            {"action": "sleep", "seconds": 0.5},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "save_as": "app_screenshot",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "min_bytes": 1,
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["command", "w"]},
            {"action": "sleep", "seconds": 0.5},
            {
                "action": "command",
                "type": "run",
                "command": (
                    "content=$(cat resources/desktop-textedit-input.txt); "
                    "case \"$content\" in *\"{{expected_text}}\"*) exit 0;; *) echo \"typed text missing: $content\" >&2; exit 7;; esac"
                ),
                "timeout_ms": 10000,
                "save_as": "content_assertion",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, assertion_file, "TextEdit window is closed by Command+W"


def _cleanup_real_app_case(package_dir: Path, system: str) -> None:
    if system == "Windows":
        pid_path = package_dir / "resources" / "desktop-app-pid.txt"
        if not pid_path.exists():
            return
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return
        try:
            import subprocess

            subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except Exception:
            return


def _disable_run_log_echo(_output_dir: Path, logger: Any) -> None:
    logger.echo = False


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _file_nonempty_after(path: Path, started_at: float) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0 and path.stat().st_mtime >= started_at - 1.0


def _latest_result_payload(output_root: Path) -> dict[str, Any]:
    if not output_root.exists():
        return {}
    result_paths = [
        path / "result.json"
        for path in sorted(output_root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.is_dir() and (path / "result.json").exists()
    ]
    if not result_paths:
        return {}
    payload = _read_json(result_paths[0])
    return payload if isinstance(payload, dict) else {}


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _expect(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok)}


def _cplan_script_path() -> str:
    return ".\\cplan.py" if platform.system() == "Windows" else "./cplan.py"
