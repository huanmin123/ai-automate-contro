from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

from ai_automate_contro.ai.terminal_tool_registry import call_ai_terminal_tool
from ai_automate_contro.engine.desktop.backends.capabilities import build_capability_matrix


AutomationDecision = Literal["browser", "desktop", "ambiguous"]


def self_check_ai_plan_generation_simulation(project_root: str | Path) -> dict[str, Any]:
    resolved_project_root = Path(project_root).resolve()
    with tempfile.TemporaryDirectory(prefix="ai-plan-generation-self-check-") as raw_temp_dir:
        simulation_root = Path(raw_temp_dir).resolve()
        _write_minimal_project_config(simulation_root)
        checks = [
            _run_browser_generation_case(simulation_root),
            _run_excel_file_generation_case(simulation_root),
            _run_excel_ambiguous_file_data_quality_gate_case(simulation_root),
            _run_excel_ambiguous_file_data_preview_case(simulation_root),
            _run_desktop_generation_case(simulation_root),
            _run_desktop_platform_contract_case(),
            _run_desktop_coordinate_quality_gate_case(simulation_root),
            _run_desktop_message_scenario_quality_gate_case(simulation_root),
            _run_desktop_game_scenario_quality_gate_case(simulation_root),
            _run_platform_desktop_intent_cases(),
            _run_file_dialog_generation_case(simulation_root),
            _run_ambiguous_confirmation_case(simulation_root),
            _run_mixed_browser_desktop_confirmation_case(simulation_root),
            _run_mixed_line_negative_case(simulation_root),
        ]
    return {
        "ok": all(check["passed"] for check in checks),
        "check": "ai_plan_generation_simulation",
        "project_root": str(resolved_project_root),
        "simulated_service": "scripted_server_ai",
        "checks": checks,
    }


def simulate_execution_line_decision(user_message: str) -> dict[str, Any]:
    text = user_message.lower()
    platform_tokens = {
        "windows",
        "macos",
        "win",
        "mac",
    }
    desktop_tokens = {
        "app",
        "client",
        "cmd",
        "desktop",
        "excel 桌面版",
        "explorer",
        "file dialog",
        "file explorer",
        "finder",
        "notepad",
        "open/save",
        "powershell",
        "save as",
        "terminal",
        "uac",
        "win32",
        "winforms",
        "textedit",
        "window",
        "qq",
        "微信",
        "客户端",
        "剪贴板",
        "命令行窗口",
        "打开文件对话框",
        "保存对话框",
        "应用窗口",
        "文件对话框",
        "文件资源管理器",
        "菜单栏",
        "本机",
        "本地应用",
        "本机应用",
        "桌面",
        "桌面应用",
        "系统弹窗",
        "系统窗口",
        "窗口",
        "记事本",
        "资源管理器",
        "系统设置",
        "终端",
        "键鼠",
        "键盘",
        "鼠标",
    }
    browser_tokens = {
        "browser",
        "chrome",
        "dom",
        "http://",
        "https://",
        "selector",
        "url",
        "web",
        "web app",
        "web page",
        "website",
        "网页",
        "网页后台",
        "后台网页",
        "网站",
        "浏览器",
        "网址",
        "后台页面",
        "页面表单",
    }
    file_data_tokens = {
        ".xlsx",
        ".csv",
        "excel 文件",
        "excel表",
        "xlsx",
        "人员名单",
        "财务表",
        "报表",
        "流水",
        "台账",
        "表格数据",
    }
    platform_hits = sorted(token for token in platform_tokens if _token_hit(text, token))
    desktop_hits = sorted(token for token in desktop_tokens if _token_hit(text, token))
    browser_hits = sorted(token for token in browser_tokens if token in text)
    file_data_hits = sorted(token for token in file_data_tokens if token in text)
    desktop_evidence = sorted(set(platform_hits + desktop_hits))
    if desktop_hits and not browser_hits:
        return {
            "decision": "desktop",
            "requires_confirmation": False,
            "confidence": "high",
            "evidence": desktop_evidence,
        }
    if browser_hits and not desktop_hits:
        return {
            "decision": "browser",
            "requires_confirmation": False,
            "confidence": "high",
            "evidence": browser_hits,
        }
    if file_data_hits and not desktop_hits and not browser_hits:
        return {
            "decision": "browser",
            "requires_confirmation": False,
            "confidence": "high",
            "evidence": ["common_file_data", *file_data_hits],
        }
    return {
        "decision": "ambiguous",
        "requires_confirmation": True,
        "confidence": "low",
        "evidence": {"browser": browser_hits, "desktop": desktop_evidence},
        "question": "你要自动化的是网页里的流程，还是本机桌面应用里的流程？两者的 plan 类型不同。",
    }


def _token_hit(text: str, token: str) -> bool:
    if token.isascii() and token.replace(" ", "").replace("/", "").replace("-", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text) is not None
    return token in text


