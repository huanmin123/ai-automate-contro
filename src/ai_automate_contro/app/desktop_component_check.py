from __future__ import annotations

import base64
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project
from ai_automate_contro.debug.run_failure_analysis import (
    analyze_latest_run_failure_tool,
    build_desktop_repair_suggestions,
    collect_desktop_diagnostics,
)
from ai_automate_contro.engine.desktop.backends.capabilities import (
    resolve_tesseract_binary,
    tesseract_binary_details,
    tesseract_language_available,
)
from ai_automate_contro.engine.desktop.coordinates import (
    CoordinateMapper,
    build_coordinate_profile,
    local_to_screen_bounds,
    local_to_screen_point,
    screen_to_local_bounds,
    screen_to_local_point,
)
from ai_automate_contro.engine.desktop.profiles import apply_desktop_app_profile
from ai_automate_contro.engine.desktop.run_protection import desktop_run_mutex_context
from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file


DESKTOP_REGRESSION_PLAN = Path("test-plans/desktop/basic/plan.json")


def desktop_temporary_form_skip_reason(system: str | None = None) -> str:
    resolved_system = system or platform.system()
    if resolved_system not in {"Windows", "Darwin"}:
        return f"temporary desktop form only runs on Windows/macOS, current={resolved_system}"
    if resolved_system == "Windows" and not _windows_powershell_executable():
        return "PowerShell is unavailable; temporary WinForms regression cannot run."
    if resolved_system == "Darwin" and not _module_available("tkinter"):
        return "tkinter is unavailable; temporary macOS form regression cannot run."
    return ""


def build_temporary_desktop_form_plan(package_dir: Path, system: str | None = None) -> tuple[dict[str, Any], Path, str]:
    return _temporary_form_plan(package_dir, system or platform.system())


def cleanup_temporary_desktop_form_case(package_dir: Path, system: str | None = None) -> None:
    _cleanup_temporary_form_case(package_dir, system or platform.system())


def self_check_desktop_components(
    project_root: Path,
    *,
    require_input: bool = False,
    require_wpf: bool = False,
    require_vision: bool = False,
    require_ocr: bool = False,
    require_ocr_zh: bool = False,
) -> dict[str, Any]:
    resolved_root = Path(project_root).resolve()
    schema_cases = _run_schema_cases(resolved_root)
    coordinate_case = _run_coordinate_profile_case()
    profile_merge_case = _run_desktop_profile_merge_case()
    run_mutex_case = _run_desktop_run_mutex_case(resolved_root)
    runtime_case = _run_runtime_case(resolved_root)
    failure_case = _run_failure_capture_case(resolved_root)
    element_failure_case = _run_element_failure_capture_case(resolved_root)
    launch_only_case = _run_launch_only_case(resolved_root)
    profile_case = _run_desktop_profile_case(resolved_root)
    vision_case = _run_vision_locator_case(resolved_root)
    ocr_case = _run_ocr_locator_case(resolved_root)
    ocr_zh_case = _run_ocr_zh_locator_case(resolved_root)
    ocr_config_case = _run_ocr_config_path_case(resolved_root)
    ocr_bad_config_case = _run_ocr_bad_config_path_case(resolved_root)
    real_app_case = _run_real_app_matrix_case(resolved_root)
    element_action_case = _run_element_action_case(resolved_root)
    wpf_action_case = _run_wpf_element_action_case(resolved_root, required=require_wpf) if require_wpf else None
    input_probe_case = _run_input_dependency_probe_case()
    capability_diagnostics_case = _run_capability_diagnostics_case()
    required_input_case = _run_required_input_case(input_probe_case, element_action_case) if require_input else None
    required_vision_case = _run_required_vision_case(vision_case, element_action_case) if require_vision else None
    required_ocr_case = _run_required_ocr_case(ocr_case, resolved_root) if require_ocr else None
    required_ocr_zh_case = _run_required_ocr_zh_case(ocr_zh_case, resolved_root) if require_ocr_zh else None
    schema_ok = all(case["ok"] for case in schema_cases)
    coordinate_ok = bool(coordinate_case["ok"])
    profile_merge_ok = bool(profile_merge_case["ok"])
    run_mutex_ok = bool(run_mutex_case["ok"])
    runtime_ok = bool(runtime_case["ok"])
    failure_ok = bool(failure_case["ok"])
    element_failure_ok = bool(element_failure_case["ok"])
    launch_only_ok = bool(launch_only_case["ok"])
    profile_ok = bool(profile_case["ok"])
    vision_ok = bool(vision_case["ok"])
    ocr_ok = bool(ocr_case["ok"])
    ocr_zh_ok = bool(ocr_zh_case["ok"])
    ocr_config_ok = bool(ocr_config_case["ok"])
    ocr_bad_config_ok = bool(ocr_bad_config_case["ok"])
    real_app_ok = bool(real_app_case["ok"])
    element_action_ok = bool(element_action_case["ok"])
    wpf_action_ok = wpf_action_case is None or bool(wpf_action_case["ok"])
    input_probe_ok = bool(input_probe_case["ok"])
    capability_diagnostics_ok = bool(capability_diagnostics_case["ok"])
    required_input_ok = required_input_case is None or bool(required_input_case["ok"])
    required_vision_ok = required_vision_case is None or bool(required_vision_case["ok"])
    required_ocr_ok = required_ocr_case is None or bool(required_ocr_case["ok"])
    required_ocr_zh_ok = required_ocr_zh_case is None or bool(required_ocr_zh_case["ok"])
    checks = [
        {
            "name": "desktop_schema_and_execution_line_validation",
            "ok": schema_ok,
            "cases": schema_cases,
        },
        coordinate_case,
        profile_merge_case,
        run_mutex_case,
        runtime_case,
        failure_case,
        element_failure_case,
        launch_only_case,
        profile_case,
        vision_case,
        ocr_case,
        ocr_zh_case,
        ocr_config_case,
        ocr_bad_config_case,
        real_app_case,
        element_action_case,
        input_probe_case,
        capability_diagnostics_case,
    ]
    if wpf_action_case is not None:
        checks.append(wpf_action_case)
    if required_input_case is not None:
        checks.append(required_input_case)
    if required_vision_case is not None:
        checks.append(required_vision_case)
    if required_ocr_case is not None:
        checks.append(required_ocr_case)
    if required_ocr_zh_case is not None:
        checks.append(required_ocr_zh_case)
    return {
        "ok": schema_ok
        and coordinate_ok
        and profile_merge_ok
        and run_mutex_ok
        and runtime_ok
        and failure_ok
        and element_failure_ok
        and launch_only_ok
        and profile_ok
        and vision_ok
        and ocr_ok
        and ocr_zh_ok
        and ocr_config_ok
        and ocr_bad_config_ok
        and real_app_ok
        and element_action_ok
        and wpf_action_ok
        and input_probe_ok
        and capability_diagnostics_ok
        and required_input_ok
        and required_vision_ok
        and required_ocr_ok
        and required_ocr_zh_ok,
        "require_input": require_input,
        "require_wpf": require_wpf,
        "require_vision": require_vision,
        "require_ocr": require_ocr,
        "require_ocr_zh": require_ocr_zh,
        "checks": checks,
        "commands": {
            "run": f"python {_cplan_script_path()} self-check desktop-components",
            "run_require_input": f"python {_cplan_script_path()} self-check desktop-components --require-input",
            "run_require_wpf": f"python {_cplan_script_path()} self-check desktop-components --require-wpf",
            "run_require_vision": f"python {_cplan_script_path()} self-check desktop-components --require-vision",
            "run_require_ocr": f"python {_cplan_script_path()} self-check desktop-components --require-ocr",
            "run_require_ocr_zh": f"python {_cplan_script_path()} self-check desktop-components --require-ocr-zh",
            "create_desktop_plan": f"python {_cplan_script_path()} create --path plans/desktop-demo --automation-type desktop",
        },
    }


def self_check_desktop_real_app(project_root: Path) -> dict[str, Any]:
    resolved_root = Path(project_root).resolve()
    real_app_case = _run_real_app_matrix_case(resolved_root)
    return {
        "ok": bool(real_app_case["ok"]),
        "checks": [real_app_case],
        "commands": {
            "run": f"python {_cplan_script_path()} self-check desktop-real-app",
            "full_desktop_components": f"python {_cplan_script_path()} self-check desktop-components",
        },
    }


def _run_coordinate_profile_case() -> dict[str, Any]:
    display = {
        "width": 1920,
        "height": 1080,
        "virtual_x": -1280,
        "virtual_y": 0,
        "virtual_width": 3200,
        "virtual_height": 1080,
        "monitor_count": 2,
        "dpi": {"x": 120, "y": 120},
        "scale": 1.25,
    }
    source_bounds = {"x": -320, "y": 80, "width": 640, "height": 360}
    local_bounds = {"x": 12, "y": 20, "width": 50, "height": 30}
    local_point = {"x": 37, "y": 35}
    screen_bounds = local_to_screen_bounds(local_bounds, source_bounds=source_bounds)
    screen_point = local_to_screen_point(local_point, source_bounds=source_bounds)
    roundtrip_bounds = screen_to_local_bounds(screen_bounds, source_bounds=source_bounds)
    roundtrip_point = screen_to_local_point(screen_point, source_bounds=source_bounds)
    screen_profile = build_coordinate_profile(
        platform="windows",
        backend="native",
        display=display,
        source_kind="window",
        source_bounds=source_bounds,
        source_size={"width": 640, "height": 360},
        coordinate_space={"origin": "screen", "unit": "logical_px", "scale": 1.25},
        screen_clickable=True,
    )
    offline_profile = build_coordinate_profile(
        platform="windows",
        backend="native",
        display=screen_profile.get("display") if isinstance(screen_profile.get("display"), dict) else {},
        source_kind="source_path",
        source_bounds={"x": 0, "y": 0, "width": 200, "height": 100},
        source_size={"width": 200, "height": 100},
        coordinate_space={"origin": "source_path", "unit": "logical_px", "scale": None},
        screen_clickable=False,
    )
    mapper = CoordinateMapper.from_profile(screen_profile)
    offline_mapper = CoordinateMapper.from_profile(offline_profile)
    mapper_screen_bounds = mapper.local_to_screen_bounds(local_bounds)
    mapper_screen_point = mapper.local_to_screen_point(local_point)
    mapper_roundtrip_bounds = mapper.screen_to_local_bounds(mapper_screen_bounds)
    mapper_roundtrip_point = mapper.screen_to_local_point(mapper_screen_point)
    safety = mapper.safety_check(mapper_screen_point, target="synthetic")
    offline_safety = offline_mapper.safety_check({"x": 10, "y": 10}, target="offline")
    passed = (
        screen_bounds == {"x": -308, "y": 100, "width": 50, "height": 30}
        and screen_point == {"x": -283, "y": 115}
        and roundtrip_bounds == local_bounds
        and roundtrip_point == local_point
        and mapper_screen_bounds == screen_bounds
        and mapper_screen_point == screen_point
        and mapper_roundtrip_bounds == local_bounds
        and mapper_roundtrip_point == local_point
        and safety.get("ok") is True
        and safety.get("scale_applied") is False
        and _coordinate_profile_ok(screen_profile, screen_clickable=True)
        and screen_profile.get("display", {}).get("virtual_bounds", {}).get("x") == -1280
        and screen_profile.get("display", {}).get("scale") == 1.25
        and "negative_source_origin" in screen_profile.get("warnings", [])
        and _coordinate_profile_ok(offline_profile, screen_clickable=False)
        and "not_screen_clickable" in offline_profile.get("warnings", [])
        and offline_safety.get("ok") is False
        and offline_safety.get("reason") == "source_not_screen_clickable"
    )
    return {
        "name": "desktop_coordinate_profile_mapper",
        "ok": passed,
        "screen_bounds": screen_bounds,
        "screen_point": screen_point,
        "roundtrip_bounds": roundtrip_bounds,
        "roundtrip_point": roundtrip_point,
        "screen_profile": screen_profile,
        "offline_profile": offline_profile,
        "mapper_safety": safety,
        "offline_mapper_safety": offline_safety,
    }


def _run_desktop_profile_merge_case() -> dict[str, Any]:
    merged, profile = apply_desktop_app_profile(
        {
            "action": "desktop_app",
            "desktop": "desktop",
            "type": "launch",
            "profile": "notepad",
            "command": "python",
            "args": ["-V"],
        },
        platform_name="windows",
    )
    custom_config = {
        "desktop_profiles": {
            "mock-chat": {
                "platforms": {
                    "windows": {
                        "launch": {"command": "mock-chat.exe"},
                        "window_query": {"process_name": "mock-chat.exe"},
                        "defaults": {"wait_for_window": True, "focus": True},
                    }
                }
            }
        }
    }
    custom_merged, custom_profile = apply_desktop_app_profile(
        {"profile": "mock-chat", "type": "launch"},
        platform_name="windows",
        desktop_config=custom_config,
    )
    passed = (
        merged.get("command") == "python"
        and "app" not in merged
        and merged.get("args") == ["-V"]
        and merged.get("process_name") == "notepad.exe"
        and profile.get("source") == "builtin"
        and custom_merged.get("command") == "mock-chat.exe"
        and custom_merged.get("process_name") == "mock-chat.exe"
        and custom_merged.get("wait_for_window") is True
        and custom_profile.get("id") == "mock_chat"
        and custom_profile.get("source") == "config"
    )
    return {
        "name": "desktop_app_profile_merge",
        "ok": passed,
        "merged": merged,
        "profile": profile,
        "custom_merged": custom_merged,
        "custom_profile": custom_profile,
    }


def _run_desktop_run_mutex_case(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-components-run-mutex-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "desktop run mutex regression",
            "automation_type": "desktop",
            "steps": [{"action": "print", "message": "desktop run mutex pass"}],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_run_mutex_blocks_concurrent_runs",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        owner_output = package_dir / "output" / "mutex-owner"
        owner_output.mkdir(parents=True, exist_ok=True)
        blocked_error = ""
        blocked_ok = False
        try:
            with desktop_run_mutex_context(
                project_root=project_root,
                plan_dir=package_dir,
                output_dir=owner_output,
                run_name="desktop-components-held-mutex",
                plan_config={},
            ):
                try:
                    execute_plan(
                        plan,
                        project_root,
                        plan_path=plan_path,
                        run_name="desktop-components-mutex-blocked",
                        run_context_handler=_disable_run_log_echo,
                    )
                except Exception as error:
                    blocked_error = str(error)
                    blocked_ok = "已有 desktop plan 正在控制当前项目桌面资源" in blocked_error
                else:
                    blocked_ok = False
        except Exception as error:
            return {
                "name": "desktop_run_mutex_blocks_concurrent_runs",
                "ok": False,
                "validation_ok": True,
                "lock_owner_error": str(error),
            }
        blocked_result_paths = sorted((package_dir / "output").glob("*desktop-components-mutex-blocked/result.json"))
        blocked_result = _read_json(blocked_result_paths[-1]) if blocked_result_paths else {}
        blocked_result_ok = (
            isinstance(blocked_result, dict)
            and blocked_result.get("status") == "failed"
            and "已有 desktop plan 正在控制当前项目桌面资源" in str(blocked_result.get("error", ""))
        )
        run_error = ""
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-mutex-free",
                run_context_handler=_disable_run_log_echo,
            )
            released_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            released_ok = False
            output_dir = ""
            run_error = str(error)
        return {
            "name": "desktop_run_mutex_blocks_concurrent_runs",
            "ok": blocked_ok and blocked_result_ok and released_ok,
            "validation_ok": True,
            "blocked_ok": blocked_ok,
            "blocked_error": blocked_error,
            "blocked_result_ok": blocked_result_ok,
            "blocked_result_paths": [str(path) for path in blocked_result_paths],
            "released_ok": released_ok,
            "output_dir": output_dir,
            "run_error": run_error,
        }


def _run_required_input_case(input_probe_case: dict[str, Any], element_action_case: dict[str, Any]) -> dict[str, Any]:
    dependency_reason = _desktop_input_dependency_skip_reason()
    input_coverage = (
        element_action_case.get("input_coverage")
        if isinstance(element_action_case.get("input_coverage"), dict)
        else {}
    )
    required_checks = (
        "mouse_steps_enabled",
        "clipboard_restore_enabled",
        "latest_candidate_click_ok",
        "candidate_click_ok",
        "bounds_center_click_ok",
        "latest_candidate_click_window_safety_ok",
        "candidate_click_window_safety_ok",
        "bounds_center_click_window_safety_ok",
        "point_ownership_ok",
        "context_menu_ok",
        "scroll_ok",
        "clipboard_restore_ok",
        "mouse_double_click_ok",
        "mouse_right_click_ok",
        "mouse_scroll_ok",
        "mouse_drag_ok",
    )
    failed = [name for name in required_checks if input_coverage.get(name) is not True]
    issues: list[str] = []
    if dependency_reason:
        issues.append(dependency_reason)
    if not bool(input_probe_case.get("ok")):
        issues.append("desktop input dependency probe did not pass.")
    if not bool(element_action_case.get("ok")):
        issues.append("desktop temporary form input regression did not pass.")
    if failed:
        issues.append("desktop input coverage missing or failed: " + ", ".join(failed))
    return {
        "name": "desktop_input_required_regression",
        "ok": not issues,
        "require_input": True,
        "dependencies_ok": not dependency_reason,
        "input_probe_ok": bool(input_probe_case.get("ok")),
        "element_action_ok": bool(element_action_case.get("ok")),
        "input_coverage": input_coverage,
        "issues": issues,
    }


def _run_required_vision_case(vision_case: dict[str, Any], element_action_case: dict[str, Any]) -> dict[str, Any]:
    dependency_reason = _desktop_vision_dependency_skip_reason()
    basic_vision_ok = bool(vision_case.get("ok")) and not bool(vision_case.get("skipped"))
    source_target_enabled = bool(element_action_case.get("vision_source_target_enabled"))
    source_target_ok = (
        bool(element_action_case.get("ok"))
        and source_target_enabled
        and bool(element_action_case.get("window_vision_ok"))
        and bool(element_action_case.get("element_vision_ok"))
    )
    issues: list[str] = []
    if dependency_reason:
        issues.append(dependency_reason)
    if not basic_vision_ok:
        issues.append("desktop_vision locate_image base regression did not run successfully.")
    if not source_target_enabled:
        issues.append("desktop_vision source_target=window/element regression was skipped.")
    elif not source_target_ok:
        issues.append("desktop_vision source_target=window/element regression did not pass.")
    return {
        "name": "desktop_vision_required_regression",
        "ok": not issues,
        "require_vision": True,
        "dependencies_ok": not dependency_reason,
        "basic_vision_ok": basic_vision_ok,
        "source_target_enabled": source_target_enabled,
        "source_target_ok": source_target_ok,
        "issues": issues,
    }


def _run_required_ocr_case(ocr_case: dict[str, Any], project_root: Path) -> dict[str, Any]:
    dependency_reason = _desktop_ocr_dependency_skip_reason("eng", project_root)
    ocr_ok = bool(ocr_case.get("ok")) and not bool(ocr_case.get("skipped"))
    issues: list[str] = []
    if dependency_reason:
        issues.append(dependency_reason)
    if not ocr_ok:
        issues.append("desktop_vision locate_text OCR regression did not run successfully.")
    return {
        "name": "desktop_ocr_required_regression",
        "ok": not issues,
        "require_ocr": True,
        "dependencies_ok": not dependency_reason,
        "ocr_ok": ocr_ok,
        "issues": issues,
    }


def _run_required_ocr_zh_case(ocr_zh_case: dict[str, Any], project_root: Path) -> dict[str, Any]:
    dependency_reason = _desktop_ocr_dependency_skip_reason("chi_sim", project_root)
    ocr_ok = bool(ocr_zh_case.get("ok")) and not bool(ocr_zh_case.get("skipped"))
    issues: list[str] = []
    if dependency_reason:
        issues.append(dependency_reason)
    if not ocr_ok:
        issues.append("desktop_vision locate_text Chinese OCR regression did not run successfully.")
    return {
        "name": "desktop_ocr_zh_required_regression",
        "ok": not issues,
        "require_ocr_zh": True,
        "dependencies_ok": not dependency_reason,
        "ocr_ok": ocr_ok,
        "issues": issues,
    }


def _desktop_vision_dependency_skip_reason() -> str:
    if not _module_available("cv2"):
        return "opencv-python is not installed; desktop_vision locate_image is unavailable."
    if not _module_available("PIL"):
        return "Pillow is not installed; desktop_vision fixture images cannot be generated."
    return ""


def _desktop_input_dependency_skip_reason() -> str:
    missing = [module for module in ("pyautogui", "pyperclip") if not _module_available(module)]
    if missing:
        return "desktop input strict regression requires installed modules: " + ", ".join(missing)
    return ""


def _desktop_ocr_dependency_skip_reason(language: str = "eng", project_root: Path | None = None) -> str:
    if not _module_available("PIL"):
        return "Pillow is not installed; desktop_vision locate_text fixture images cannot be generated."
    if "chi_sim" in str(language) and not _ocr_fixture_font_available("zh"):
        return "Chinese OCR fixture font is unavailable; install Microsoft YaHei/SimHei/PingFang/Noto CJK."
    desktop_config = _desktop_ocr_config(project_root)
    tesseract = tesseract_binary_details(desktop_config)
    if not resolve_tesseract_binary(desktop_config):
        return (
            "tesseract is not installed, not on PATH, and not configured via "
            "config.json desktop.ocr.tesseract_path; desktop_vision locate_text is unavailable. "
            f"source={tesseract.get('source') or 'unresolved'}"
        )
    if not tesseract_language_available(language, desktop_config):
        return f"tesseract language data is missing: {language}"
    return ""


