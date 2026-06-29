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
        )


def _run_windows_recovery_scenario(project_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="desktop-scenario-recovery-") as raw_temp_dir:
        package_dir = Path(raw_temp_dir)
        (package_dir / "resources").mkdir(parents=True, exist_ok=True)
        plan, result_file, pid_file, title = _windows_recovery_plan(package_dir)
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
        )


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
) -> dict[str, Any]:
    plan_path = package_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        _cleanup_process(pid_file)
        return {
            "name": run_name,
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
        "ok": run_ok and result_ok and evidence_ok and guard_evidence_ok,
        "title": title,
        "validation_ok": True,
        "run_ok": run_ok,
        "result_ok": result_ok,
        "evidence_ok": evidence_ok,
        "guard_evidence_ok": guard_evidence_ok,
        "output_dir": output_dir,
        "run_error": run_error,
        "result_file": str(result_file),
        "result_text": result_text,
        "expected_fragments": expected_fragments,
        "evidence": evidence,
        "guard_evidence": guard_evidence,
        "summary": {
            "result_file_written": result_file.exists(),
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
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
                "save_as": "chat_launch",
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
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
                "save_as": "game_launch",
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "save_as": "desktop_probe"},
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
                "save_as": "recovery_launch",
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


def _wait_window_step(title: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_wait",
        "desktop": "desktop",
        "type": "window",
        "title_contains": title,
        "state": "exists",
        "timeout_ms": 8000,
        "interval_ms": 100,
        "save_as": save_as,
    }


def _wait_window_gone_step(title: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_wait",
        "desktop": "desktop",
        "type": "window",
        "title_contains": title,
        "state": "not_exists",
        "timeout_ms": 4000,
        "interval_ms": 100,
        "save_as": save_as,
    }


def _focus_window_step(title: str, save_as: str) -> dict[str, Any]:
    return {"action": "desktop_window", "desktop": "desktop", "type": "focus", "title_contains": title, "save_as": save_as}


def _restore_window_step(title: str, save_as: str) -> dict[str, Any]:
    return {"action": "desktop_window", "desktop": "desktop", "type": "restore", "title_contains": title, "save_as": save_as}


def _close_window_step(title: str, save_as: str) -> dict[str, Any]:
    return {"action": "desktop_window", "desktop": "desktop", "type": "close", "title_contains": title, "save_as": save_as}


def _observe_step(title: str, path: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_capture",
        "desktop": "desktop",
        "type": "observe",
        "title_contains": title,
        "include_windows": True,
        "include_elements": True,
        "include_screenshot": True,
        "path": path,
        "save_as": save_as,
        "max_depth": 5,
        "max_elements": 200,
    }


def _dump_step(title: str, locator: dict[str, Any], path: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "dump",
        "title_contains": title,
        **locator,
        "path": path,
        "save_as": save_as,
        "max_depth": 5,
        "max_elements": 200,
    }


def _set_text_step(title: str, locator: dict[str, Any], value: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "set_text",
        "title_contains": title,
        **locator,
        "value": value,
        "preserve_clipboard": False,
        "save_as": save_as,
        "max_depth": 5,
        "max_elements": 200,
    }


def _invoke_step(title: str, locator: dict[str, Any], save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_element",
        "desktop": "desktop",
        "type": "invoke",
        "title_contains": title,
        **locator,
        "save_as": save_as,
        "max_depth": 5,
        "max_elements": 200,
    }


def _assert_element_step(title: str, locator: dict[str, Any], expected: str, path: str, save_as: str) -> dict[str, Any]:
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
        "save_as": save_as,
        "max_depth": 5,
        "max_elements": 200,
    }


def _window_screenshot_step(title: str, path: str, save_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_capture",
        "desktop": "desktop",
        "type": "screenshot",
        "target": "window",
        "title_contains": title,
        "path": path,
        "save_as": save_as,
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