def _run_browser_generation_case(project_root: Path) -> dict[str, Any]:
    user_message = "请帮我自动化一个网页 URL，打开浏览器页面并截图。"
    decision = simulate_execution_line_decision(user_message)
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/browser-simulated-plan",
        automation_type="browser",
        name="browser simulated plan",
        plan_document={
            "name": "browser simulated plan",
            "automation_type": "browser",
            "variables": {},
            "steps": [
                {"action": "open_browser", "name": "main"},
                {"action": "navigate", "browser": "main", "type": "goto", "url": "https://example.com"},
                {"action": "capture", "browser": "main", "type": "screenshot", "path": "example.png"},
                {"action": "close_browser", "browser": "main"},
            ],
        },
    )
    passed = (
        decision.get("decision") == "browser"
        and not decision.get("requires_confirmation")
        and result.get("created_automation_type") == "browser"
        and result.get("validation_ok") is True
    )
    return _self_check_result(
        name="scripted_ai_generates_browser_plan_with_automation_type",
        passed=passed,
        detail={"decision": decision, **result},
    )


def _run_excel_file_generation_case(project_root: Path) -> dict[str, Any]:
    user_message = "读取 resources/人员名单.xlsx，筛选财务在职人员，并导出 Excel 和 JSON。"
    decision = simulate_execution_line_decision(user_message)
    plan_document = {
        "name": "excel file data simulated plan",
        "automation_type": "browser",
        "variables": {},
        "steps": [
            {
                "action": "read",
                "type": "excel",
                "path": "resources/人员名单.xlsx",
                "sheet": "名单",
                "save_as": "employees",
                "save_meta_as": "employees_meta",
            },
            {
                "action": "table",
                "type": "filter",
                "source": "{{employees}}",
                "where": {"部门": "财务", "状态": "在职"},
                "save_as": "finance_people",
            },
            {
                "action": "write",
                "type": "excel",
                "path": "财务在职人员.xlsx",
                "sheet": "名单",
                "value": "{{finance_people}}",
                "freeze_header": True,
                "auto_filter": True,
            },
            {
                "action": "write",
                "type": "json",
                "path": "财务在职人员.json",
                "value": {"rows": "{{finance_people}}", "meta": "{{employees_meta}}"},
            },
        ],
    }
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/excel-file-data-simulated-plan",
        automation_type="browser",
        name="excel file data simulated plan",
        plan_document=plan_document,
        quality_user_request=user_message,
        quality_evidence_summary=(
            "用户需求是 .xlsx 文件数据处理，不是 Excel 桌面版窗口控制；"
            "plan 使用 read.type=excel 读取 resources/人员名单.xlsx，"
            "table.filter 筛选财务在职人员，再用 write.type=excel/json 写出 output。"
        ),
        planned_output_path="财务在职人员.xlsx",
    )
    actions = [step.get("action") for step in plan_document["steps"]]
    passed = (
        decision.get("decision") == "browser"
        and not decision.get("requires_confirmation")
        and result.get("created_automation_type") == "browser"
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and actions == ["read", "table", "write", "write"]
        and "missing_data_extraction" not in set(result.get("quality_issue_codes", []))
    )
    return _self_check_result(
        name="scripted_ai_generates_excel_file_data_plan",
        passed=passed,
        detail={"decision": decision, **result, "actions": actions},
    )


def _run_excel_ambiguous_file_data_quality_gate_case(project_root: Path) -> dict[str, Any]:
    user_message = "处理 resources/财务流水.xlsx，按常见报表输出。"
    decision = simulate_execution_line_decision(user_message)
    plan_document = {
        "name": "ambiguous excel file data quality gate",
        "automation_type": "browser",
        "variables": {},
        "steps": [
            {
                "action": "read",
                "type": "excel",
                "path": "resources/财务流水.xlsx",
                "sheet": "流水",
                "save_as": "rows",
            },
            {
                "action": "table",
                "type": "group",
                "source": "{{rows}}",
                "by": "账户",
                "aggregations": {"金额合计": {"sum": "金额"}},
                "save_as": "report_rows",
            },
            {
                "action": "write",
                "type": "excel",
                "path": "常见报表.xlsx",
                "sheet": "报表",
                "value": "{{report_rows}}",
                "freeze_header": True,
                "auto_filter": True,
            },
        ],
    }
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/ambiguous-excel-file-data-quality-gate",
        automation_type="browser",
        name="ambiguous excel file data quality gate",
        plan_document=plan_document,
        quality_user_request=user_message,
        quality_evidence_summary="用户只给了模糊表格处理目标，没有确认具体处理规则。",
        planned_output_path="常见报表.xlsx",
    )
    issue_codes = set(result.get("quality_issue_codes", []))
    passed = (
        decision.get("decision") == "browser"
        and not decision.get("requires_confirmation")
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is False
        and "ambiguous_file_data_transformation" in issue_codes
    )
    return _self_check_result(
        name="scripted_ai_rejects_scene_word_hardcoded_excel_plan",
        passed=passed,
        detail={"decision": decision, **result},
    )


