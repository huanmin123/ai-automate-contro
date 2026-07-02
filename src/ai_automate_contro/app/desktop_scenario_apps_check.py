from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.validator import validate_plan_file


def self_check_desktop_scenario_apps(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    system = platform.system()
    skip_reason = _scenario_app_skip_reason(system)
    if skip_reason:
        return {
            "ok": True,
            "skipped": True,
            "check": "desktop_scenario_apps",
            "project_root": str(root),
            "platform": system,
            "reason": skip_reason,
            "scenarios": [],
            "commands": {"run": "python .\\cplan.py self-check desktop-scenario-apps"},
        }
    scenarios = [
        _run_windows_chat_scenario(root),
        _run_windows_game_scenario(root),
        _run_windows_recovery_scenario(root),
        _run_windows_interference_scenario(root),
    ]
    return {
        "ok": all(bool(item.get("ok")) for item in scenarios),
        "check": "desktop_scenario_apps",
        "project_root": str(root),
        "platform": system,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "checks": [
            {
                "name": item.get("name", ""),
                "ok": bool(item.get("ok")),
                "summary": item.get("summary", {}),
            }
            for item in scenarios
        ],
        "commands": {
            "run": "python .\\cplan.py self-check desktop-scenario-apps",
            "desktop_components": "python .\\cplan.py self-check desktop-components --require-input",
        },
    }


def _scenario_app_skip_reason(system: str) -> str:
    if system != "Windows":
        return f"controlled scenario app regression currently uses Windows WinForms, current={system}"
    if not _powershell_executable():
        return "PowerShell is unavailable; controlled WinForms scenario regression cannot run."
    return ""


def _run_windows_chat_scenario(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-scenario-chat-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan, result_file, pid_file, title = _windows_chat_plan(package_dir)
        return _run_scenario_plan(
            project_root,
            package_dir,
            plan,
            run_name="desktop-scenario-chat",
            result_file=result_file,
            pid_file=pid_file,
            title=title,
            expected_fragments=["recipient=Alice", "message=scheduled greeting", "send_count=1"],
            evidence_paths=[
                package_dir / "output" / "desktop-state" / "mock-chat-observe.json",
                package_dir / "output" / "desktop-screenshots" / "mock-chat-window.png",
                package_dir / "output" / "desktop-elements" / "mock-chat-status-assertion.json",
            ],
            required_plan_steps=[
                _required_plan_step("observe_chat_window", action="desktop_capture", type="observe", path="mock-chat-observe.json"),
                _required_plan_step("dump_search_box", action="desktop_element", type="dump", automation_id="MockChatSearchBox"),
                _required_plan_step("set_recipient", action="desktop_element", type="set_text", automation_id="MockChatSearchBox"),
                _required_plan_step("set_message", action="desktop_element", type="set_text", automation_id="MockChatMessageBox"),
                _required_plan_step("send_message", action="desktop_element", type="invoke", automation_id="MockChatSendButton"),
                _required_plan_step("assert_sent_status", action="desktop_assert", type="element", automation_id="MockChatStatusLabel"),
                _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
                _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
                _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
            ],
        )


def _run_windows_game_scenario(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-scenario-game-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan, result_file, pid_file, title = _windows_game_plan(package_dir)
        return _run_scenario_plan(
            project_root,
            package_dir,
            plan,
            run_name="desktop-scenario-game",
            result_file=result_file,
            pid_file=pid_file,
            title=title,
            expected_fragments=["reward=True", "dungeon_runs=1", "battle_complete=True"],
            evidence_paths=[
                package_dir / "output" / "desktop-state" / "mock-game-observe.json",
                package_dir / "output" / "desktop-screenshots" / "mock-game-window.png",
                package_dir / "output" / "desktop-elements" / "mock-game-status-assertion.json",
            ],
            required_plan_steps=[
                _required_plan_step("observe_game_window", action="desktop_capture", type="observe", path="mock-game-observe.json"),
                _required_plan_step("claim_reward", action="desktop_element", type="invoke", automation_id="MockGameRewardButton"),
                _required_plan_step("enter_dungeon", action="desktop_element", type="invoke", automation_id="MockGameDungeonButton"),
                _required_plan_step(
                    "skill_rotation",
                    min_count=3,
                    action="desktop_element",
                    type="invoke",
                    automation_id="MockGameSkillButton",
                ),
                _required_plan_step("assert_battle_complete", action="desktop_assert", type="element", expected="Battle complete"),
                _required_plan_step("collect_reward", action="desktop_element", type="invoke", automation_id="MockGameCollectButton"),
                _required_plan_step("assert_final_status", action="desktop_assert", type="element", automation_id="MockGameStatusLabel"),
                _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
                _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
                _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
            ],
        )


def _run_windows_recovery_scenario(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-scenario-recovery-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan, result_file, pid_file, title = _windows_recovery_plan(package_dir)
        variables = plan.get("variables") if isinstance(plan.get("variables"), dict) else {}
        popup_title = str(variables.get("popup_title") or "")
        return _run_scenario_plan(
            project_root,
            package_dir,
            plan,
            run_name="desktop-scenario-recovery",
            result_file=result_file,
            pid_file=pid_file,
            title=title,
            expected_fragments=["popup_closed=True", "restored=True", "action=completed"],
            evidence_paths=[
                package_dir / "output" / "desktop-state" / "mock-recovery-observe.json",
                package_dir / "output" / "desktop-screenshots" / "mock-recovery-window.png",
                package_dir / "output" / "desktop-elements" / "mock-recovery-status-assertion.json",
            ],
            required_plan_steps=[
                _required_plan_step("wait_main_window", action="desktop_wait", type="window", state="exists", title_contains=title),
                _required_plan_step("wait_popup_window", action="desktop_wait", type="window", state="exists", title_contains=popup_title),
                _required_plan_step("focus_popup", action="desktop_window", type="focus", title_contains=popup_title),
                _required_plan_step(
                    "dismiss_popup",
                    action="desktop_element",
                    type="invoke",
                    title_contains=popup_title,
                    automation_id="MockRecoveryPopupDismissButton",
                ),
                _required_plan_step("wait_popup_closed", action="desktop_wait", type="window", state="not_exists", title_contains=popup_title),
                _required_plan_step("restore_main_window", action="desktop_window", type="restore", title_contains=title),
                _required_plan_step("focus_main_window", action="desktop_window", type="focus", title_contains=title),
                _required_plan_step("observe_recovered_window", action="desktop_capture", type="observe", path="mock-recovery-observe.json"),
                _required_plan_step("set_payload", action="desktop_element", type="set_text", automation_id="MockRecoveryInputBox"),
                _required_plan_step("complete_action", action="desktop_element", type="invoke", automation_id="MockRecoveryActionButton"),
                _required_plan_step("assert_recovered_status", action="desktop_assert", type="element", automation_id="MockRecoveryStatusLabel"),
                _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
                _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
                _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
            ],
        )


def _run_windows_interference_scenario(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-scenario-interference-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan, result_file, pid_file, title = _windows_interference_plan(package_dir)
        variables = plan.get("variables") if isinstance(plan.get("variables"), dict) else {}
        title_prefix = str(variables.get("title_prefix") or "")
        blocker_title = str(variables.get("blocker_title") or "")
        input_click_path = package_dir / "output" / "json" / "mock-interference-input-click.json"
        result = _run_scenario_plan(
            project_root,
            package_dir,
            plan,
            run_name="desktop-scenario-interference",
            result_file=result_file,
            pid_file=pid_file,
            title=title,
            expected_fragments=[
                "interference_active=True",
                "moved=True",
                "completed=True",
                "payload=resumed after interference",
                "decoy_touched=False",
            ],
            evidence_paths=[
                package_dir / "output" / "desktop-state" / "mock-interference-observe.json",
                package_dir / "output" / "desktop-windows" / "mock-interference-windows.json",
                input_click_path,
                package_dir / "output" / "desktop-screenshots" / "mock-interference-window.png",
                package_dir / "output" / "desktop-elements" / "mock-interference-status-assertion.json",
            ],
            required_plan_steps=[
                _required_plan_step(
                    "wait_interference_window_by_id",
                    action="desktop_wait",
                    type="window",
                    state="exists",
                    window_id="{{interference_launch.window.id}}",
                ),
                _required_plan_step("list_interference_windows", action="desktop_window", type="list", title_contains=title_prefix),
                _required_plan_step("observe_interference_target", action="desktop_capture", type="observe", path="mock-interference-observe.json"),
                _required_plan_step("start_interference", action="desktop_element", type="invoke", automation_id="MockInterferencePrepareButton"),
                _required_plan_step("set_payload_after_focus_steal", action="desktop_element", type="set_text", automation_id="MockInterferenceInputBox"),
                _required_plan_step("complete_after_focus_steal", action="desktop_input", type="click", target="element_center", automation_id="MockInterferenceActionButton"),
                _required_plan_step("write_input_click_payload", action="write", type="json", path="mock-interference-input-click.json"),
                _required_plan_step("assert_completed_status", action="desktop_assert", type="element", automation_id="MockInterferenceStatusLabel"),
                _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
                _required_plan_step("close_blocker", action="desktop_window", type="close", title_contains=blocker_title),
                _required_plan_step("close_window", action="desktop_window", type="close", window_id="{{interference_window.window.id}}"),
                _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
            ],
        )
        window_evidence = _window_list_count_evidence(
            package_dir / "output" / "desktop-windows" / "mock-interference-windows.json",
            title_contains=title_prefix,
            min_count=2,
        )
        input_ownership_evidence = _desktop_input_ownership_evidence(input_click_path)
        result["extra_evidence"] = [window_evidence, input_ownership_evidence]
        result["multi_window_ok"] = bool(window_evidence.get("ok"))
        result["input_ownership_ok"] = bool(input_ownership_evidence.get("ok"))
        result["ok"] = (
            bool(result.get("ok"))
            and bool(window_evidence.get("ok"))
            and bool(input_ownership_evidence.get("ok"))
        )
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        summary["extra_evidence_count"] = 2
        summary["multi_window_count"] = window_evidence.get("matched_count", 0)
        summary["input_ownership_checked"] = input_ownership_evidence.get("ownership_checked", False)
        result["summary"] = summary
        return result


def _run_scenario_plan(
    project_root: Path,
    package_dir: Path,
    plan: dict[str, Any],
    *,
    run_name: str,
    result_file: Path,
    pid_file: Path,
    title: str,
    expected_fragments: list[str],
    evidence_paths: list[Path],
    required_plan_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plan_path = package_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan_contract = _plan_contract_evidence(plan, required_plan_steps or [])
    plan_contract_ok = all(item["ok"] for item in plan_contract)
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        _cleanup_process(pid_file)
        return {
            "name": run_name,
            "ok": False,
            "validation_ok": False,
            "plan_contract_ok": plan_contract_ok,
            "plan_contract": plan_contract,
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
            log_echo=False,
        )
        run_ok = result.status == "passed"
        output_dir = result.output_dir
    except Exception as error:
        run_ok = False
        output_dir = ""
        run_error = str(error)
    finally:
        _cleanup_process(pid_file)
    result_text = result_file.read_text(encoding="utf-8", errors="replace") if result_file.exists() else ""
    result_ok = all(fragment in result_text for fragment in expected_fragments)
    evidence = [_evidence_file(path, started_at) for path in evidence_paths]
    evidence_ok = all(item["ok"] for item in evidence)
    guard_evidence = _interaction_guard_evidence(evidence_paths)
    guard_evidence_ok = all(item["ok"] for item in guard_evidence)
    return {
        "name": run_name,
        "ok": run_ok and result_ok and evidence_ok and guard_evidence_ok and plan_contract_ok,
        "title": title,
        "validation_ok": True,
        "plan_contract_ok": plan_contract_ok,
        "run_ok": run_ok,
        "result_ok": result_ok,
        "evidence_ok": evidence_ok,
        "guard_evidence_ok": guard_evidence_ok,
        "output_dir": output_dir,
        "run_error": run_error,
        "result_file": str(result_file),
        "result_text": result_text,
        "expected_fragments": expected_fragments,
        "plan_contract": plan_contract,
        "evidence": evidence,
        "guard_evidence": guard_evidence,
        "summary": {
            "result_file_written": result_file.exists(),
            "plan_contract_count": len(plan_contract),
            "evidence_count": len(evidence),
            "guard_evidence_count": len(guard_evidence),
            "output_dir": output_dir,
        },
    }


def _windows_chat_plan(package_dir: Path) -> tuple[dict[str, Any], Path, Path, str]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mock Chat {suffix}"
    result_file = package_dir / "resources" / "mock-chat-result.txt"
    pid_file = package_dir / "resources" / "mock-chat-pid.txt"
    powershell = _powershell_executable()
    assert powershell is not None
    plan = {
        "name": "desktop controlled mock chat scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "recipient": "Alice",
            "message": "scheduled greeting",
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": _powershell_args(_windows_chat_script(title, str(result_file), str(pid_file))),
                "title_contains": title,
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 8000,
                "interval_ms": 100,
                "output": {"as": "chat_launch"},
            },
            _wait_window_step(title, "chat_window"),
            _focus_window_step(title, "chat_focus"),
            _observe_step(title, "mock-chat-observe.json", "chat_observe"),
            _dump_step(title, {"automation_id": "MockChatSearchBox", "control_type": "Edit"}, "mock-chat-search-dump.json", "chat_search_dump"),
            _set_text_step(title, {"automation_id": "MockChatSearchBox", "control_type": "Edit"}, "{{recipient}}", "chat_search_set"),
            _assert_element_step(title, {"automation_id": "MockChatRecipientLabel", "control_type": "Text"}, "Recipient: {{recipient}}", "mock-chat-recipient-assertion.json", "chat_recipient_assert"),
            _set_text_step(title, {"automation_id": "MockChatMessageBox", "control_type": "Edit"}, "{{message}}", "chat_message_set"),
            _assert_element_step(title, {"automation_id": "MockChatMessageBox", "control_type": "Edit"}, "{{message}}", "mock-chat-message-assertion.json", "chat_message_assert"),
            _invoke_step(title, {"automation_id": "MockChatSendButton", "control_type": "Button"}, "chat_send"),
            {"action": "sleep", "seconds": 0.2},
            _assert_element_step(title, {"automation_id": "MockChatStatusLabel", "control_type": "Text"}, "Sent to {{recipient}}: {{message}}", "mock-chat-status-assertion.json", "chat_status_assert"),
            _window_screenshot_step(title, "mock-chat-window.png", "chat_window_screenshot"),
            _close_window_step(title, "chat_close"),
            _wait_window_gone_step(title, "chat_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, result_file, pid_file, title


def _windows_game_plan(package_dir: Path) -> tuple[dict[str, Any], Path, Path, str]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mock Game {suffix}"
    result_file = package_dir / "resources" / "mock-game-result.txt"
    pid_file = package_dir / "resources" / "mock-game-pid.txt"
    powershell = _powershell_executable()
    assert powershell is not None
    plan = {
        "name": "desktop controlled mock game scenario",
        "automation_type": "desktop",
        "variables": {"window_title": title},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": _powershell_args(_windows_game_script(title, str(result_file), str(pid_file))),
                "title_contains": title,
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 8000,
                "interval_ms": 100,
                "output": {"as": "game_launch"},
            },
            _wait_window_step(title, "game_window"),
            _focus_window_step(title, "game_focus"),
            _observe_step(title, "mock-game-observe.json", "game_observe"),
            _assert_element_step(title, {"automation_id": "MockGameStatusLabel", "control_type": "Text"}, "Home", "mock-game-home-assertion.json", "game_home_assert"),
            _invoke_step(title, {"automation_id": "MockGameRewardButton", "control_type": "Button"}, "game_reward"),
            _assert_element_step(title, {"automation_id": "MockGameStatusLabel", "control_type": "Text"}, "Daily reward claimed", "mock-game-reward-assertion.json", "game_reward_assert"),
            _invoke_step(title, {"automation_id": "MockGameDungeonButton", "control_type": "Button"}, "game_dungeon"),
            _assert_element_step(title, {"automation_id": "MockGameStatusLabel", "control_type": "Text"}, "Dungeon ready", "mock-game-dungeon-assertion.json", "game_dungeon_assert"),
            _invoke_step(title, {"automation_id": "MockGameSkillButton", "control_type": "Button"}, "game_skill_1"),
            _invoke_step(title, {"automation_id": "MockGameSkillButton", "control_type": "Button"}, "game_skill_2"),
            _invoke_step(title, {"automation_id": "MockGameSkillButton", "control_type": "Button"}, "game_skill_3"),
            _assert_element_step(title, {"automation_id": "MockGameStatusLabel", "control_type": "Text"}, "Battle complete", "mock-game-battle-assertion.json", "game_battle_assert"),
            _invoke_step(title, {"automation_id": "MockGameCollectButton", "control_type": "Button"}, "game_collect"),
            {"action": "sleep", "seconds": 0.2},
            _assert_element_step(title, {"automation_id": "MockGameStatusLabel", "control_type": "Text"}, "Done: reward=True dungeon=1", "mock-game-status-assertion.json", "game_status_assert"),
            _window_screenshot_step(title, "mock-game-window.png", "game_window_screenshot"),
            _close_window_step(title, "game_close"),
            _wait_window_gone_step(title, "game_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, result_file, pid_file, title


def _windows_recovery_plan(package_dir: Path) -> tuple[dict[str, Any], Path, Path, str]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mock Recovery {suffix}"
    popup_title = f"AI Automate Mock Recovery Popup {suffix}"
    result_file = package_dir / "resources" / "mock-recovery-result.txt"
    pid_file = package_dir / "resources" / "mock-recovery-pid.txt"
    powershell = _powershell_executable()
    assert powershell is not None
    plan = {
        "name": "desktop controlled mock recovery scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "popup_title": popup_title,
            "payload": "recovered payload",
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": _powershell_args(_windows_recovery_script(title, popup_title, str(result_file), str(pid_file))),
                "title_contains": title,
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 8000,
                "interval_ms": 100,
                "output": {"as": "recovery_launch"},
            },
            _wait_window_step(title, "recovery_window"),
            _wait_window_step(popup_title, "recovery_popup"),
            _focus_window_step(popup_title, "recovery_popup_focus"),
            _invoke_step(popup_title, {"automation_id": "MockRecoveryPopupDismissButton", "control_type": "Button"}, "recovery_popup_dismiss"),
            _wait_window_gone_step(popup_title, "recovery_popup_closed"),
            _restore_window_step(title, "recovery_restore"),
            _focus_window_step(title, "recovery_focus"),
            _observe_step(title, "mock-recovery-observe.json", "recovery_observe"),
            _assert_element_step(title, {"automation_id": "MockRecoveryStatusLabel", "control_type": "Text"}, "Ready after recovery", "mock-recovery-ready-assertion.json", "recovery_ready_assert"),
            _set_text_step(title, {"automation_id": "MockRecoveryInputBox", "control_type": "Edit"}, "{{payload}}", "recovery_input_set"),
            _invoke_step(title, {"automation_id": "MockRecoveryActionButton", "control_type": "Button"}, "recovery_action"),
            {"action": "sleep", "seconds": 0.2},
            _assert_element_step(title, {"automation_id": "MockRecoveryStatusLabel", "control_type": "Text"}, "Recovered action completed: {{payload}}", "mock-recovery-status-assertion.json", "recovery_status_assert"),
            _window_screenshot_step(title, "mock-recovery-window.png", "recovery_window_screenshot"),
            _close_window_step(title, "recovery_close"),
            _wait_window_gone_step(title, "recovery_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, result_file, pid_file, title


def _windows_interference_plan(package_dir: Path) -> tuple[dict[str, Any], Path, Path, str]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title_prefix = f"AI Automate Mock Interference {suffix}"
    title = f"{title_prefix} Shared"
    decoy_title = title
    blocker_title = f"{title_prefix} Blocker"
    result_file = package_dir / "resources" / "mock-interference-result.txt"
    pid_file = package_dir / "resources" / "mock-interference-pid.txt"
    powershell = _powershell_executable()
    assert powershell is not None
    plan = {
        "name": "desktop controlled mock interference scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "title_prefix": title_prefix,
            "decoy_title": decoy_title,
            "blocker_title": blocker_title,
            "payload": "resumed after interference",
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": _powershell_args(
                    _windows_interference_script(
                        title,
                        decoy_title,
                        blocker_title,
                        str(result_file),
                        str(pid_file),
                    )
                ),
                "title_contains": title,
                "wait_for_window": True,
                "focus": True,
                "window_timeout_ms": 8000,
                "interval_ms": 100,
                "output": {"as": "interference_launch"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "window_id": "{{interference_launch.window.id}}",
                "state": "exists",
                "timeout_ms": 8000,
                "interval_ms": 100,
                "output": {"as": "interference_window"},
            },
            {"action": "sleep", "seconds": 0.8},
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title_prefix,
                "include_invisible": True,
                "path": "mock-interference-windows.json",
                "output": {"as": "interference_windows"},
            },
            {"action": "desktop_window", "desktop": "desktop", "type": "focus", "window_id": "{{interference_window.window.id}}", "output": {"as": "interference_focus"}},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "window_id": "{{interference_window.window.id}}",
                "include_windows": True,
                "include_elements": True,
                "include_screenshot": True,
                "path": "mock-interference-observe.json",
                "output": {"as": "interference_observe"},
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "window_id": "{{interference_window.window.id}}",
                "automation_id": "MockInterferencePrepareButton",
                "control_type": "Button",
                "output": {"as": "interference_prepare"},
                "max_depth": 5,
                "max_elements": 200,
            },
            {"action": "sleep", "seconds": 0.4},
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "window_id": "{{interference_window.window.id}}",
                "automation_id": "MockInterferenceInputBox",
                "control_type": "Edit",
                "value": "{{payload}}",
                "preserve_clipboard": False,
                "output": {"as": "interference_input_set"},
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "element_center",
                "window_id": "{{interference_window.window.id}}",
                "automation_id": "MockInterferenceActionButton",
                "control_type": "Button",
                "output": {"as": "interference_input_click"},
            },
            {"action": "write", "type": "json", "path": "mock-interference-input-click.json", "value": "{{interference_input_click}}"},
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "window_id": "{{interference_window.window.id}}",
                "automation_id": "MockInterferenceStatusLabel",
                "control_type": "Text",
                "state": "exists",
                "expected": "Completed after interference: {{payload}}",
                "mode": "equals",
                "expected_count": 1,
                "path": "mock-interference-status-assertion.json",
                "output": {"as": "interference_status_assert"},
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "window_id": "{{interference_window.window.id}}",
                "path": "mock-interference-window.png",
                "output": {"as": "interference_window_screenshot"},
            },
            _close_window_step(blocker_title, "interference_blocker_close"),
            _wait_window_gone_step(blocker_title, "interference_blocker_closed"),
            {"action": "desktop_window", "desktop": "desktop", "type": "close", "window_id": "{{interference_window.window.id}}", "output": {"as": "interference_close"}},
            _wait_window_gone_step(title, "interference_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return plan, result_file, pid_file, title


def _wait_window_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_wait",
        "desktop": "desktop",
        "type": "window",
        "title_contains": title,
        "state": "exists",
        "timeout_ms": 8000,
        "interval_ms": 100,
        "output": {"as": output_as},
    }


def _wait_window_gone_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_wait",
        "desktop": "desktop",
        "type": "window",
        "title_contains": title,
        "state": "not_exists",
        "timeout_ms": 4000,
        "interval_ms": 100,
        "output": {"as": output_as},
    }


def _focus_window_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_window",
        "desktop": "desktop",
        "type": "focus",
        "title_contains": title,
        "output": {"as": output_as},
    }


def _restore_window_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_window",
        "desktop": "desktop",
        "type": "restore",
        "title_contains": title,
        "output": {"as": output_as},
    }


def _close_window_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_window",
        "desktop": "desktop",
        "type": "close",
        "title_contains": title,
        "output": {"as": output_as},
    }


def _observe_step(title: str, path: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_capture",
        "desktop": "desktop",
        "type": "observe",
        "title_contains": title,
        "include_windows": True,
        "include_elements": True,
        "include_screenshot": True,
        "path": path,
        "output": {"as": output_as},
        "max_depth": 5,
        "max_elements": 200,
    }


def _dump_step(title: str, locator: dict[str, Any], path: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "dump",
        "title_contains": title,
        **locator,
        "path": path,
        "output": {"as": output_as},
        "max_depth": 5,
        "max_elements": 200,
    }


def _set_text_step(title: str, locator: dict[str, Any], value: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "set_text",
        "title_contains": title,
        **locator,
        "value": value,
        "preserve_clipboard": False,
        "output": {"as": output_as},
        "max_depth": 5,
        "max_elements": 200,
    }


def _invoke_step(title: str, locator: dict[str, Any], output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "invoke",
        "title_contains": title,
        **locator,
        "output": {"as": output_as},
        "max_depth": 5,
        "max_elements": 200,
    }


def _assert_element_step(title: str, locator: dict[str, Any], expected: str, path: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_assert",
        "desktop": "desktop",
        "type": "element",
        "title_contains": title,
        **locator,
        "state": "exists",
        "expected": expected,
        "mode": "equals",
        "expected_count": 1,
        "path": path,
        "output": {"as": output_as},
        "max_depth": 5,
        "max_elements": 200,
    }


def _window_screenshot_step(title: str, path: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_capture",
        "desktop": "desktop",
        "type": "screenshot",
        "target": "window",
        "title_contains": title,
        "path": path,
        "output": {"as": output_as},
    }


def _powershell_args(script: str) -> list[str]:
    return ["-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-Command", script]


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _windows_chat_script(title: str, result_path: str, pid_path: str) -> str:
    return f"""
$ResultPath = {_powershell_string(result_path)}
$PidPath = {_powershell_string(pid_path)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($ResultPath))
[System.IO.File]::WriteAllText($PidPath, [string]$PID, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($ResultPath, '', [System.Text.Encoding]::UTF8)
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 620
$form.Height = 320
$form.StartPosition = 'Manual'
$form.Left = 180
$form.Top = 180
$form.TopMost = $true
$searchLabel = New-Object System.Windows.Forms.Label
$searchLabel.Text = 'Search'
$searchLabel.Left = 24
$searchLabel.Top = 24
$searchLabel.AutoSize = $true
$searchBox = New-Object System.Windows.Forms.TextBox
$searchBox.Name = 'MockChatSearchBox'
$searchBox.Left = 100
$searchBox.Top = 20
$searchBox.Width = 360
$recipient = New-Object System.Windows.Forms.Label
$recipient.Name = 'MockChatRecipientLabel'
$recipient.Left = 100
$recipient.Top = 56
$recipient.Width = 360
$recipient.Text = 'Recipient:'
$messageLabel = New-Object System.Windows.Forms.Label
$messageLabel.Text = 'Message'
$messageLabel.Left = 24
$messageLabel.Top = 92
$messageLabel.AutoSize = $true
$messageBox = New-Object System.Windows.Forms.TextBox
$messageBox.Name = 'MockChatMessageBox'
$messageBox.Left = 100
$messageBox.Top = 88
$messageBox.Width = 360
$sendButton = New-Object System.Windows.Forms.Button
$sendButton.Name = 'MockChatSendButton'
$sendButton.AccessibleName = 'MockChatSendButton'
$sendButton.Text = 'Send'
$sendButton.Left = 470
$sendButton.Top = 86
$sendButton.Width = 96
$status = New-Object System.Windows.Forms.Label
$status.Name = 'MockChatStatusLabel'
$status.Left = 100
$status.Top = 138
$status.Width = 460
$status.Text = 'Ready'
$script:sendCount = 0
$searchBox.Add_TextChanged({{
    $recipient.Text = 'Recipient: ' + $searchBox.Text
}})
$sendButton.Add_Click({{
    $script:sendCount += 1
    $line = "recipient=$($searchBox.Text)`nmessage=$($messageBox.Text)`nsend_count=$script:sendCount"
    [System.IO.File]::WriteAllText($ResultPath, $line, [System.Text.Encoding]::UTF8)
    $status.Text = "Sent to $($searchBox.Text): $($messageBox.Text)"
}})
[void]$form.Controls.Add($searchLabel)
[void]$form.Controls.Add($searchBox)
[void]$form.Controls.Add($recipient)
[void]$form.Controls.Add($messageLabel)
[void]$form.Controls.Add($messageBox)
[void]$form.Controls.Add($sendButton)
[void]$form.Controls.Add($status)
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _windows_game_script(title: str, result_path: str, pid_path: str) -> str:
    return f"""
$ResultPath = {_powershell_string(result_path)}
$PidPath = {_powershell_string(pid_path)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($ResultPath))
[System.IO.File]::WriteAllText($PidPath, [string]$PID, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($ResultPath, '', [System.Text.Encoding]::UTF8)
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 620
$form.Height = 360
$form.StartPosition = 'Manual'
$form.Left = 220
$form.Top = 220
$form.TopMost = $true
$status = New-Object System.Windows.Forms.Label
$status.Name = 'MockGameStatusLabel'
$status.Left = 24
$status.Top = 24
$status.Width = 520
$status.Text = 'Home'
$rewardButton = New-Object System.Windows.Forms.Button
$rewardButton.Name = 'MockGameRewardButton'
$rewardButton.AccessibleName = 'MockGameRewardButton'
$rewardButton.Text = 'Claim Daily Reward'
$rewardButton.Left = 24
$rewardButton.Top = 70
$rewardButton.Width = 160
$dungeonButton = New-Object System.Windows.Forms.Button
$dungeonButton.Name = 'MockGameDungeonButton'
$dungeonButton.AccessibleName = 'MockGameDungeonButton'
$dungeonButton.Text = 'Enter Dungeon'
$dungeonButton.Left = 204
$dungeonButton.Top = 70
$dungeonButton.Width = 140
$skillButton = New-Object System.Windows.Forms.Button
$skillButton.Name = 'MockGameSkillButton'
$skillButton.AccessibleName = 'MockGameSkillButton'
$skillButton.Text = 'Skill Rotation'
$skillButton.Left = 364
$skillButton.Top = 70
$skillButton.Width = 140
$collectButton = New-Object System.Windows.Forms.Button
$collectButton.Name = 'MockGameCollectButton'
$collectButton.AccessibleName = 'MockGameCollectButton'
$collectButton.Text = 'Collect Reward'
$collectButton.Left = 24
$collectButton.Top = 120
$collectButton.Width = 160
$script:rewardClaimed = $false
$script:dungeonRuns = 0
$script:skillClicks = 0
$script:battleComplete = $false
$rewardButton.Add_Click({{
    $script:rewardClaimed = $true
    $status.Text = 'Daily reward claimed'
}})
$dungeonButton.Add_Click({{
    $script:skillClicks = 0
    $script:battleComplete = $false
    $status.Text = 'Dungeon ready'
}})
$skillButton.Add_Click({{
    $script:skillClicks += 1
    if ($script:skillClicks -lt 3) {{
        $status.Text = 'Battle stalled'
    }} else {{
        $script:battleComplete = $true
        $status.Text = 'Battle complete'
    }}
}})
$collectButton.Add_Click({{
    if ($script:rewardClaimed -and $script:battleComplete) {{
        $script:dungeonRuns += 1
        $status.Text = "Done: reward=$script:rewardClaimed dungeon=$script:dungeonRuns"
        $line = "reward=$script:rewardClaimed`ndungeon_runs=$script:dungeonRuns`nbattle_complete=$script:battleComplete"
        [System.IO.File]::WriteAllText($ResultPath, $line, [System.Text.Encoding]::UTF8)
    }} else {{
        $status.Text = 'Not ready'
    }}
}})
[void]$form.Controls.Add($status)
[void]$form.Controls.Add($rewardButton)
[void]$form.Controls.Add($dungeonButton)
[void]$form.Controls.Add($skillButton)
[void]$form.Controls.Add($collectButton)
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _windows_recovery_script(title: str, popup_title: str, result_path: str, pid_path: str) -> str:
    return f"""
$ResultPath = {_powershell_string(result_path)}
$PidPath = {_powershell_string(pid_path)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($ResultPath))
[System.IO.File]::WriteAllText($PidPath, [string]$PID, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($ResultPath, '', [System.Text.Encoding]::UTF8)
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 640
$form.Height = 330
$form.StartPosition = 'Manual'
$form.Left = 260
$form.Top = 260
$status = New-Object System.Windows.Forms.Label
$status.Name = 'MockRecoveryStatusLabel'
$status.Left = 24
$status.Top = 24
$status.Width = 560
$status.Text = 'Waiting for recovery'
$inputLabel = New-Object System.Windows.Forms.Label
$inputLabel.Text = 'Payload'
$inputLabel.Left = 24
$inputLabel.Top = 70
$inputLabel.AutoSize = $true
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.Name = 'MockRecoveryInputBox'
$inputBox.Left = 100
$inputBox.Top = 66
$inputBox.Width = 360
$actionButton = New-Object System.Windows.Forms.Button
$actionButton.Name = 'MockRecoveryActionButton'
$actionButton.AccessibleName = 'MockRecoveryActionButton'
$actionButton.Text = 'Complete Action'
$actionButton.Left = 470
$actionButton.Top = 64
$actionButton.Width = 128
$script:popupClosed = $false
$script:restored = $false
$actionButton.Add_Click({{
    if (-not $script:popupClosed) {{
        $status.Text = 'Blocked by startup notice'
        return
    }}
    $status.Text = "Recovered action completed: $($inputBox.Text)"
    $line = "popup_closed=$($script:popupClosed)`nrestored=$($script:restored)`naction=completed`npayload=$($inputBox.Text)"
    [System.IO.File]::WriteAllText($ResultPath, $line, [System.Text.Encoding]::UTF8)
}})
[void]$form.Controls.Add($status)
[void]$form.Controls.Add($inputLabel)
[void]$form.Controls.Add($inputBox)
[void]$form.Controls.Add($actionButton)
$script:popup = $null
$form.Add_Shown({{
    $form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
    $script:popup = New-Object System.Windows.Forms.Form
    $script:popup.Text = {_powershell_string(popup_title)}
    $script:popup.Width = 420
    $script:popup.Height = 180
    $script:popup.StartPosition = 'Manual'
    $script:popup.Left = 320
    $script:popup.Top = 220
    $script:popup.TopMost = $true
    $notice = New-Object System.Windows.Forms.Label
    $notice.Name = 'MockRecoveryPopupNoticeLabel'
    $notice.Left = 20
    $notice.Top = 20
    $notice.Width = 360
    $notice.Text = 'Startup notice blocks automation until dismissed'
    $dismiss = New-Object System.Windows.Forms.Button
    $dismiss.Name = 'MockRecoveryPopupDismissButton'
    $dismiss.AccessibleName = 'MockRecoveryPopupDismissButton'
    $dismiss.Text = 'Dismiss'
    $dismiss.Left = 150
    $dismiss.Top = 74
    $dismiss.Width = 110
    $dismiss.Add_Click({{
        $script:popupClosed = $true
        $script:restored = $true
        $status.Text = 'Ready after recovery'
        $script:popup.Close()
        $form.WindowState = [System.Windows.Forms.FormWindowState]::Normal
        $form.Show()
        $form.Activate()
        $form.BringToFront()
    }})
    [void]$script:popup.Controls.Add($notice)
    [void]$script:popup.Controls.Add($dismiss)
    [void]$script:popup.Show()
    $script:popup.Activate()
}})
$form.Add_FormClosing({{
    if ($script:popup -and -not $script:popup.IsDisposed) {{
        $script:popup.Close()
    }}
}})
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _windows_interference_script(
    title: str,
    decoy_title: str,
    blocker_title: str,
    result_path: str,
    pid_path: str,
) -> str:
    return f"""
$ResultPath = {_powershell_string(result_path)}
$PidPath = {_powershell_string(pid_path)}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($ResultPath))
[System.IO.File]::WriteAllText($PidPath, [string]$PID, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($ResultPath, '', [System.Text.Encoding]::UTF8)
$script:interferenceActive = $false
$script:moved = $false
$script:decoyTouched = $false
$form = New-Object System.Windows.Forms.Form
$form.Text = {_powershell_string(title)}
$form.Width = 640
$form.Height = 330
$form.StartPosition = 'Manual'
$form.Left = 180
$form.Top = 160
$status = New-Object System.Windows.Forms.Label
$status.Name = 'MockInterferenceStatusLabel'
$status.Left = 24
$status.Top = 24
$status.Width = 560
$status.Text = 'Ready'
$inputLabel = New-Object System.Windows.Forms.Label
$inputLabel.Text = 'Payload'
$inputLabel.Left = 24
$inputLabel.Top = 70
$inputLabel.AutoSize = $true
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.Name = 'MockInterferenceInputBox'
$inputBox.Left = 100
$inputBox.Top = 66
$inputBox.Width = 340
$prepareButton = New-Object System.Windows.Forms.Button
$prepareButton.Name = 'MockInterferencePrepareButton'
$prepareButton.AccessibleName = 'MockInterferencePrepareButton'
$prepareButton.Text = 'Start Interference'
$prepareButton.Left = 454
$prepareButton.Top = 62
$prepareButton.Width = 146
$actionButton = New-Object System.Windows.Forms.Button
$actionButton.Name = 'MockInterferenceActionButton'
$actionButton.AccessibleName = 'MockInterferenceActionButton'
$actionButton.Text = 'Complete'
$actionButton.Left = 454
$actionButton.Top = 106
$actionButton.Width = 146
$script:blocker = New-Object System.Windows.Forms.Form
$script:blocker.Text = {_powershell_string(blocker_title)}
$script:blocker.Width = 460
$script:blocker.Height = 190
$script:blocker.StartPosition = 'Manual'
$script:blocker.Left = 250
$script:blocker.Top = 210
$script:blocker.TopMost = $true
$blockerLabel = New-Object System.Windows.Forms.Label
$blockerLabel.Left = 18
$blockerLabel.Top = 24
$blockerLabel.Width = 400
$blockerLabel.Text = 'Topmost blocker stealing focus'
[void]$script:blocker.Controls.Add($blockerLabel)
$script:decoy = New-Object System.Windows.Forms.Form
$script:decoy.Text = {_powershell_string(decoy_title)}
$script:decoy.Width = 520
$script:decoy.Height = 230
$script:decoy.StartPosition = 'Manual'
$script:decoy.Left = 70
$script:decoy.Top = 500
$decoyStatus = New-Object System.Windows.Forms.Label
$decoyStatus.Left = 18
$decoyStatus.Top = 20
$decoyStatus.Width = 450
$decoyStatus.Text = 'Decoy window must not receive the target action'
$decoyButton = New-Object System.Windows.Forms.Button
$decoyButton.Name = 'MockInterferenceActionButton'
$decoyButton.AccessibleName = 'MockInterferenceActionButton'
$decoyButton.Text = 'Decoy Complete'
$decoyButton.Left = 18
$decoyButton.Top = 64
$decoyButton.Width = 160
$decoyButton.Add_Click({{
    $script:decoyTouched = $true
    [System.IO.File]::WriteAllText($ResultPath, 'decoy_touched=True', [System.Text.Encoding]::UTF8)
}})
[void]$script:decoy.Controls.Add($decoyStatus)
[void]$script:decoy.Controls.Add($decoyButton)
$prepareButton.Add_Click({{
    $script:interferenceActive = $true
    $script:moved = $true
    $form.Left = 430
    $form.Top = 280
    $status.Text = 'Interference active'
    $script:blocker.Show()
    $script:blocker.Activate()
    $script:blocker.BringToFront()
}})
$actionButton.Add_Click({{
    $status.Text = "Completed after interference: $($inputBox.Text)"
    $line = "interference_active=$($script:interferenceActive)`nmoved=$($script:moved)`nblocker_visible=$($script:blocker.Visible)`ncompleted=True`npayload=$($inputBox.Text)`ndecoy_touched=$($script:decoyTouched)"
    [System.IO.File]::WriteAllText($ResultPath, $line, [System.Text.Encoding]::UTF8)
}})
[void]$form.Controls.Add($status)
[void]$form.Controls.Add($inputLabel)
[void]$form.Controls.Add($inputBox)
[void]$form.Controls.Add($prepareButton)
[void]$form.Controls.Add($actionButton)
$script:decoyTimer = New-Object System.Windows.Forms.Timer
$script:decoyTimer.Interval = 250
$script:decoyTimer.Add_Tick({{
    $script:decoyTimer.Stop()
    if ($script:decoy -and -not $script:decoy.IsDisposed) {{
        $script:decoy.Show()
    }}
    $form.Activate()
    $form.BringToFront()
}})
$form.Add_Shown({{
    $form.Activate()
    $form.BringToFront()
    $script:decoyTimer.Start()
}})
$form.Add_FormClosing({{
    if ($script:decoyTimer) {{
        $script:decoyTimer.Stop()
    }}
    if ($script:blocker -and -not $script:blocker.IsDisposed) {{
        $script:blocker.Close()
    }}
    if ($script:decoy -and -not $script:decoy.IsDisposed) {{
        $script:decoy.Close()
    }}
}})
[void][System.Windows.Forms.Application]::Run($form)
""".strip()


def _powershell_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _cleanup_process(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    raw_pid = pid_file.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_pid.isdigit():
        return
    powershell = _powershell_executable()
    if not powershell:
        return
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            f"Stop-Process -Id {raw_pid} -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _required_plan_step(name: str, *, min_count: int = 1, **match: Any) -> dict[str, Any]:
    return {
        "name": name,
        "min_count": min_count,
        "match": match,
    }


def _plan_contract_evidence(plan: dict[str, Any], required_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    evidence: list[dict[str, Any]] = []
    for required in required_steps:
        match = required.get("match") if isinstance(required.get("match"), dict) else {}
        min_count = int(required.get("min_count", 1) or 1)
        matched_indices = [
            index
            for index, step in enumerate(steps, start=1)
            if isinstance(step, dict) and _step_matches_contract(step, match)
        ]
        evidence.append(
            {
                "name": str(required.get("name") or ""),
                "ok": len(matched_indices) >= min_count,
                "min_count": min_count,
                "matched_count": len(matched_indices),
                "matched_steps": matched_indices,
                "match": match,
            }
        )
    return evidence


def _step_matches_contract(step: dict[str, Any], match: dict[str, Any]) -> bool:
    for key, expected in match.items():
        if step.get(key) != expected:
            return False
    return True


def _window_list_count_evidence(path: Path, *, title_contains: str, min_count: int) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as error:
        return {
            "name": "window_list_count",
            "path": str(path),
            "ok": False,
            "reason": "json_read_failed",
            "error": str(error),
            "error_type": type(error).__name__,
        }
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    matched = [
        window
        for window in windows
        if isinstance(window, dict) and title_contains in str(window.get("title", ""))
    ]
    return {
        "name": "window_list_count",
        "path": str(path),
        "ok": len(matched) >= min_count,
        "title_contains": title_contains,
        "min_count": min_count,
        "matched_count": len(matched),
        "matched_titles": [str(window.get("title", "")) for window in matched],
    }


def _desktop_input_ownership_evidence(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as error:
        return {
            "name": "desktop_input_ownership",
            "path": str(path),
            "ok": False,
            "reason": "json_read_failed",
            "error": str(error),
            "error_type": type(error).__name__,
        }
    interaction_guard = data.get("interaction_guard") if isinstance(data.get("interaction_guard"), dict) else {}
    safety = data.get("window_safety_check") if isinstance(data.get("window_safety_check"), dict) else {}
    points = safety.get("points") if isinstance(safety.get("points"), list) else []
    ownerships = [
        point.get("ownership")
        for point in points
        if isinstance(point, dict) and isinstance(point.get("ownership"), dict)
    ]
    checked = [
        ownership
        for ownership in ownerships
        if isinstance(ownership, dict) and bool(ownership.get("checked"))
    ]
    belongs = [
        ownership
        for ownership in checked
        if bool(ownership.get("belongs_to_expected_window", ownership.get("ok")))
    ]
    inside_points = [point for point in points if isinstance(point, dict) and bool(point.get("inside_window"))]
    ok = (
        bool(interaction_guard.get("ok"))
        and bool(safety.get("ok"))
        and bool(points)
        and len(inside_points) == len(points)
        and bool(checked)
        and len(belongs) == len(checked)
    )
    return {
        "name": "desktop_input_ownership",
        "path": str(path),
        "ok": ok,
        "interaction_guard_ok": bool(interaction_guard.get("ok")),
        "window_safety_check_ok": bool(safety.get("ok")),
        "point_count": len(points),
        "inside_point_count": len(inside_points),
        "ownership_checked": bool(checked),
        "ownership_checked_count": len(checked),
        "ownership_belongs_count": len(belongs),
        "ownership_reasons": [
            str(ownership.get("reason", ""))
            for ownership in ownerships
            if isinstance(ownership, dict) and ownership.get("reason")
        ],
    }


def _evidence_file(path: Path, started_at: float) -> dict[str, Any]:
    try:
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        modified = path.stat().st_mtime if exists else 0
    except OSError:
        exists = False
        size = 0
        modified = 0
    return {
        "path": str(path),
        "ok": exists and size > 0 and modified >= started_at,
        "exists": exists,
        "size": size,
    }


def _interaction_guard_evidence(evidence_paths: list[Path]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for path in evidence_paths:
        if not path.name.endswith("observe.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as error:
            evidence.append({"path": str(path), "ok": False, "reason": "json_read_failed", "error": str(error)})
            continue
        has_guard = isinstance(data, dict) and (
            "interaction_guard" in data
            or (
                isinstance(data.get("diagnostics"), dict)
                and "interaction_guard" in data.get("diagnostics", {})
            )
        )
        evidence.append({"path": str(path), "ok": has_guard, "has_interaction_guard": has_guard})
    return evidence