def _desktop_ocr_config(project_root: Path | None = None) -> dict[str, Any]:
    if project_root is None:
        return {}
    try:
        config_dir = default_ai_config_dir_for_project(project_root)
        config = load_plan_config(project_root, config_dir)
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


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
            "name": "desktop-open-rejects-unimplemented-backend",
            "expected_message": "backend 不支持的取值",
            "plan": {
                "name": "bad desktop backend",
                "automation_type": "desktop",
                "steps": [{"action": "open_desktop", "name": "desktop", "backend": "windows-uia"}],
            },
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
            "name": "desktop-find-requires-query",
            "expected_message": "desktop_window.find 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window find query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "find"},
                ],
            },
        },
        {
            "name": "desktop-app-wait-for-window-requires-query",
            "expected_message": "desktop_app.launch wait_for_window 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing launch wait window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_app",
                        "desktop": "desktop",
                        "type": "launch",
                        "command": "notepad.exe",
                        "wait_for_window": True,
                    },
                ],
            },
        },
        {
            "name": "desktop-app-profile-validates",
            "expected_ok": True,
            "plan": {
                "name": "valid desktop app profile",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_app",
                        "desktop": "desktop",
                        "type": "launch",
                        "profile": "notepad",
                        "save_as": "launch_result",
                    },
                ],
            },
        },
        {
            "name": "desktop-window-profile-validates",
            "expected_ok": True,
            "plan": {
                "name": "valid desktop window profile",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_window",
                        "desktop": "desktop",
                        "type": "focus",
                        "profile": "notepad",
                    },
                ],
            },
        },
        {
            "name": "desktop-profile-config-rejects-bad-launch",
            "expected_message": "launch 必须是 JSON 对象",
            "files": {
                "config.json": {
                    "desktop_profiles": {
                        "bad-profile": {
                            "platforms": {
                                "windows": {
                                    "launch": "not-an-object"
                                }
                            }
                        }
                    }
                }
            },
            "plan": {
                "name": "bad desktop profile config",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_app",
                        "desktop": "desktop",
                        "type": "launch",
                        "profile": "bad-profile",
                    },
                ],
            },
        },
        {
            "name": "desktop-run-mutex-config-rejects-bad-timeout",
            "expected_message": "wait_timeout_seconds 必须是非负整数",
            "files": {
                "config.json": {
                    "desktop": {
                        "run_mutex": {
                            "enabled": True,
                            "wait_timeout_seconds": "slow",
                        }
                    }
                }
            },
            "plan": {
                "name": "bad desktop run mutex config",
                "automation_type": "desktop",
                "steps": [{"action": "print", "message": "ok"}],
            },
        },
        {
            "name": "desktop-foreground-protection-config-rejects-bad-attempts",
            "expected_message": "activation_attempts 必须是正整数",
            "files": {
                "config.json": {
                    "desktop": {
                        "foreground_protection": {
                            "activation_attempts": 0,
                        }
                    }
                }
            },
            "plan": {
                "name": "bad desktop foreground protection config",
                "automation_type": "desktop",
                "steps": [{"action": "print", "message": "ok"}],
            },
        },
        {
            "name": "desktop-close-requires-query",
            "expected_message": "desktop_window.close 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window close query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "close"},
                ],
            },
        },
        {
            "name": "desktop-minimize-requires-query",
            "expected_message": "desktop_window.minimize 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window minimize query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "minimize"},
                ],
            },
        },
        {
            "name": "desktop-maximize-requires-query",
            "expected_message": "desktop_window.maximize 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window maximize query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "maximize"},
                ],
            },
        },
        {
            "name": "desktop-restore-requires-query",
            "expected_message": "desktop_window.restore 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing window restore query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_window", "desktop": "desktop", "type": "restore"},
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
            "name": "desktop-click-element-center-requires-window-query",
            "expected_message": "desktop_input.click 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop element center query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "element_center",
                        "name_contains": "Save",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-element-center-profile-validates",
            "expected_ok": True,
            "plan": {
                "name": "valid desktop element center profile click",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "element_center",
                        "profile": "notepad",
                        "name_contains": "Save",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-current-window-offset-requires-offset",
            "expected_message": "desktop_input.click target=current_window_offset 缺少必填字段：offset_x",
            "plan": {
                "name": "missing desktop offset",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "current_window_offset",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-bounds-center-requires-bounds",
            "expected_message": "desktop_input.click target=bounds_center 缺少必填字段：bounds",
            "plan": {
                "name": "missing desktop bounds center bounds",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "bounds_center",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-bounds-center-rejects-invalid-bounds",
            "expected_message": "bounds.width 必须大于 0",
            "plan": {
                "name": "invalid desktop bounds center bounds",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "bounds_center",
                        "bounds": {"x": 1, "y": 1, "width": 0, "height": 10},
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-requires-target-candidates",
            "expected_message": "desktop_input.click target=candidate 缺少候选来源",
            "plan": {
                "name": "missing desktop candidate source",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "candidate_id": "element_match-0",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-requires-candidate-id",
            "expected_message": "desktop_input.click target=candidate 缺少必填字段：candidate_id",
            "plan": {
                "name": "missing desktop candidate id",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "target_candidates": {"kind": "desktop_target_candidates", "candidates": []},
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-rejects-expanded-bounds",
            "expected_message": "target=candidate 不能同时展开 bounds",
            "plan": {
                "name": "mixed desktop candidate bounds",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "target_candidates": {"kind": "desktop_target_candidates", "candidates": []},
                        "candidate_id": "element_match-0",
                        "bounds": {"x": 1, "y": 1, "width": 10, "height": 10},
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-rejects-profile",
            "expected_message": "target=candidate 不能同时展开 bounds",
            "plan": {
                "name": "mixed desktop candidate profile",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "target_candidates": {"kind": "desktop_target_candidates", "candidates": []},
                        "candidate_id": "element_match-0",
                        "profile": "notepad",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-validates",
            "expected_ok": True,
            "plan": {
                "name": "valid desktop candidate click",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "target_candidates": {
                            "kind": "desktop_target_candidates",
                            "best_candidate": {"id": "element_match-0", "candidate_id": "element_match-0"},
                            "candidates": [{"id": "element_match-0", "candidate_id": "element_match-0"}],
                        },
                        "candidate_id": "element_match-0",
                    },
                ],
            },
        },
        {
            "name": "desktop-click-candidate-latest-source-validates",
            "expected_ok": True,
            "plan": {
                "name": "valid desktop latest candidate source click",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "candidate",
                        "candidate_source": "latest",
                        "candidate_id": "best_candidate",
                    },
                ],
            },
        },
        {
            "name": "desktop-double-click-requires-target-or-coordinates",
            "expected_message": "desktop_input.double_click 需要 target 或 x/y",
            "plan": {
                "name": "missing desktop double click target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "double_click"},
                ],
            },
        },
        {
            "name": "desktop-right-click-requires-target-or-coordinates",
            "expected_message": "desktop_input.right_click 需要 target 或 x/y",
            "plan": {
                "name": "missing desktop right click target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "right_click"},
                ],
            },
        },
        {
            "name": "desktop-scroll-requires-amount",
            "expected_message": "desktop_input.scroll 需要 amount",
            "plan": {
                "name": "missing desktop scroll amount",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "scroll",
                        "target": "current_window_center",
                    },
                ],
            },
        },
        {
            "name": "desktop-scroll-rejects-zero-amount",
            "expected_message": "desktop_input.scroll amount 不能为 0",
            "plan": {
                "name": "zero desktop scroll amount",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "scroll",
                        "target": "current_window_center",
                        "amount": 0,
                    },
                ],
            },
        },
        {
            "name": "desktop-scroll-rejects-mixed-target-and-coordinates",
            "expected_message": "desktop_input.scroll 不能同时使用 target 和 x/y",
            "plan": {
                "name": "mixed desktop scroll target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "scroll",
                        "target": "current_window_center",
                        "x": 10,
                        "y": 10,
                        "amount": -1,
                    },
                ],
            },
        },
        {
            "name": "desktop-drag-requires-start-and-end",
            "expected_message": "desktop_input.drag 需要 target+delta_x/delta_y 或 start_x/start_y/end_x/end_y",
            "plan": {
                "name": "missing desktop drag points",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "drag"},
                ],
            },
        },
        {
            "name": "desktop-drag-target-requires-delta",
            "expected_message": "desktop_input.drag 使用 target 时需要 delta_x 或 delta_y",
            "plan": {
                "name": "missing desktop drag target delta",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "drag",
                        "target": "current_window_center",
                    },
                ],
            },
        },
        {
            "name": "desktop-type-text-requires-value",
            "expected_message": "desktop_input.type_text 缺少必填字段：value",
            "plan": {
                "name": "missing desktop type_text value",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "type_text"},
                ],
            },
        },
        {
            "name": "desktop-hotkey-requires-keys",
            "expected_message": "desktop_input.hotkey 缺少必填字段：keys",
            "plan": {
                "name": "missing desktop hotkey keys",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "hotkey"},
                ],
            },
        },
        {
            "name": "desktop-hotkey-rejects-empty-keys",
            "expected_message": "keys 必须是非空字符串数组",
            "plan": {
                "name": "empty desktop hotkey keys",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": []},
                ],
            },
        },
        {
            "name": "desktop-hotkey-rejects-non-string-key",
            "expected_message": "keys 每一项必须是非空字符串",
            "plan": {
                "name": "bad desktop hotkey key",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["ctrl", 1]},
                ],
            },
        },
        {
            "name": "desktop-app-args-rejects-non-string",
            "expected_message": "args 每一项必须是非空字符串",
            "plan": {
                "name": "bad desktop app args",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_app",
                        "desktop": "desktop",
                        "type": "launch",
                        "command": "notepad.exe",
                        "args": ["ok", 1],
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-image-requires-template",
            "expected_message": "desktop_vision.locate_image 缺少必填字段：template_path",
            "plan": {
                "name": "missing desktop vision template",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-image-rejects-invalid-threshold",
            "expected_message": "desktop_vision.locate_image threshold 必须在 0 到 1 之间",
            "plan": {
                "name": "bad desktop vision threshold",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "threshold": 1.5,
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-text-requires-text-query",
            "expected_message": "desktop_vision.locate_text 需要 text、text_contains 或 text_regex 之一",
            "plan": {
                "name": "missing desktop vision OCR text query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_text",
                        "path": "ocr.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-text-rejects-invalid-min-confidence",
            "expected_message": "desktop_vision.locate_text min_confidence 必须在 0 到 1 之间",
            "plan": {
                "name": "bad desktop vision OCR confidence",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_text",
                        "text_contains": "Ready",
                        "min_confidence": 1.5,
                        "path": "ocr.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-text-rejects-invalid-provider",
            "expected_message": "provider 不支持的取值",
            "plan": {
                "name": "bad desktop vision OCR provider",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_text",
                        "text_contains": "Ready",
                        "provider": "cloud",
                        "path": "ocr.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-text-source-target-window-requires-query",
            "expected_message": "desktop_vision.locate_text 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop vision OCR source window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_text",
                        "text_contains": "Ready",
                        "source_target": "window",
                        "path": "ocr.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-locate-text-rejects-source-path-and-source-target",
            "expected_message": "desktop_vision.locate_text 不能同时使用 source_path 和 source_target",
            "plan": {
                "name": "bad desktop vision OCR source mix",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_text",
                        "text_contains": "Ready",
                        "source_path": "resources/source.png",
                        "source_target": "window",
                        "title_contains": "Demo",
                        "path": "ocr.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-window-requires-query",
            "expected_message": "desktop_vision.locate_image 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop vision source window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "window",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-window-rejects-invalid-query-type",
            "expected_message": "title_contains 必须是非空字符串",
            "plan": {
                "name": "bad desktop vision source window query type",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "window",
                        "title_contains": 123,
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-window-rejects-invalid-window-match-index",
            "expected_message": "window_match_index 必须是整数",
            "plan": {
                "name": "bad desktop vision source window match index",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "window",
                        "title_contains": "Demo",
                        "window_match_index": "second",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-element-requires-locator",
            "expected_message": "desktop_vision.locate_image 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop vision source element locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "element",
                        "title_contains": "Demo",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-element-rejects-invalid-locator-type",
            "expected_message": "automation_id 必须是非空字符串",
            "plan": {
                "name": "bad desktop vision source element locator type",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "element",
                        "title_contains": "Demo",
                        "automation_id": [],
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-rejects-source-path-and-source-target",
            "expected_message": "desktop_vision.locate_image 不能同时使用 source_path 和 source_target",
            "plan": {
                "name": "bad desktop vision source mix",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_path": "resources/source.png",
                        "source_target": "window",
                        "title_contains": "Demo",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-rejects-invalid-source-target",
            "expected_message": "source_target 不支持的取值",
            "plan": {
                "name": "bad desktop vision source target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "dialog",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-source-target-element-rejects-not-exists-state",
            "expected_message": "state 不支持的取值",
            "plan": {
                "name": "bad desktop vision source element state",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "source_target": "element",
                        "title_contains": "Demo",
                        "automation_id": "DemoButton",
                        "state": "not_exists",
                        "path": "vision.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-rejects-invalid-region",
            "expected_message": "region.width 必须大于 0",
            "plan": {
                "name": "bad desktop capture region",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "path": "screen.png",
                        "region": {"x": 0, "y": 0, "width": 0, "height": 20},
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-allows-negative-region-origin",
            "expected_ok": True,
            "plan": {
                "name": "desktop region negative origin",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "region",
                        "region": {"x": -120, "y": -80, "width": 40, "height": 30},
                        "path": "negative-region.png",
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-window-target-requires-query",
            "expected_message": "desktop_capture.screenshot 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop capture window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "window",
                        "path": "window.png",
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-element-target-requires-locator",
            "expected_message": "desktop_capture.screenshot 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop capture element locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "element",
                        "title_contains": "Demo",
                        "path": "element.png",
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-region-target-requires-region",
            "expected_message": "desktop_capture.screenshot target=region 缺少必填字段：region",
            "plan": {
                "name": "missing desktop capture region target region",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "region",
                        "path": "region.png",
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-element-target-rejects-region",
            "expected_message": "desktop_capture.screenshot target=window/element 不能同时使用 region",
            "plan": {
                "name": "bad desktop capture element region mix",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "element",
                        "title_contains": "Demo",
                        "automation_id": "DemoButton",
                        "path": "element.png",
                        "region": {"x": 0, "y": 0, "width": 20, "height": 20},
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-window-target-rejects-region",
            "expected_message": "desktop_capture.screenshot target=window/element 不能同时使用 region",
            "plan": {
                "name": "bad desktop capture window region mix",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "window",
                        "title_contains": "Demo",
                        "path": "window.png",
                        "region": {"x": 0, "y": 0, "width": 20, "height": 20},
                    },
                ],
            },
        },
        {
            "name": "desktop-capture-element-target-rejects-not-exists-state",
            "expected_message": "state 不支持的取值",
            "plan": {
                "name": "bad desktop capture element state",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_capture",
                        "desktop": "desktop",
                        "type": "screenshot",
                        "target": "element",
                        "title_contains": "Demo",
                        "automation_id": "DemoButton",
                        "state": "not_exists",
                        "path": "element.png",
                    },
                ],
            },
        },
        {
            "name": "desktop-vision-rejects-incomplete-region",
            "expected_message": "region.height 缺少必填字段",
            "plan": {
                "name": "bad desktop vision region",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_vision",
                        "desktop": "desktop",
                        "type": "locate_image",
                        "template_path": "resources/template.png",
                        "path": "vision.json",
                        "region": {"x": 0, "y": 0, "width": 20},
                    },
                ],
            },
        },
        {
            "name": "desktop-input-rejects-unknown-target",
            "expected_message": "target 不支持的取值",
            "plan": {
                "name": "bad desktop input target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_input", "desktop": "desktop", "type": "click", "target": "screen-center"},
                ],
            },
        },
        {
            "name": "desktop-drag-rejects-target-and-start-end",
            "expected_message": "desktop_input.drag 不能同时使用 target 和 start/end 坐标",
            "plan": {
                "name": "mixed desktop drag modes",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "drag",
                        "target": "current_window_center",
                        "delta_x": 10,
                        "start_x": 1,
                        "start_y": 1,
                        "end_x": 2,
                        "end_y": 2,
                    },
                ],
            },
        },
        {
            "name": "desktop-drag-rejects-zero-delta",
            "expected_message": "desktop_input.drag delta_x 和 delta_y 不能同时为 0",
            "plan": {
                "name": "zero desktop drag delta",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "drag",
                        "target": "current_window_center",
                        "delta_x": 0,
                        "delta_y": 0,
                    },
                ],
            },
        },
        {
            "name": "desktop-click-rejects-invalid-button",
            "expected_message": "button 不支持的取值",
            "plan": {
                "name": "bad desktop click button",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "current_window_center",
                        "button": "primary",
                    },
                ],
            },
        },
        {
            "name": "desktop-drag-rejects-invalid-button",
            "expected_message": "button 不支持的取值",
            "plan": {
                "name": "bad desktop drag button",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "drag",
                        "target": "current_window_center",
                        "delta_x": 10,
                        "button": "primary",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-list-requires-window-query",
            "expected_message": "desktop_element.list 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop element window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_element", "desktop": "desktop", "type": "list"},
                ],
            },
        },
        {
            "name": "desktop-element-dump-requires-window-query",
            "expected_message": "desktop_element.dump 需要至少一种窗口定位字段",
            "plan": {
                "name": "missing desktop element dump window query",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_element", "desktop": "desktop", "type": "dump", "path": "elements-dump.json"},
                ],
            },
        },
        {
            "name": "desktop-element-find-requires-locator",
            "expected_message": "desktop_element.find 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop element locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "find",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-set-text-requires-value",
            "expected_message": "desktop_element.set_text 缺少必填字段：value",
            "plan": {
                "name": "missing desktop element set_text value",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "set_text",
                        "title_contains": "Demo",
                        "name_contains": "Login",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-invoke-requires-locator",
            "expected_message": "desktop_element.invoke 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop element invoke locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-click-path-rejects-output-prefix",
            "expected_message": "不要以 output/ 开头",
            "plan": {
                "name": "bad desktop element click path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "click",
                        "title_contains": "Demo",
                        "name_contains": "Save",
                        "path": "output/desktop-elements/click.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-requires-value",
            "expected_message": "desktop_element.select 需要 value 或 option_index",
            "plan": {
                "name": "missing desktop element select value",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select",
                        "title_contains": "Demo",
                        "automation_id": "Options",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-get-table-requires-locator",
            "expected_message": "desktop_element.get_table 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop table locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "get_table",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-get-table-rejects-bad-max-rows",
            "expected_message": "max_rows 必须大于或等于 1",
            "plan": {
                "name": "bad desktop table max rows",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "get_table",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "max_rows": 0,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-get-table-path-rejects-output-prefix",
            "expected_message": "不要以 output/ 开头",
            "plan": {
                "name": "bad desktop table path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "get_table",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "path": "output/desktop-elements/table.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-cell-requires-locator",
            "expected_message": "desktop_element.select_cell 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop table cell locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_cell",
                        "title_contains": "Demo",
                        "row": 1,
                        "column_index": 2,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-cell-requires-row",
            "expected_message": "desktop_element.select_cell 缺少必填字段：row",
            "plan": {
                "name": "missing desktop table cell row",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_cell",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "column_index": 2,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-cell-requires-column",
            "expected_message": "desktop_element.select_cell 需要 column 或 column_index",
            "plan": {
                "name": "missing desktop table cell column",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_cell",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "row": 1,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-cell-rejects-bad-column-index",
            "expected_message": "column_index 必须大于或等于 0",
            "plan": {
                "name": "bad desktop table cell column",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_cell",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "row": 1,
                        "column_index": -1,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-cell-path-rejects-output-prefix",
            "expected_message": "不要以 output/ 开头",
            "plan": {
                "name": "bad desktop table cell path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_cell",
                        "title_contains": "Demo",
                        "automation_id": "OrdersGrid",
                        "row": 1,
                        "column_index": 2,
                        "path": "output/desktop-elements/cell.json",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-get-tree-requires-locator",
            "expected_message": "desktop_element.get_tree 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop tree locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "get_tree",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-expand-tree-requires-path",
            "expected_message": "desktop_element.expand_tree 缺少必填字段：tree_path",
            "plan": {
                "name": "missing desktop tree path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "expand_tree",
                        "title_contains": "Demo",
                        "automation_id": "NavTree",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-select-tree-rejects-empty-path",
            "expected_message": "tree_path 必须是非空字符串数组",
            "plan": {
                "name": "bad desktop tree path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "select_tree",
                        "title_contains": "Demo",
                        "automation_id": "NavTree",
                        "tree_path": [],
                    },
                ],
            },
        },
        {
            "name": "desktop-element-invoke-menu-requires-path",
            "expected_message": "desktop_element.invoke_menu 缺少必填字段：menu_path",
            "plan": {
                "name": "missing desktop menu path",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke_menu",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-invoke-context-menu-requires-locator",
            "expected_message": "desktop_element.invoke_menu 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop context menu locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke_menu",
                        "title_contains": "Demo",
                        "open_context_menu": True,
                        "menu_path": ["Mark Context"],
                    },
                ],
            },
        },
        {
            "name": "desktop-element-scroll-element-requires-amount-or-target",
            "expected_message": "desktop_element.scroll_element 需要 amount 或 scroll_to",
            "plan": {
                "name": "missing desktop scroll amount",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "scroll_element",
                        "title_contains": "Demo",
                        "automation_id": "ScrollPanel",
                    },
                ],
            },
        },
        {
            "name": "desktop-element-scroll-element-rejects-zero",
            "expected_message": "desktop_element.scroll_element amount 不能为 0",
            "plan": {
                "name": "bad desktop scroll amount",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "scroll_element",
                        "title_contains": "Demo",
                        "automation_id": "ScrollPanel",
                        "amount": 0,
                    },
                ],
            },
        },
        {
            "name": "desktop-element-wait-rejects-invalid-state",
            "expected_message": "state 不支持的取值",
            "plan": {
                "name": "bad desktop element state",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "wait",
                        "title_contains": "Demo",
                        "name_contains": "Login",
                        "state": "visible",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-requires-locator",
            "expected_message": "desktop_assert.element 需要至少一种控件定位字段",
            "plan": {
                "name": "missing desktop assert element locator",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-rejects-invalid-mode",
            "expected_message": "mode 不支持的取值",
            "plan": {
                "name": "bad desktop assert element mode",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Status",
                        "mode": "starts_with",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-rejects-invalid-text-source",
            "expected_message": "text_source 不支持的取值",
            "plan": {
                "name": "bad desktop assert element text source",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Status",
                        "text_source": "label",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-not-exists-rejects-expected",
            "expected_message": "state=not_exists 不能同时使用 expected",
            "plan": {
                "name": "bad desktop assert not exists text",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Missing",
                        "state": "not_exists",
                        "expected": "Missing",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-property-requires-expected",
            "expected_message": "使用 property 时必须提供 property_expected",
            "plan": {
                "name": "bad desktop assert property",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Status",
                        "property": "enabled",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-rejects-invalid-property-mode",
            "expected_message": "property_mode 不支持的取值",
            "plan": {
                "name": "bad desktop assert property mode",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Status",
                        "property": "name",
                        "property_expected": "Status",
                        "property_mode": "starts_with",
                    },
                ],
            },
        },
        {
            "name": "desktop-assert-element-rejects-invalid-count-range",
            "expected_message": "min_count 不能大于 max_count",
            "plan": {
                "name": "bad desktop assert count range",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Demo",
                        "name_contains": "Status",
                        "min_count": 2,
                        "max_count": 1,
                    },
                ],
            },
        },
        {
            "name": "desktop-app-launch-requires-target",
            "expected_message": "desktop_app.launch 需要 app、path、command 或 profile 之一",
            "plan": {
                "name": "missing desktop app target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {"action": "desktop_app", "desktop": "desktop", "type": "launch"},
                ],
            },
        },
        {
            "name": "desktop-app-launch-rejects-mixed-targets",
            "expected_message": "desktop_app.launch 只能同时使用 app、path 或 command 之一",
            "plan": {
                "name": "mixed desktop app target",
                "automation_type": "desktop",
                "steps": [
                    {"action": "open_desktop", "name": "desktop"},
                    {
                        "action": "desktop_app",
                        "desktop": "desktop",
                        "type": "launch",
                        "app": "notepad.exe",
                        "command": "notepad.exe",
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
    if case.get("expected_ok") is True:
        return {
            "name": str(case["name"]),
            "ok": validation.ok,
            "validation_ok": validation.ok,
            "matched": validation.ok,
            "expected_message": "",
            "errors": errors,
        }
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
    observe_path = package_dir / "output" / "desktop-state" / "observe.json"
    observe_screenshot_path = package_dir / "output" / "desktop-state" / "observe.png"
    windows = _read_json(windows_path) if windows_path.exists() else {}
    snapshot = _read_json(snapshot_path) if snapshot_path.exists() else {}
    observation = _read_json(observe_path) if observe_path.exists() else {}
    return [
        _expect("windows_artifact_fresh", _file_nonempty_after(windows_path, started_at)),
        _expect("windows_payload_shape", isinstance(windows.get("windows"), list)),
        _expect("screenshot_artifact_fresh", _file_nonempty_after(screenshot_path, started_at)),
        _expect("snapshot_artifact_fresh", _file_nonempty_after(snapshot_path, started_at)),
        _expect("snapshot_payload_shape", isinstance(snapshot.get("snapshot"), dict)),
        _expect(
            "snapshot_capability_matrix_shape",
            isinstance(snapshot.get("capability_matrix"), dict)
            and snapshot["capability_matrix"].get("schema_version") == 1
            and isinstance(snapshot["capability_matrix"].get("capabilities"), dict)
            and isinstance(snapshot["capability_matrix"].get("capabilities", {}).get("coordinates"), dict),
        ),
        _expect("snapshot_coordinate_profile_shape", _coordinate_profile_ok(snapshot.get("coordinate_profile"))),
        _expect("observe_artifact_fresh", _file_nonempty_after(observe_path, started_at)),
        _expect("observe_screenshot_artifact_fresh", _file_nonempty_after(observe_screenshot_path, started_at)),
        _expect(
            "observe_payload_shape",
            observation.get("kind") == "desktop_observation"
            and observation.get("schema_version") == 1
            and observation.get("type") == "observe"
            and isinstance(observation.get("summary"), dict)
            and isinstance(observation.get("windows"), list)
            and isinstance(observation.get("capability_matrix"), dict)
            and isinstance(observation.get("screenshot"), dict)
            and _coordinate_profile_ok(observation.get("coordinate_profile"))
            and _coordinate_profile_ok(observation["screenshot"].get("coordinate_profile"), screen_clickable=True)
            and isinstance(observation.get("target_candidates"), dict)
            and observation["target_candidates"].get("kind") == "desktop_target_candidates"
            and int(observation["target_candidates"].get("candidate_count", 0) or 0) >= 1
            and observation["screenshot"].get("path") == str(observe_screenshot_path),
        ),
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
        diagnostics_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("diagnostics"), dict)
            and isinstance(payload["diagnostics"].get("window"), dict)
            and payload["diagnostics"]["window"].get("query", {}).get("title_contains")
            == "__ai_automate_contro_missing_window__"
            and isinstance(payload["diagnostics"].get("element"), dict)
            for payload in state_payloads
        )
        target_candidates_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("target_candidates"), dict)
            and payload["target_candidates"].get("kind") == "desktop_target_candidates"
            and int(payload["target_candidates"].get("candidate_count", 0) or 0) >= 1
            for payload in state_payloads
        )
        capability_matrix_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("capability_matrix"), dict)
            and payload["capability_matrix"].get("schema_version") == 1
            and isinstance(payload["capability_matrix"].get("capabilities", {}).get("coordinates"), dict)
            for payload in state_payloads
        )
        coordinate_profile_ok = any(
            isinstance(payload, dict)
            and _coordinate_profile_ok(payload.get("coordinate_profile"))
            and isinstance(payload.get("diagnostics"), dict)
            and _coordinate_profile_ok(payload["diagnostics"].get("coordinate_profile"))
            for payload in state_payloads
        )
        analysis = _analyze_failure_for_self_check(plan_path, package_dir / "output")
        analysis_diagnostics = analysis.get("desktop_diagnostics", [])
        analysis_ok = (
            bool(analysis.get("ok"))
            and isinstance(analysis_diagnostics, list)
            and any(
                isinstance(item, dict)
                and item.get("window", {}).get("query", {}).get("title_contains")
                == "__ai_automate_contro_missing_window__"
                and isinstance(item.get("target_candidates"), dict)
                and int(item["target_candidates"].get("candidate_count", 0) or 0) >= 1
                and _coordinate_profile_ok(item.get("coordinate_profile"))
                for item in analysis_diagnostics
            )
            and bool(analysis.get("desktop_repair_suggestions"))
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
                and diagnostics_ok
                and target_candidates_ok
                and capability_matrix_ok
                and coordinate_profile_ok
                and analysis_ok
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
            "diagnostics_ok": diagnostics_ok,
            "target_candidates_ok": target_candidates_ok,
            "capability_matrix_ok": capability_matrix_ok,
            "coordinate_profile_ok": coordinate_profile_ok,
            "analysis_ok": analysis_ok,
            "analysis_desktop_diagnostics_count": len(analysis_diagnostics) if isinstance(analysis_diagnostics, list) else 0,
            "analysis_desktop_repair_suggestions": analysis.get("desktop_repair_suggestions", []),
        }


def _run_element_failure_capture_case(project_root: Path) -> dict[str, Any]:
    if platform.system() not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_element_failure_capture",
            "ok": True,
            "skipped": True,
            "reason": f"desktop element failure capture only runs on Windows/macOS, current={platform.system()}",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-element-failure-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        plan_path = package_dir / "plan.json"
        missing_window = "__ai_automate_contro_missing_element_window__"
        missing_element = "__ai_automate_contro_missing_element__"
        plan = {
            "name": "desktop element failure capture",
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop"},
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "find",
                    "title_contains": missing_window,
                    "name_contains": missing_element,
                    "timeout_ms": 100,
                    "interval_ms": 20,
                },
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_element_failure_capture",
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
                run_name="desktop-components-element-failure",
                run_context_handler=_disable_run_log_echo,
            )
            failed_as_expected = False
        except Exception as error:
            failed_as_expected = True
            run_error = str(error)
        result_payload = _latest_result_payload(package_dir / "output")
        failure_states = [Path(path) for path in result_payload.get("failure_desktop_states", [])]
        state_payloads = [_read_json(path) for path in failure_states if path.exists()]
        target_ok = any(
            isinstance(payload, dict)
            and payload.get("action") == "desktop_element"
            and isinstance(payload.get("target"), dict)
            and payload["target"].get("title_contains") == missing_window
            and payload["target"].get("name_contains") == missing_element
            for payload in state_payloads
        )
        error_ok = any(
            isinstance(payload, dict)
            and payload.get("error_type") in {"DesktopBackendError", "TimeoutError"}
            and (
                "未找到匹配窗口" in str(payload.get("error", ""))
                or "等待桌面控件超时" in str(payload.get("error", ""))
            )
            for payload in state_payloads
        )
        diagnostics_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("diagnostics"), dict)
            and payload["diagnostics"].get("window", {}).get("query", {}).get("title_contains") == missing_window
            and payload["diagnostics"].get("element", {}).get("locator", {}).get("name_contains") == missing_element
            for payload in state_payloads
        )
        target_candidates_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("target_candidates"), dict)
            and payload["target_candidates"].get("kind") == "desktop_target_candidates"
            and int(payload["target_candidates"].get("candidate_count", 0) or 0) >= 1
            for payload in state_payloads
        )
        capability_matrix_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("capability_matrix"), dict)
            and payload["capability_matrix"].get("schema_version") == 1
            and isinstance(payload["capability_matrix"].get("capabilities", {}).get("coordinates"), dict)
            for payload in state_payloads
        )
        coordinate_profile_ok = any(
            isinstance(payload, dict)
            and _coordinate_profile_ok(payload.get("coordinate_profile"))
            and isinstance(payload.get("diagnostics"), dict)
            and _coordinate_profile_ok(payload["diagnostics"].get("coordinate_profile"))
            for payload in state_payloads
        )
        analysis = _analyze_failure_for_self_check(plan_path, package_dir / "output")
        analysis_diagnostics = analysis.get("desktop_diagnostics", [])
        analysis_ok = (
            bool(analysis.get("ok"))
            and isinstance(analysis_diagnostics, list)
            and any(
                isinstance(item, dict)
                and item.get("window", {}).get("query", {}).get("title_contains") == missing_window
                and item.get("element", {}).get("locator", {}).get("name_contains") == missing_element
                and isinstance(item.get("target_candidates"), dict)
                and int(item["target_candidates"].get("candidate_count", 0) or 0) >= 1
                and _coordinate_profile_ok(item.get("coordinate_profile"))
                for item in analysis_diagnostics
            )
            and bool(analysis.get("desktop_repair_suggestions"))
        )
        return {
            "name": "desktop_element_failure_capture",
            "ok": (
                failed_as_expected
                and result_payload.get("status") == "failed"
                and target_ok
                and error_ok
                and diagnostics_ok
                and target_candidates_ok
                and capability_matrix_ok
                and coordinate_profile_ok
                and analysis_ok
            ),
            "validation_ok": True,
            "failed_as_expected": failed_as_expected,
            "run_error": run_error,
            "result_status": result_payload.get("status"),
            "failure_desktop_state_count": len(failure_states),
            "target_ok": target_ok,
            "error_ok": error_ok,
            "diagnostics_ok": diagnostics_ok,
            "target_candidates_ok": target_candidates_ok,
            "capability_matrix_ok": capability_matrix_ok,
            "coordinate_profile_ok": coordinate_profile_ok,
            "analysis_ok": analysis_ok,
            "analysis_desktop_diagnostics_count": len(analysis_diagnostics) if isinstance(analysis_diagnostics, list) else 0,
            "analysis_desktop_repair_suggestions": analysis.get("desktop_repair_suggestions", []),
        }