def _run_excel_ambiguous_file_data_preview_case(project_root: Path) -> dict[str, Any]:
    user_message = "处理 resources/财务流水.xlsx，按常见报表输出。"
    decision = simulate_execution_line_decision(user_message)
    plan_document = {
        "name": "ambiguous excel file data preview",
        "automation_type": "browser",
        "variables": {},
        "steps": [
            {
                "action": "read",
                "type": "excel",
                "path": "resources/财务流水.xlsx",
                "sheet": "流水",
                "preview_rows": 20,
                "max_cells": 2000,
                "save_as": "preview_rows",
                "save_meta_as": "preview_meta",
            },
            {
                "action": "write",
                "type": "json",
                "path": "excel-preview.json",
                "value": {"rows": "{{preview_rows}}", "meta": "{{preview_meta}}"},
            },
        ],
    }
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/ambiguous-excel-file-data-preview",
        automation_type="browser",
        name="ambiguous excel file data preview",
        plan_document=plan_document,
        quality_user_request=user_message,
        quality_evidence_summary=(
            "用户只给了模糊表格处理目标；plan 仅用 read.type=excel "
            "preview_rows/max_cells/save_meta_as 做只读预览，并写出 JSON preview/meta，"
            "没有写入 filter/group/pivot/join/formula 等业务转换。"
        ),
        planned_output_path="excel-preview.json",
    )
    issue_codes = set(result.get("quality_issue_codes", []))
    passed = (
        decision.get("decision") == "browser"
        and not decision.get("requires_confirmation")
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and "ambiguous_file_data_transformation" not in issue_codes
    )
    return _self_check_result(
        name="scripted_ai_allows_ambiguous_excel_preview_plan",
        passed=passed,
        detail={"decision": decision, **result},
    )


def _run_desktop_generation_case(project_root: Path) -> dict[str, Any]:
    user_message = "请控制本机桌面 Notepad 窗口，截图并保存状态。"
    decision = simulate_execution_line_decision(user_message)
    plan_document = {
        "name": "desktop simulated plan",
        "automation_type": "desktop",
        "variables": {},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "profile": "notepad",
                "wait_for_window": True,
                "focus": True,
                "save_as": "notepad_launch",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "notepad",
                "state": "exists",
                "timeout_ms": 5000,
                "save_as": "notepad_window",
            },
            {"action": "desktop_window", "desktop": "desktop", "type": "list", "path": "windows.json"},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "path": "observe.json",
                "include_windows": True,
                "include_screenshot": True,
            },
            {"action": "desktop_capture", "desktop": "desktop", "type": "screenshot", "path": "screen.png"},
            {"action": "desktop_assert", "desktop": "desktop", "type": "screenshot", "path": "screen.png"},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-simulated-plan",
        automation_type="desktop",
        name="desktop simulated plan",
        plan_document=plan_document,
        quality_user_request=(
            "这是本机桌面控制 desktop，不是浏览器自动化。"
            "请优先用内置 profile=notepad 启动并等待窗口，"
            "再做安全桌面探测：desktop_window list 写 windows.json，"
            "desktop_capture observe 写 observe.json，desktop_capture screenshot 写 screen.png，并用 desktop_assert 验证截图。"
        ),
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "automation_type=desktop；plan 使用 profile=notepad；包含 open_desktop、desktop_app launch、desktop_wait window、desktop_window list、"
            "desktop_capture observe、desktop_capture screenshot、desktop_assert screenshot、close_desktop。"
        ),
    )
    steps = plan_document["steps"]
    profile_steps = [step for step in steps if step.get("profile") == "notepad"]
    passed = (
        decision.get("decision") == "desktop"
        and not decision.get("requires_confirmation")
        and result.get("created_automation_type") == "desktop"
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and any(step.get("action") == "desktop_app" and step.get("profile") == "notepad" for step in steps)
        and any(step.get("action") == "desktop_wait" and step.get("profile") == "notepad" for step in steps)
        and len(profile_steps) >= 2
        and "missing_browser_navigation" not in "\n".join(result.get("quality_issue_codes", []))
    )
    return _self_check_result(
        name="scripted_ai_generates_desktop_plan_with_automation_type",
        passed=passed,
        detail={"decision": decision, **result, "profile_steps": profile_steps},
    )


