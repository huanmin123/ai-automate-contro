from __future__ import annotations

import json
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.run_failure_analysis import (
    analyze_latest_run_failure_tool,
    build_desktop_repair_suggestions,
    collect_desktop_diagnostics,
)
from ai_automate_contro.engine.executor import execute_plan
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


def self_check_desktop_components(project_root: Path) -> dict[str, Any]:
    resolved_root = Path(project_root).resolve()
    schema_cases = _run_schema_cases(resolved_root)
    runtime_case = _run_runtime_case(resolved_root)
    failure_case = _run_failure_capture_case(resolved_root)
    element_failure_case = _run_element_failure_capture_case(resolved_root)
    launch_only_case = _run_launch_only_case(resolved_root)
    vision_case = _run_vision_locator_case(resolved_root)
    real_app_case = _run_real_app_matrix_case(resolved_root)
    element_action_case = _run_element_action_case(resolved_root)
    input_probe_case = _run_input_dependency_probe_case()
    capability_diagnostics_case = _run_capability_diagnostics_case()
    schema_ok = all(case["ok"] for case in schema_cases)
    runtime_ok = bool(runtime_case["ok"])
    failure_ok = bool(failure_case["ok"])
    element_failure_ok = bool(element_failure_case["ok"])
    launch_only_ok = bool(launch_only_case["ok"])
    vision_ok = bool(vision_case["ok"])
    real_app_ok = bool(real_app_case["ok"])
    element_action_ok = bool(element_action_case["ok"])
    input_probe_ok = bool(input_probe_case["ok"])
    capability_diagnostics_ok = bool(capability_diagnostics_case["ok"])
    return {
        "ok": schema_ok
        and runtime_ok
        and failure_ok
        and element_failure_ok
        and launch_only_ok
        and vision_ok
        and real_app_ok
        and element_action_ok
        and input_probe_ok
        and capability_diagnostics_ok,
        "checks": [
            {
                "name": "desktop_schema_and_execution_line_validation",
                "ok": schema_ok,
                "cases": schema_cases,
            },
            runtime_case,
            failure_case,
            element_failure_case,
            launch_only_case,
            vision_case,
            real_app_case,
            element_action_case,
            input_probe_case,
            capability_diagnostics_case,
        ],
        "commands": {
            "run": f"python {_cplan_script_path()} self-check desktop-components",
            "create_desktop_plan": f"python {_cplan_script_path()} create --path .\\plans\\desktop-demo --automation-type desktop",
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
            "name": "desktop-app-launch-requires-target",
            "expected_message": "desktop_app.launch 需要 app、path 或 command 之一",
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
        _expect(
            "snapshot_capability_matrix_shape",
            isinstance(snapshot.get("capability_matrix"), dict)
            and snapshot["capability_matrix"].get("schema_version") == 1
            and isinstance(snapshot["capability_matrix"].get("capabilities"), dict),
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
        capability_matrix_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("capability_matrix"), dict)
            and payload["capability_matrix"].get("schema_version") == 1
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
                and capability_matrix_ok
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
            "capability_matrix_ok": capability_matrix_ok,
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
        capability_matrix_ok = any(
            isinstance(payload, dict)
            and isinstance(payload.get("capability_matrix"), dict)
            and payload["capability_matrix"].get("schema_version") == 1
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
                and capability_matrix_ok
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
            "capability_matrix_ok": capability_matrix_ok,
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


def _run_vision_locator_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": True,
            "skipped": True,
            "reason": f"desktop vision regression only runs on Windows/macOS, current={system}",
        }
    if not _module_available("cv2"):
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": True,
            "skipped": True,
            "reason": "opencv-python is not installed; desktop_vision locate_image is unavailable.",
        }
    if not _module_available("PIL"):
        return {
            "name": "desktop_vision_locate_image_regression",
            "ok": True,
            "skipped": True,
            "reason": "Pillow is not installed; desktop_vision fixture images cannot be generated.",
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


def _run_real_app_matrix_case(project_root: Path) -> dict[str, Any]:
    system = platform.system()
    cases = [_run_real_app_case(project_root)]
    if system == "Windows":
        cases.append(_run_windows_explorer_real_app_case(project_root))
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
            plan, assertion_relative_file, cleanup_hint = _windows_notepad_plan(package_dir)
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
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "real-app-screen.png"
        elements_path = package_dir / "output" / "desktop-elements" / "real-app-elements.json"
        elements_payload = _read_json(elements_path) if elements_path.exists() else {}
        element_output_ok = (
            _file_nonempty_after(elements_path, started_at)
            and isinstance(elements_payload, dict)
            and isinstance(elements_payload.get("elements"), list)
            and int(elements_payload.get("count", 0) or 0) > 0
        )
        return {
            "name": "desktop_real_app_regression",
            "ok": run_ok and expected_text in content and _file_nonempty_after(screenshot_path, started_at) and element_output_ok,
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
        elements_path = package_dir / "output" / "desktop-elements" / "explorer-elements.json"
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "explorer-screen.png"
        windows_payload = _read_json(windows_path) if windows_path.exists() else {}
        elements_payload = _read_json(elements_path) if elements_path.exists() else {}
        window_found = any(
            folder_name in str(window.get("title", ""))
            for window in windows_payload.get("windows", [])
            if isinstance(window, dict)
        )
        elements_ok = (
            _file_nonempty_after(elements_path, started_at)
            and isinstance(elements_payload, dict)
            and isinstance(elements_payload.get("elements"), list)
        )
        return {
            "name": "desktop_windows_explorer_real_app_regression",
            "ok": run_ok
            and window_found
            and elements_ok
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
            "elements_path": str(elements_path),
            "elements_ok": elements_ok,
            "screenshot_path": str(screenshot_path),
            "cleanup": "Explorer window is closed by desktop_window.close; no explorer.exe process kill fallback is used.",
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
        open_dialog_screenshot_path = package_dir / "output" / "desktop-screenshots" / "open-dialog-screen.png"
        save_dialog_screenshot_path = package_dir / "output" / "desktop-screenshots" / "save-dialog-screen.png"
        screenshot_path = package_dir / "output" / "desktop-screenshots" / "file-dialog-final-screen.png"
        form_elements_ok = _desktop_elements_file_ok(form_elements_path, started_at)
        open_dialog_screenshot_ok = _file_nonempty_after(open_dialog_screenshot_path, started_at)
        save_dialog_screenshot_ok = _file_nonempty_after(save_dialog_screenshot_path, started_at)
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
                "DesktopElementOrdersGrid",
            }
            if system == "Windows"
            else set()
        )
        expected_controls_found = not expected_automation_ids or expected_automation_ids.issubset(automation_ids)
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
        status_assertion_ok = system != "Windows" or _file_nonempty_after(status_assert_path, started_at)
        expected_agree = "agree=True" if _module_available("pyautogui") else "agree=False"
        metadata_found = (
            expected_agree in content and "mode=Audit" in content and "option=Green" in content
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
                for payload in annotation_payloads
            )
            and select_cell_annotation_ok
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
                and _file_nonempty_after(assert_path, started_at)
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
            "element_assertion_path": str(assert_path),
            "status_assertion_path": str(status_assert_path),
            "set_text_expected": set_text_payload,
            "annotation_ok": annotation_ok,
            "annotation_png_count": len(annotation_pngs),
            "annotation_json_count": len(annotation_jsons),
            "annotation_dir": str(annotation_dir),
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
        },
        "limitations": [
            "window_list_unavailable",
            "pyautogui_missing",
            "pillow_imagegrab_missing",
            "opencv_missing_for_image_locator",
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
        status_locator = {"automation_id": "DesktopElementStatus", "control_type": "Text"}
        grid_locator = {"automation_id": "DesktopElementOrdersGrid"}
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
    extra_control_steps: list[dict[str, Any]] = []
    clipboard_steps: list[dict[str, Any]] = []
    status_assert_steps: list[dict[str, Any]] = []
    expected_content_fragments = ["{{expected_text}}"]
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
                        "mode": "equals",
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
                "target": "bounds_center",
                "bounds": "{{form_elements_dump.selected_element.bounds}}",
                "save_as": "entry_bounds_center_click",
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


def _windows_powershell_executable() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or ""


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
$form.Width = 760
$form.Height = 600
$form.StartPosition = 'Manual'
$form.Left = 120
$form.Top = 120
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
$status = New-Object System.Windows.Forms.Label
$status.Name = 'DesktopElementStatus'
$status.AutoSize = $true
$status.Left = 20
$status.Top = 470
$status.Width = 700
function Write-RegressionPayload {{
    $optionText = ''
    if ($null -ne $listBox.SelectedItem) {{ $optionText = [string]$listBox.SelectedItem }}
    $gridCell = ''
    if ($null -ne $grid.CurrentCell) {{ $gridCell = [string]$grid.CurrentCell.Value }}
    $payload = "$($textBox.Text)`nagree=$($checkBox.Checked)`nmode=$($combo.Text)`noption=$optionText`ngrid_cell=$gridCell`nmouse_double_click=$($mouse['double_click'])`nmouse_right_click=$($mouse['right_click'])`nmouse_scroll=$($mouse['scroll'])`nmouse_drag=$($mouse['drag'])"
    [System.IO.File]::WriteAllText($OutputPath, $payload, [System.Text.Encoding]::UTF8)
    $status.Text = "Saved: $($textBox.Text) | agree=$($checkBox.Checked) | mode=$($combo.Text) | option=$optionText | grid=$gridCell | mouse=$($mouse['double_click'])/$($mouse['right_click'])/$($mouse['scroll'])/$($mouse['drag'])"
}}
$button.Add_Click({{
    Write-RegressionPayload
}})
$mousePanel.Add_Click({{
    $mousePanel.Focus()
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
[void]$form.Controls.Add($button)
[void]$form.Controls.Add($grid)
[void]$form.Controls.Add($status)
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _powershell_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _windows_notepad_plan(package_dir: Path) -> tuple[dict[str, Any], Path, str]:
    file_name = f"desktop-notepad-input-{package_dir.name.rsplit('-', 1)[-1]}.txt"
    expected_text = "desktop automation regression input"
    assertion_file = Path("resources") / file_name
    absolute_assertion_file = str((package_dir / assertion_file).resolve())
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
                    f"$file = '{absolute_assertion_file}'; "
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
                "app": "notepad.exe",
                "args": [absolute_assertion_file],
                "save_as": "app_launch",
            },
            {
                "action": "command",
                "type": "run",
                "command": "Set-Content -LiteralPath 'resources\\\\desktop-app-pid.txt' -Value '{{app_launch.pid}}'",
                "timeout_ms": 10000,
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
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["esc"]},
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["ctrl", "a"]},
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{expected_text}}",
                "method": "clipboard",
                "preserve_clipboard": False,
                "save_as": "typed_text",
            },
            {"action": "sleep", "seconds": 0.2},
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
                    f"$content = Get-Content -Raw -LiteralPath 'resources\\\\{file_name}'; "
                    "if ($content -notlike '*{{expected_text}}*') { "
                    "Write-Error ('typed text missing: ' + $content); exit 7 }"
                ),
                "timeout_ms": 10000,
                "save_as": "content_assertion",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, assertion_file, "notepad window is closed by desktop_window.close; fallback cleanup uses resources/desktop-app-pid.txt"


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
                "app": "explorer.exe",
                "args": [absolute_target_dir],
                "save_as": "explorer_launch",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
                "state": "exists",
                "timeout_ms": 7000,
                "interval_ms": 150,
                "save_as": "explorer_window",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
                "save_as": "explorer_focus",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
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
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
                "path": "explorer-elements.json",
                "save_as": "explorer_elements",
                "max_depth": 4,
                "max_elements": 300,
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
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
                "save_as": "explorer_close",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{folder_name}}",
                "process_name": "explorer.exe",
                "state": "not_exists",
                "timeout_ms": 5000,
                "interval_ms": 150,
                "save_as": "explorer_closed",
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
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": title,
                "automation_id": "DesktopFileDialogOpenButton",
                "control_type": "Button",
                "save_as": "open_button_click",
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
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
                "title_contains": open_dialog_title,
                "save_as": "open_dialog_focus",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
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
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": title,
                "automation_id": "DesktopFileDialogSaveButton",
                "control_type": "Button",
                "save_as": "save_button_click",
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
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
                "title_contains": save_dialog_title,
                "save_as": "save_dialog_focus",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
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