def _run_launch_only_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_app_launch_runtime",
            "ok": True,
            "skipped": True,
            "reason": f"desktop_app launch runtime only runs on Windows/macOS, current={system}",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-launch-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        plan_path = package_dir / "plan.json"
        expected_stdout = "desktop_app_launch_ok"
        plan = {
            "name": "desktop app launch runtime",
            "automation_type": "desktop",
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
                {"action": "write", "type": "json", "path": "desktop-probe.json", "value": "{{desktop_probe}}"},
                {
                    "action": "desktop_app",
                    "desktop": "desktop",
                    "type": "launch",
                    "command": sys.executable,
                    "args": ["-c", f"print('{expected_stdout}')"],
                    "wait": True,
                    "timeout_ms": 10000,
                    "save_as": "launch_result",
                },
                {"action": "write", "type": "json", "path": "launch-result.json", "value": "{{launch_result}}"},
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_app_launch_runtime",
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
                run_name="desktop-components-launch",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        launch_result_path = package_dir / "output" / "json" / "launch-result.json"
        desktop_probe_path = package_dir / "output" / "json" / "desktop-probe.json"
        launch_result = _read_json(launch_result_path) if launch_result_path.exists() else {}
        desktop_probe = _read_json(desktop_probe_path) if desktop_probe_path.exists() else {}
        stdout = str(launch_result.get("stdout", "")) if isinstance(launch_result, dict) else ""
        capability_matrix = desktop_probe.get("capability_matrix") if isinstance(desktop_probe, dict) else {}
        capability_matrix_ok = (
            isinstance(capability_matrix, dict)
            and capability_matrix.get("schema_version") == 1
            and capability_matrix.get("platform") in {"windows", "macos"}
            and isinstance(capability_matrix.get("capabilities"), dict)
        )
        return {
            "name": "desktop_app_launch_runtime",
            "ok": (
                run_ok
                and isinstance(launch_result, dict)
                and launch_result.get("exit_code") == 0
                and expected_stdout in stdout
                and isinstance(launch_result.get("pid"), int)
                and capability_matrix_ok
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "launch_result_path": str(launch_result_path),
            "desktop_probe_path": str(desktop_probe_path),
            "capability_matrix_ok": capability_matrix_ok,
            "exit_code": launch_result.get("exit_code") if isinstance(launch_result, dict) else None,
            "stdout": stdout,
            "pid": launch_result.get("pid") if isinstance(launch_result, dict) else None,
        }


def _run_desktop_profile_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_app_profile_runtime",
            "ok": True,
            "skipped": True,
            "reason": f"desktop app profile runtime only runs on Windows/macOS, current={system}",
        }
    platform_name = "windows" if system == "Windows" else "macos"
    with tempfile.TemporaryDirectory(prefix="desktop-components-profile-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        plan_path = package_dir / "plan.json"
        profile_name = "python-echo"
        expected_stdout = "desktop_profile_launch_ok"
        config = {
            "desktop_profiles": {
                profile_name: {
                    "platforms": {
                        platform_name: {
                            "launch": {
                                "command": sys.executable,
                                "args": ["-c", f"print('{expected_stdout}')"],
                            },
                            "defaults": {
                                "wait": True,
                                "timeout_ms": 10000,
                            },
                        }
                    }
                }
            }
        }
        plan = {
            "name": "desktop app profile runtime",
            "automation_type": "desktop",
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto"},
                {
                    "action": "desktop_app",
                    "desktop": "desktop",
                    "type": "launch",
                    "profile": profile_name,
                    "save_as": "launch_result",
                },
                {"action": "write", "type": "json", "path": "profile-launch-result.json", "value": "{{launch_result}}"},
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (package_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_app_profile_runtime",
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
                run_name="desktop-components-profile",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        launch_result_path = package_dir / "output" / "json" / "profile-launch-result.json"
        launch_result = _read_json(launch_result_path) if launch_result_path.exists() else {}
        stdout = str(launch_result.get("stdout", "")) if isinstance(launch_result, dict) else ""
        profile = launch_result.get("profile") if isinstance(launch_result, dict) else {}
        profile_ok = (
            isinstance(profile, dict)
            and profile.get("id") == "python_echo"
            and profile.get("requested") == profile_name
            and profile.get("source") == "config"
            and profile.get("platform") == platform_name
        )
        return {
            "name": "desktop_app_profile_runtime",
            "ok": (
                run_ok
                and isinstance(launch_result, dict)
                and launch_result.get("exit_code") == 0
                and expected_stdout in stdout
                and launch_result.get("command") == sys.executable
                and launch_result.get("args") == ["-c", f"print('{expected_stdout}')"]
                and profile_ok
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "launch_result_path": str(launch_result_path),
            "exit_code": launch_result.get("exit_code") if isinstance(launch_result, dict) else None,
            "stdout": stdout,
            "profile": profile,
            "profile_ok": profile_ok,
        }


def _run_vision_locator_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": True,
            "skipped": True,
            "reason": f"desktop vision regression only runs on Windows/macOS, current={system}",
        }
    dependency_reason = _desktop_vision_dependency_skip_reason()
    if dependency_reason:
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": True,
            "skipped": True,
            "reason": dependency_reason,
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-vision-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        source_path = resources_dir / "vision-source.png"
        template_path = resources_dir / "vision-template.png"
        missing_template_path = resources_dir / "vision-missing-template.png"
        expected_bounds = _write_vision_fixture_images(source_path, template_path)
        _write_vision_missing_template(missing_template_path)
        region = {"x": 100, "y": 60, "width": 140, "height": 100}
        capture_region = {"x": 0, "y": 0, "width": 32, "height": 24}
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "desktop vision locate image regression",
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
                {
                    "action": "desktop_capture",
                    "desktop": "desktop",
                    "type": "screenshot",
                    "path": "region-screen.png",
                    "region": capture_region,
                    "save_as": "region_capture",
                },
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_image",
                    "template_path": "resources/vision-template.png",
                    "source_path": "resources/vision-source.png",
                    "threshold": 0.98,
                    "match_index": 0,
                    "max_matches": 3,
                    "path": "vision-match.json",
                    "save_as": "vision_match",
                },
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_image",
                    "template_path": "resources/vision-template.png",
                    "source_path": "resources/vision-source.png",
                    "region": region,
                    "threshold": 0.98,
                    "match_index": 0,
                    "max_matches": 3,
                    "path": "vision-region-match.json",
                    "save_as": "vision_region_match",
                },
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_vision_locate_image_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-vision",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        vision_path = package_dir / "output" / "desktop-vision" / "vision-match.json"
        region_vision_path = package_dir / "output" / "desktop-vision" / "vision-region-match.json"
        region_capture_path = package_dir / "output" / "desktop-screenshots" / "region-screen.png"
        source_artifact_path = package_dir / "output" / "desktop-vision" / "vision-match-source.png"
        crop_path = package_dir / "output" / "desktop-vision" / "vision-match-crop.png"
        annotation_path = package_dir / "output" / "desktop-vision" / "vision-match-annotated.png"
        payload = _read_json(vision_path) if vision_path.exists() else {}
        region_payload = _read_json(region_vision_path) if region_vision_path.exists() else {}
        match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
        bounds = match.get("bounds") if isinstance(match.get("bounds"), dict) else {}
        region_match = region_payload.get("match") if isinstance(region_payload.get("match"), dict) else {}
        region_bounds = region_match.get("bounds") if isinstance(region_match.get("bounds"), dict) else {}
        bounds_ok = all(int(bounds.get(key, -1)) == value for key, value in expected_bounds.items())
        region_bounds_ok = all(int(region_bounds.get(key, -1)) == value for key, value in expected_bounds.items())
        region_payload_ok = region_payload.get("region") == region
        target_candidates = payload.get("target_candidates") if isinstance(payload.get("target_candidates"), dict) else {}
        best_target = target_candidates.get("best_candidate") if isinstance(target_candidates.get("best_candidate"), dict) else {}
        coordinate_profile_ok = (
            _coordinate_profile_ok(payload.get("coordinate_profile"), screen_clickable=False)
            and _coordinate_profile_ok(region_payload.get("coordinate_profile"), screen_clickable=False)
            and target_candidates.get("kind") == "desktop_target_candidates"
            and best_target.get("screen_clickable") is False
            and not best_target.get("action_templates")
        )
        region_capture_size = _image_size(region_capture_path)
        region_capture_ok = (
            _file_nonempty_after(region_capture_path, started_at)
            and region_capture_size == {"width": capture_region["width"], "height": capture_region["height"]}
        )
        artifacts_ok = all(
            _file_nonempty_after(path, started_at)
            for path in (vision_path, source_artifact_path, crop_path, annotation_path)
        )
        score = float(match.get("score", 0.0) or 0.0) if isinstance(match, dict) else 0.0
        region_score = float(region_match.get("score", 0.0) or 0.0) if isinstance(region_match, dict) else 0.0
        miss_result = _run_vision_locator_miss_case(project_root, package_dir)
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": (
                run_ok
                and artifacts_ok
                and bool(payload.get("ok"))
                and bounds_ok
                and score >= 0.98
                and region_capture_ok
                and bool(region_payload.get("ok"))
                and region_bounds_ok
                and region_payload_ok
                and coordinate_profile_ok
                and region_score >= 0.98
                and bool(miss_result.get("ok"))
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "vision_path": str(vision_path),
            "region_vision_path": str(region_vision_path),
            "region_capture_path": str(region_capture_path),
            "source_artifact_path": str(source_artifact_path),
            "crop_path": str(crop_path),
            "annotation_path": str(annotation_path),
            "artifacts_ok": artifacts_ok,
            "region_capture_ok": region_capture_ok,
            "region_capture_size": region_capture_size,
            "bounds_ok": bounds_ok,
            "region_bounds_ok": region_bounds_ok,
            "region_payload_ok": region_payload_ok,
            "coordinate_profile_ok": coordinate_profile_ok,
            "expected_bounds": expected_bounds,
            "actual_bounds": bounds,
            "actual_region_bounds": region_bounds,
            "score": score,
            "region_score": region_score,
            "miss_case": miss_result,
        }


def _run_vision_locator_miss_case(project_root: Path, package_dir: Path) -> dict[str, Any]:
    plan_path = package_dir / "plan.json"
    plan = {
        "name": "desktop vision locate image miss regression",
        "automation_type": "desktop",
        "variables": {},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "desktop_vision",
                "desktop": "desktop",
                "type": "locate_image",
                "template_path": "resources/vision-missing-template.png",
                "source_path": "resources/vision-source.png",
                "threshold": 0.99,
                "match_index": 0,
                "max_matches": 5,
                "path": "vision-miss.json",
                "save_as": "vision_miss",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        return {
            "name": "desktop_vision_locate_image_miss_regression",
            "ok": False,
            "validation_ok": False,
            "errors": [error.format() for error in validation.errors],
        }
    started_at = time.time()
    run_error = ""
    try:
        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name="desktop-components-vision-miss",
            run_context_handler=_disable_run_log_echo,
        )
        failed_as_expected = result.status == "failed"
        output_dir = result.output_dir
    except Exception as error:
        failed_as_expected = True
        output_dir = ""
        run_error = str(error)
    miss_path = package_dir / "output" / "desktop-vision" / "vision-miss.json"
    payload = _read_json(miss_path) if miss_path.exists() else {}
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    source_artifact = payload.get("artifacts", {}).get("source_path") if isinstance(payload.get("artifacts"), dict) else ""
    diagnostics_ok = (
        payload.get("ok") is False
        and isinstance(diagnostics.get("max_score"), (int, float))
        and isinstance(diagnostics.get("candidate_count"), int)
        and isinstance(diagnostics.get("source_size"), dict)
        and isinstance(diagnostics.get("template_size"), dict)
    )
    return {
        "name": "desktop_vision_locate_image_miss_regression",
        "ok": failed_as_expected and _file_nonempty_after(miss_path, started_at) and diagnostics_ok,
        "validation_ok": True,
        "failed_as_expected": failed_as_expected,
        "output_dir": output_dir,
        "run_error": run_error,
        "miss_path": str(miss_path),
        "source_artifact": str(source_artifact),
        "diagnostics_ok": diagnostics_ok,
        "diagnostics": diagnostics,
    }


def _run_ocr_locator_case(project_root: Path) -> dict[str, Any]:
    return _run_ocr_locator_language_case(
        project_root,
        case_name="desktop_vision_locate_text_regression",
        temp_prefix="desktop-components-ocr-",
        plan_name="desktop vision locate text regression",
        run_name="desktop-components-ocr",
        source_filename="ocr-source.png",
        output_filename="ocr-match.json",
        fixture_text="AI DESKTOP OCR READY",
        fixture_language="latin",
        text_query={"text_contains": "OCR READY"},
        language="eng",
        min_confidence=0.30,
        raw_text_checks=("OCR", "READY"),
    )


def _run_ocr_zh_locator_case(project_root: Path) -> dict[str, Any]:
    return _run_ocr_locator_language_case(
        project_root,
        case_name="desktop_vision_locate_text_zh_regression",
        temp_prefix="desktop-components-ocr-zh-",
        plan_name="desktop vision locate Chinese text regression",
        run_name="desktop-components-ocr-zh",
        source_filename="ocr-zh-source.png",
        output_filename="ocr-zh-match.json",
        fixture_text="中文 OCR 测试",
        fixture_language="zh",
        text_query={"text_contains": "测试"},
        language="chi_sim",
        min_confidence=0.10,
        raw_text_checks=("测试", "OCR"),
    )


def _run_ocr_config_path_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_vision_locate_text_config_path_regression",
            "ok": True,
            "skipped": True,
            "reason": f"desktop OCR config path regression only runs on Windows/macOS, current={system}",
        }
    dependency_reason = _desktop_ocr_dependency_skip_reason("eng", project_root)
    if dependency_reason:
        return {
            "name": "desktop_vision_locate_text_config_path_regression",
            "ok": True,
            "skipped": True,
            "reason": dependency_reason,
        }
    tesseract = tesseract_binary_details(_desktop_ocr_config(project_root))
    tesseract_path = str(tesseract.get("path") or "")
    if not tesseract_path:
        return {
            "name": "desktop_vision_locate_text_config_path_regression",
            "ok": True,
            "skipped": True,
            "reason": "tesseract path could not be resolved for config-path regression.",
        }
    tessdata_dir = Path(tesseract_path).resolve().parent / "tessdata"
    ocr_config: dict[str, Any] = {"tesseract_path": tesseract_path}
    if tessdata_dir.exists():
        ocr_config["tessdata_dir"] = str(tessdata_dir)
    return _run_ocr_locator_language_case(
        project_root,
        case_name="desktop_vision_locate_text_config_path_regression",
        temp_prefix="desktop-components-ocr-config-",
        plan_name="desktop vision locate text config path regression",
        run_name="desktop-components-ocr-config",
        source_filename="ocr-config-source.png",
        output_filename="ocr-config-match.json",
        fixture_text="AI DESKTOP OCR READY",
        fixture_language="latin",
        text_query={"text_contains": "OCR READY"},
        language="eng",
        min_confidence=0.30,
        raw_text_checks=("OCR", "READY"),
        local_config={"desktop": {"ocr": ocr_config}},
        expected_tesseract_source="config.desktop.ocr.tesseract_path",
        expected_tesseract_path=tesseract_path,
        expected_tessdata_dir=str(tessdata_dir) if tessdata_dir.exists() else "",
    )