def _run_desktop_platform_contract_case() -> dict[str, Any]:
    matrices = {
        platform_name: build_capability_matrix(
            platform_name=platform_name,
            backend_name="native",
            source="self_check",
            permissions={
                "accessibility": "unknown",
                "screen_recording": "unknown",
                "input_control": "unknown",
            },
            dependencies={
                "Pillow.ImageGrab": True,
                "opencv-python": True,
                "pyautogui": True,
                "pyperclip": True,
            },
        )
        for platform_name in ("windows", "macos")
    }
    top_level_keys = {platform_name: sorted(matrix.keys()) for platform_name, matrix in matrices.items()}
    capability_keys = {
        platform_name: sorted(matrix.get("capabilities", {}).keys())
        for platform_name, matrix in matrices.items()
    }
    semantic_keys = {
        platform_name: sorted(matrix.get("capabilities", {}).get("semantic", {}).keys())
        for platform_name, matrix in matrices.items()
    }
    platform_values_ok = all(
        matrix.get("platform") == platform_name and matrix.get("backend") == "native"
        for platform_name, matrix in matrices.items()
    )
    window_contract_ok = all(
        "window_list" in matrix.get("capabilities", {}).get("semantic", {})
        and "windows" not in matrix.get("capabilities", {}).get("semantic", {})
        for matrix in matrices.values()
    )
    required_semantic_keys = {
        "window_list",
        "elements",
        "get_text",
        "get_state",
        "set_text",
        "select",
        "invoke",
        "get_table",
        "select_cell",
        "get_tree",
        "expand_tree",
        "collapse_tree",
        "select_tree",
        "invoke_menu",
        "scroll_element",
    }
    semantic_contract_ok = all(
        required_semantic_keys.issubset(set(matrix.get("capabilities", {}).get("semantic", {}).keys()))
        for matrix in matrices.values()
    )
    shape_ok = (
        top_level_keys["windows"] == top_level_keys["macos"]
        and capability_keys["windows"] == capability_keys["macos"]
        and semantic_keys["windows"] == semantic_keys["macos"]
    )
    permissions_ok = all(
        {"accessibility", "screen_recording", "input_control"}.issubset(
            set(matrix.get("permissions", {}).keys())
        )
        for matrix in matrices.values()
    )
    passed = shape_ok and platform_values_ok and window_contract_ok and semantic_contract_ok and permissions_ok
    return _self_check_result(
        name="desktop_capability_matrix_contract_is_platform_neutral",
        passed=passed,
        detail={
            "top_level_keys": top_level_keys,
            "capability_keys": capability_keys,
            "semantic_keys": semantic_keys,
            "required_semantic_keys": sorted(required_semantic_keys),
            "semantic_contract_ok": semantic_contract_ok,
            "platform_values": {name: matrix.get("platform") for name, matrix in matrices.items()},
            "limitations": {name: matrix.get("limitations", []) for name, matrix in matrices.items()},
        },
    )


