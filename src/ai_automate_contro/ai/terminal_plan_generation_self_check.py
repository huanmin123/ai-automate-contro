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
            _run_desktop_generation_case(simulation_root),
            _run_desktop_platform_contract_case(),
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
    platform_hits = sorted(token for token in platform_tokens if _token_hit(text, token))
    desktop_hits = sorted(token for token in desktop_tokens if _token_hit(text, token))
    browser_hits = sorted(token for token in browser_tokens if token in text)
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


def _run_desktop_generation_case(project_root: Path) -> dict[str, Any]:
    user_message = "请控制本机桌面 Notepad 窗口，截图并保存状态。"
    decision = simulate_execution_line_decision(user_message)
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/desktop-simulated-plan",
        automation_type="desktop",
        name="desktop simulated plan",
        plan_document={
            "name": "desktop simulated plan",
            "automation_type": "desktop",
            "variables": {},
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto"},
                {"action": "desktop_window", "desktop": "desktop", "type": "list", "path": "windows.json"},
                {"action": "desktop_capture", "desktop": "desktop", "type": "screenshot", "path": "screen.png"},
                {"action": "desktop_assert", "desktop": "desktop", "type": "screenshot", "path": "screen.png"},
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        },
        quality_user_request=(
            "这是本机桌面控制 desktop，不是浏览器自动化。"
            "请做安全桌面探测：desktop_window list 写 windows.json，"
            "desktop_capture screenshot 写 screen.png，并用 desktop_assert 验证截图。"
        ),
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "automation_type=desktop；plan 包含 open_desktop、desktop_window list、"
            "desktop_capture screenshot、desktop_assert screenshot、close_desktop。"
        ),
    )
    passed = (
        decision.get("decision") == "desktop"
        and not decision.get("requires_confirmation")
        and result.get("created_automation_type") == "desktop"
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and "missing_browser_navigation" not in "\n".join(result.get("quality_issue_codes", []))
    )
    return _self_check_result(
        name="scripted_ai_generates_desktop_plan_with_automation_type",
        passed=passed,
        detail={"decision": decision, **result},
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
    passed = shape_ok and platform_values_ok and window_contract_ok and permissions_ok
    return _self_check_result(
        name="desktop_capability_matrix_contract_is_platform_neutral",
        passed=passed,
        detail={
            "top_level_keys": top_level_keys,
            "capability_keys": capability_keys,
            "semantic_keys": semantic_keys,
            "platform_values": {name: matrix.get("platform") for name, matrix in matrices.items()},
            "limitations": {name: matrix.get("limitations", []) for name, matrix in matrices.items()},
        },
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
    result = _simulate_plan_generation(
        project_root,
        package_path="plans/file-dialog-simulated-plan",
        automation_type="desktop",
        name="file dialog simulated plan",
        plan_document={
            "name": "file dialog simulated plan",
            "automation_type": "desktop",
            "variables": {"absolute_file_path": "C:/Temp/input.txt"},
            "steps": [
                {"action": "open_desktop", "name": "desktop", "backend": "auto"},
                {
                    "action": "desktop_wait",
                    "desktop": "desktop",
                    "type": "window",
                    "title_contains": "Open",
                    "state": "exists",
                    "timeout_ms": 5000,
                    "save_as": "open_dialog",
                },
                {
                    "action": "desktop_capture",
                    "desktop": "desktop",
                    "type": "screenshot",
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
                    "title_contains": "Open",
                    "state": "not_exists",
                    "timeout_ms": 5000,
                    "save_as": "open_dialog_closed",
                },
                {"action": "close_desktop", "desktop": "desktop"},
            ],
        },
        quality_user_request=user_message,
        quality_evidence_summary=(
            "inspect_desktop platform=auto backend=native capability_matrix.schema_version=1 window_count=3；"
            "desktop intent confirmed；系统 Open/Save 文件对话框按桌面窗口处理。"
            "plan 使用 desktop_wait window、desktop_capture screenshot、"
            "desktop_input type_text method=clipboard 和 hotkey enter 留证并推进。"
        ),
    )
    passed = (
        decision.get("decision") == "desktop"
        and decision.get("requires_confirmation") is False
        and result.get("created_automation_type") == "desktop"
        and result.get("validation_ok") is True
        and result.get("quality_review_ok") is True
        and "missing_browser_navigation" not in "\n".join(result.get("quality_issue_codes", []))
    )
    return _self_check_result(
        name="scripted_ai_generates_file_dialog_desktop_plan",
        passed=passed,
        detail={"decision": decision, **result},
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