def _run_ocr_bad_config_path_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_vision_locate_text_bad_config_path_regression",
            "ok": True,
            "skipped": True,
            "reason": f"desktop OCR bad config path regression only runs on Windows/macOS, current={system}",
        }
    if not _module_available("PIL"):
        return {
            "name": "desktop_vision_locate_text_bad_config_path_regression",
            "ok": True,
            "skipped": True,
            "reason": "Pillow is not installed; desktop_vision locate_text fixture images cannot be generated.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-ocr-bad-config-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        source_filename = "ocr-bad-config-source.png"
        output_filename = "ocr-bad-config-match.json"
        source_path = resources_dir / source_filename
        _write_ocr_fixture_image(source_path, text="AI DESKTOP OCR READY", language="latin")
        missing_binary = resources_dir / "missing-tesseract" / ("tesseract.exe" if system == "Windows" else "tesseract")
        missing_tessdata = resources_dir / "missing-tessdata"
        local_config = {
            "desktop": {
                "ocr": {
                    "tesseract_path": str(missing_binary),
                    "tessdata_dir": str(missing_tessdata),
                }
            }
        }
        (package_dir / "config.json").write_text(
            json.dumps(local_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "desktop vision locate text bad config path regression",
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_text",
                    "source_path": f"resources/{source_filename}",
                    "text_contains": "OCR READY",
                    "language": "eng",
                    "provider": "tesseract",
                    "min_confidence": 0.30,
                    "match_index": 0,
                    "max_matches": 5,
                    "path": output_filename,
                    "save_as": "ocr_match",
                },
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_vision_locate_text_bad_config_path_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        output_dir = ""
        run_error = ""
        failed_as_expected = False
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-ocr-bad-config",
                run_context_handler=_disable_run_log_echo,
            )
            output_dir = result.output_dir
            run_error = str(result.error or "")
            failed_as_expected = result.status == "failed"
        except Exception as error:
            run_error = str(error)
            failed_as_expected = True
        message_ok = "desktop.ocr.tesseract_path" in run_error and str(missing_binary) in run_error
        return {
            "name": "desktop_vision_locate_text_bad_config_path_regression",
            "ok": failed_as_expected and message_ok,
            "validation_ok": True,
            "failed_as_expected": failed_as_expected,
            "message_ok": message_ok,
            "run_error": run_error,
            "output_dir": output_dir,
            "configured_tesseract_path": str(missing_binary),
        }


def _run_ocr_locator_language_case(
    project_root: Path,
    *,
    case_name: str,
    temp_prefix: str,
    plan_name: str,
    run_name: str,
    source_filename: str,
    output_filename: str,
    fixture_text: str,
    fixture_language: str,
    text_query: dict[str, str],
    language: str,
    min_confidence: float,
    raw_text_checks: tuple[str, ...],
    local_config: dict[str, Any] | None = None,
    expected_tesseract_source: str = "",
    expected_tesseract_path: str = "",
    expected_tessdata_dir: str = "",
) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": case_name,
            "ok": True,
            "skipped": True,
            "reason": f"desktop OCR regression only runs on Windows/macOS, current={system}",
        }
    dependency_reason = _desktop_ocr_dependency_skip_reason(language, project_root)
    if dependency_reason:
        return {
            "name": case_name,
            "ok": True,
            "skipped": True,
            "reason": dependency_reason,
        }
    with tempfile.TemporaryDirectory(prefix=temp_prefix) as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        source_path = resources_dir / source_filename
        _write_ocr_fixture_image(source_path, text=fixture_text, language=fixture_language)
        if local_config is not None:
            (package_dir / "config.json").write_text(
                json.dumps(local_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        plan_path = package_dir / "plan.json"
        plan = {
            "name": plan_name,
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_text",
                    "source_path": f"resources/{source_filename}",
                    **text_query,
                    "language": language,
                    "provider": "tesseract",
                    "min_confidence": min_confidence,
                    "match_index": 0,
                    "max_matches": 5,
                    "path": output_filename,
                    "save_as": "ocr_match",
                },
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": case_name,
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name=run_name,
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        ocr_path = package_dir / "output" / "desktop-vision" / output_filename
        stem = Path(output_filename).stem
        source_artifact_path = package_dir / "output" / "desktop-vision" / f"{stem}-source.png"
        crop_path = package_dir / "output" / "desktop-vision" / f"{stem}-crop.png"
        annotation_path = package_dir / "output" / "desktop-vision" / f"{stem}-annotated.png"
        payload = _read_json(ocr_path) if ocr_path.exists() else {}
        match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
        bounds = match.get("bounds") if isinstance(match.get("bounds"), dict) else {}
        local_bounds = match.get("local_bounds") if isinstance(match.get("local_bounds"), dict) else {}
        source_bounds = payload.get("source_bounds") if isinstance(payload.get("source_bounds"), dict) else {}
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
        coordinate_diagnostics = (
            payload.get("coordinate_diagnostics") if isinstance(payload.get("coordinate_diagnostics"), dict) else {}
        )
        coordinate_profile_ok = _coordinate_profile_ok(payload.get("coordinate_profile"), screen_clickable=False)
        raw_text = str(payload.get("raw_text", ""))
        normalized_raw_text = re.sub(r"\s+", "", raw_text)
        artifacts_ok = all(
            _file_nonempty_after(path, started_at)
            for path in (ocr_path, source_artifact_path, crop_path, annotation_path)
        )
        coordinate_ok = (
            isinstance(bounds, dict)
            and isinstance(local_bounds, dict)
            and int(bounds.get("x", -1)) == int(local_bounds.get("x", -2)) + int(source_bounds.get("x", 0) or 0)
            and int(bounds.get("y", -1)) == int(local_bounds.get("y", -2)) + int(source_bounds.get("y", 0) or 0)
            and isinstance(coordinate_diagnostics.get("local_to_global_offset"), dict)
        )
        raw_text_ok = all(_ocr_raw_text_contains(normalized_raw_text, item) for item in raw_text_checks)
        tesseract_source_ok = (
            not expected_tesseract_source
            or str(diagnostics.get("tesseract_source") or "") == expected_tesseract_source
        )
        tesseract_path_ok = (
            not expected_tesseract_path
            or _same_path(str(diagnostics.get("tesseract_path") or ""), expected_tesseract_path)
        )
        tessdata_dir_ok = (
            not expected_tessdata_dir
            or _same_path(str(diagnostics.get("tessdata_dir") or ""), expected_tessdata_dir)
        )
        return {
            "name": case_name,
            "ok": (
                run_ok
                and artifacts_ok
                and bool(payload.get("ok"))
                and raw_text_ok
                and bool(match.get("text"))
                and float(match.get("confidence", 0.0) or 0.0) >= min_confidence
                and isinstance(payload.get("ocr_blocks"), list)
                and bool(payload.get("ocr_blocks"))
                and coordinate_ok
                and coordinate_profile_ok
                and diagnostics.get("provider") == "tesseract"
                and tesseract_source_ok
                and tesseract_path_ok
                and tessdata_dir_ok
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "ocr_path": str(ocr_path),
            "source_artifact_path": str(source_artifact_path),
            "crop_path": str(crop_path),
            "annotation_path": str(annotation_path),
            "artifacts_ok": artifacts_ok,
            "coordinate_ok": coordinate_ok,
            "coordinate_profile_ok": coordinate_profile_ok,
            "raw_text_ok": raw_text_ok,
            "tesseract_source_ok": tesseract_source_ok,
            "tesseract_path_ok": tesseract_path_ok,
            "tessdata_dir_ok": tessdata_dir_ok,
            "raw_text": raw_text,
            "match": match,
            "diagnostics": diagnostics,
        }


def _run_real_app_matrix_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    cases = [_run_real_app_case(project_root)]
    if system == "Windows":
        cases.append(_run_windows_explorer_real_app_case(project_root))
        cases.append(_run_windows_terminal_real_app_case(project_root))
        cases.append(_run_windows_file_dialog_real_app_case(project_root))
    return {
        "name": "desktop_real_app_matrix",
        "ok": all(bool(case.get("ok")) for case in cases),
        "platform": system,
        "checks": cases,
    }


def _run_real_app_case(project_root: Path) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    last_result: dict[str, Any] = {}
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        result = _run_real_app_case_once(project_root)
        result["attempt"] = attempt
        attempts.append(
            {
                "attempt": attempt,
                "ok": bool(result.get("ok")),
                "skipped": bool(result.get("skipped")),
                "validation_ok": result.get("validation_ok"),
                "run_ok": result.get("run_ok"),
                "run_error": result.get("run_error", ""),
                "expected_text_found": result.get("expected_text_found"),
                "output_dir": result.get("output_dir", ""),
            }
        )
        last_result = result
        if result.get("ok") or result.get("skipped") or result.get("validation_ok") is False:
            break
        if attempt < max_attempts:
            time.sleep(0.75)
    last_result["attempt_count"] = len(attempts)
    last_result["attempts"] = attempts
    return last_result


def _run_real_app_case_once(project_root: Path) -> dict[str, Any]:
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
            plan, assertion_relative_file, cleanup_hint = _windows_controlled_editor_plan(package_dir)
        else:
            plan, assertion_relative_file, cleanup_hint = _macos_textedit_plan(package_dir)
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
        started_at = time.time()
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
        expected_window_title = str(plan.get("variables", {}).get("window_title") or assertion_file.name)
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "real-app-screen.png"
        elements_path = package_dir / "output" / "desktop-elements" / "real-app-elements.json"
        active_window_path = package_dir / "output" / "desktop-windows" / "real-app-active-window.json"
        window_find_path = package_dir / "output" / "desktop-windows" / "real-app-window-find.json"
        restored_active_window_path = package_dir / "output" / "desktop-windows" / "real-app-restored-active-window.json"
        maximized_screenshot_path = package_dir / "output" / "desktop-screenshots" / "real-app-maximized-window.png"
        elements_payload = _read_json(elements_path) if elements_path.exists() else {}
        active_window_payload = _read_json(active_window_path) if active_window_path.exists() else {}
        window_find_payload = _read_json(window_find_path) if window_find_path.exists() else {}
        restored_active_window_payload = (
            _read_json(restored_active_window_path) if restored_active_window_path.exists() else {}
        )
        element_output_ok = (
            _file_nonempty_after(elements_path, started_at)
            and isinstance(elements_payload, dict)
            and isinstance(elements_payload.get("elements"), list)
            and int(elements_payload.get("count", 0) or 0) > 0
        )
        active_window_ok = (
            _file_nonempty_after(active_window_path, started_at)
            and isinstance(active_window_payload.get("window"), dict)
            and expected_window_title in str(active_window_payload.get("window", {}).get("title", ""))
        )
        window_find_ok = (
            _file_nonempty_after(window_find_path, started_at)
            and int(window_find_payload.get("match_count", 0) or 0) > 0
            and isinstance(window_find_payload.get("selected_window"), dict)
            and expected_window_title in str(window_find_payload.get("selected_window", {}).get("title", ""))
        )
        window_lifecycle_ok = (
            _file_nonempty_after(maximized_screenshot_path, started_at)
            and _file_nonempty_after(restored_active_window_path, started_at)
            and isinstance(restored_active_window_payload.get("window"), dict)
            and expected_window_title in str(restored_active_window_payload.get("window", {}).get("title", ""))
        )
        return {
            "name": "desktop_real_app_regression",
            "ok": run_ok
            and expected_text in content
            and _file_nonempty_after(screenshot_path, started_at)
            and element_output_ok
            and active_window_ok
            and window_find_ok
            and window_lifecycle_ok,
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "assertion_file": str(assertion_file),
            "expected_text_found": expected_text in content,
            "content_preview": content[:500],
            "screenshot_ok": _file_nonempty_after(screenshot_path, 0),
            "element_output_ok": element_output_ok,
            "elements_path": str(elements_path),
            "active_window_ok": active_window_ok,
            "active_window_path": str(active_window_path),
            "window_find_ok": window_find_ok,
            "window_find_path": str(window_find_path),
            "window_lifecycle_ok": window_lifecycle_ok,
            "maximized_screenshot_path": str(maximized_screenshot_path),
            "restored_active_window_path": str(restored_active_window_path),
            "cleanup": cleanup_hint,
        }


def _run_windows_explorer_real_app_case(project_root: Path) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "name": "desktop_windows_explorer_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": "Windows Explorer regression only runs on Windows.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-explorer-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        folder_name = f"desktop-explorer-{package_dir.name.rsplit('-', 1)[-1]}"
        target_dir = resources_dir / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "sample.txt").write_text("desktop explorer regression\n", encoding="utf-8")
        plan_path = package_dir / "plan.json"
        plan = _windows_explorer_plan(target_dir, folder_name)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_windows_explorer_real_app_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-explorer",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        windows_path = package_dir / "output" / "desktop-windows" / "explorer-windows.json"
        window_find_path = package_dir / "output" / "desktop-windows" / "explorer-window-find.json"
        elements_path = package_dir / "output" / "desktop-elements" / "explorer-elements.json"
        sample_file_path = package_dir / "output" / "desktop-elements" / "explorer-sample-file.json"
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "explorer-screen.png"
        windows_payload = _read_json(windows_path) if windows_path.exists() else {}
        window_find_payload = _read_json(window_find_path) if window_find_path.exists() else {}
        elements_payload = _read_json(elements_path) if elements_path.exists() else {}
        sample_file_payload = _read_json(sample_file_path) if sample_file_path.exists() else {}
        window_found = any(
            folder_name in str(window.get("title", ""))
            for window in windows_payload.get("windows", [])
            if isinstance(window, dict)
        )
        window_find_ok = (
            _file_nonempty_after(window_find_path, started_at)
            and int(window_find_payload.get("match_count", 0) or 0) > 0
        )
        explorer_profile = window_find_payload.get("profile") if isinstance(window_find_payload, dict) else {}
        profile_ok = (
            isinstance(explorer_profile, dict)
            and explorer_profile.get("id") == "explorer"
            and explorer_profile.get("source") == "builtin"
            and explorer_profile.get("platform") == "windows"
        )
        elements_ok = (
            _file_nonempty_after(elements_path, started_at)
            and isinstance(elements_payload, dict)
            and isinstance(elements_payload.get("elements"), list)
        )
        sample_file_ok = (
            _file_nonempty_after(sample_file_path, started_at)
            and isinstance(sample_file_payload.get("element"), dict)
            and "sample.txt" in str(sample_file_payload.get("element", {}).get("name", ""))
        )
        return {
            "name": "desktop_windows_explorer_real_app_regression",
            "ok": run_ok
            and window_found
            and window_find_ok
            and profile_ok
            and elements_ok
            and sample_file_ok
            and _file_nonempty_after(windows_path, started_at)
            and _file_nonempty_after(screenshot_path, started_at),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "target_dir": str(target_dir),
            "window_title_contains": folder_name,
            "window_found": window_found,
            "windows_path": str(windows_path),
            "window_find_ok": window_find_ok,
            "window_find_path": str(window_find_path),
            "profile_ok": profile_ok,
            "profile": explorer_profile,
            "elements_path": str(elements_path),
            "elements_ok": elements_ok,
            "sample_file_ok": sample_file_ok,
            "sample_file_path": str(sample_file_path),
            "screenshot_path": str(screenshot_path),
            "cleanup": "Explorer window is closed by desktop_window.close; no explorer.exe process kill fallback is used.",
        }


def _run_windows_terminal_real_app_case(project_root: Path) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "name": "desktop_windows_terminal_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": "Windows terminal regression only runs on Windows.",
        }
    powershell = _windows_powershell_executable()
    if not powershell:
        return {
            "name": "desktop_windows_terminal_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": "PowerShell is unavailable; skipping Windows terminal regression.",
        }
    if not _module_available("pyautogui") or not _module_available("pyperclip"):
        return {
            "name": "desktop_windows_terminal_real_app_regression",
            "ok": True,
            "skipped": True,
            "reason": "pyautogui and pyperclip are required for stable terminal keyboard input.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-terminal-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        suffix = package_dir.name.rsplit("-", 1)[-1]
        title = f"AI Automate Terminal {suffix}"
        result_file = resources_dir / "desktop-terminal-result.txt"
        expected_text = "desktop terminal regression ok"
        plan_path = package_dir / "plan.json"
        plan = _windows_terminal_plan(
            powershell=powershell,
            package_dir=package_dir,
            title=title,
            result_file=result_file,
            expected_text=expected_text,
        )
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_windows_terminal_real_app_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-terminal",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        finally:
            _cleanup_windows_terminal_case(package_dir)
        content = result_file.read_text(encoding="utf-8", errors="replace") if result_file.exists() else ""
        windows_path = package_dir / "output" / "desktop-windows" / "terminal-window-find.json"
        active_path = package_dir / "output" / "desktop-windows" / "terminal-active-window.json"
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "terminal-window.png"
        windows_payload = _read_json(windows_path) if windows_path.exists() else {}
        active_payload = _read_json(active_path) if active_path.exists() else {}
        window_find_ok = (
            _file_nonempty_after(windows_path, started_at)
            and int(windows_payload.get("match_count", 0) or 0) > 0
            and title in str(windows_payload.get("selected_window", {}).get("title", ""))
        )
        active_ok = (
            _file_nonempty_after(active_path, started_at)
            and title in str(active_payload.get("window", {}).get("title", ""))
        )
        result_ok = expected_text in content
        return {
            "name": "desktop_windows_terminal_real_app_regression",
            "ok": run_ok
            and result_ok
            and window_find_ok
            and active_ok
            and _file_nonempty_after(screenshot_path, started_at),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "terminal_title": title,
            "result_file": str(result_file),
            "result_ok": result_ok,
            "content_preview": content[:500],
            "window_find_ok": window_find_ok,
            "window_find_path": str(windows_path),
            "active_ok": active_ok,
            "active_path": str(active_path),
            "screenshot_path": str(screenshot_path),
            "cleanup": "terminal exits after the typed command; fallback cleanup kills only its recorded PowerShell pid.",
        }


def _run_windows_file_dialog_real_app_case(project_root: Path) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "name": "desktop_windows_file_dialog_regression",
            "ok": True,
            "skipped": True,
            "reason": "Windows file dialog regression only runs on Windows.",
        }
    powershell = _windows_powershell_executable()
    if not powershell:
        return {
            "name": "desktop_windows_file_dialog_regression",
            "ok": True,
            "skipped": True,
            "reason": "PowerShell is unavailable; skipping Windows file dialog regression.",
        }
    if not _module_available("pyautogui") or not _module_available("pyperclip"):
        return {
            "name": "desktop_windows_file_dialog_regression",
            "ok": True,
            "skipped": True,
            "reason": "pyautogui and pyperclip are required for stable file dialog keyboard input.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-file-dialog-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        resources_dir = package_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        input_file = resources_dir / "desktop-file-dialog-input.txt"
        save_file = resources_dir / "desktop-file-dialog-save.txt"
        result_file = resources_dir / "desktop-file-dialog-result.txt"
        expected_open_text = "desktop file dialog open payload"
        expected_save_text = "desktop file dialog save payload"
        input_file.write_text(expected_open_text, encoding="utf-8")
        if save_file.exists():
            save_file.unlink()
        plan_path = package_dir / "plan.json"
        plan = _windows_file_dialog_plan(
            powershell=powershell,
            package_dir=package_dir,
            input_file=input_file,
            save_file=save_file,
            result_file=result_file,
            expected_open_text=expected_open_text,
            expected_save_text=expected_save_text,
        )
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_windows_file_dialog_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-file-dialog",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        finally:
            _cleanup_windows_file_dialog_case(package_dir)
        result_content = result_file.read_text(encoding="utf-8", errors="replace") if result_file.exists() else ""
        save_content = save_file.read_text(encoding="utf-8", errors="replace") if save_file.exists() else ""
        form_elements_path = package_dir / "output" / "desktop-elements" / "file-dialog-form-elements.json"
        open_dialog_elements_path = package_dir / "output" / "desktop-elements" / "open-dialog-elements.json"
        save_dialog_elements_path = package_dir / "output" / "desktop-elements" / "save-dialog-elements.json"
        open_dialog_screenshot_path = package_dir / "output" / "desktop-screenshots" / "open-dialog-screen.png"
        save_dialog_screenshot_path = package_dir / "output" / "desktop-screenshots" / "save-dialog-screen.png"
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "file-dialog-final-screen.png"
        open_dialog_elements_payload = _read_json(open_dialog_elements_path) if open_dialog_elements_path.exists() else {}
        save_dialog_elements_payload = _read_json(save_dialog_elements_path) if save_dialog_elements_path.exists() else {}
        form_elements_ok = _desktop_elements_file_ok(form_elements_path, started_at)
        open_dialog_screenshot_ok = _file_nonempty_after(open_dialog_screenshot_path, started_at)
        save_dialog_screenshot_ok = _file_nonempty_after(save_dialog_screenshot_path, started_at)
        open_profile = (
            open_dialog_elements_payload.get("profile")
            if isinstance(open_dialog_elements_payload, dict)
            else {}
        )
        save_profile = (
            save_dialog_elements_payload.get("profile")
            if isinstance(save_dialog_elements_payload, dict)
            else {}
        )
        profile_ok = (
            isinstance(open_profile, dict)
            and open_profile.get("id") == "file_dialog_open"
            and open_profile.get("source") == "builtin"
            and isinstance(save_profile, dict)
            and save_profile.get("id") == "file_dialog_save"
            and save_profile.get("source") == "builtin"
        )
        result_ok = (
            expected_open_text in result_content
            and expected_save_text in result_content
            and expected_save_text in save_content
            and str(input_file.resolve()) in result_content
            and str(save_file.resolve()) in result_content
        )
        return {
            "name": "desktop_windows_file_dialog_regression",
            "ok": (
                run_ok
                and result_ok
                and form_elements_ok
                and profile_ok
                and open_dialog_screenshot_ok
                and save_dialog_screenshot_ok
                and _file_nonempty_after(screenshot_path, started_at)
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "result_file": str(result_file),
            "result_ok": result_ok,
            "result_preview": result_content[:500],
            "save_file": str(save_file),
            "save_content_preview": save_content[:500],
            "form_elements_ok": form_elements_ok,
            "profile_ok": profile_ok,
            "open_profile": open_profile,
            "save_profile": save_profile,
            "open_dialog_elements_path": str(open_dialog_elements_path),
            "save_dialog_elements_path": str(save_dialog_elements_path),
            "open_dialog_screenshot_ok": open_dialog_screenshot_ok,
            "save_dialog_screenshot_ok": save_dialog_screenshot_ok,
            "open_dialog_screenshot_path": str(open_dialog_screenshot_path),
            "save_dialog_screenshot_path": str(save_dialog_screenshot_path),
            "screenshot_path": str(screenshot_path),
            "cleanup": "temporary WinForms file dialog harness is closed by desktop_window.close; fallback cleanup kills only its recorded PowerShell pid.",
        }


def _run_element_action_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_element_set_text_invoke_regression",
            "ok": True,
            "skipped": True,
            "reason": f"element action regression only runs on Windows/macOS, current={system}",
        }
    if system == "Windows" and not _windows_powershell_executable():
        return {
            "name": "desktop_element_set_text_invoke_regression",
            "ok": True,
            "skipped": True,
            "reason": "PowerShell is unavailable; skipping temporary WinForms regression.",
        }
    if system == "Darwin" and not _module_available("tkinter"):
        return {
            "name": "desktop_element_set_text_invoke_regression",
            "ok": True,
            "skipped": True,
            "reason": "tkinter is unavailable; skipping temporary macOS form regression.",
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-element-action-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan, assertion_relative_file, cleanup_hint = _temporary_form_plan(package_dir, system)
        assertion_file = package_dir / assertion_relative_file
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_element_set_text_invoke_regression",
                "ok": False,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-element-action",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        finally:
            _cleanup_temporary_form_case(package_dir, system)
        content = assertion_file.read_text(encoding="utf-8", errors="replace") if assertion_file.exists() else ""
        expected_text = str(plan["variables"]["expected_text"])
        form_title = "AI Automate Desktop Element Form"
        clipboard_restore_enabled = bool(plan["variables"].get("clipboard_restore_enabled"))
        clipboard_after_file = package_dir / "resources" / "desktop-clipboard-after.txt"
        clipboard_after_text = clipboard_after_file.read_text(encoding="utf-8", errors="replace") if clipboard_after_file.exists() else ""
        clipboard_restore_ok = (
            not clipboard_restore_enabled
            or (
                _file_nonempty_after(clipboard_after_file, started_at)
                and clipboard_after_text == str(plan["variables"].get("clipboard_sentinel", ""))
            )
        )
        elements_path = package_dir / "output" / "desktop-elements" / "form-elements.json"
        dump_path = package_dir / "output" / "desktop-elements" / "form-elements-dump.json"
        assert_path = package_dir / "output" / "desktop-elements" / "form-entry-assertion.json"
        clipboard_assert_path = package_dir / "output" / "desktop-elements" / "form-clipboard-assertion.json"
        status_assert_path = package_dir / "output" / "desktop-elements" / "form-status-assertion.json"
        table_path = package_dir / "output" / "desktop-elements" / "form-orders-table.json"
        cell_path = package_dir / "output" / "desktop-elements" / "form-orders-cell.json"
        tree_path = package_dir / "output" / "desktop-elements" / "form-nav-tree.json"
        tree_expand_path = package_dir / "output" / "desktop-elements" / "form-nav-tree-expand.json"
        tree_select_path = package_dir / "output" / "desktop-elements" / "form-nav-tree-select.json"
        tree_collapse_path = package_dir / "output" / "desktop-elements" / "form-nav-tree-collapse.json"
        menu_path = package_dir / "output" / "desktop-elements" / "form-menu-invoke.json"
        context_menu_path = package_dir / "output" / "desktop-elements" / "form-context-menu-invoke.json"
        scroll_path = package_dir / "output" / "desktop-elements" / "form-scroll-panel.json"
        scroll_target_path = package_dir / "output" / "desktop-elements" / "form-scroll-target-state.json"
        observe_path = package_dir / "output" / "desktop-state" / "form-observe.json"
        observe_screenshot_path = package_dir / "output" / "desktop-state" / "form-observe.png"
        window_capture_path = package_dir / "output" / "desktop-screenshots" / "form-window-screen.png"
        element_capture_path = package_dir / "output" / "desktop-screenshots" / "form-entry-element-screen.png"
        vision_capture_path = package_dir / "output" / "desktop-screenshots" / "form-vision-element-screen.png"
        window_capture_payload_path = package_dir / "output" / "json" / "form-window-capture.json"
        element_capture_payload_path = package_dir / "output" / "json" / "form-entry-capture.json"
        vision_capture_payload_path = package_dir / "output" / "json" / "form-vision-capture.json"
        latest_candidate_click_payload_path = package_dir / "output" / "json" / "form-entry-latest-candidate-click.json"
        candidate_click_payload_path = package_dir / "output" / "json" / "form-entry-candidate-click.json"
        bounds_center_click_payload_path = package_dir / "output" / "json" / "form-entry-bounds-center-click.json"
        window_vision_path = package_dir / "output" / "desktop-vision" / "form-vision-window-vision.json"
        element_vision_path = package_dir / "output" / "desktop-vision" / "form-vision-element-vision.json"
        run_output_dir = Path(output_dir) if output_dir else package_dir / "output"
        annotation_dir = run_output_dir / "desktop-annotations"
        set_text_payload = plan.get("variables", {}).get("expected_text", "")
        dump_payload = _read_json(dump_path) if dump_path.exists() else {}
        dump_ok = (
            bool(dump_payload.get("ok"))
            and isinstance(dump_payload.get("elements"), list)
            and isinstance(dump_payload.get("tree"), list)
            and isinstance(dump_payload.get("selector_hints"), list)
            and isinstance(dump_payload.get("diagnostics"), dict)
            and int(dump_payload.get("count", 0) or 0) > 0
            and int(dump_payload.get("match_count", 0) or 0) >= 1
        )
        element_payload = _read_json(elements_path) if elements_path.exists() else {}
        element_rows = element_payload.get("elements") if isinstance(element_payload.get("elements"), list) else []
        automation_ids = {
            str(element.get("automation_id", ""))
            for element in element_rows
            if isinstance(element, dict)
        }
        expected_automation_ids = (
            {
                "DesktopElementTextBox",
                "DesktopElementSaveButton",
                "DesktopElementAgreeCheckBox",
                "DesktopElementModeCombo",
                "DesktopElementOptionsList",
                "DesktopElementMousePanel",
                "DesktopElementContextPanel",
                "DesktopElementOrdersGrid",
                "DesktopElementNavTree",
                "DesktopElementScrollPanel",
            }
            if system == "Windows"
            else set()
        )
        expected_controls_found = not expected_automation_ids or expected_automation_ids.issubset(automation_ids)
        observe_payload = _read_json(observe_path) if observe_path.exists() else {}
        observe_elements = observe_payload.get("elements") if isinstance(observe_payload.get("elements"), dict) else {}
        observe_matches = observe_elements.get("matches") if isinstance(observe_elements.get("matches"), list) else []
        observe_targeting = (
            observe_payload.get("target_candidates")
            if isinstance(observe_payload.get("target_candidates"), dict)
            else {}
        )
        observe_best_target = (
            observe_targeting.get("best_candidate") if isinstance(observe_targeting.get("best_candidate"), dict) else {}
        )
        observe_best_candidate_id = str(observe_best_target.get("candidate_id") or observe_best_target.get("id") or "")
        observe_selected_window = (
            observe_payload.get("selected_window") if isinstance(observe_payload.get("selected_window"), dict) else {}
        )
        observe_elements_ok = (
            bool(observe_elements.get("ok"))
            and int(observe_elements.get("match_count", 0) or 0) >= 1
            and any(
                isinstance(match, dict)
                and str(match.get("automation_id", "")) == "DesktopElementTextBox"
                for match in observe_matches
            )
        )
        observe_targeting_ok = (
            bool(observe_targeting)
            and observe_targeting.get("kind") == "desktop_target_candidates"
            and int(observe_targeting.get("candidate_count", 0) or 0) >= 1
            and (
                system != "Windows"
                or (
                    observe_best_target.get("strategy") == "semantic_locator"
                    and observe_best_candidate_id
                    and observe_best_target.get("confidence") in {"high", "medium"}
                    and observe_best_target.get("locator", {}).get("automation_id") == "DesktopElementTextBox"
                    and isinstance(observe_best_target.get("action_templates"), list)
                    and bool(observe_best_target.get("action_templates"))
                )
            )
        )
        observe_ok = (
            bool(observe_payload.get("ok"))
            and observe_payload.get("kind") == "desktop_observation"
            and observe_payload.get("type") == "observe"
            and isinstance(observe_payload.get("summary"), dict)
            and isinstance(observe_payload.get("capability_matrix"), dict)
            and str(observe_selected_window.get("title", "")).find(form_title) >= 0
            and (system != "Windows" or observe_elements_ok)
            and observe_targeting_ok
            and _file_nonempty_after(observe_path, started_at)
            and _file_nonempty_after(observe_screenshot_path, started_at)
        )
        table_payload = _read_json(table_path) if table_path.exists() else {}
        table_data = table_payload.get("table") if isinstance(table_payload.get("table"), dict) else {}
        table_columns = table_data.get("columns") if isinstance(table_data.get("columns"), list) else []
        table_cells = table_data.get("cells") if isinstance(table_data.get("cells"), list) else []
        table_cell_texts = {
            str(cell.get(field, ""))
            for cell in table_cells
            if isinstance(cell, dict)
            for field in ("text", "value", "name")
            if str(cell.get(field, ""))
        }
        table_ok = (
            system != "Windows"
            or (
                bool(table_payload.get("ok"))
                and isinstance(table_data, dict)
                and int(table_data.get("row_count", 0) or 0) >= 3
                and int(table_data.get("column_count", 0) or 0) >= 3
                and len(table_cells) >= 9
                and any("Status" in str(column) for column in table_columns)
                and "Beta" in table_cell_texts
                and "Review" in table_cell_texts
            )
        )
        cell_payload = _read_json(cell_path) if cell_path.exists() else {}
        selected_cell = cell_payload.get("selected_cell") if isinstance(cell_payload.get("selected_cell"), dict) else {}
        selected_cell_texts = {
            str(selected_cell.get(field, ""))
            for field in ("text", "value", "name")
            if str(selected_cell.get(field, ""))
        }
        selected_cell_ok = (
            system != "Windows"
            or (
                bool(cell_payload.get("ok"))
                and int(selected_cell.get("row", -1) or -1) == 1
                and int(selected_cell.get("column_index", -1) or -1) == 2
                and "Review" in selected_cell_texts
            )
        )
        tree_payload = _read_json(tree_path) if tree_path.exists() else {}
        tree_data = tree_payload.get("tree") if isinstance(tree_payload.get("tree"), dict) else {}
        tree_nodes = tree_data.get("nodes") if isinstance(tree_data.get("nodes"), list) else []
        tree_node_names = {str(node.get("name", "")) for node in tree_nodes if isinstance(node, dict)}
        tree_expand_payload = _read_json(tree_expand_path) if tree_expand_path.exists() else {}
        tree_select_payload = _read_json(tree_select_path) if tree_select_path.exists() else {}
        selected_tree_node = tree_select_payload.get("tree_node") if isinstance(tree_select_payload.get("tree_node"), dict) else {}
        tree_collapse_payload = _read_json(tree_collapse_path) if tree_collapse_path.exists() else {}
        selected_tree_path = selected_tree_node.get("path") if isinstance(selected_tree_node.get("path"), list) else []
        tree_ok = (
            system != "Windows"
            or (
                bool(tree_payload.get("ok"))
                and {"Settings", "Accounts", "Security", "Reports", "Monthly"}.issubset(tree_node_names)
                and bool(tree_expand_payload.get("ok"))
                and bool(tree_select_payload.get("ok"))
                and selected_tree_path == ["Settings", "Accounts"]
                and bool(tree_collapse_payload.get("ok"))
            )
        )
        menu_payload = _read_json(menu_path) if menu_path.exists() else {}
        menu_item = menu_payload.get("menu_item") if isinstance(menu_payload.get("menu_item"), dict) else {}
        menu_ok = (
            system != "Windows"
            or (
                bool(menu_payload.get("ok"))
                and menu_payload.get("menu_path") == ["File", "Mark Menu"]
                and str(menu_item.get("name", "")) == "Mark Menu"
            )
        )
        context_menu_payload = _read_json(context_menu_path) if context_menu_path.exists() else {}
        context_menu_item = (
            context_menu_payload.get("menu_item") if isinstance(context_menu_payload.get("menu_item"), dict) else {}
        )
        context_menu_expected = system == "Windows" and _module_available("pyautogui")
        context_menu_ok = (
            not context_menu_expected
            or (
                bool(context_menu_payload.get("ok"))
                and context_menu_payload.get("open_context_menu") is True
                and context_menu_payload.get("menu_path") == ["Mark Context"]
                and str(context_menu_item.get("name", "")) == "Mark Context"
                and isinstance(context_menu_payload.get("context_target"), dict)
            )
        )
        scroll_payload = _read_json(scroll_path) if scroll_path.exists() else {}
        scroll_target_payload = _read_json(scroll_target_path) if scroll_target_path.exists() else {}
        scroll_target_state = (
            scroll_target_payload.get("element_state") if isinstance(scroll_target_payload.get("element_state"), dict) else {}
        )
        scroll_ok = (
            system != "Windows"
            or (
                _module_available("pyautogui")
                and bool(scroll_payload.get("ok"))
                and bool(scroll_target_payload.get("ok"))
                and bool(scroll_target_state.get("visible", False))
            )
        )
        window_capture_payload = _read_json(window_capture_payload_path) if window_capture_payload_path.exists() else {}
        element_capture_payload = _read_json(element_capture_payload_path) if element_capture_payload_path.exists() else {}
        vision_capture_payload = _read_json(vision_capture_payload_path) if vision_capture_payload_path.exists() else {}
        window_capture_bounds = (
            window_capture_payload.get("source_bounds")
            if isinstance(window_capture_payload.get("source_bounds"), dict)
            else {}
        )
        element_capture_bounds = (
            element_capture_payload.get("source_bounds")
            if isinstance(element_capture_payload.get("source_bounds"), dict)
            else {}
        )
        vision_capture_bounds = (
            vision_capture_payload.get("source_bounds")
            if isinstance(vision_capture_payload.get("source_bounds"), dict)
            else {}
        )
        window_capture_size = _image_size(window_capture_path)
        element_capture_size = _image_size(element_capture_path)
        vision_capture_size = _image_size(vision_capture_path)
        window_capture_ok = (
            bool(window_capture_payload.get("ok"))
            and window_capture_payload.get("target") == "window"
            and isinstance(window_capture_payload.get("coordinate_space"), dict)
            and _coordinate_profile_ok(window_capture_payload.get("coordinate_profile"), screen_clickable=True)
            and _file_nonempty_after(window_capture_path, started_at)
            and _image_size_matches_bounds(window_capture_size, window_capture_bounds)
        )
        element_capture_ok = (
            bool(element_capture_payload.get("ok"))
            and element_capture_payload.get("target") == "element"
            and isinstance(element_capture_payload.get("coordinate_space"), dict)
            and _coordinate_profile_ok(element_capture_payload.get("coordinate_profile"), screen_clickable=True)
            and isinstance(element_capture_payload.get("element"), dict)
            and _file_nonempty_after(element_capture_path, started_at)
            and _image_size_matches_bounds(element_capture_size, element_capture_bounds)
        )
        vision_source_target_enabled = bool(plan["variables"].get("vision_source_target_enabled"))
        vision_capture_ok = (
            not vision_source_target_enabled
            or (
                bool(vision_capture_payload.get("ok"))
                and vision_capture_payload.get("target") == "element"
                and isinstance(vision_capture_payload.get("coordinate_space"), dict)
                and _coordinate_profile_ok(vision_capture_payload.get("coordinate_profile"), screen_clickable=True)
                and isinstance(vision_capture_payload.get("element"), dict)
                and _file_nonempty_after(vision_capture_path, started_at)
                and _image_size_matches_bounds(vision_capture_size, vision_capture_bounds)
            )
        )
        candidate_click_payload = _read_json(candidate_click_payload_path) if candidate_click_payload_path.exists() else {}
        latest_candidate_click_payload = (
            _read_json(latest_candidate_click_payload_path) if latest_candidate_click_payload_path.exists() else {}
        )
        bounds_center_click_payload = (
            _read_json(bounds_center_click_payload_path) if bounds_center_click_payload_path.exists() else {}
        )
        candidate_click_resolution = (
            candidate_click_payload.get("input_resolution")
            if isinstance(candidate_click_payload.get("input_resolution"), dict)
            else {}
        )
        latest_candidate_click_resolution = (
            latest_candidate_click_payload.get("input_resolution")
            if isinstance(latest_candidate_click_payload.get("input_resolution"), dict)
            else {}
        )
        candidate_click_safety = (
            candidate_click_payload.get("safety_check")
            if isinstance(candidate_click_payload.get("safety_check"), dict)
            else {}
        )
        latest_candidate_click_safety = (
            latest_candidate_click_payload.get("safety_check")
            if isinstance(latest_candidate_click_payload.get("safety_check"), dict)
            else {}
        )
        candidate_click_window_safety = (
            candidate_click_payload.get("window_safety_check")
            if isinstance(candidate_click_payload.get("window_safety_check"), dict)
            else {}
        )
        latest_candidate_click_window_safety = (
            latest_candidate_click_payload.get("window_safety_check")
            if isinstance(latest_candidate_click_payload.get("window_safety_check"), dict)
            else {}
        )
        candidate_click_candidate = (
            candidate_click_resolution.get("candidate")
            if isinstance(candidate_click_resolution.get("candidate"), dict)
            else {}
        )
        latest_candidate_click_candidate = (
            latest_candidate_click_resolution.get("candidate")
            if isinstance(latest_candidate_click_resolution.get("candidate"), dict)
            else {}
        )
        latest_candidate_click_ok = (
            system != "Windows"
            or (
                bool(latest_candidate_click_payload.get("ok"))
                and latest_candidate_click_payload.get("target") == "candidate"
                and latest_candidate_click_resolution.get("mode") == "candidate_semantic_locator"
                and latest_candidate_click_candidate.get("candidate_id") == observe_best_candidate_id
                and latest_candidate_click_safety.get("ok") is True
                and _window_safety_ok(latest_candidate_click_window_safety)
                and _file_nonempty_after(latest_candidate_click_payload_path, started_at)
            )
        )
        candidate_click_ok = (
            system != "Windows"
            or (
                bool(candidate_click_payload.get("ok"))
                and candidate_click_payload.get("target") == "candidate"
                and candidate_click_resolution.get("mode") == "candidate_semantic_locator"
                and candidate_click_candidate.get("candidate_id") == observe_best_candidate_id
                and candidate_click_safety.get("ok") is True
                and _window_safety_ok(candidate_click_window_safety)
                and _file_nonempty_after(candidate_click_payload_path, started_at)
            )
        )
        bounds_center_click_resolution = (
            bounds_center_click_payload.get("input_resolution")
            if isinstance(bounds_center_click_payload.get("input_resolution"), dict)
            else {}
        )
        bounds_center_click_safety = (
            bounds_center_click_payload.get("safety_check")
            if isinstance(bounds_center_click_payload.get("safety_check"), dict)
            else {}
        )
        bounds_center_click_window_safety = (
            bounds_center_click_payload.get("window_safety_check")
            if isinstance(bounds_center_click_payload.get("window_safety_check"), dict)
            else {}
        )
        bounds_center_click_ok = (
            system != "Windows"
            or (
                bool(bounds_center_click_payload.get("ok"))
                and bounds_center_click_payload.get("target") == "bounds_center"
                and bounds_center_click_resolution.get("mode") == "bounds_center"
                and bounds_center_click_safety.get("ok") is True
                and _window_safety_ok(bounds_center_click_window_safety)
                and _file_nonempty_after(bounds_center_click_payload_path, started_at)
            )
        )
        window_vision_payload = _read_json(window_vision_path) if window_vision_path.exists() else {}
        element_vision_payload = _read_json(element_vision_path) if element_vision_path.exists() else {}
        window_vision_match = (
            window_vision_payload.get("match") if isinstance(window_vision_payload.get("match"), dict) else {}
        )
        element_vision_match = (
            element_vision_payload.get("match") if isinstance(element_vision_payload.get("match"), dict) else {}
        )
        window_vision_targeting = (
            window_vision_payload.get("target_candidates")
            if isinstance(window_vision_payload.get("target_candidates"), dict)
            else {}
        )
        element_vision_targeting = (
            element_vision_payload.get("target_candidates")
            if isinstance(element_vision_payload.get("target_candidates"), dict)
            else {}
        )
        window_vision_best_target = (
            window_vision_targeting.get("best_candidate")
            if isinstance(window_vision_targeting.get("best_candidate"), dict)
            else {}
        )
        element_vision_best_target = (
            element_vision_targeting.get("best_candidate")
            if isinstance(element_vision_targeting.get("best_candidate"), dict)
            else {}
        )
        window_vision_target_query = (
            window_vision_payload.get("target_query")
            if isinstance(window_vision_payload.get("target_query"), dict)
            else {}
        )
        element_vision_target_query = (
            element_vision_payload.get("target_query")
            if isinstance(element_vision_payload.get("target_query"), dict)
            else {}
        )
        expected_window_local_bounds = _bounds_relative_to(vision_capture_bounds, window_capture_bounds)
        expected_element_local_bounds = {
            "x": 0,
            "y": 0,
            "width": int(vision_capture_bounds.get("width", 0) or 0),
            "height": int(vision_capture_bounds.get("height", 0) or 0),
        }
        expected_global_point = _point_center_from_bounds(vision_capture_bounds)
        expected_window_local_point = _point_center_from_bounds(expected_window_local_bounds)
        expected_element_local_point = _point_center_from_bounds(expected_element_local_bounds)
        window_vision_ok = (
            not vision_source_target_enabled
            or (
                bool(window_vision_payload.get("ok"))
                and window_vision_payload.get("source_target") == "window"
                and _file_nonempty_after(window_vision_path, started_at)
                and window_vision_target_query.get("match_index") == 0
                and _bounds_match(window_vision_payload.get("source_bounds"), window_capture_bounds)
                and _bounds_match(window_vision_match.get("bounds"), vision_capture_bounds)
                and _bounds_match(window_vision_match.get("local_bounds"), expected_window_local_bounds)
                and _point_match(window_vision_match.get("point"), expected_global_point)
                and _point_match(window_vision_match.get("local_point"), expected_window_local_point)
                and _coordinate_profile_ok(window_vision_payload.get("coordinate_profile"), screen_clickable=True)
                and window_vision_targeting.get("kind") == "desktop_target_candidates"
                and window_vision_best_target.get("strategy") == "visual_bounds"
                and window_vision_best_target.get("screen_clickable") is True
                and _bounds_match(window_vision_best_target.get("bounds"), vision_capture_bounds)
                and isinstance(window_vision_best_target.get("action_templates"), list)
                and bool(window_vision_best_target.get("action_templates"))
            )
        )
        element_vision_ok = (
            not vision_source_target_enabled
            or (
                bool(element_vision_payload.get("ok"))
                and element_vision_payload.get("source_target") == "element"
                and _file_nonempty_after(element_vision_path, started_at)
                and element_vision_target_query.get("match_index") == 0
                and _bounds_match(element_vision_payload.get("source_bounds"), vision_capture_bounds)
                and _bounds_match(element_vision_match.get("bounds"), vision_capture_bounds)
                and _bounds_match(element_vision_match.get("local_bounds"), expected_element_local_bounds)
                and _point_match(element_vision_match.get("point"), expected_global_point)
                and _point_match(element_vision_match.get("local_point"), expected_element_local_point)
                and _coordinate_profile_ok(element_vision_payload.get("coordinate_profile"), screen_clickable=True)
                and element_vision_targeting.get("kind") == "desktop_target_candidates"
                and element_vision_best_target.get("strategy") == "visual_bounds"
                and element_vision_best_target.get("screen_clickable") is True
                and _bounds_match(element_vision_best_target.get("bounds"), vision_capture_bounds)
                and isinstance(element_vision_best_target.get("action_templates"), list)
                and bool(element_vision_best_target.get("action_templates"))
            )
        )
        entry_assert_payload = _read_json(assert_path) if assert_path.exists() else {}
        status_assert_payload = _read_json(status_assert_path) if status_assert_path.exists() else {}
        entry_count_assertion = (
            entry_assert_payload.get("count_assertion")
            if isinstance(entry_assert_payload.get("count_assertion"), dict)
            else {}
        )
        entry_property_assertion = (
            entry_assert_payload.get("property_assertion")
            if isinstance(entry_assert_payload.get("property_assertion"), dict)
            else {}
        )
        status_count_assertion = (
            status_assert_payload.get("count_assertion")
            if isinstance(status_assert_payload.get("count_assertion"), dict)
            else {}
        )
        status_property_assertion = (
            status_assert_payload.get("property_assertion")
            if isinstance(status_assert_payload.get("property_assertion"), dict)
            else {}
        )
        entry_assertion_ok = (
            system != "Windows"
            or (
                bool(entry_assert_payload.get("ok"))
                and _file_nonempty_after(assert_path, started_at)
                and entry_count_assertion.get("ok") is True
                and int(entry_count_assertion.get("actual", 0) or 0) == 1
                and entry_count_assertion.get("expected_count") == 1
                and entry_property_assertion.get("ok") is True
                and entry_property_assertion.get("property") == "enabled"
                and entry_property_assertion.get("actual") is True
            )
        )
        status_assertion_ok = (
            system != "Windows"
            or (
                bool(status_assert_payload.get("ok"))
                and _file_nonempty_after(status_assert_path, started_at)
                and status_count_assertion.get("ok") is True
                and int(status_count_assertion.get("actual", 0) or 0) == 1
                and status_count_assertion.get("expected_count") == 1
                and status_property_assertion.get("ok") is True
                and status_property_assertion.get("property") == "visible"
                and status_property_assertion.get("actual") is True
            )
        )
        expected_agree = "agree=True" if _module_available("pyautogui") else "agree=False"
        expected_context = "context_marked=True" if context_menu_expected else "context_marked=False"
        mouse_steps_enabled = system == "Windows" and _module_available("pyautogui")
        mouse_double_click_ok = "mouse_double_click=True" in content if mouse_steps_enabled else system != "Windows"
        mouse_right_click_ok = "mouse_right_click=True" in content if mouse_steps_enabled else system != "Windows"
        mouse_scroll_ok = "mouse_scroll=True" in content if mouse_steps_enabled else system != "Windows"
        mouse_drag_ok = "mouse_drag=True" in content if mouse_steps_enabled else system != "Windows"
        input_coverage = {
            "mouse_steps_enabled": mouse_steps_enabled,
            "clipboard_restore_enabled": clipboard_restore_enabled,
            "latest_candidate_click_ok": latest_candidate_click_ok,
            "latest_candidate_click_window_safety_ok": system != "Windows"
            or _window_safety_ok(latest_candidate_click_window_safety),
            "candidate_click_ok": candidate_click_ok,
            "candidate_click_window_safety_ok": system != "Windows" or _window_safety_ok(candidate_click_window_safety),
            "bounds_center_click_ok": bounds_center_click_ok,
            "bounds_center_click_window_safety_ok": system != "Windows"
            or _window_safety_ok(bounds_center_click_window_safety),
            "point_ownership_ok": system != "Windows"
            or all(
                _window_safety_ownership_ok(value)
                for value in (
                    latest_candidate_click_window_safety,
                    candidate_click_window_safety,
                    bounds_center_click_window_safety,
                )
            ),
            "context_menu_ok": context_menu_ok,
            "scroll_ok": scroll_ok,
            "clipboard_restore_ok": clipboard_restore_ok,
            "mouse_double_click_ok": mouse_double_click_ok,
            "mouse_right_click_ok": mouse_right_click_ok,
            "mouse_scroll_ok": mouse_scroll_ok,
            "mouse_drag_ok": mouse_drag_ok,
        }
        metadata_found = (
            expected_agree in content
            and "mode=Audit" in content
            and "option=Green" in content
            and "menu_marked=True" in content
            and expected_context in content
            if system == "Windows"
            else True
        )
        annotation_pngs = sorted(annotation_dir.glob("*.png")) if annotation_dir.exists() else []
        annotation_jsons = sorted(annotation_dir.glob("*.json")) if annotation_dir.exists() else []
        annotation_payloads = [_read_json(path) for path in annotation_jsons]
        select_cell_annotation_ok = (
            system != "Windows"
            or any(
                isinstance(payload, dict)
                and str(payload.get("action", "")).endswith("desktop_element.select_cell")
                for payload in annotation_payloads
            )
        )
        complex_control_annotation_ok = (
            system != "Windows"
            or {
                "desktop_element.expand_tree",
                "desktop_element.select_tree",
                "desktop_element.collapse_tree",
                "desktop_element.invoke_menu",
                "desktop_element.scroll_element",
            }.issubset(
                {
                    str(payload.get("action", ""))
                    for payload in annotation_payloads
                    if isinstance(payload, dict)
                }
            )
        )
        candidate_click_annotation_ok = (
            system != "Windows"
            or any(
                isinstance(payload, dict)
                and str(payload.get("action", "")).endswith("desktop_input.click")
                and isinstance(payload.get("target"), dict)
                and isinstance(payload["target"].get("input_resolution"), dict)
                and isinstance(payload["target"]["input_resolution"].get("candidate"), dict)
                and payload["target"]["input_resolution"]["candidate"].get("candidate_id") == observe_best_candidate_id
                for payload in annotation_payloads
            )
        )
        annotation_ok = (
            annotation_dir.exists()
            and bool(annotation_pngs)
            and bool(annotation_jsons)
            and all(_file_nonempty_after(path, started_at) for path in annotation_pngs)
            and all(
                isinstance(payload, dict)
                and payload.get("schema_version") == 1
                and isinstance(payload.get("overlays"), list)
                and isinstance(payload.get("coordinate_space"), dict)
                and _coordinate_profile_ok(payload.get("coordinate_profile"), screen_clickable=True)
                for payload in annotation_payloads
            )
            and select_cell_annotation_ok
            and complex_control_annotation_ok
            and candidate_click_annotation_ok
        )
        return {
            "name": "desktop_element_set_text_invoke_regression",
            "ok": (
                run_ok
                and expected_text in content
                and metadata_found
                and _file_nonempty_after(elements_path, started_at)
                and _file_nonempty_after(dump_path, started_at)
                and dump_ok
                and expected_controls_found
                and _file_nonempty_after(table_path, started_at)
                and _file_nonempty_after(cell_path, started_at)
                and table_ok
                and selected_cell_ok
                and _file_nonempty_after(tree_path, started_at)
                and _file_nonempty_after(tree_expand_path, started_at)
                and _file_nonempty_after(tree_select_path, started_at)
                and _file_nonempty_after(tree_collapse_path, started_at)
                and _file_nonempty_after(menu_path, started_at)
                and (not context_menu_expected or _file_nonempty_after(context_menu_path, started_at))
                and _file_nonempty_after(scroll_path, started_at)
                and _file_nonempty_after(scroll_target_path, started_at)
                and observe_ok
                and _file_nonempty_after(window_capture_payload_path, started_at)
                and _file_nonempty_after(element_capture_payload_path, started_at)
                and window_capture_ok
                and element_capture_ok
                and vision_capture_ok
                and latest_candidate_click_ok
                and candidate_click_ok
                and bounds_center_click_ok
                and window_vision_ok
                and element_vision_ok
                and tree_ok
                and menu_ok
                and context_menu_ok
                and scroll_ok
                and entry_assertion_ok
                and (not clipboard_restore_enabled or _file_nonempty_after(clipboard_assert_path, started_at))
                and clipboard_restore_ok
                and status_assertion_ok
                and annotation_ok
            ),
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "assertion_file": str(assertion_file),
            "expected_text_found": expected_text in content,
            "clipboard_restore_enabled": clipboard_restore_enabled,
            "clipboard_restore_ok": clipboard_restore_ok,
            "clipboard_after_file": str(clipboard_after_file),
            "clipboard_after_text": clipboard_after_text,
            "metadata_found": metadata_found,
            "content_preview": content[:500],
            "expected_controls_found": expected_controls_found,
            "observe_path": str(observe_path),
            "observe_screenshot_path": str(observe_screenshot_path),
            "observe_ok": observe_ok,
            "observe_elements_ok": observe_elements_ok,
            "observe_targeting_ok": observe_targeting_ok,
            "observe_best_target": observe_best_target,
            "observe_selected_window": observe_selected_window,
            "observe_match_count": observe_elements.get("match_count", 0) if isinstance(observe_elements, dict) else 0,
            "status_assertion_ok": status_assertion_ok,
            "automation_ids": sorted(value for value in automation_ids if value),
            "elements_path": str(elements_path),
            "dump_path": str(dump_path),
            "dump_ok": dump_ok,
            "table_path": str(table_path),
            "table_ok": table_ok,
            "selected_cell_path": str(cell_path),
            "selected_cell_ok": selected_cell_ok,
            "table_columns": [str(column) for column in table_columns],
            "selected_cell": selected_cell,
            "tree_path": str(tree_path),
            "tree_ok": tree_ok,
            "tree_node_names": sorted(tree_node_names),
            "selected_tree_path": selected_tree_path,
            "menu_path": str(menu_path),
            "menu_ok": menu_ok,
            "menu_item": menu_item,
            "context_menu_path": str(context_menu_path),
            "context_menu_expected": context_menu_expected,
            "context_menu_ok": context_menu_ok,
            "context_menu_item": context_menu_item,
            "scroll_path": str(scroll_path),
            "scroll_ok": scroll_ok,
            "scroll_target_path": str(scroll_target_path),
            "scroll_target_state": scroll_target_state,
            "window_capture_path": str(window_capture_path),
            "window_capture_ok": window_capture_ok,
            "window_capture_size": window_capture_size,
            "window_capture_bounds": window_capture_bounds,
            "window_capture_payload_path": str(window_capture_payload_path),
            "element_capture_path": str(element_capture_path),
            "element_capture_ok": element_capture_ok,
            "element_capture_size": element_capture_size,
            "element_capture_bounds": element_capture_bounds,
            "element_capture_payload_path": str(element_capture_payload_path),
            "vision_capture_path": str(vision_capture_path),
            "vision_capture_ok": vision_capture_ok,
            "vision_capture_size": vision_capture_size,
            "vision_capture_bounds": vision_capture_bounds,
            "vision_capture_payload_path": str(vision_capture_payload_path),
            "latest_candidate_click_payload_path": str(latest_candidate_click_payload_path),
            "latest_candidate_click_ok": latest_candidate_click_ok,
            "latest_candidate_click_payload": latest_candidate_click_payload,
            "candidate_click_payload_path": str(candidate_click_payload_path),
            "candidate_click_ok": candidate_click_ok,
            "candidate_click_payload": candidate_click_payload,
            "bounds_center_click_payload_path": str(bounds_center_click_payload_path),
            "bounds_center_click_ok": bounds_center_click_ok,
            "bounds_center_click_payload": bounds_center_click_payload,
            "input_coverage": input_coverage,
            "vision_source_target_enabled": vision_source_target_enabled,
            "window_vision_path": str(window_vision_path),
            "window_vision_ok": window_vision_ok,
            "window_vision_match": window_vision_match,
            "window_vision_best_target": window_vision_best_target,
            "window_vision_target_query": window_vision_target_query,
            "expected_window_local_bounds": expected_window_local_bounds,
            "expected_window_local_point": expected_window_local_point,
            "element_vision_path": str(element_vision_path),
            "element_vision_ok": element_vision_ok,
            "element_vision_match": element_vision_match,
            "element_vision_best_target": element_vision_best_target,
            "element_vision_target_query": element_vision_target_query,
            "expected_element_local_bounds": expected_element_local_bounds,
            "expected_element_local_point": expected_element_local_point,
            "element_assertion_path": str(assert_path),
            "entry_assertion_ok": entry_assertion_ok,
            "entry_count_assertion": entry_count_assertion,
            "entry_property_assertion": entry_property_assertion,
            "status_assertion_path": str(status_assert_path),
            "status_count_assertion": status_count_assertion,
            "status_property_assertion": status_property_assertion,
            "set_text_expected": set_text_payload,
            "annotation_ok": annotation_ok,
            "candidate_click_annotation_ok": candidate_click_annotation_ok,
            "annotation_png_count": len(annotation_pngs),
            "annotation_json_count": len(annotation_jsons),
            "annotation_dir": str(annotation_dir),
            "cleanup": cleanup_hint,
        }


def _run_wpf_element_action_case(project_root: Path, *, required: bool = False) -> dict[str, Any]:
    system = platform.system()
    skip_reason = _windows_wpf_skip_reason(system)
    if skip_reason:
        return {
            "name": "desktop_wpf_complex_control_regression",
            "ok": not required,
            "required": required,
            "skipped": True,
            "reason": skip_reason,
        }
    with tempfile.TemporaryDirectory(prefix="desktop-components-wpf-action-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan, assertion_relative_file, cleanup_hint = _temporary_wpf_form_plan(package_dir)
        assertion_file = package_dir / assertion_relative_file
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        if not validation.ok:
            return {
                "name": "desktop_wpf_complex_control_regression",
                "ok": False,
                "required": required,
                "validation_ok": False,
                "errors": [error.format() for error in validation.errors],
            }
        run_error = ""
        started_at = time.time()
        try:
            result = execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                run_name="desktop-components-wpf-action",
                run_context_handler=_disable_run_log_echo,
            )
            run_ok = result.status == "passed"
            output_dir = result.output_dir
        except Exception as error:
            run_ok = False
            output_dir = ""
            run_error = str(error)
        finally:
            _cleanup_temporary_form_case(package_dir, "Windows")
        content = assertion_file.read_text(encoding="utf-8", errors="replace") if assertion_file.exists() else ""
        expected_text = str(plan["variables"]["expected_text"])
        elements_path = package_dir / "output" / "desktop-elements" / "wpf-elements.json"
        dump_path = package_dir / "output" / "desktop-elements" / "wpf-entry-dump.json"
        state_path = package_dir / "output" / "desktop-elements" / "wpf-entry-state.json"
        assert_path = package_dir / "output" / "desktop-elements" / "wpf-entry-assertion.json"
        table_path = package_dir / "output" / "desktop-elements" / "wpf-orders-table.json"
        cell_path = package_dir / "output" / "desktop-elements" / "wpf-orders-cell.json"
        tree_path = package_dir / "output" / "desktop-elements" / "wpf-nav-tree.json"
        tree_expand_path = package_dir / "output" / "desktop-elements" / "wpf-nav-tree-expand.json"
        tree_select_path = package_dir / "output" / "desktop-elements" / "wpf-nav-tree-select.json"
        tree_collapse_path = package_dir / "output" / "desktop-elements" / "wpf-nav-tree-collapse.json"
        menu_path = package_dir / "output" / "desktop-elements" / "wpf-menu-invoke.json"
        context_menu_path = package_dir / "output" / "desktop-elements" / "wpf-context-menu-invoke.json"
        scroll_path = package_dir / "output" / "desktop-elements" / "wpf-scroll-viewer.json"
        scroll_target_path = package_dir / "output" / "desktop-elements" / "wpf-scroll-target-state.json"
        window_capture_path = package_dir / "output" / "desktop-screenshots" / "wpf-window-screen.png"
        element_capture_path = package_dir / "output" / "desktop-screenshots" / "wpf-entry-element-screen.png"
        window_capture_payload_path = package_dir / "output" / "json" / "wpf-window-capture.json"
        element_capture_payload_path = package_dir / "output" / "json" / "wpf-entry-capture.json"
        element_payload = _read_json(elements_path) if elements_path.exists() else {}
        element_rows = element_payload.get("elements") if isinstance(element_payload.get("elements"), list) else []
        automation_ids = {
            str(element.get("automation_id", ""))
            for element in element_rows
            if isinstance(element, dict)
        }
        expected_automation_ids = {
            "DesktopWpfTextBox",
            "DesktopWpfSaveButton",
            "DesktopWpfAgreeCheckBox",
            "DesktopWpfModeCombo",
            "DesktopWpfOptionsList",
            "DesktopWpfOrdersGrid",
            "DesktopWpfNavTree",
            "DesktopWpfContextPanel",
            "DesktopWpfScrollViewer",
        }
        expected_controls_found = expected_automation_ids.issubset(automation_ids)
        dump_payload = _read_json(dump_path) if dump_path.exists() else {}
        dump_ok = (
            bool(dump_payload.get("ok"))
            and isinstance(dump_payload.get("selected_element"), dict)
            and isinstance(dump_payload.get("tree"), list)
        )
        state_payload = _read_json(state_path) if state_path.exists() else {}
        state_ok = bool(state_payload.get("ok")) and isinstance(state_payload.get("element_state"), dict)
        assert_payload = _read_json(assert_path) if assert_path.exists() else {}
        assert_ok = bool(assert_payload.get("ok")) and _file_nonempty_after(assert_path, started_at)
        table_payload = _read_json(table_path) if table_path.exists() else {}
        table_data = table_payload.get("table") if isinstance(table_payload.get("table"), dict) else {}
        table_cells = table_data.get("cells") if isinstance(table_data.get("cells"), list) else []
        table_texts = {
            str(cell.get(field, ""))
            for cell in table_cells
            if isinstance(cell, dict)
            for field in ("text", "value", "name")
            if str(cell.get(field, ""))
        }
        table_ok = bool(table_payload.get("ok")) and "Beta" in table_texts and "Review" in table_texts
        cell_payload = _read_json(cell_path) if cell_path.exists() else {}
        selected_cell = cell_payload.get("selected_cell") if isinstance(cell_payload.get("selected_cell"), dict) else {}
        selected_cell_texts = {
            str(selected_cell.get(field, ""))
            for field in ("text", "value", "name")
            if str(selected_cell.get(field, ""))
        }
        selected_cell_ok = bool(cell_payload.get("ok")) and "Review" in selected_cell_texts
        tree_payload = _read_json(tree_path) if tree_path.exists() else {}
        tree_data = tree_payload.get("tree") if isinstance(tree_payload.get("tree"), dict) else {}
        tree_nodes = tree_data.get("nodes") if isinstance(tree_data.get("nodes"), list) else []
        tree_node_names = {str(node.get("name", "")) for node in tree_nodes if isinstance(node, dict)}
        tree_expand_payload = _read_json(tree_expand_path) if tree_expand_path.exists() else {}
        tree_select_payload = _read_json(tree_select_path) if tree_select_path.exists() else {}
        tree_collapse_payload = _read_json(tree_collapse_path) if tree_collapse_path.exists() else {}
        selected_tree_node = tree_select_payload.get("tree_node") if isinstance(tree_select_payload.get("tree_node"), dict) else {}
        selected_tree_path = selected_tree_node.get("path") if isinstance(selected_tree_node.get("path"), list) else []
        tree_ok = (
            bool(tree_payload.get("ok"))
            and {"Settings", "Accounts", "Security", "Reports", "Monthly"}.issubset(tree_node_names)
            and bool(tree_expand_payload.get("ok"))
            and bool(tree_select_payload.get("ok"))
            and selected_tree_path == ["Settings", "Accounts"]
            and bool(tree_collapse_payload.get("ok"))
        )
        menu_payload = _read_json(menu_path) if menu_path.exists() else {}
        menu_ok = bool(menu_payload.get("ok")) and menu_payload.get("menu_path") == ["File", "Mark Menu"]
        context_menu_payload = _read_json(context_menu_path) if context_menu_path.exists() else {}
        context_menu_ok = (
            bool(context_menu_payload.get("ok"))
            and context_menu_payload.get("open_context_menu") is True
            and context_menu_payload.get("menu_path") == ["Mark Context"]
        )
        scroll_payload = _read_json(scroll_path) if scroll_path.exists() else {}
        scroll_target_payload = _read_json(scroll_target_path) if scroll_target_path.exists() else {}
        scroll_target_state = (
            scroll_target_payload.get("element_state") if isinstance(scroll_target_payload.get("element_state"), dict) else {}
        )
        scroll_ok = (
            bool(scroll_payload.get("ok"))
            and bool(scroll_target_payload.get("ok"))
            and bool(scroll_target_state.get("visible", False))
        )
        window_capture_payload = _read_json(window_capture_payload_path) if window_capture_payload_path.exists() else {}
        element_capture_payload = _read_json(element_capture_payload_path) if element_capture_payload_path.exists() else {}
        capture_ok = (
            bool(window_capture_payload.get("ok"))
            and bool(element_capture_payload.get("ok"))
            and _file_nonempty_after(window_capture_path, started_at)
            and _file_nonempty_after(element_capture_path, started_at)
        )
        content_ok = (
            expected_text in content
            and "agree=True" in content
            and "mode=Audit" in content
            and "option=Green" in content
            and "menu_marked=True" in content
            and "context_marked=True" in content
        )
        ok = (
            run_ok
            and content_ok
            and expected_controls_found
            and _file_nonempty_after(elements_path, started_at)
            and _file_nonempty_after(dump_path, started_at)
            and dump_ok
            and state_ok
            and assert_ok
            and table_ok
            and selected_cell_ok
            and tree_ok
            and menu_ok
            and context_menu_ok
            and scroll_ok
            and capture_ok
        )
        return {
            "name": "desktop_wpf_complex_control_regression",
            "ok": ok,
            "required": required,
            "validation_ok": True,
            "run_ok": run_ok,
            "output_dir": output_dir,
            "run_error": run_error,
            "assertion_file": str(assertion_file),
            "content_ok": content_ok,
            "content_preview": content[:500],
            "expected_controls_found": expected_controls_found,
            "automation_ids": sorted(value for value in automation_ids if value),
            "elements_path": str(elements_path),
            "dump_ok": dump_ok,
            "state_ok": state_ok,
            "assert_ok": assert_ok,
            "table_ok": table_ok,
            "selected_cell_ok": selected_cell_ok,
            "tree_ok": tree_ok,
            "selected_tree_path": selected_tree_path,
            "menu_ok": menu_ok,
            "context_menu_ok": context_menu_ok,
            "scroll_ok": scroll_ok,
            "capture_ok": capture_ok,
            "paths": {
                "table": str(table_path),
                "cell": str(cell_path),
                "tree": str(tree_path),
                "menu": str(menu_path),
                "context_menu": str(context_menu_path),
                "scroll": str(scroll_path),
                "scroll_target": str(scroll_target_path),
                "window_capture": str(window_capture_path),
                "element_capture": str(element_capture_path),
            },
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
        "covered_by": (
            "desktop_input.type_text/hotkey/click/double_click/right_click/scroll/drag handlers require "
            "pyautogui at runtime; self-check uses only its own temporary app window."
        ),
    }


def _run_capability_diagnostics_case() -> dict[str, Any]:
    capability_matrix = {
        "schema_version": 1,
        "platform": "macos",
        "backend": "native",
        "source": "simulated",
        "capabilities": {
            "semantic": {"window_list": False, "elements": False},
            "input": {"keyboard": False, "mouse": False, "clipboard": False},
            "screenshot": {"full_screen": False, "region": False, "annotation": False},
            "vision": {"image_locator": False, "template_matching": False, "ocr": False},
        },
        "permissions": {
            "accessibility": "not_granted_or_unavailable",
            "screen_recording": "not_granted_or_unavailable",
            "input_control": "unknown",
        },
        "dependencies": {
            "pyautogui": False,
            "pyperclip": False,
            "Pillow.ImageGrab": False,
            "opencv-python": False,
            "tesseract": False,
            "tessdata.eng": False,
            "tessdata.chi_sim": False,
        },
        "limitations": [
            "window_list_unavailable",
            "pyautogui_missing",
            "pillow_imagegrab_missing",
            "opencv_missing_for_image_locator",
            "tesseract_or_eng_tessdata_missing_for_ocr",
            "macos_tcc_permissions_may_require_user_approval",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="desktop-capability-diagnostics-") as raw_temp_dir:
        state_path = Path(raw_temp_dir) / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "step": 1,
                    "action": "open_desktop",
                    "error": "simulated desktop permission and dependency failure",
                    "capability_matrix": capability_matrix,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        diagnostics = collect_desktop_diagnostics([str(state_path)])
    suggestions = build_desktop_repair_suggestions(diagnostics)
    summary = diagnostics[0].get("capability_matrix", {}) if diagnostics else {}
    expected_limitations = set(capability_matrix["limitations"])
    actual_limitations = set(summary.get("limitations", [])) if isinstance(summary.get("limitations"), list) else set()
    summary_capabilities = summary.get("capabilities") if isinstance(summary.get("capabilities"), dict) else {}
    return {
        "name": "desktop_capability_diagnostics_simulation",
        "ok": (
            bool(diagnostics)
            and summary.get("schema_version") == 1
            and "semantic" in summary_capabilities
            and "semantic" not in summary
            and summary.get("permissions", {}).get("accessibility") == "not_granted_or_unavailable"
            and summary.get("dependencies", {}).get("pyautogui") is False
            and expected_limitations.issubset(actual_limitations)
            and any("桌面能力限制" in suggestion for suggestion in suggestions)
        ),
        "diagnostics": diagnostics,
        "suggestions": suggestions,
    }


def _write_vision_fixture_images(source_path: Path, template_path: Path) -> dict[str, int]:
    from PIL import Image, ImageDraw

    source_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template = Image.new("RGB", (64, 42), (21, 92, 184))
    draw = ImageDraw.Draw(template)
    draw.rectangle((0, 0, 63, 41), outline=(255, 255, 255), width=3)
    draw.line((6, 35, 58, 6), fill=(255, 210, 64), width=4)
    draw.rectangle((14, 12, 30, 28), fill=(41, 196, 128))
    draw.ellipse((39, 13, 55, 29), fill=(230, 72, 92))
    source = Image.new("RGB", (320, 220), (238, 241, 245))
    background = ImageDraw.Draw(source)
    for x in range(0, 320, 20):
        background.line((x, 0, x, 220), fill=(226, 230, 236))
    for y in range(0, 220, 20):
        background.line((0, y, 320, y), fill=(226, 230, 236))
    bounds = {"x": 123, "y": 77, "width": template.width, "height": template.height}
    source.paste(template, (bounds["x"], bounds["y"]))
    template.save(template_path)
    source.save(source_path)
    return bounds


def _write_ocr_fixture_image(source_path: Path, *, text: str, language: str = "latin") -> None:
    from PIL import Image, ImageDraw, ImageFont

    source_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 180), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _ocr_fixture_font(ImageFont, language=language)
    draw.rectangle((18, 18, 622, 162), outline=(35, 35, 35), width=2)
    draw.text((54, 58), text, fill=(0, 0, 0), font=font)
    image.save(source_path)


def _ocr_fixture_font(image_font_module: Any, *, language: str = "latin") -> Any:
    for candidate in _ocr_fixture_font_candidates(language):
        if candidate.exists():
            try:
                return image_font_module.truetype(str(candidate), 44)
            except Exception:
                continue
    return image_font_module.load_default()


def _ocr_fixture_font_available(language: str = "latin") -> bool:
    try:
        from PIL import ImageFont
    except Exception:
        return False
    for candidate in _ocr_fixture_font_candidates(language):
        if not candidate.exists():
            continue
        try:
            ImageFont.truetype(str(candidate), 44)
            return True
        except Exception:
            continue
    return language != "zh"


def _ocr_fixture_font_candidates(language: str = "latin") -> list[Path]:
    if language == "zh":
        return [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msyh.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("C:/Windows/Fonts/simsun.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
            Path("/Library/Fonts/NotoSansCJK-Regular.ttc"),
        ]
    return [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]


def _ocr_raw_text_contains(normalized_raw_text: str, expected: str) -> bool:
    normalized_expected = re.sub(r"\s+", "", expected)
    if normalized_expected.upper().isascii():
        return normalized_expected.upper() in normalized_raw_text.upper()
    return normalized_expected in normalized_raw_text


def _write_vision_missing_template(template_path: Path) -> None:
    from PIL import Image, ImageDraw

    template_path.parent.mkdir(parents=True, exist_ok=True)
    template = Image.new("RGB", (58, 38), (35, 31, 32))
    draw = ImageDraw.Draw(template)
    draw.rectangle((0, 0, 57, 37), outline=(248, 248, 242), width=3)
    draw.line((5, 5, 52, 33), fill=(165, 42, 214), width=5)
    draw.line((7, 31, 50, 4), fill=(255, 88, 34), width=3)
    draw.rectangle((20, 9, 38, 27), fill=(0, 210, 230))
    template.save(template_path)


def _image_size(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        from PIL import Image

        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return {}


def _image_size_matches_bounds(size: dict[str, int], bounds: dict[str, Any], *, tolerance: int = 4) -> bool:
    if not size or not bounds:
        return False
    try:
        width = int(size.get("width", 0) or 0)
        height = int(size.get("height", 0) or 0)
        expected_width = int(float(bounds.get("width", 0) or 0))
        expected_height = int(float(bounds.get("height", 0) or 0))
    except (TypeError, ValueError):
        return False
    return (
        width > 0
        and height > 0
        and expected_width > 0
        and expected_height > 0
        and abs(width - expected_width) <= tolerance
        and abs(height - expected_height) <= tolerance
    )


def _coordinate_profile_ok(value: Any, *, screen_clickable: bool | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    transforms = value.get("transforms") if isinstance(value.get("transforms"), dict) else {}
    local_to_screen = transforms.get("local_to_screen") if isinstance(transforms.get("local_to_screen"), dict) else {}
    screen_to_local = transforms.get("screen_to_local") if isinstance(transforms.get("screen_to_local"), dict) else {}
    if (
        value.get("kind") != "desktop_coordinate_profile"
        or value.get("schema_version") != 1
        or not isinstance(value.get("space"), dict)
        or not isinstance(value.get("display"), dict)
        or not isinstance(source.get("bounds"), dict)
        or not isinstance(local_to_screen.get("offset"), dict)
        or not isinstance(screen_to_local.get("offset"), dict)
    ):
        return False
    if screen_clickable is not None and bool(source.get("screen_clickable")) is not bool(screen_clickable):
        return False
    return True


def _window_safety_ok(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("ok") is not True:
        return False
    bounds = value.get("window_bounds") if isinstance(value.get("window_bounds"), dict) else {}
    points = value.get("points") if isinstance(value.get("points"), list) else []
    return (
        isinstance(bounds.get("x"), int)
        and isinstance(bounds.get("y"), int)
        and isinstance(bounds.get("width"), int)
        and isinstance(bounds.get("height"), int)
        and bounds.get("width", 0) > 0
        and bounds.get("height", 0) > 0
        and bool(points)
        and all(isinstance(point, dict) and point.get("inside_window") is True for point in points)
        and _window_safety_ownership_ok(value)
    )


def _window_safety_ownership_ok(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    points = value.get("points") if isinstance(value.get("points"), list) else []
    if not points:
        return False
    checked = False
    for point in points:
        if not isinstance(point, dict):
            return False
        ownership = point.get("ownership") if isinstance(point.get("ownership"), dict) else {}
        if not ownership:
            continue
        if ownership.get("checked") is True:
            checked = True
            if ownership.get("belongs_to_expected_window") is not True:
                return False
    return checked


def _bounds_match(actual: Any, expected: Any, *, tolerance: int = 4) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    try:
        return all(
            abs(int(float(actual.get(field, 0) or 0)) - int(float(expected.get(field, 0) or 0))) <= tolerance
            for field in ("x", "y", "width", "height")
        )
    except (TypeError, ValueError):
        return False


def _point_match(actual: Any, expected: Any, *, tolerance: int = 4) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    try:
        return all(
            abs(int(float(actual.get(field, 0) or 0)) - int(float(expected.get(field, 0) or 0))) <= tolerance
            for field in ("x", "y")
        )
    except (TypeError, ValueError):
        return False


def _point_center_from_bounds(bounds: dict[str, Any]) -> dict[str, int]:
    try:
        x = int(float(bounds.get("x", 0) or 0))
        y = int(float(bounds.get("y", 0) or 0))
        width = int(float(bounds.get("width", 0) or 0))
        height = int(float(bounds.get("height", 0) or 0))
        return {"x": x + width // 2, "y": y + height // 2}
    except (TypeError, ValueError):
        return {"x": 0, "y": 0}


def _bounds_relative_to(bounds: dict[str, Any], source_bounds: dict[str, Any]) -> dict[str, int]:
    try:
        return {
            "x": int(float(bounds.get("x", 0) or 0)) - int(float(source_bounds.get("x", 0) or 0)),
            "y": int(float(bounds.get("y", 0) or 0)) - int(float(source_bounds.get("y", 0) or 0)),
            "width": int(float(bounds.get("width", 0) or 0)),
            "height": int(float(bounds.get("height", 0) or 0)),
        }
    except (TypeError, ValueError):
        return {"x": 0, "y": 0, "width": 0, "height": 0}


def _temporary_form_plan(package_dir: Path, system: str) -> tuple[dict[str, Any], Path, str]:
    title = "AI Automate Desktop Element Form"
    expected_text = "desktop element set_text regression input"
    clipboard_sentinel = f"desktop-clipboard-sentinel-{package_dir.name}"
    clipboard_text = "desktop clipboard restore regression input"
    assertion_file = Path("resources") / "desktop-element-action-output.txt"
    pid_file = Path("resources") / "desktop-element-action-pid.txt"
    clipboard_after_file = Path("resources") / "desktop-clipboard-after.txt"
    absolute_assertion_file = str((package_dir / assertion_file).resolve())
    absolute_pid_file = str((package_dir / pid_file).resolve())
    absolute_clipboard_after_file = str((package_dir / clipboard_after_file).resolve())
    if system == "Windows":
        powershell = _windows_powershell_executable()
        if not powershell:
            raise RuntimeError("PowerShell is required for the Windows desktop element action regression.")
        include_mouse_steps = _module_available("pyautogui")
        include_clipboard_steps = include_mouse_steps and _module_available("pyperclip")
        entry_locator = {"automation_id": "DesktopElementTextBox", "control_type": "Edit"}
        button_locator = {"automation_id": "DesktopElementSaveButton", "control_type": "Button"}
        checkbox_locator = {"automation_id": "DesktopElementAgreeCheckBox", "control_type": "CheckBox"}
        combo_locator = {"automation_id": "DesktopElementModeCombo", "control_type": "ComboBox"}
        list_locator = {"automation_id": "DesktopElementOptionsList", "control_type": "List"}
        panel_locator = {"automation_id": "DesktopElementMousePanel", "control_type": "Pane"}
        context_panel_locator = {"automation_id": "DesktopElementContextPanel", "control_type": "Pane"}
        status_locator = {"automation_id": "DesktopElementStatus", "control_type": "Text"}
        grid_locator = {"automation_id": "DesktopElementOrdersGrid"}
        tree_locator = {"automation_id": "DesktopElementNavTree", "control_type": "Tree"}
        scroll_locator = {"automation_id": "DesktopElementScrollPanel", "control_type": "Pane"}
        scroll_target_locator = {"automation_id": "DesktopElementScrollTargetButton", "control_type": "Button"}
        app_command = powershell
        app_args = [
            "-NoProfile",
            "-Sta",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _windows_forms_script(title, absolute_assertion_file),
        ]
        cleanup_hint = f"temporary WinForms app title={title}; pid file={absolute_pid_file}"
    else:
        include_mouse_steps = False
        include_clipboard_steps = False
        entry_locator = {"role": "AXTextField", "element_match_index": 0}
        button_locator = {"name": "Save", "role": "AXButton"}
        checkbox_locator = {}
        combo_locator = {}
        list_locator = {}
        panel_locator = {}
        context_panel_locator = {}
        status_locator = {}
        app_script = f"""
import pathlib
import sys
import tkinter as tk

output = pathlib.Path(sys.argv[1])
root = tk.Tk()
root.title({title!r})
root.geometry("520x180")
root.resizable(False, False)
tk.Label(root, text="Value").pack(pady=(12, 4))
entry = tk.Entry(root, width=52)
entry.pack(padx=20)
status = tk.StringVar(value="")

def save_value():
    output.write_text(entry.get(), encoding="utf-8")
    status.set(entry.get())

tk.Button(root, text="Save", command=save_value).pack(pady=10)
tk.Label(root, textvariable=status).pack()
root.mainloop()
""".strip()
        app_command = sys.executable
        app_args = ["-c", app_script, absolute_assertion_file]
        cleanup_hint = f"temporary tkinter app title={title}; pid file={absolute_pid_file}"
    vision_locator = context_panel_locator if system == "Windows" else entry_locator
    extra_control_steps: list[dict[str, Any]] = []
    clipboard_steps: list[dict[str, Any]] = []
    vision_source_target_steps: list[dict[str, Any]] = []
    status_assert_steps: list[dict[str, Any]] = []
    expected_content_fragments = ["{{expected_text}}"]
    include_vision_source_target_steps = _module_available("cv2") and _module_available("PIL")
    if include_vision_source_target_steps:
        vision_source_target_steps.extend(
            [
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_image",
                    "template_path": "output/desktop-screenshots/form-vision-element-screen.png",
                    "source_target": "window",
                    "title_contains": title,
                    "window_match_index": 0,
                    "threshold": 0.80,
                    "match_index": 0,
                    "max_matches": 3,
                    "path": "form-vision-window-vision.json",
                    "save_as": "entry_window_vision",
                    "timeout_ms": 2000,
                    "interval_ms": 100,
                },
                {
                    "action": "desktop_vision",
                    "desktop": "desktop",
                    "type": "locate_image",
                    "template_path": "output/desktop-screenshots/form-vision-element-screen.png",
                    "source_target": "element",
                    "title_contains": title,
                    "window_match_index": 0,
                    **vision_locator,
                    "threshold": 0.80,
                    "match_index": 0,
                    "max_matches": 3,
                    "path": "form-vision-element-vision.json",
                    "save_as": "entry_element_vision",
                    "timeout_ms": 2000,
                    "interval_ms": 100,
                    "max_depth": 5,
                    "max_elements": 200,
                },
            ]
        )
    if system == "Windows":
        if include_clipboard_steps:
            clipboard_steps.extend(
                [
                    {
                        "action": "command",
                        "type": "run",
                        "argv": [
                            sys.executable,
                            "-c",
                            "import pyperclip, sys; pyperclip.copy(sys.argv[1])",
                            "{{clipboard_sentinel}}",
                        ],
                        "timeout_ms": 10000,
                        "save_as": "clipboard_seed",
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "type_text",
                        "value": "{{clipboard_text}}",
                        "method": "clipboard",
                        "preserve_clipboard": True,
                        "save_as": "clipboard_type_text",
                    },
                    {
                        "action": "command",
                        "type": "run",
                        "argv": [
                            sys.executable,
                            "-c",
                            (
                                "import pathlib, pyperclip, sys; "
                                "pathlib.Path(sys.argv[1]).write_text(pyperclip.paste(), encoding='utf-8')"
                            ),
                            absolute_clipboard_after_file,
                        ],
                        "timeout_ms": 10000,
                        "save_as": "clipboard_after",
                    },
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": title,
                        **entry_locator,
                        "state": "exists",
                        "expected": "{{clipboard_text}}",
                        "mode": "contains",
                        "path": "form-clipboard-assertion.json",
                        "save_as": "clipboard_assertion",
                        "max_depth": 5,
                        "max_elements": 200,
                    },
                ]
            )
        extra_control_steps.append(
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "title_contains": title,
                **checkbox_locator,
                "save_as": "agree_checkbox",
                "max_depth": 5,
                "max_elements": 200,
            }
        )
        if include_mouse_steps:
            extra_control_steps.extend(
                [
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke_menu",
                        "title_contains": title,
                        **context_panel_locator,
                        "open_context_menu": True,
                        "menu_path": ["Mark Context"],
                        "max_depth": 8,
                        "max_elements": 800,
                        "path": "form-context-menu-invoke.json",
                        "save_as": "context_menu_invoke",
                    },
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "click",
                        "title_contains": title,
                        **checkbox_locator,
                        "save_as": "agree_checkbox_click",
                        "max_depth": 5,
                        "max_elements": 200,
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "click",
                        "target": "current_window_offset",
                        "offset_x": 460,
                        "offset_y": 210,
                        "save_as": "mouse_panel_focus_click",
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "double_click",
                        "target": "element_center",
                        "title_contains": title,
                        **panel_locator,
                        "max_depth": 5,
                        "max_elements": 200,
                        "interval_ms": 50,
                        "save_as": "mouse_panel_double_click",
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "right_click",
                        "target": "element_center",
                        "title_contains": title,
                        **panel_locator,
                        "max_depth": 5,
                        "max_elements": 200,
                        "save_as": "mouse_panel_right_click",
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "scroll",
                        "target": "element_center",
                        "title_contains": title,
                        **panel_locator,
                        "max_depth": 5,
                        "max_elements": 200,
                        "amount": -1,
                        "save_as": "mouse_panel_scroll",
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "drag",
                        "target": "element_center",
                        "title_contains": title,
                        **panel_locator,
                        "max_depth": 5,
                        "max_elements": 200,
                        "delta_x": 40,
                        "delta_y": 0,
                        "duration_ms": 150,
                        "save_as": "mouse_panel_drag",
                    },
                ]
            )
        extra_control_steps.extend(
            [
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "get_state",
                    "title_contains": title,
                    **combo_locator,
                    "save_as": "mode_combo_state",
                    "max_depth": 5,
                    "max_elements": 200,
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "select",
                    "title_contains": title,
                    **combo_locator,
                    "option_index": 2,
                    "save_as": "mode_combo_select",
                    "max_depth": 5,
                    "max_elements": 200,
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "find",
                    "title_contains": title,
                    **list_locator,
                    "save_as": "options_list",
                    "max_depth": 5,
                    "max_elements": 200,
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "select",
                    "title_contains": title,
                    **list_locator,
                    "option_index": 2,
                    "save_as": "options_list_select",
                    "max_depth": 5,
                    "max_elements": 200,
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "get_table",
                    "title_contains": title,
                    **grid_locator,
                    "max_depth": 6,
                    "max_elements": 300,
                    "max_rows": 5,
                    "max_columns": 5,
                    "path": "form-orders-table.json",
                    "save_as": "orders_table",
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "select_cell",
                    "title_contains": title,
                    **grid_locator,
                    "row": 1,
                    "column_index": 2,
                    "max_depth": 6,
                    "max_elements": 300,
                    "path": "form-orders-cell.json",
                    "save_as": "orders_cell",
                },
            ]
        )
        extra_control_steps.extend(
            [
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "get_tree",
                    "title_contains": title,
                    **tree_locator,
                    "max_depth": 8,
                    "max_elements": 400,
                    "max_nodes": 50,
                    "path": "form-nav-tree.json",
                    "save_as": "nav_tree",
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "expand_tree",
                    "title_contains": title,
                    **tree_locator,
                    "tree_path": ["Settings"],
                    "max_depth": 8,
                    "max_elements": 400,
                    "path": "form-nav-tree-expand.json",
                    "save_as": "nav_tree_expand",
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "select_tree",
                    "title_contains": title,
                    **tree_locator,
                    "tree_path": ["Settings", "Accounts"],
                    "max_depth": 8,
                    "max_elements": 400,
                    "path": "form-nav-tree-select.json",
                    "save_as": "nav_tree_select",
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "collapse_tree",
                    "title_contains": title,
                    **tree_locator,
                    "tree_path": ["Settings"],
                    "max_depth": 8,
                    "max_elements": 400,
                    "path": "form-nav-tree-collapse.json",
                    "save_as": "nav_tree_collapse",
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "invoke_menu",
                    "title_contains": title,
                    "menu_path": ["File", "Mark Menu"],
                    "max_depth": 8,
                    "max_elements": 400,
                    "path": "form-menu-invoke.json",
                    "save_as": "menu_invoke",
                },
            ]
        )
        if include_mouse_steps:
            extra_control_steps.extend(
                [
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "scroll_element",
                        "title_contains": title,
                        **scroll_locator,
                        "scroll_to": "end",
                        "max_depth": 8,
                        "max_elements": 400,
                        "path": "form-scroll-panel.json",
                        "save_as": "scroll_panel",
                    },
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "get_state",
                        "title_contains": title,
                        **scroll_target_locator,
                        "max_depth": 8,
                        "max_elements": 400,
                        "path": "form-scroll-target-state.json",
                        "save_as": "scroll_target_state",
                    },
                ]
            )
        status_assert_steps.append(
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": title,
                **status_locator,
                "state": "exists",
                "expected": "{{expected_text}}",
                "mode": "contains",
                "expected_count": 1,
                "property": "visible",
                "property_expected": True,
                "path": "form-status-assertion.json",
                "save_as": "status_assertion",
                "max_depth": 5,
                "max_elements": 200,
            }
        )
        expected_content_fragments.extend(
            [
                "agree=True" if include_mouse_steps else "agree=False",
                "mode=Audit",
                "option=Green",
                "menu_marked=True",
                "context_marked=True" if include_mouse_steps else "context_marked=False",
            ]
        )
        if include_mouse_steps:
            expected_content_fragments.extend(
                [
                    "mouse_double_click=True",
                    "mouse_right_click=True",
                    "mouse_scroll=True",
                    "mouse_drag=True",
                ]
            )
    plan = {
        "name": "desktop element set_text invoke regression",
        "automation_type": "desktop",
        "variables": {
            "expected_text": expected_text,
            "clipboard_restore_enabled": include_clipboard_steps,
            "clipboard_sentinel": clipboard_sentinel,
            "clipboard_text": clipboard_text,
            "vision_source_target_enabled": include_vision_source_target_steps,
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {"action": "write", "type": "json", "path": "desktop-probe.json", "value": "{{desktop_probe}}"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": app_command,
                "args": app_args,
                "save_as": "app_launch",
            },
            {
                "action": "command",
                "type": "run",
                "argv": [
                    sys.executable,
                    "-c",
                    "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text(str(sys.argv[2]), encoding='utf-8')",
                    absolute_pid_file,
                    "{{app_launch.pid}}",
                ],
                "timeout_ms": 10000,
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "exists",
                "timeout_ms": 8000,
                "interval_ms": 100,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "title_contains": title,
                **entry_locator,
                "path": "form-observe.json",
                "include_windows": True,
                "include_elements": True,
                "include_screenshot": True,
                "max_depth": 5,
                "max_elements": 200,
                "save_as": "form_observation",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "candidate",
                "candidate_source": "latest",
                "candidate_id": "{{form_observation.target_candidates.best_candidate.candidate_id}}",
                "min_confidence": "medium",
                "save_as": "entry_latest_candidate_click",
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-entry-latest-candidate-click.json",
                "value": "{{entry_latest_candidate_click}}",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": title,
                "path": "form-window-screen.png",
                "save_as": "form_window_capture",
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-window-capture.json",
                "value": "{{form_window_capture}}",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "element",
                "title_contains": title,
                **entry_locator,
                "path": "form-entry-element-screen.png",
                "save_as": "form_entry_capture",
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-entry-capture.json",
                "value": "{{form_entry_capture}}",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "element",
                "title_contains": title,
                **vision_locator,
                "path": "form-vision-element-screen.png",
                "save_as": "form_vision_capture",
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-vision-capture.json",
                "value": "{{form_vision_capture}}",
            },
            *vision_source_target_steps,
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "form-elements.json",
                "save_as": "form_elements",
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "dump",
                "title_contains": title,
                **entry_locator,
                "path": "form-elements-dump.json",
                "save_as": "form_elements_dump",
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "candidate",
                "target_candidates": "{{form_observation.target_candidates}}",
                "candidate_id": "{{form_observation.target_candidates.best_candidate.candidate_id}}",
                "min_confidence": "medium",
                "save_as": "entry_candidate_click",
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-entry-candidate-click.json",
                "value": "{{entry_candidate_click}}",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": "{{form_elements_dump.selected_element.bounds}}",
                "save_as": "entry_bounds_center_click",
            },
            {
                "action": "write",
                "type": "json",
                "path": "form-entry-bounds-center-click.json",
                "value": "{{entry_bounds_center_click}}",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["esc"]},
            *clipboard_steps,
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": title,
                **entry_locator,
                "value": "{{expected_text}}",
                "preserve_clipboard": False,
                "save_as": "entry_set_text",
                "max_depth": 5,
                "max_elements": 200,
            },
            *extra_control_steps,
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": title,
                **entry_locator,
                "state": "exists",
                "expected": "{{expected_text}}",
                "mode": "equals",
                "expected_count": 1,
                "property": "enabled",
                "property_expected": True,
                "path": "form-entry-assertion.json",
                "save_as": "entry_assertion",
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "save_as": "save_button_invoke",
                "max_depth": 5,
                "max_elements": 200,
            },
            {"action": "sleep", "seconds": 0.3},
            *status_assert_steps,
            {
                "action": "command",
                "type": "run",
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib, sys; "
                        "content = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace'); "
                        "expected = sys.argv[2]; "
                        "extra = sys.argv[3:]; "
                        "ok = expected in content and all(item in content for item in extra); "
                        "raise SystemExit(0 if ok else 7)"
                    ),
                    absolute_assertion_file,
                    *expected_content_fragments,
                ],
                "timeout_ms": 10000,
                "save_as": "content_assertion",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "save_as": "app_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "save_as": "app_closed",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, assertion_file, cleanup_hint