def _run_desktop_coordinate_quality_gate_case(project_root: Path) -> dict[str, Any]:
    plan_document = {
        "name": "desktop coordinate quality gate",
        "automation_type": "desktop",
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {"action": "desktop_input", "desktop": "desktop", "type": "click", "x": 120, "y": 140},
            {"action": "desktop_capture", "desktop": "desktop", "type": "screenshot", "path": "after-click.png"},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    missing = _simulate_plan_generation(
        project_root,
        package_path="plans/coordinate-quality-missing-plan",
        automation_type="desktop",
        name="coordinate quality missing plan",
        plan_document=plan_document,
        quality_user_request="控制本机桌面窗口，在已确认位置点击并截图。",
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "仅确认有桌面窗口，但没有定位来源或框选事实。"
        ),
    )
    covered = _simulate_plan_generation(
        project_root,
        package_path="plans/coordinate-quality-covered-plan",
        automation_type="desktop",
        name="coordinate quality covered plan",
        plan_document=plan_document,
        quality_user_request="控制本机桌面窗口，在已确认位置点击并截图。",
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "target_candidates.best_candidate strategy=visual_bounds confidence=high screen_clickable=true "
            "bounds={x:100,y:120,width:40,height:40}；coordinate_profile kind=desktop_coordinate_profile "
            "coordinate_diagnostics source_bounds={x:0,y:0,width:800,height:600} coordinate_space=screen logical_px；"
            "坐标点击后用 desktop_capture screenshot 验证结果。"
        ),
    )
    candidate_plan_document = {
        "name": "desktop candidate quality gate",
        "automation_type": "desktop",
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "candidate",
                "target_candidates": {
                    "kind": "desktop_target_candidates",
                    "best_candidate": {
                        "id": "element_match-0",
                        "candidate_id": "element_match-0",
                        "strategy": "semantic_locator",
                        "confidence": "high",
                        "window_query": {"title_contains": "Demo"},
                        "locator": {"automation_id": "DesktopElementTextBox"},
                    },
                    "candidates": [
                        {
                            "id": "element_match-0",
                            "candidate_id": "element_match-0",
                            "strategy": "semantic_locator",
                            "confidence": "high",
                            "window_query": {"title_contains": "Demo"},
                            "locator": {"automation_id": "DesktopElementTextBox"},
                        }
                    ],
                },
                "candidate_id": "element_match-0",
                "min_confidence": "medium",
            },
            {"action": "desktop_assert", "desktop": "desktop", "type": "element", "title_contains": "Demo", "automation_id": "DesktopElementTextBox"},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    candidate_missing = _simulate_plan_generation(
        project_root,
        package_path="plans/candidate-quality-missing-plan",
        automation_type="desktop",
        name="candidate quality missing plan",
        plan_document=candidate_plan_document,
        quality_user_request="控制本机桌面窗口，选择定位候选并点击。",
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "只说明有桌面窗口，没有写明 candidate_id、strategy、confidence 或 screen_clickable。"
        ),
    )
    candidate_covered = _simulate_plan_generation(
        project_root,
        package_path="plans/candidate-quality-covered-plan",
        automation_type="desktop",
        name="candidate quality covered plan",
        plan_document=candidate_plan_document,
        quality_user_request="控制本机桌面窗口，选择定位候选并点击。",
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "target=candidate target_candidates.best_candidate candidate_id=element_match-0 "
            "strategy=semantic_locator confidence=high screen_clickable=true locator.automation_id=DesktopElementTextBox；"
            "desktop_input 会重新 find_element 后点击实时中心，随后 desktop_assert element 验证结果。"
        ),
    )
    missing_codes = set(missing.get("quality_issue_codes", []))
    covered_codes = set(covered.get("quality_issue_codes", []))
    candidate_missing_codes = set(candidate_missing.get("quality_issue_codes", []))
    candidate_covered_codes = set(candidate_covered.get("quality_issue_codes", []))
    passed = (
        missing.get("validation_ok") is True
        and missing.get("quality_review_ok") is False
        and "missing_desktop_coordinate_evidence" in missing_codes
        and "unsafe_raw_desktop_coordinates" in missing_codes
        and covered.get("validation_ok") is True
        and covered.get("quality_review_ok") is True
        and "missing_desktop_coordinate_evidence" not in covered_codes
        and "unsafe_raw_desktop_coordinates" not in covered_codes
        and candidate_missing.get("validation_ok") is True
        and candidate_missing.get("quality_review_ok") is False
        and "missing_candidate_target_evidence" in candidate_missing_codes
        and candidate_covered.get("validation_ok") is True
        and candidate_covered.get("quality_review_ok") is True
        and "missing_candidate_target_evidence" not in candidate_covered_codes
    )
    return _self_check_result(
        name="desktop_coordinate_quality_gate_requires_coordinate_evidence",
        passed=passed,
        detail={
            "missing": missing,
            "covered": covered,
            "candidate_missing": candidate_missing,
            "candidate_covered": candidate_covered,
        },
    )


def _run_desktop_message_scenario_quality_gate_case(project_root: Path) -> dict[str, Any]:
    user_request = "请控制微信桌面客户端给 Alice 发送消息 scheduled greeting，发送前确认联系人和消息内容。"
    missing_plan = {
        "name": "desktop message missing verification gate",
        "automation_type": "desktop",
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {"action": "desktop_input", "desktop": "desktop", "type": "type_text", "value": "scheduled greeting"},
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["enter"]},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    covered_plan = {
        "name": "desktop message covered verification gate",
        "automation_type": "desktop",
        "variables": {"recipient": "Alice", "message": "scheduled greeting"},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {"action": "desktop_window", "desktop": "desktop", "type": "list", "path": "windows.json"},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "title_contains": "Mock Chat",
                "include_windows": True,
                "include_elements": True,
                "include_screenshot": True,
                "path": "chat-observe.json",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": "Mock Chat",
                "automation_id": "MockChatSearchBox",
                "value": "{{recipient}}",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": "Mock Chat",
                "automation_id": "MockChatRecipientLabel",
                "state": "exists",
                "expected": "Recipient: {{recipient}}",
                "mode": "equals",
                "path": "recipient-confirmed.json",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": "Mock Chat",
                "automation_id": "MockChatMessageBox",
                "value": "{{message}}",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": "Mock Chat",
                "automation_id": "MockChatMessageBox",
                "state": "exists",
                "expected": "{{message}}",
                "mode": "equals",
                "path": "draft-confirmed.json",
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": "Mock Chat",
                "automation_id": "MockChatSendButton",
            },
            {"action": "desktop_capture", "desktop": "desktop", "type": "screenshot", "path": "after-send.png"},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    missing = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-message-missing-quality-plan",
        automation_type="desktop",
        name="desktop message missing quality plan",
        plan_document=missing_plan,
        quality_user_request=user_request,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "只确认桌面可用，没有确认微信联系人、群或草稿内容。"
        ),
    )
    covered = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-message-covered-quality-plan",
        automation_type="desktop",
        name="desktop message covered quality plan",
        plan_document=covered_plan,
        quality_user_request=user_request,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "recipient=Alice target_chat confirmed；draft_text=scheduled greeting message confirmed；"
            "发送前已有 desktop_assert element 验证联系人和草稿内容，发送后截图验证。"
        ),
    )
    missing_codes = set(missing.get("quality_issue_codes", []))
    covered_codes = set(covered.get("quality_issue_codes", []))
    expected_codes = {
        "missing_desktop_message_recipient_verification",
        "missing_desktop_message_content_verification",
        "missing_desktop_message_pre_send_evidence",
    }
    passed = (
        missing.get("validation_ok") is True
        and missing.get("quality_review_ok") is False
        and expected_codes.issubset(missing_codes)
        and covered.get("validation_ok") is True
        and covered.get("quality_review_ok") is True
        and expected_codes.isdisjoint(covered_codes)
    )
    return _self_check_result(
        name="desktop_message_quality_gate_requires_target_and_draft_verification",
        passed=passed,
        detail={"missing": missing, "covered": covered},
    )