def _temporary_wpf_form_plan(package_dir: Path) -> tuple[dict[str, Any], Path, str]:
    title = "AI Automate Desktop WPF Element Form"
    expected_text = "desktop WPF set_text regression input"
    assertion_file = Path("resources") / "desktop-wpf-element-action-output.txt"
    pid_file = Path("resources") / "desktop-element-action-pid.txt"
    absolute_assertion_file = str((package_dir / assertion_file).resolve())
    absolute_pid_file = str((package_dir / pid_file).resolve())
    powershell = _windows_powershell_executable()
    app_args = [
        "-NoProfile",
        "-Sta",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _windows_wpf_script(title, absolute_assertion_file),
    ]
    entry_locator = {"automation_id": "DesktopWpfTextBox"}
    button_locator = {"automation_id": "DesktopWpfSaveButton"}
    checkbox_locator = {"automation_id": "DesktopWpfAgreeCheckBox"}
    combo_locator = {"automation_id": "DesktopWpfModeCombo"}
    list_locator = {"automation_id": "DesktopWpfOptionsList"}
    grid_locator = {"automation_id": "DesktopWpfOrdersGrid"}
    tree_locator = {"automation_id": "DesktopWpfNavTree"}
    context_panel_locator = {"automation_id": "DesktopWpfContextPanel"}
    scroll_locator = {"automation_id": "DesktopWpfScrollViewer"}
    scroll_target_locator = {"automation_id": "DesktopWpfScrollTargetButton"}
    plan = {
        "name": "desktop WPF complex control regression",
        "automation_type": "desktop",
        "variables": {"expected_text": expected_text},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": app_args,
                "save_as": "app_launch",
            },
            {
                "action": "command",
                "type": "run",
                "argv": [
                    sys.executable,
                    "-c",
                    "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text(str(sys.argv[2]), encoding='utf-8')",
                    absolute_pid_file,
                    "{{app_launch.pid}}",
                ],
                "timeout_ms": 10000,
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "exists",
                "timeout_ms": 10000,
                "interval_ms": 100,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "wpf-elements.json",
                "save_as": "wpf_elements",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "dump",
                "title_contains": title,
                **entry_locator,
                "path": "wpf-entry-dump.json",
                "save_as": "wpf_entry_dump",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": title,
                "path": "wpf-window-screen.png",
                "save_as": "wpf_window_capture",
            },
            {
                "action": "write",
                "type": "json",
                "path": "wpf-window-capture.json",
                "value": "{{wpf_window_capture}}",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "element",
                "title_contains": title,
                **entry_locator,
                "path": "wpf-entry-element-screen.png",
                "save_as": "wpf_entry_capture",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "write",
                "type": "json",
                "path": "wpf-entry-capture.json",
                "value": "{{wpf_entry_capture}}",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": title,
                **entry_locator,
                "value": "{{expected_text}}",
                "preserve_clipboard": False,
                "save_as": "wpf_entry_set_text",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": title,
                **entry_locator,
                "path": "wpf-entry-state.json",
                "save_as": "wpf_entry_state",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": title,
                **entry_locator,
                "state": "exists",
                "expected": "{{expected_text}}",
                "mode": "equals",
                "path": "wpf-entry-assertion.json",
                "save_as": "wpf_entry_assertion",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": title,
                **checkbox_locator,
                "save_as": "wpf_agree_click",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "select",
                "title_contains": title,
                **combo_locator,
                "option_index": 2,
                "save_as": "wpf_mode_select",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "select",
                "title_contains": title,
                **list_locator,
                "option_index": 2,
                "save_as": "wpf_options_select",
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_table",
                "title_contains": title,
                **grid_locator,
                "path": "wpf-orders-table.json",
                "save_as": "wpf_orders_table",
                "max_depth": 10,
                "max_elements": 1000,
                "max_rows": 5,
                "max_columns": 5,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "select_cell",
                "title_contains": title,
                **grid_locator,
                "row": 1,
                "column_index": 2,
                "path": "wpf-orders-cell.json",
                "save_as": "wpf_orders_cell",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_tree",
                "title_contains": title,
                **tree_locator,
                "path": "wpf-nav-tree.json",
                "save_as": "wpf_nav_tree",
                "max_depth": 10,
                "max_elements": 1000,
                "max_nodes": 80,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "expand_tree",
                "title_contains": title,
                **tree_locator,
                "tree_path": ["Settings"],
                "path": "wpf-nav-tree-expand.json",
                "save_as": "wpf_nav_tree_expand",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "select_tree",
                "title_contains": title,
                **tree_locator,
                "tree_path": ["Settings", "Accounts"],
                "path": "wpf-nav-tree-select.json",
                "save_as": "wpf_nav_tree_select",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "collapse_tree",
                "title_contains": title,
                **tree_locator,
                "tree_path": ["Settings"],
                "path": "wpf-nav-tree-collapse.json",
                "save_as": "wpf_nav_tree_collapse",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke_menu",
                "title_contains": title,
                "menu_path": ["File", "Mark Menu"],
                "path": "wpf-menu-invoke.json",
                "save_as": "wpf_menu_invoke",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke_menu",
                "title_contains": title,
                **context_panel_locator,
                "open_context_menu": True,
                "menu_path": ["Mark Context"],
                "path": "wpf-context-menu-invoke.json",
                "save_as": "wpf_context_menu_invoke",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "scroll_element",
                "title_contains": title,
                **scroll_locator,
                "scroll_to": "end",
                "path": "wpf-scroll-viewer.json",
                "save_as": "wpf_scroll_viewer",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": title,
                **scroll_target_locator,
                "path": "wpf-scroll-target-state.json",
                "save_as": "wpf_scroll_target_state",
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "save_as": "wpf_save_invoke",
                "max_depth": 8,
                "max_elements": 600,
            },
            {"action": "sleep", "seconds": 0.3},
            {
                "action": "command",
                "type": "run",
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib, sys; "
                        "content = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace'); "
                        "expected = sys.argv[2:]; "
                        "ok = all(item in content for item in expected); "
                        "raise SystemExit(0 if ok else 7)"
                    ),
                    absolute_assertion_file,
                    "{{expected_text}}",
                    "agree=True",
                    "mode=Audit",
                    "option=Green",
                    "menu_marked=True",
                    "context_marked=True",
                ],
                "timeout_ms": 10000,
                "save_as": "wpf_content_assertion",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "save_as": "wpf_app_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "save_as": "wpf_app_closed",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    cleanup_hint = f"temporary WPF app title={title}; pid file={absolute_pid_file}"
    return plan, assertion_file, cleanup_hint


def _windows_powershell_executable() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or ""


def _windows_wpf_skip_reason(system: str | None = None) -> str:
    resolved_system = system or platform.system()
    if resolved_system != "Windows":
        return f"WPF regression only runs on Windows, current={resolved_system}"
    powershell = _windows_powershell_executable()
    if not powershell:
        return "PowerShell is unavailable; WPF regression cannot run."
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-Sta",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Add-Type -AssemblyName PresentationFramework; "
                "Add-Type -AssemblyName PresentationCore; "
                "Add-Type -AssemblyName WindowsBase; "
                "'ok'",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as error:
        return f"WPF runtime probe failed: {error}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return f"WPF runtime is unavailable: {detail[:300]}"
    return ""


def _windows_wpf_script(title: str, output_path: str) -> str:
    script = r"""
$Title = __TITLE__
$OutputPath = __OUTPUT_PATH__
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Xaml
Add-Type -AssemblyName System.Data

[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Width="1060" Height="760" Left="140" Top="140"
        WindowStartupLocation="Manual">
  <DockPanel>
    <Menu DockPanel.Dock="Top" AutomationProperties.AutomationId="DesktopWpfMainMenu">
      <MenuItem Header="File" AutomationProperties.AutomationId="DesktopWpfFileMenu">
        <MenuItem x:Name="MarkMenuItem" Header="Mark Menu" AutomationProperties.AutomationId="DesktopWpfMarkMenu" />
      </MenuItem>
    </Menu>
    <Grid Margin="12">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="330" />
        <ColumnDefinition Width="350" />
        <ColumnDefinition Width="*" />
      </Grid.ColumnDefinitions>
      <Grid.RowDefinitions>
        <RowDefinition Height="Auto" />
        <RowDefinition Height="Auto" />
        <RowDefinition Height="220" />
        <RowDefinition Height="*" />
      </Grid.RowDefinitions>
      <TextBlock Grid.Row="0" Grid.Column="0" Text="Input" Margin="0,0,0,4" />
      <TextBox x:Name="InputBox" Grid.Row="1" Grid.Column="0" Width="280" Height="30"
               AutomationProperties.AutomationId="DesktopWpfTextBox" />
      <Button x:Name="SaveButton" Grid.Row="1" Grid.Column="1" Width="150" Height="32" HorizontalAlignment="Left"
              Content="Save WPF State" AutomationProperties.AutomationId="DesktopWpfSaveButton" />
      <CheckBox x:Name="AgreeCheck" Grid.Row="1" Grid.Column="2" Width="180" Height="30" Content="Agree"
                AutomationProperties.AutomationId="DesktopWpfAgreeCheckBox" />
      <ComboBox x:Name="ModeCombo" Grid.Row="2" Grid.Column="0" Width="220" Height="32" VerticalAlignment="Top"
                AutomationProperties.AutomationId="DesktopWpfModeCombo">
        <ComboBoxItem Content="Draft" />
        <ComboBoxItem Content="Review" />
        <ComboBoxItem Content="Audit" />
      </ComboBox>
      <ListBox x:Name="OptionsList" Grid.Row="2" Grid.Column="0" Width="220" Height="110" Margin="0,48,0,0"
               AutomationProperties.AutomationId="DesktopWpfOptionsList">
        <ListBoxItem Content="Red" />
        <ListBoxItem Content="Blue" />
        <ListBoxItem Content="Green" />
      </ListBox>
      <DataGrid x:Name="OrdersGrid" Grid.Row="2" Grid.Column="1" Width="320" Height="170"
                AutomationProperties.AutomationId="DesktopWpfOrdersGrid"
                AutoGenerateColumns="False" IsReadOnly="True"
                EnableRowVirtualization="False" EnableColumnVirtualization="False">
        <DataGrid.Columns>
          <DataGridTextColumn Header="ID" Binding="{Binding ID}" />
          <DataGridTextColumn Header="Name" Binding="{Binding Name}" />
          <DataGridTextColumn Header="Status" Binding="{Binding Status}" />
        </DataGrid.Columns>
      </DataGrid>
      <TreeView x:Name="NavTree" Grid.Row="2" Grid.Column="2" Width="260" Height="170" HorizontalAlignment="Left"
                AutomationProperties.AutomationId="DesktopWpfNavTree">
        <TreeViewItem Header="Settings" IsExpanded="True">
          <TreeViewItem Header="Accounts" />
          <TreeViewItem Header="Security" />
        </TreeViewItem>
        <TreeViewItem Header="Reports" IsExpanded="True">
          <TreeViewItem Header="Monthly" />
        </TreeViewItem>
      </TreeView>
      <Button x:Name="ContextPanel" Grid.Row="3" Grid.Column="0" Width="260" Height="120"
              HorizontalAlignment="Left" VerticalAlignment="Top" Margin="0,20,0,0"
              Content="Context Target"
              AutomationProperties.AutomationId="DesktopWpfContextPanel">
        <Button.ContextMenu>
          <ContextMenu>
            <MenuItem Header="Mark Context" AutomationProperties.AutomationId="DesktopWpfMarkContext" />
          </ContextMenu>
        </Button.ContextMenu>
      </Button>
      <ScrollViewer x:Name="ScrollViewer" Grid.Row="3" Grid.Column="1" Width="300" Height="160"
                    VerticalScrollBarVisibility="Auto"
                    AutomationProperties.AutomationId="DesktopWpfScrollViewer">
        <StackPanel Height="520">
          <TextBlock Text="Scroll Area" Margin="12" />
          <Button Content="Far Scroll Target" Width="190" Height="34" Margin="12,390,12,12"
                  AutomationProperties.AutomationId="DesktopWpfScrollTargetButton" />
        </StackPanel>
      </ScrollViewer>
      <TextBlock x:Name="StatusText" Grid.Row="3" Grid.Column="2" Width="300" Height="120"
                 TextWrapping="Wrap" Text="Ready"
                 AutomationProperties.AutomationId="DesktopWpfStatusText" />
    </Grid>
  </DockPanel>
</Window>
'@

$reader = New-Object System.Xml.XmlNodeReader($xaml)
$window = [Windows.Markup.XamlReader]::Load($reader)
$window.Title = $Title
$inputBox = $window.FindName('InputBox')
$saveButton = $window.FindName('SaveButton')
$agreeCheck = $window.FindName('AgreeCheck')
$modeCombo = $window.FindName('ModeCombo')
$optionsList = $window.FindName('OptionsList')
$ordersGrid = $window.FindName('OrdersGrid')
$navTree = $window.FindName('NavTree')
$markMenuItem = $window.FindName('MarkMenuItem')
$contextPanel = $window.FindName('ContextPanel')
$scrollViewer = $window.FindName('ScrollViewer')
$statusText = $window.FindName('StatusText')

$rows = New-Object System.Collections.ArrayList
[void]$rows.Add([pscustomobject]@{ ID = '100'; Name = 'Alpha'; Status = 'Open' })
[void]$rows.Add([pscustomobject]@{ ID = '200'; Name = 'Beta'; Status = 'Review' })
[void]$rows.Add([pscustomobject]@{ ID = '300'; Name = 'Gamma'; Status = 'Closed' })
$ordersGrid.ItemsSource = $rows
$ordersGrid.SelectedIndex = 0
$modeCombo.SelectedIndex = 0
$optionsList.SelectedIndex = 0
$script:menuMarked = $false
$script:contextMarked = $false
$script:selectedTree = ''

$markMenuItem.Add_Click({
    $script:menuMarked = $true
})
$contextPanel.ContextMenu.Items[0].Add_Click({
    $script:contextMarked = $true
})
$navTree.Add_SelectedItemChanged({
    param($sender, $eventArgs)
    if ($eventArgs.NewValue -ne $null -and $eventArgs.NewValue.Header -ne $null) {
        $script:selectedTree = $eventArgs.NewValue.Header.ToString()
    }
})
$saveButton.Add_Click({
    $modeText = ''
    if ($modeCombo.SelectedItem -ne $null -and $modeCombo.SelectedItem.Content -ne $null) {
        $modeText = $modeCombo.SelectedItem.Content.ToString()
    }
    $optionText = ''
    if ($optionsList.SelectedItem -ne $null -and $optionsList.SelectedItem.Content -ne $null) {
        $optionText = $optionsList.SelectedItem.Content.ToString()
    }
    $selectedOrder = $ordersGrid.SelectedItem
    $gridCell = ''
    if ($selectedOrder -ne $null) {
        $gridCell = "$($selectedOrder.Name):$($selectedOrder.Status)"
    }
    $payload = "$($inputBox.Text)`nagree=$($agreeCheck.IsChecked)`nmode=$modeText`noption=$optionText`ngrid_cell=$gridCell`ntree_path=$script:selectedTree`nmenu_marked=$script:menuMarked`ncontext_marked=$script:contextMarked`nscroll_value=$($scrollViewer.VerticalOffset)"
    [System.IO.File]::WriteAllText($OutputPath, $payload, [System.Text.Encoding]::UTF8)
    $statusText.Text = "Saved: $($inputBox.Text)"
})

[void]$window.ShowDialog()
""".strip()
    return script.replace("__TITLE__", _powershell_string(title)).replace("__OUTPUT_PATH__", _powershell_string(output_path))