def _run_desktop_game_scenario_quality_gate_case(project_root: Path) -> dict[str, Any]:
    user_request = "请控制我的游戏桌面窗口完成每日签到、副本刷图和奖励领取，必须避免无限循环。"
    missing_plan = {
        "name": "desktop game missing boundary gate",
        "automation_type": "desktop",
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {
                "action": "trigger",
                "type": "interval",
                "every_seconds": 1,
                "allow_infinite": True,
                "steps": [
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke",
                        "title_contains": "Mock Game",
                        "automation_id": "MockGameSkillButton",
                    }
                ],
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    covered_plan = {
        "name": "desktop game covered boundary gate",
        "automation_type": "desktop",
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "title_contains": "Mock Game",
                "include_windows": True,
                "include_elements": True,
                "include_screenshot": True,
                "path": "game-observe.json",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "title_contains": "Mock Game",
                "automation_id": "MockGameStatusLabel",
                "state": "exists",
                "expected": "Home",
                "mode": "equals",
                "path": "game-home.json",
            },
            {
                "action": "trigger",
                "type": "interval",
                "every_seconds": 1,
                "max_runs": 2,
                "steps": [
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "invoke",
                        "title_contains": "Mock Game",
                        "automation_id": "MockGameRewardButton",
                    },
                    {
                        "action": "desktop_assert",
                        "desktop": "desktop",
                        "type": "element",
                        "title_contains": "Mock Game",
                        "automation_id": "MockGameStatusLabel",
                        "state": "exists",
                        "expected": "Daily reward claimed",
                        "mode": "equals",
                        "path": "game-reward.json",
                    },
                ],
            },
            {"action": "desktop_capture", "desktop": "desktop", "type": "screenshot", "path": "game-finished.png"},
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    missing = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-game-missing-quality-plan",
        automation_type="desktop",
        name="desktop game missing quality plan",
        plan_document=missing_plan,
        quality_user_request=user_request,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "没有游戏状态截图、状态文本或完成断言。"
        ),
    )
    covered = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-game-covered-quality-plan",
        automation_type="desktop",
        name="desktop game covered quality plan",
        plan_document=covered_plan,
        quality_user_request=user_request,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "bounded_runtime max_runs=2；desktop_capture observe 和 desktop_assert element 证明状态，"
            "完成后 desktop_capture screenshot 留证。"
        ),
    )
    missing_codes = set(missing.get("quality_issue_codes", []))
    covered_codes = set(covered.get("quality_issue_codes", []))
    expected_codes = {
        "missing_desktop_game_progress_evidence",
        "missing_desktop_scenario_stop_budget",
        "unsafe_desktop_game_infinite_loop",
    }
    passed = (
        missing.get("validation_ok") is True
        and missing.get("quality_review_ok") is False
        and expected_codes.issubset(missing_codes)
        and covered.get("validation_ok") is True
        and covered.get("quality_review_ok") is True
        and expected_codes.isdisjoint(covered_codes)
    )
    return _self_check_result(
        name="desktop_game_quality_gate_requires_state_evidence_and_stop_boundary",
        passed=passed,
        detail={"missing": missing, "covered": covered},
    )


def _run_platform_desktop_intent_cases() -> dict[str, Any]:
    cases = [
        "请在 Windows 桌面控制 Notepad 记事本输入文字并保存。",
        "打开 Windows 文件资源管理器窗口，选中一个文件并截图。",
        "控制 PowerShell 终端窗口输入一条命令。",
        "请在 macOS 桌面控制 TextEdit 输入文字并保存。",
        "打开 macOS Finder 窗口，选中一个文件并截图。",
        "在系统 Open/Save 文件对话框里输入完整路径并按 Enter。",
        "控制本机客户端窗口，用键盘和鼠标完成一次表单输入。",
    ]
    decisions = [simulate_execution_line_decision(message) for message in cases]
    browser_on_windows = simulate_execution_line_decision("请在 Windows 上用 Chrome 浏览器打开 https://example.com 并截图。")
    browser_on_macos = simulate_execution_line_decision("请在 macOS 上用 Chrome 浏览器打开 https://example.com 并截图。")
    passed = (
        all(
            decision.get("decision") == "desktop" and decision.get("requires_confirmation") is False
            for decision in decisions
        )
        and browser_on_windows.get("decision") == "browser"
        and browser_on_windows.get("requires_confirmation") is False
        and browser_on_macos.get("decision") == "browser"
        and browser_on_macos.get("requires_confirmation") is False
    )
    return _self_check_result(
        name="scripted_ai_routes_platform_desktop_intents_without_confusing_platform_word",
        passed=passed,
        detail={
            "desktop_cases": [
                {"message": message, "decision": decision}
                for message, decision in zip(cases, decisions)
            ],
            "browser_on_windows": browser_on_windows,
            "browser_on_macos": browser_on_macos,
        },
    )


def _run_file_dialog_generation_case(project_root: Path) -> dict[str, Any]:
    user_message = "请控制当前系统桌面 App 的 Open/Save 文件对话框，输入完整文件路径，截图留证并按 Enter 确认。"
    decision = simulate_execution_line_decision(user_message)
    plan_document = {
        "name": "file dialog simulated plan",
        "automation_type": "desktop",
        "variables": {"absolute_file_path": "C:/Temp/input.txt"},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto"},
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_open",
                "state": "exists",
                "timeout_ms": 5000,
                "save_as": "open_dialog",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "profile": "file_dialog_open",
                "path": "open-dialog.png",
                "save_as": "open_dialog_screen",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{absolute_file_path}}",
                "method": "clipboard",
                "preserve_clipboard": True,
                "save_as": "dialog_path_typed",
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["enter"],
                "save_as": "dialog_confirmed",
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "profile": "file_dialog_open",
                "state": "not_exists",
                "timeout_ms": 5000,
                "save_as": "open_dialog_closed",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/file-dialog-simulated-plan",
        automation_type="desktop",
        name="file dialog simulated plan",
        plan_document=plan_document,
        quality_user_request=user_message,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "desktop intent confirmed；系统 Open/Save 文件对话框按桌面窗口处理。"
            "plan 使用 profile=file_dialog_open、desktop_wait window、desktop_capture screenshot target=window、"
            "desktop_input type_text method=clipboard 和 hotkey enter 留证并推进。"
        ),
    )
    steps = plan_document["steps"]
    profile_steps = [step for step in steps if step.get("profile") == "file_dialog_open"]
    passed = (
        decision.get("decision") == "desktop"
        and decision.get("requires_confirmation") is False
        and result.get("created_automation_type") == "desktop"
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and any(step.get("action") == "desktop_wait" and step.get("profile") == "file_dialog_open" for step in steps)
        and any(
            step.get("action") == "desktop_capture"
            and step.get("profile") == "file_dialog_open"
            and step.get("target") == "window"
            for step in steps
        )
        and len(profile_steps) >= 2
        and "missing_browser_navigation" not in "\n".join(result.get("quality_issue_codes", []))
    )
    return _self_check_result(
        name="scripted_ai_generates_file_dialog_desktop_plan",
        passed=passed,
        detail={"decision": decision, **result, "profile_steps": profile_steps},
    )


def _run_ambiguous_confirmation_case(project_root: Path) -> dict[str, Any]:
    user_message = "帮我自动化企业后台登录，然后填一下表格。"
    decision = simulate_execution_line_decision(user_message)
    plan_count_before = _count_plan_packages(project_root)
    tool_calls: list[dict[str, Any]] = []
    plan_count_after = _count_plan_packages(project_root)
    passed = (
        decision.get("decision") == "ambiguous"
        and decision.get("requires_confirmation") is True
        and "网页里的流程" in str(decision.get("question", ""))
        and not tool_calls
        and plan_count_before == plan_count_after
    )
    return _self_check_result(
        name="scripted_ai_requires_confirmation_for_ambiguous_execution_line",
        passed=passed,
        detail={
            "decision": decision,
            "tool_calls": tool_calls,
            "plan_count_before": plan_count_before,
            "plan_count_after": plan_count_after,
        },
    )