def _windows_file_dialog_form_script(
    *,
    title: str,
    result_path: str,
    open_initial_directory: str,
    save_initial_directory: str,
    save_payload: str,
) -> str:
    open_dialog_title = "AI Automate Open File Dialog"
    save_dialog_title = "AI Automate Save File Dialog"
    return f"""
$ResultPath = {_powershell_string(result_path)}
$OpenInitialDirectory = {_powershell_string(open_initial_directory)}
$SaveInitialDirectory = {_powershell_string(save_initial_directory)}
$SavePayload = {_powershell_string(save_payload)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($ResultPath))
[System.IO.File]::WriteAllText($ResultPath, '', [System.Text.Encoding]::UTF8)
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 660
$form.Height = 260
$form.StartPosition = 'Manual'
$form.Left = 160
$form.Top = 160
$form.KeyPreview = $true
$form.TopMost = $true
$openButton = New-Object System.Windows.Forms.Button
$openButton.Name = 'DesktopFileDialogOpenButton'
$openButton.Text = 'Open File'
$openButton.Left = 24
$openButton.Top = 28
$openButton.Width = 160
$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Name = 'DesktopFileDialogSaveButton'
$saveButton.Text = 'Save File'
$saveButton.Left = 208
$saveButton.Top = 28
$saveButton.Width = 160
$status = New-Object System.Windows.Forms.Label
$status.Name = 'DesktopFileDialogStatus'
$status.AutoSize = $true
$status.Left = 24
$status.Top = 94
$status.Width = 580
$status.Text = 'Ready'
function Append-DialogResult {{
    param([string]$Line)
    [System.IO.File]::AppendAllText($ResultPath, $Line + [Environment]::NewLine, [System.Text.Encoding]::UTF8)
}}
$openButton.Add_Click({{
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = {_powershell_string(open_dialog_title)}
    $dialog.InitialDirectory = $OpenInitialDirectory
    $dialog.Filter = 'Text files (*.txt)|*.txt|All files (*.*)|*.*'
    $dialog.CheckFileExists = $true
    $dialog.Multiselect = $false
    if ($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {{
        $selectedPath = $dialog.FileName
        $content = [System.IO.File]::ReadAllText($selectedPath, [System.Text.Encoding]::UTF8)
        Append-DialogResult "open_path=$selectedPath"
        Append-DialogResult "open_content=$content"
        $status.Text = "Opened: $content"
    }} else {{
        Append-DialogResult 'open_cancelled=true'
        $status.Text = 'Open cancelled'
    }}
}})
$saveButton.Add_Click({{
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Title = {_powershell_string(save_dialog_title)}
    $dialog.InitialDirectory = $SaveInitialDirectory
    $dialog.FileName = 'desktop-file-dialog-save.txt'
    $dialog.Filter = 'Text files (*.txt)|*.txt|All files (*.*)|*.*'
    $dialog.AddExtension = $false
    $dialog.OverwritePrompt = $false
    if ($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {{
        $selectedPath = $dialog.FileName
        [System.IO.File]::WriteAllText($selectedPath, $SavePayload, [System.Text.Encoding]::UTF8)
        Append-DialogResult "save_path=$selectedPath"
        Append-DialogResult "save_content=$SavePayload"
        $status.Text = "Saved: $SavePayload"
    }} else {{
        Append-DialogResult 'save_cancelled=true'
        $status.Text = 'Save cancelled'
    }}
}})
[void]$form.Controls.Add($openButton)
[void]$form.Controls.Add($saveButton)
[void]$form.Controls.Add($status)
$form.Add_KeyDown({{
    param($sender, $eventArgs)
    if ($eventArgs.Control -and $eventArgs.KeyCode -eq [System.Windows.Forms.Keys]::O) {{
        $eventArgs.SuppressKeyPress = $true
        $openButton.PerformClick()
    }} elseif ($eventArgs.Control -and $eventArgs.KeyCode -eq [System.Windows.Forms.Keys]::S) {{
        $eventArgs.SuppressKeyPress = $true
        $saveButton.PerformClick()
    }}
}})
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _windows_forms_script(title: str, output_path: str) -> str:
    return f"""
$OutputPath = {_powershell_string(output_path)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 1040
$form.Height = 760
$form.StartPosition = 'Manual'
$form.Left = 120
$form.Top = 120
$menuState = @{{
    marked = $false
}}
$contextMenuState = @{{
    marked = $false
}}
$menuStrip = New-Object System.Windows.Forms.MenuStrip
$fileMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$fileMenu.Name = 'DesktopElementFileMenu'
$fileMenu.Text = 'File'
$markMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$markMenu.Name = 'DesktopElementMarkMenuItem'
$markMenu.Text = 'Mark Menu'
[void]$fileMenu.DropDownItems.Add($markMenu)
[void]$menuStrip.Items.Add($fileMenu)
$form.MainMenuStrip = $menuStrip
$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$contextMarkMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$contextMarkMenu.Name = 'DesktopElementContextMarkMenuItem'
$contextMarkMenu.Text = 'Mark Context'
[void]$contextMenu.Items.Add($contextMarkMenu)
$label = New-Object System.Windows.Forms.Label
$label.Text = 'Value'
$label.AutoSize = $true
$label.Left = 20
$label.Top = 20
$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Name = 'DesktopElementTextBox'
$textBox.Left = 20
$textBox.Top = 48
$textBox.Width = 470
$checkBox = New-Object System.Windows.Forms.CheckBox
$checkBox.Name = 'DesktopElementAgreeCheckBox'
$checkBox.Text = 'Agree to desktop automation'
$checkBox.Left = 20
$checkBox.Top = 82
$checkBox.Width = 240
$combo = New-Object System.Windows.Forms.ComboBox
$combo.Name = 'DesktopElementModeCombo'
$combo.Left = 280
$combo.Top = 80
$combo.Width = 180
$combo.DropDownStyle = 'DropDownList'
[void]$combo.Items.Add('Standard')
[void]$combo.Items.Add('Advanced')
[void]$combo.Items.Add('Audit')
$combo.SelectedIndex = 1
$listBox = New-Object System.Windows.Forms.ListBox
$listBox.Name = 'DesktopElementOptionsList'
$listBox.Left = 20
$listBox.Top = 118
$listBox.Width = 180
$listBox.Height = 72
[void]$listBox.Items.Add('Red')
[void]$listBox.Items.Add('Blue')
[void]$listBox.Items.Add('Green')
$listBox.SelectedIndex = 1
$mouse = @{{
    double_click = $false
    right_click = $false
    scroll = $false
    drag = $false
    dragging = $false
    start_x = 0
    start_y = 0
    last_left_up_ms = 0
}}
$mousePanel = New-Object System.Windows.Forms.Panel
$mousePanel.Name = 'DesktopElementMousePanel'
$mousePanel.Left = 300
$mousePanel.Top = 118
$mousePanel.Width = 320
$mousePanel.Height = 170
$mousePanel.TabStop = $true
$mousePanel.BackColor = [System.Drawing.Color]::FromArgb(238, 244, 255)
$mouseLabel = New-Object System.Windows.Forms.Label
$mouseLabel.Text = 'Mouse Surface'
$mouseLabel.AutoSize = $true
$mouseLabel.Left = 12
$mouseLabel.Top = 12
[void]$mousePanel.Controls.Add($mouseLabel)
$contextPanel = New-Object System.Windows.Forms.Panel
$contextPanel.Name = 'DesktopElementContextPanel'
$contextPanel.AccessibleName = 'DesktopElementContextPanel'
$contextPanel.Left = 510
$contextPanel.Top = 48
$contextPanel.Width = 170
$contextPanel.Height = 44
$contextPanel.TabStop = $true
$contextPanel.BackColor = [System.Drawing.Color]::FromArgb(245, 247, 232)
$contextPanel.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$contextPanel.ContextMenuStrip = $contextMenu
$contextLabel = New-Object System.Windows.Forms.Label
$contextLabel.Text = 'Context Menu'
$contextLabel.Dock = 'Fill'
$contextLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$contextLabel.ContextMenuStrip = $contextMenu
[void]$contextPanel.Controls.Add($contextLabel)
$button = New-Object System.Windows.Forms.Button
$button.Name = 'DesktopElementSaveButton'
$button.Text = 'Save'
$button.Left = 220
$button.Top = 122
$button.Width = 100
$grid = New-Object System.Windows.Forms.DataGridView
$grid.Name = 'DesktopElementOrdersGrid'
$grid.AccessibleName = 'DesktopElementOrdersGrid'
$grid.Left = 20
$grid.Top = 310
$grid.Width = 680
$grid.Height = 145
$grid.ReadOnly = $true
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.AllowUserToResizeRows = $false
$grid.RowHeadersVisible = $false
$grid.MultiSelect = $false
$grid.SelectionMode = [System.Windows.Forms.DataGridViewSelectionMode]::CellSelect
[void]$grid.Columns.Add('OrderId', 'ID')
[void]$grid.Columns.Add('OrderName', 'Name')
[void]$grid.Columns.Add('OrderStatus', 'Status')
[void]$grid.Rows.Add('A-100', 'Alpha', 'Ready')
[void]$grid.Rows.Add('B-200', 'Beta', 'Review')
[void]$grid.Rows.Add('C-300', 'Gamma', 'Done')
$grid.CurrentCell = $grid.Rows[0].Cells[0]
$tree = New-Object System.Windows.Forms.TreeView
$tree.Name = 'DesktopElementNavTree'
$tree.AccessibleName = 'DesktopElementNavTree'
$tree.Left = 720
$tree.Top = 48
$tree.Width = 280
$tree.Height = 180
$settingsNode = New-Object System.Windows.Forms.TreeNode('Settings')
[void]$settingsNode.Nodes.Add('Accounts')
[void]$settingsNode.Nodes.Add('Security')
$reportsNode = New-Object System.Windows.Forms.TreeNode('Reports')
[void]$reportsNode.Nodes.Add('Monthly')
[void]$tree.Nodes.Add($settingsNode)
[void]$tree.Nodes.Add($reportsNode)
$tree.ExpandAll()
$scrollPanel = New-Object System.Windows.Forms.Panel
$scrollPanel.Name = 'DesktopElementScrollPanel'
$scrollPanel.AccessibleName = 'DesktopElementScrollPanel'
$scrollPanel.Left = 720
$scrollPanel.Top = 250
$scrollPanel.Width = 280
$scrollPanel.Height = 210
$scrollPanel.AutoScroll = $true
$scrollPanel.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$scrollPanel.AutoScrollMinSize = New-Object System.Drawing.Size(240, 520)
$scrollLabel = New-Object System.Windows.Forms.Label
$scrollLabel.Text = 'Scroll Area'
$scrollLabel.AutoSize = $true
$scrollLabel.Left = 12
$scrollLabel.Top = 12
$scrollTarget = New-Object System.Windows.Forms.Button
$scrollTarget.Name = 'DesktopElementScrollTargetButton'
$scrollTarget.AccessibleName = 'DesktopElementScrollTargetButton'
$scrollTarget.Text = 'Scroll Target'
$scrollTarget.Left = 24
$scrollTarget.Top = 430
$scrollTarget.Width = 180
$scrollTarget.Height = 32
[void]$scrollPanel.Controls.Add($scrollLabel)
[void]$scrollPanel.Controls.Add($scrollTarget)
$status = New-Object System.Windows.Forms.Label
$status.Name = 'DesktopElementStatus'
$status.AutoSize = $true
$status.Left = 20
$status.Top = 650
$status.Width = 980
function Write-RegressionPayload {{
    $optionText = ''
    if ($null -ne $listBox.SelectedItem) {{ $optionText = [string]$listBox.SelectedItem }}
    $gridCell = ''
    if ($null -ne $grid.CurrentCell) {{ $gridCell = [string]$grid.CurrentCell.Value }}
    $treePath = ''
    if ($null -ne $tree.SelectedNode) {{ $treePath = $tree.SelectedNode.FullPath -replace '\\', '/' }}
    $payload = "$($textBox.Text)`nagree=$($checkBox.Checked)`nmode=$($combo.Text)`noption=$optionText`ngrid_cell=$gridCell`ntree_path=$treePath`nmenu_marked=$($menuState['marked'])`ncontext_marked=$($contextMenuState['marked'])`nscroll_value=$($scrollPanel.VerticalScroll.Value)`nmouse_double_click=$($mouse['double_click'])`nmouse_right_click=$($mouse['right_click'])`nmouse_scroll=$($mouse['scroll'])`nmouse_drag=$($mouse['drag'])"
    [System.IO.File]::WriteAllText($OutputPath, $payload, [System.Text.Encoding]::UTF8)
    $status.Text = "Saved: $($textBox.Text) | agree=$($checkBox.Checked) | mode=$($combo.Text) | option=$optionText | grid=$gridCell | tree=$treePath | menu=$($menuState['marked'])/$($contextMenuState['marked']) | mouse=$($mouse['double_click'])/$($mouse['right_click'])/$($mouse['scroll'])/$($mouse['drag'])"
}}
$markMenu.Add_Click({{
    $menuState['marked'] = $true
    Write-RegressionPayload
}})
$contextMarkMenu.Add_Click({{
    $contextMenuState['marked'] = $true
    Write-RegressionPayload
}})
$tree.Add_AfterSelect({{
    Write-RegressionPayload
}})
$button.Add_Click({{
    Write-RegressionPayload
}})
$mousePanel.Add_Click({{
    $mousePanel.Focus()
}})
$contextPanel.Add_Click({{
    $contextPanel.Focus()
}})
$mousePanel.Add_MouseDoubleClick({{
    $mouse['double_click'] = $true
    Write-RegressionPayload
}})
$mousePanel.Add_MouseDown({{
    $mousePanel.Focus()
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {{
        $mouse['dragging'] = $true
        $mouse['start_x'] = $_.X
        $mouse['start_y'] = $_.Y
    }}
}})
$mousePanel.Add_MouseMove({{
    if ($mouse['dragging']) {{
        $dx = [Math]::Abs($_.X - [int]$mouse['start_x'])
        $dy = [Math]::Abs($_.Y - [int]$mouse['start_y'])
        if (($dx + $dy) -ge 8) {{
            $mouse['drag'] = $true
        }}
    }}
}})
$mousePanel.Add_MouseUp({{
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {{
        $now_ms = [Environment]::TickCount64
        $previous_ms = [int64]$mouse['last_left_up_ms']
        if ($previous_ms -gt 0 -and ($now_ms - $previous_ms) -le 700) {{
            $mouse['double_click'] = $true
        }}
        if ($mouse['dragging']) {{
            $dx = [Math]::Abs($_.X - [int]$mouse['start_x'])
            $dy = [Math]::Abs($_.Y - [int]$mouse['start_y'])
            if (($dx + $dy) -ge 8) {{
                $mouse['drag'] = $true
            }}
        }}
        $mouse['last_left_up_ms'] = $now_ms
    }}
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Right) {{
        $mouse['right_click'] = $true
    }}
    if ($mouse['dragging']) {{
        $mouse['dragging'] = $false
    }}
    Write-RegressionPayload
}})
$mousePanel.Add_MouseWheel({{
    $mouse['scroll'] = $true
    Write-RegressionPayload
}})
$form.Add_MouseWheel({{
    $mouse['scroll'] = $true
    Write-RegressionPayload
}})
[void]$form.Controls.Add($label)
[void]$form.Controls.Add($textBox)
[void]$form.Controls.Add($checkBox)
[void]$form.Controls.Add($combo)
[void]$form.Controls.Add($listBox)
[void]$form.Controls.Add($mousePanel)
[void]$form.Controls.Add($contextPanel)
[void]$form.Controls.Add($button)
[void]$form.Controls.Add($grid)
[void]$form.Controls.Add($tree)
[void]$form.Controls.Add($scrollPanel)
[void]$form.Controls.Add($menuStrip)
[void]$form.Controls.Add($status)
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _powershell_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _windows_controlled_editor_plan(package_dir: Path) -> tuple[dict[str, Any], Path, str]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Desktop Real App {suffix}"
    expected_text = "desktop automation regression input"
    assertion_file = Path("resources") / f"desktop-real-app-input-{suffix}.txt"
    pid_file = Path("resources") / "desktop-app-pid.txt"
    absolute_assertion_file = str((package_dir / assertion_file).resolve())
    absolute_pid_file = str((package_dir / pid_file).resolve())
    powershell = _windows_powershell_executable()
    if not powershell:
        raise RuntimeError("PowerShell is required for the Windows desktop real app regression.")
    app_args = [
        "-NoProfile",
        "-Sta",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _windows_controlled_editor_script(title, absolute_assertion_file),
    ]
    textbox_locator = {"automation_id": "DesktopRealAppTextBox", "control_type": "Edit"}
    button_locator = {"automation_id": "DesktopRealAppSaveButton", "control_type": "Button"}
    plan = {
        "name": "desktop controlled editor regression",
        "automation_type": "desktop",
        "variables": {"expected_text": expected_text, "window_title": title},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "command",
                "type": "run",
                "command": (
                    f"$file = {_powershell_string(absolute_assertion_file)}; "
                    "Set-Content -LiteralPath $file -Value ''; "
                    "Write-Output $file"
                ),
                "timeout_ms": 10000,
                "save_as": "app_file_created",
            },
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": app_args,
                "title_contains": title,
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 8000,
                "interval_ms": 100,
                "save_as": "app_launch",
            },
            {
                "action": "command",
                "type": "run",
                "command": "Set-Content -LiteralPath 'resources\\\\desktop-app-pid.txt' -Value '{{app_launch.pid}}'",
                "timeout_ms": 10000,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "active",
                "path": "real-app-active-window.json",
                "save_as": "active_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "title_contains": title,
                "path": "real-app-window-find.json",
                "save_as": "found_window",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "exists",
                "timeout_ms": 8000,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": title,
                "timeout_ms": 2000,
                "save_as": "app_focused_assertion",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "maximize",
                "title_contains": title,
                "save_as": "app_maximize",
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": title,
                "path": "real-app-maximized-window.png",
                "save_as": "app_maximized_screenshot",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "minimize",
                "title_contains": title,
                "save_as": "app_minimize",
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "restore",
                "title_contains": title,
                "save_as": "app_restore",
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_refocus_after_restore",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": title,
                "timeout_ms": 2000,
                "save_as": "app_restored_focused_assertion",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "active",
                "path": "real-app-restored-active-window.json",
                "save_as": "restored_active_window",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "real-app-elements.json",
                "save_as": "app_elements",
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "title_contains": title,
                **textbox_locator,
                "save_as": "app_textbox_element",
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": title,
                **textbox_locator,
                "save_as": "app_textbox_state",
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": title,
                **textbox_locator,
                "value": "{{expected_text}}",
                "save_as": "app_textbox_set_text",
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "save_as": "app_save_invoke",
                "max_depth": 4,
            },
            {"action": "sleep", "seconds": 0.2},
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
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "save_as": "app_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "save_as": "app_closed",
            },
            {
                "action": "command",
                "type": "run",
                "command": (
                    f"$content = Get-Content -Raw -LiteralPath 'resources\\\\{assertion_file.name}'; "
                    "if ($content -notlike '*{{expected_text}}*') { "
                    "Write-Error ('typed text missing: ' + $content); exit 7 }"
                ),
                "timeout_ms": 10000,
                "save_as": "content_assertion",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, assertion_file, f"temporary WinForms real app title={title}; pid file={absolute_pid_file}"


def _windows_controlled_editor_script(title: str, output_path: str) -> str:
    return f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$outputPath = {_powershell_string(output_path)}
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 720
$form.Height = 420
$form.StartPosition = 'CenterScreen'
$form.KeyPreview = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = 'Value'
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(20, 20)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Name = 'DesktopRealAppTextBox'
$textBox.Multiline = $true
$textBox.AcceptsReturn = $true
$textBox.ScrollBars = 'Vertical'
$textBox.Location = New-Object System.Drawing.Point(20, 50)
$textBox.Size = New-Object System.Drawing.Size(660, 230)

$save = New-Object System.Windows.Forms.Button
$save.Name = 'DesktopRealAppSaveButton'
$save.Text = 'Save'
$save.Location = New-Object System.Drawing.Point(20, 300)
$save.Size = New-Object System.Drawing.Size(100, 34)

$status = New-Object System.Windows.Forms.Label
$status.Name = 'DesktopRealAppStatus'
$status.Text = 'Ready'
$status.AutoSize = $true
$status.Location = New-Object System.Drawing.Point(140, 308)

$save.Add_Click({{
    [System.IO.File]::WriteAllText($outputPath, $textBox.Text, [System.Text.Encoding]::UTF8)
    $status.Text = 'Saved ' + $textBox.Text.Length + ' chars'
}})
$form.Add_Shown({{ $form.Activate(); $textBox.Focus() }})

[void]$form.Controls.Add($label)
[void]$form.Controls.Add($textBox)
[void]$form.Controls.Add($save)
[void]$form.Controls.Add($status)
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _windows_explorer_plan(target_dir: Path, folder_name: str) -> dict[str, Any]:
    absolute_target_dir = str(target_dir.resolve())
    return {
        "name": "desktop explorer regression",
        "automation_type": "desktop",
        "variables": {"folder_name": folder_name},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "profile": "explorer",
                "app": "explorer.exe",
                "args": [absolute_target_dir],
                "title_contains": "{{folder_name}}",
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 7000,
                "interval_ms": 150,
                "save_as": "explorer_launch",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "state": "exists",
                "timeout_ms": 7000,
                "interval_ms": 150,
                "save_as": "explorer_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "save_as": "explorer_focus",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "state": "focused",
                "timeout_ms": 3000,
                "interval_ms": 100,
                "save_as": "explorer_focused",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "list",
                "path": "explorer-windows.json",
                "save_as": "explorer_windows",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "path": "explorer-window-find.json",
                "save_as": "explorer_found_window",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "path": "explorer-elements.json",
                "save_as": "explorer_elements",
                "max_depth": 4,
                "max_elements": 300,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "name_contains": "sample.txt",
                "path": "explorer-sample-file.json",
                "save_as": "explorer_sample_file",
                "max_depth": 6,
                "max_elements": 500,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "explorer-screen.png",
                "save_as": "explorer_screen",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "explorer-screen.png",
                "min_bytes": 1,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "save_as": "explorer_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "state": "not_exists",
                "timeout_ms": 5000,
                "interval_ms": 150,
                "save_as": "explorer_closed",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }


def _windows_terminal_plan(
    *,
    powershell: str,
    package_dir: Path,
    title: str,
    result_file: Path,
    expected_text: str,
) -> dict[str, Any]:
    pid_file = package_dir / "resources" / "desktop-terminal-pid.txt"
    terminal_bootstrap = (
        f"$host.UI.RawUI.WindowTitle = {_powershell_string(title)}; "
        f"Set-Location -LiteralPath {_powershell_string(str((package_dir / 'resources').resolve()))}; "
        "Write-Host 'AI Automate terminal regression ready'"
    )
    encoded_bootstrap = base64.b64encode(terminal_bootstrap.encode("utf-16le")).decode("ascii")
    launcher_script = (
        "$childArgs = @('-NoLogo', '-NoExit', '-EncodedCommand', "
        f"{_powershell_string(encoded_bootstrap)}); "
        f"$process = Start-Process -FilePath {_powershell_string(powershell)} "
        "-ArgumentList $childArgs -PassThru -WindowStyle Normal; "
        f"Set-Content -LiteralPath {_powershell_string(str(pid_file.resolve()))} -Value $process.Id"
    )
    typed_command = (
        "Set-Content -LiteralPath '{{result_file}}' -Value '{{expected_text}}'; "
        "exit"
    )
    return {
        "name": "desktop Windows terminal regression",
        "automation_type": "desktop",
        "variables": {
            "terminal_title": title,
            "result_file": str(result_file.resolve()),
            "expected_text": expected_text,
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "path": powershell,
                "args": ["-NoProfile", "-Command", launcher_script],
                "wait": True,
                "timeout_ms": 10000,
                "title_contains": "{{terminal_title}}",
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 10000,
                "interval_ms": 150,
                "save_as": "terminal_launch",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "title_contains": "{{terminal_title}}",
                "path": "terminal-window-find.json",
                "save_as": "terminal_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "active",
                "path": "terminal-active-window.json",
                "save_as": "terminal_active",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{terminal_title}}",
                "state": "focused",
                "timeout_ms": 3000,
                "interval_ms": 100,
                "save_as": "terminal_focused",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": "{{terminal_title}}",
                "path": "terminal-window.png",
                "save_as": "terminal_screenshot",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "current_window_center",
                "save_as": "terminal_click",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": typed_command,
                "method": "clipboard",
                "preserve_clipboard": False,
                "save_as": "terminal_command_typed",
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["enter"]},
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{terminal_title}}",
                "state": "not_exists",
                "timeout_ms": 10000,
                "interval_ms": 150,
                "save_as": "terminal_closed",
            },
            {
                "action": "command",
                "type": "run",
                "command": (
                    "$content = Get-Content -Raw -LiteralPath '{{result_file}}'; "
                    "if ($content -notlike '*{{expected_text}}*') { "
                    "Write-Error ('terminal output missing: ' + $content); exit 9 }"
                ),
                "timeout_ms": 10000,
                "save_as": "terminal_result_assertion",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }


def _windows_file_dialog_plan(
    *,
    powershell: str,
    package_dir: Path,
    input_file: Path,
    save_file: Path,
    result_file: Path,
    expected_open_text: str,
    expected_save_text: str,
) -> dict[str, Any]:
    title = "AI Automate Desktop File Dialog Form"
    open_dialog_title = "AI Automate Open File Dialog"
    save_dialog_title = "AI Automate Save File Dialog"
    pid_file = package_dir / "resources" / "desktop-file-dialog-pid.txt"
    absolute_input_file = str(input_file.resolve())
    absolute_save_file = str(save_file.resolve())
    absolute_result_file = str(result_file.resolve())
    absolute_pid_file = str(pid_file.resolve())
    app_args = [
        "-NoProfile",
        "-Sta",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _windows_file_dialog_form_script(
            title=title,
            result_path=absolute_result_file,
            open_initial_directory=str(input_file.parent.resolve()),
            save_initial_directory=str(save_file.parent.resolve()),
            save_payload=expected_save_text,
        ),
    ]
    return {
        "name": "desktop Windows file dialog regression",
        "automation_type": "desktop",
        "variables": {
            "input_file": absolute_input_file,
            "save_file": absolute_save_file,
            "result_file": absolute_result_file,
            "expected_open_text": expected_open_text,
            "expected_save_text": expected_save_text,
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": app_args,
                "save_as": "app_launch",
            },
            {
                "action": "command",
                "type": "run",
                "argv": [
                    sys.executable,
                    "-c",
                    "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text(str(sys.argv[2]), encoding='utf-8')",
                    absolute_pid_file,
                    "{{app_launch.pid}}",
                ],
                "timeout_ms": 10000,
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "exists",
                "timeout_ms": 8000,
                "interval_ms": 100,
                "save_as": "app_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_focus",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "save_as": "app_focus_click",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "file-dialog-form-elements.json",
                "save_as": "form_elements",
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_refocus_before_open",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "save_as": "app_focus_click_before_open",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["ctrl", "o"],
                "save_as": "open_button_click",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "state": "exists",
                "timeout_ms": 8000,
                "interval_ms": 100,
                "save_as": "open_dialog_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "save_as": "open_dialog_focus",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "path": "open-dialog-elements.json",
                "save_as": "open_dialog_elements",
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "path": "open-dialog-screen.png",
                "save_as": "open_dialog_screen",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{input_file}}",
                "method": "clipboard",
                "preserve_clipboard": False,
                "save_as": "open_dialog_path_typed",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["enter"],
                "save_as": "open_dialog_accept",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "state": "not_exists",
                "timeout_ms": 5000,
                "interval_ms": 100,
                "save_as": "open_dialog_closed",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": title,
                "automation_id": "DesktopFileDialogStatus",
                "control_type": "Text",
                "state": "exists",
                "expected": "Opened: {{expected_open_text}}",
                "mode": "contains",
                "path": "file-dialog-open-status.json",
                "save_as": "open_status_assertion",
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "save_as": "app_refocus_before_save",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "save_as": "app_focus_click_before_save",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["ctrl", "s"],
                "save_as": "save_button_click",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "state": "exists",
                "timeout_ms": 8000,
                "interval_ms": 100,
                "save_as": "save_dialog_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "save_as": "save_dialog_focus",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "path": "save-dialog-elements.json",
                "save_as": "save_dialog_elements",
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "path": "save-dialog-screen.png",
                "save_as": "save_dialog_screen",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{save_file}}",
                "method": "clipboard",
                "preserve_clipboard": False,
                "save_as": "save_dialog_path_typed",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["enter"],
                "save_as": "save_dialog_accept",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "state": "not_exists",
                "timeout_ms": 5000,
                "interval_ms": 100,
                "save_as": "save_dialog_closed",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": title,
                "automation_id": "DesktopFileDialogStatus",
                "control_type": "Text",
                "state": "exists",
                "expected": "Saved: {{expected_save_text}}",
                "mode": "contains",
                "path": "file-dialog-save-status.json",
                "save_as": "save_status_assertion",
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "file-dialog-final-screen.png",
                "save_as": "file_dialog_screenshot",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "save_as": "app_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "save_as": "app_closed",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }


def _macos_textedit_plan(package_dir: Path) -> tuple[dict[str, Any], Path, str]:
    file_name = "desktop-textedit-input.txt"
    expected_text = "desktop automation regression input"
    assertion_file = Path("resources") / file_name
    absolute_assertion_file = str((package_dir / assertion_file).resolve())
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
                    f"file=\"{absolute_assertion_file}\"; "
                    ": > \"$file\"; "
                    "printf '%s\\n' \"$file\""
                ),
                "timeout_ms": 10000,
                "save_as": "app_file_created",
            },
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "app": "TextEdit",
                "args": [absolute_assertion_file],
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
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": file_name,
                "path": "real-app-elements.json",
                "save_as": "app_elements",
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "title_contains": file_name,
                "name_contains": file_name,
                "save_as": "app_window_element",
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_text",
                "title_contains": file_name,
                "name_contains": file_name,
                "save_as": "app_window_element_text",
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": file_name,
                "name_contains": file_name,
                "save_as": "app_window_element_state",
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": file_name,
                "name_contains": file_name,
                "save_as": "app_element_click",
                "max_depth": 2,
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
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": file_name,
                "save_as": "app_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": file_name,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "save_as": "app_closed",
            },
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
    return plan, assertion_file, "TextEdit window is closed by desktop_window.close"


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


def _cleanup_temporary_form_case(package_dir: Path, system: str) -> None:
    pid_path = package_dir / "resources" / "desktop-element-action-pid.txt"
    if not pid_path.exists():
        return
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return
    try:
        import subprocess

        if system == "Windows":
            subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=5,
            )
        else:
            subprocess.run(["kill", "-TERM", str(pid)], capture_output=True, check=False, timeout=5)
    except Exception:
        return


def _cleanup_windows_terminal_case(package_dir: Path) -> None:
    pid_path = package_dir / "resources" / "desktop-terminal-pid.txt"
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


def _cleanup_windows_file_dialog_case(package_dir: Path) -> None:
    pid_path = package_dir / "resources" / "desktop-file-dialog-pid.txt"
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


def _desktop_elements_file_ok(path: Path, started_at: float) -> bool:
    payload = _read_json(path) if path.exists() else {}
    return (
        _file_nonempty_after(path, started_at)
        and isinstance(payload, dict)
        and isinstance(payload.get("elements"), list)
        and int(payload.get("count", 0) or 0) > 0
    )


def _file_nonempty_after(path: Path, started_at: float) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0 and path.stat().st_mtime >= started_at - 1.0


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        left_path = str(Path(left).resolve())
        right_path = str(Path(right).resolve())
    except Exception:
        left_path = left
        right_path = right
    if platform.system() == "Windows":
        return left_path.casefold() == right_path.casefold()
    return left_path == right_path


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


def _latest_run_output_dir(output_root: Path) -> Path | None:
    if not output_root.exists():
        return None
    run_dirs = [
        path
        for path in sorted(output_root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.is_dir() and (path / "result.json").exists()
    ]
    return run_dirs[0] if run_dirs else None


def _analyze_failure_for_self_check(plan_path: Path, output_root: Path) -> dict[str, Any]:
    run_output_dir = _latest_run_output_dir(output_root)
    if run_output_dir is None:
        return {"ok": False, "error": "latest run output dir not found"}

    def resolve_plan_path(path: str | Path) -> Path:
        return Path(path).resolve()

    def resolve_run_output_dir(_plan_path: str | Path, output_dir: str | Path | None = None) -> Path:
        return Path(output_dir).resolve() if output_dir else run_output_dir.resolve()

    return analyze_latest_run_failure_tool(
        resolve_plan_path,
        resolve_run_output_dir,
        plan_path,
        output_dir=run_output_dir,
    )


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