def _run_mixed_browser_desktop_confirmation_case(project_root: Path) -> dict[str, Any]:
    user_message = "帮我自动化客户端后台登录，也可能是在网页后台里操作表格。"
    decision = simulate_execution_line_decision(user_message)
    plan_count_before = _count_plan_packages(project_root)
    tool_calls: list[dict[str, Any]] = []
    plan_count_after = _count_plan_packages(project_root)
    passed = (
        decision.get("decision") == "ambiguous"
        and decision.get("requires_confirmation") is True
        and "网页里的流程" in str(decision.get("question", ""))
        and not tool_calls
        and plan_count_before == plan_count_after
    )
    return _self_check_result(
        name="scripted_ai_requires_confirmation_for_mixed_browser_desktop_terms",
        passed=passed,
        detail={
            "decision": decision,
            "tool_calls": tool_calls,
            "plan_count_before": plan_count_before,
            "plan_count_after": plan_count_after,
        },
    )


def _run_mixed_line_negative_case(project_root: Path) -> dict[str, Any]:
    user_message = "这是桌面控制 plan，但模型错误地写入了跨线 action。"
    decision = simulate_execution_line_decision(user_message)
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/mixed-line-negative-plan",
        automation_type="desktop",
        name="mixed line negative plan",
        plan_document={
            "name": "mixed line negative plan",
            "automation_type": "desktop",
            "variables": {},
            "steps": [{"action": "open_browser", "name": "main"}],
        },
    )
    validation_errors = "\n".join(result.get("validation_errors", []))
    passed = (
        decision.get("decision") == "desktop"
        and result.get("created_automation_type") == "desktop"
        and result.get("validation_ok") is False
        and "automation_type=desktop 不支持 action：open_browser" in validation_errors
    )
    return _self_check_result(
        name="scripted_ai_mixed_line_plan_is_rejected",
        passed=passed,
        detail={"decision": decision, **result},
    )


def _simulate_plan_generation(
    project_root: Path,
    *,
    package_path: str,
    automation_type: Literal["browser", "desktop"],
    name: str,
    plan_document: dict[str, Any],
    quality_user_request: str = "",
    quality_evidence_summary: str = "",
    planned_output_path: str = "",
) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []

    create_result = _call_tool(
        project_root,
        tool_calls,
        "create_plan_package",
        {"package_path": package_path, "automation_type": automation_type, "name": name},
    )
    plan_path = str(create_result.get("plan_path", ""))
    write_result = _call_tool(
        project_root,
        tool_calls,
        "write_plan_package_file",
        {"plan_path": plan_path, "relative_path": "plan.json", "json_value": plan_document},
    )
    validation_result = _call_tool(project_root, tool_calls, "validate_plan", {"plan_path": plan_path})
    quality_result: dict[str, Any] = {}
    if quality_user_request:
        quality_result = _call_tool(
            project_root,
            tool_calls,
            "review_plan_quality",
            {
                "plan_path": plan_path,
                "user_request": quality_user_request,
                "evidence_summary": quality_evidence_summary,
                "planned_output_path": planned_output_path,
            },
        )
    return {
        "created_automation_type": (
            create_result.get("summary", {}).get("automation_type")
            if isinstance(create_result.get("summary"), dict)
            else ""
        ),
        "plan_path": plan_path,
        "write_ok": bool(write_result.get("ok")),
        "validation_ok": bool(validation_result.get("ok")),
        "validation_errors": [str(error.get("formatted") or error) for error in validation_result.get("errors", [])],
        "quality_review_ok": bool(quality_result.get("ok")) if quality_result else None,
        "quality_issue_codes": [
            str(issue.get("code") or issue)
            for issue in quality_result.get("issues", [])
            if isinstance(issue, dict)
        ],
        "tool_calls": tool_calls,
    }


def _call_tool(
    project_root: Path,
    tool_calls: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = call_ai_terminal_tool(project_root=project_root, tool_name=tool_name, arguments=arguments)
    tool_calls.append(
        {
            "tool": tool_name,
            "arguments": _compact_arguments(arguments),
            "ok": bool(result.get("ok")),
        }
    )
    return result


def _compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(arguments)
    if isinstance(compacted.get("json_value"), dict):
        document = compacted["json_value"]
        compacted["json_value"] = {
            "automation_type": document.get("automation_type"),
            "step_count": len(document.get("steps", [])) if isinstance(document.get("steps"), list) else 0,
        }
    return compacted


def _write_minimal_project_config(project_root: Path) -> None:
    (project_root / "plans").mkdir(parents=True, exist_ok=True)
    (project_root / "test-plans").mkdir(parents=True, exist_ok=True)
    (project_root / "handbook").mkdir(parents=True, exist_ok=True)
    (project_root / "plan.config").write_text(
        json.dumps(
            {
                "handbook_path": "handbook",
                "plan_roots": ["plans", "test-plans"],
                "default_ai_config_dir": "plans",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _count_plan_packages(project_root: Path) -> int:
    return sum(1 for _path in (project_root / "plans").glob("*/plan.json"))


def _self_check_result(*, name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed}
    if detail is not None:
        result["detail"] = detail
    return result
