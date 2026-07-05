from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def macos_scenario_app_skip_reason() -> str:
    if not shutil.which("swiftc"):
        return "swiftc is unavailable; controlled macOS Cocoa scenario regression cannot run."
    return ""


def build_macos_chat_scenario(package_dir: Path) -> dict[str, Any]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mac Mock Chat {suffix}"
    result_file = package_dir / "resources" / "mac-mock-chat-result.txt"
    pid_file = package_dir / "resources" / "mac-mock-chat-pid.txt"
    executable = _compile_macos_mock_app(package_dir)
    plan = {
        "name": "desktop controlled macOS mock chat scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "recipient": "Alice",
            "message": "scheduled greeting",
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            _launch_step(executable, "chat", title, "", result_file, pid_file, "chat_launch"),
            _wait_window_step(title, "chat_window"),
            _focus_window_step(title, "chat_focus"),
            _observe_step(title, "mac-mock-chat-observe.json", "chat_observe"),
            _dump_step(title, {"control_type": "AXTextField", "element_match_index": 0}, "mac-mock-chat-recipient-dump.json", "chat_recipient_dump"),
            _set_text_step(title, {"control_type": "AXTextField", "element_match_index": 0}, "{{recipient}}", "chat_recipient_set"),
            _set_text_step(title, {"control_type": "AXTextField", "element_match_index": 1}, "{{message}}", "chat_message_set"),
            _invoke_step(title, {"name": "MockMacChatSendButton"}, "chat_send"),
            {"action": "sleep", "seconds": 0.3},
            _assert_element_step(
                title,
                {"text": "Sent to {{recipient}}: {{message}}"},
                "Sent to {{recipient}}: {{message}}",
                "mac-mock-chat-status-assertion.json",
                "chat_status_assert",
            ),
            _window_screenshot_step(title, "mac-mock-chat-window.png", "chat_window_screenshot"),
            _close_window_step(title, "chat_close"),
            _wait_window_gone_step(title, "chat_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return {
        "plan": plan,
        "result_file": result_file,
        "pid_file": pid_file,
        "title": title,
        "expected_fragments": ["recipient=Alice", "message=scheduled greeting", "send_count=1"],
        "evidence_paths": [
            package_dir / "output" / "desktop-state" / "mac-mock-chat-observe.json",
            package_dir / "output" / "desktop-screenshots" / "mac-mock-chat-window.png",
            package_dir / "output" / "desktop-elements" / "mac-mock-chat-status-assertion.json",
        ],
        "required_plan_steps": [
            _required_plan_step("observe_chat_window", action="desktop_capture", type="observe", path="mac-mock-chat-observe.json"),
            _required_plan_step("dump_recipient_input", action="desktop_element", type="dump", control_type="AXTextField", element_match_index=0),
            _required_plan_step("set_recipient", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=0),
            _required_plan_step("set_message", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=1),
            _required_plan_step("send_message", action="desktop_element", type="invoke", name="MockMacChatSendButton"),
            _required_plan_step("assert_sent_status", action="desktop_assert", type="element", text="Sent to {{recipient}}: {{message}}"),
            _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
            _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
        ],
    }


def build_macos_game_scenario(package_dir: Path) -> dict[str, Any]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mac Mock Game {suffix}"
    result_file = package_dir / "resources" / "mac-mock-game-result.txt"
    pid_file = package_dir / "resources" / "mac-mock-game-pid.txt"
    executable = _compile_macos_mock_app(package_dir)
    plan = {
        "name": "desktop controlled macOS mock game scenario",
        "automation_type": "desktop",
        "variables": {"window_title": title},
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            _launch_step(executable, "game", title, "", result_file, pid_file, "game_launch"),
            _wait_window_step(title, "game_window"),
            _focus_window_step(title, "game_focus"),
            _observe_step(title, "mac-mock-game-observe.json", "game_observe"),
            _assert_element_step(title, {"text": "Home"}, "Home", "mac-mock-game-home-assertion.json", "game_home_assert"),
            _invoke_step(title, {"name": "MockMacGameRewardButton"}, "game_reward"),
            _assert_element_step(title, {"text": "Daily reward claimed"}, "Daily reward claimed", "mac-mock-game-reward-assertion.json", "game_reward_assert"),
            _invoke_step(title, {"name": "MockMacGameDungeonButton"}, "game_dungeon"),
            _assert_element_step(title, {"text": "Dungeon ready"}, "Dungeon ready", "mac-mock-game-dungeon-assertion.json", "game_dungeon_assert"),
            _invoke_step(title, {"name": "MockMacGameSkillButton"}, "game_skill_1"),
            _invoke_step(title, {"name": "MockMacGameSkillButton"}, "game_skill_2"),
            _invoke_step(title, {"name": "MockMacGameSkillButton"}, "game_skill_3"),
            _assert_element_step(title, {"text": "Battle complete"}, "Battle complete", "mac-mock-game-battle-assertion.json", "game_battle_assert"),
            _invoke_step(title, {"name": "MockMacGameCollectButton"}, "game_collect"),
            {"action": "sleep", "seconds": 0.3},
            _assert_element_step(
                title,
                {"text": "Done: reward=true dungeon=1"},
                "Done: reward=true dungeon=1",
                "mac-mock-game-status-assertion.json",
                "game_status_assert",
            ),
            _window_screenshot_step(title, "mac-mock-game-window.png", "game_window_screenshot"),
            _close_window_step(title, "game_close"),
            _wait_window_gone_step(title, "game_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return {
        "plan": plan,
        "result_file": result_file,
        "pid_file": pid_file,
        "title": title,
        "expected_fragments": ["reward=true", "dungeon_runs=1", "battle_complete=true"],
        "evidence_paths": [
            package_dir / "output" / "desktop-state" / "mac-mock-game-observe.json",
            package_dir / "output" / "desktop-screenshots" / "mac-mock-game-window.png",
            package_dir / "output" / "desktop-elements" / "mac-mock-game-status-assertion.json",
        ],
        "required_plan_steps": [
            _required_plan_step("observe_game_window", action="desktop_capture", type="observe", path="mac-mock-game-observe.json"),
            _required_plan_step("claim_reward", action="desktop_element", type="invoke", name="MockMacGameRewardButton"),
            _required_plan_step("enter_dungeon", action="desktop_element", type="invoke", name="MockMacGameDungeonButton"),
            _required_plan_step("skill_rotation", min_count=3, action="desktop_element", type="invoke", name="MockMacGameSkillButton"),
            _required_plan_step("assert_battle_complete", action="desktop_assert", type="element", text="Battle complete"),
            _required_plan_step("collect_reward", action="desktop_element", type="invoke", name="MockMacGameCollectButton"),
            _required_plan_step("assert_final_status", action="desktop_assert", type="element", text="Done: reward=true dungeon=1"),
            _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
            _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
        ],
    }


def build_macos_recovery_scenario(package_dir: Path) -> dict[str, Any]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mac Mock Recovery {suffix}"
    popup_title = f"AI Automate Mac Mock Recovery Popup {suffix}"
    result_file = package_dir / "resources" / "mac-mock-recovery-result.txt"
    pid_file = package_dir / "resources" / "mac-mock-recovery-pid.txt"
    executable = _compile_macos_mock_app(package_dir)
    plan = {
        "name": "desktop controlled macOS mock recovery scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "popup_title": popup_title,
            "payload": "recovered payload",
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            _launch_step(executable, "recovery", title, popup_title, result_file, pid_file, "recovery_launch"),
            _wait_window_step(title, "recovery_window"),
            _wait_window_step(popup_title, "recovery_popup"),
            _focus_window_step(popup_title, "recovery_popup_focus"),
            _invoke_step(popup_title, {"name": "MockMacRecoveryPopupDismissButton"}, "recovery_popup_dismiss"),
            _wait_window_gone_step(popup_title, "recovery_popup_closed"),
            _restore_window_step(title, "recovery_restore"),
            _focus_window_step(title, "recovery_focus"),
            _observe_step(title, "mac-mock-recovery-observe.json", "recovery_observe"),
            _assert_element_step(
                title,
                {"text": "Ready after recovery"},
                "Ready after recovery",
                "mac-mock-recovery-ready-assertion.json",
                "recovery_ready_assert",
            ),
            _set_text_step(title, {"control_type": "AXTextField", "element_match_index": 0}, "{{payload}}", "recovery_input_set"),
            _invoke_step(title, {"name": "MockMacRecoveryActionButton"}, "recovery_action"),
            {"action": "sleep", "seconds": 0.3},
            _assert_element_step(
                title,
                {"text": "Recovered action completed: {{payload}}"},
                "Recovered action completed: {{payload}}",
                "mac-mock-recovery-status-assertion.json",
                "recovery_status_assert",
            ),
            _window_screenshot_step(title, "mac-mock-recovery-window.png", "recovery_window_screenshot"),
            _close_window_step(title, "recovery_close"),
            _wait_window_gone_step(title, "recovery_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return {
        "plan": plan,
        "result_file": result_file,
        "pid_file": pid_file,
        "title": title,
        "expected_fragments": ["popup_closed=true", "restored=true", "action=completed", "payload=recovered payload"],
        "evidence_paths": [
            package_dir / "output" / "desktop-state" / "mac-mock-recovery-observe.json",
            package_dir / "output" / "desktop-screenshots" / "mac-mock-recovery-window.png",
            package_dir / "output" / "desktop-elements" / "mac-mock-recovery-status-assertion.json",
        ],
        "required_plan_steps": [
            _required_plan_step("wait_main_window", action="desktop_wait", type="window", state="exists", title_contains=title),
            _required_plan_step("wait_popup_window", action="desktop_wait", type="window", state="exists", title_contains=popup_title),
            _required_plan_step("focus_popup", action="desktop_window", type="focus", title_contains=popup_title),
            _required_plan_step("dismiss_popup", action="desktop_element", type="invoke", title_contains=popup_title, name="MockMacRecoveryPopupDismissButton"),
            _required_plan_step("wait_popup_closed", action="desktop_wait", type="window", state="not_exists", title_contains=popup_title),
            _required_plan_step("restore_main_window", action="desktop_window", type="restore", title_contains=title),
            _required_plan_step("observe_recovered_window", action="desktop_capture", type="observe", path="mac-mock-recovery-observe.json"),
            _required_plan_step("set_payload", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=0),
            _required_plan_step("complete_action", action="desktop_element", type="invoke", name="MockMacRecoveryActionButton"),
            _required_plan_step("assert_recovered_status", action="desktop_assert", type="element", text="Recovered action completed: {{payload}}"),
            _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("close_window", action="desktop_window", type="close", title_contains=title),
            _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
        ],
    }


def build_macos_interference_scenario(package_dir: Path) -> dict[str, Any]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title_prefix = f"AI Automate Mac Mock Interference {suffix}"
    title = f"{title_prefix} Shared"
    decoy_title = f"{title_prefix} Decoy"
    blocker_title = f"{title_prefix} Blocker"
    result_file = package_dir / "resources" / "mac-mock-interference-result.txt"
    pid_file = package_dir / "resources" / "mac-mock-interference-pid.txt"
    executable = _compile_macos_mock_app(package_dir)
    plan = {
        "name": "desktop controlled macOS mock interference scenario",
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
            _launch_step(executable, "interference", title, blocker_title, result_file, pid_file, "interference_launch"),
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "window_id": "{{interference_launch.window.id}}",
                "state": "exists",
                "timeout_ms": 10000,
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
                "path": "mac-mock-interference-windows.json",
                "output": {"as": "interference_windows"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "window_id": "{{interference_window.window.id}}",
                "output": {"as": "interference_focus"},
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "observe",
                "window_id": "{{interference_window.window.id}}",
                "include_windows": True,
                "include_elements": True,
                "include_screenshot": True,
                "path": "mac-mock-interference-observe.json",
                "output": {"as": "interference_observe"},
                "max_depth": 6,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "window_id": "{{interference_window.window.id}}",
                "name": "MockMacInterferencePrepareButton",
                "output": {"as": "interference_prepare"},
                "max_depth": 6,
                "max_elements": 200,
            },
            {"action": "sleep", "seconds": 0.4},
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "window_id": "{{interference_window.window.id}}",
                "control_type": "AXTextField",
                "element_match_index": 0,
                "value": "{{payload}}",
                "preserve_clipboard": False,
                "output": {"as": "interference_input_set"},
                "max_depth": 6,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "window_id": "{{interference_window.window.id}}",
                "name": "MockMacInterferenceActionButton",
                "output": {"as": "interference_action"},
                "max_depth": 6,
                "max_elements": 200,
            },
            {"action": "sleep", "seconds": 0.3},
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "element",
                "window_id": "{{interference_window.window.id}}",
                "text": "Completed after interference: {{payload}}",
                "state": "exists",
                "expected": "Completed after interference: {{payload}}",
                "mode": "equals",
                "expected_count": 1,
                "path": "mac-mock-interference-status-assertion.json",
                "output": {"as": "interference_status_assert"},
                "max_depth": 6,
                "max_elements": 200,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "window_id": "{{interference_window.window.id}}",
                "path": "mac-mock-interference-window.png",
                "output": {"as": "interference_window_screenshot"},
            },
            _close_window_step(blocker_title, "interference_blocker_close"),
            _wait_window_gone_step(blocker_title, "interference_blocker_closed"),
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "window_id": "{{interference_window.window.id}}",
                "output": {"as": "interference_close"},
            },
            _close_window_step(decoy_title, "interference_decoy_close"),
            _wait_window_gone_step(decoy_title, "interference_decoy_closed"),
            _wait_window_gone_step(title, "interference_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return {
        "plan": plan,
        "result_file": result_file,
        "pid_file": pid_file,
        "title": title,
        "title_prefix": title_prefix,
        "window_list_path": package_dir / "output" / "desktop-windows" / "mac-mock-interference-windows.json",
        "expected_fragments": [
            "interference_active=true",
            "moved=true",
            "completed=true",
            "payload=resumed after interference",
            "decoy_touched=false",
        ],
        "evidence_paths": [
            package_dir / "output" / "desktop-state" / "mac-mock-interference-observe.json",
            package_dir / "output" / "desktop-windows" / "mac-mock-interference-windows.json",
            package_dir / "output" / "desktop-screenshots" / "mac-mock-interference-window.png",
            package_dir / "output" / "desktop-elements" / "mac-mock-interference-status-assertion.json",
        ],
        "required_plan_steps": [
            _required_plan_step(
                "wait_interference_window_by_id",
                action="desktop_wait",
                type="window",
                state="exists",
                window_id="{{interference_launch.window.id}}",
            ),
            _required_plan_step("list_interference_windows", action="desktop_window", type="list", title_contains=title_prefix),
            _required_plan_step("focus_interference_target", action="desktop_window", type="focus", window_id="{{interference_window.window.id}}"),
            _required_plan_step("observe_interference_target", action="desktop_capture", type="observe", path="mac-mock-interference-observe.json"),
            _required_plan_step("start_interference", action="desktop_element", type="invoke", name="MockMacInterferencePrepareButton"),
            _required_plan_step("set_payload_after_focus_steal", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=0),
            _required_plan_step("complete_after_focus_steal", action="desktop_element", type="invoke", name="MockMacInterferenceActionButton"),
            _required_plan_step("assert_completed_status", action="desktop_assert", type="element", text="Completed after interference: {{payload}}"),
            _required_plan_step("window_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("close_blocker", action="desktop_window", type="close", title_contains=blocker_title),
            _required_plan_step("close_window", action="desktop_window", type="close", window_id="{{interference_window.window.id}}"),
            _required_plan_step("close_decoy", action="desktop_window", type="close", title_contains=decoy_title),
            _required_plan_step("wait_closed", action="desktop_wait", type="window", state="not_exists", title_contains=title),
        ],
    }


def build_macos_file_dialog_scenario(package_dir: Path) -> dict[str, Any]:
    suffix = package_dir.name.rsplit("-", 1)[-1]
    title = f"AI Automate Mac Mock File Dialog {suffix}"
    open_dialog_title = f"AI Automate Mac Open Dialog {suffix}"
    save_dialog_title = f"AI Automate Mac Save Dialog {suffix}"
    input_file = package_dir / "resources" / "desktop-file-dialog-input.txt"
    save_file = package_dir / "resources" / "desktop-file-dialog-save.txt"
    result_file = package_dir / "resources" / "mac-mock-file-dialog-result.txt"
    pid_file = package_dir / "resources" / "mac-mock-file-dialog-pid.txt"
    expected_open_text = "desktop file dialog open payload"
    expected_save_text = "desktop file dialog save payload"
    input_file.write_text(expected_open_text, encoding="utf-8")
    if save_file.exists():
        save_file.unlink()
    executable = _compile_macos_mock_app(package_dir)
    plan = {
        "name": "desktop controlled macOS file dialog scenario",
        "automation_type": "desktop",
        "variables": {
            "window_title": title,
            "open_dialog_title": open_dialog_title,
            "save_dialog_title": save_dialog_title,
            "input_file": str(input_file),
            "save_dir": str(save_file.parent),
            "expected_open_text": expected_open_text,
            "expected_save_text": expected_save_text,
        },
        "steps": [
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            _launch_step(executable, "fileDialog", title, open_dialog_title, result_file, pid_file, "file_dialog_launch"),
            _wait_window_step(title, "file_dialog_window"),
            _focus_window_step(title, "file_dialog_focus"),
            _observe_step(title, "mac-mock-file-dialog-observe.json", "file_dialog_observe"),
            _invoke_step(title, {"name": "MockMacFileDialogOpenButton"}, "file_dialog_open_button"),
            _wait_window_step(open_dialog_title, "open_dialog_window"),
            _window_screenshot_step(open_dialog_title, "mac-open-dialog-window.png", "open_dialog_screenshot"),
            _set_text_step(open_dialog_title, {"control_type": "AXTextField", "element_match_index": 0}, "{{input_file}}", "open_dialog_path_set"),
            _invoke_step(open_dialog_title, {"name": "MockMacFileDialogOpenConfirmButton"}, "open_dialog_confirm"),
            _wait_window_gone_step(open_dialog_title, "open_dialog_closed"),
            _assert_element_step(
                title,
                {"text": "Opened: {{expected_open_text}}"},
                "Opened: {{expected_open_text}}",
                "mac-file-dialog-open-status.json",
                "file_dialog_open_status",
            ),
            _invoke_step(title, {"name": "MockMacFileDialogSaveButton"}, "file_dialog_save_button"),
            _wait_window_step(save_dialog_title, "save_dialog_window"),
            _window_screenshot_step(save_dialog_title, "mac-save-dialog-window.png", "save_dialog_screenshot"),
            _set_text_step(save_dialog_title, {"control_type": "AXTextField", "element_match_index": 0}, str(save_file), "save_dialog_path_set"),
            _invoke_step(save_dialog_title, {"name": "MockMacFileDialogSaveConfirmButton"}, "save_dialog_confirm"),
            _wait_window_gone_step(save_dialog_title, "save_dialog_closed"),
            _assert_element_step(
                title,
                {"text": "Saved: {{expected_save_text}}"},
                "Saved: {{expected_save_text}}",
                "mac-file-dialog-save-status.json",
                "file_dialog_save_status",
            ),
            _window_screenshot_step(title, "mac-file-dialog-window.png", "file_dialog_window_screenshot"),
            _close_window_step(title, "file_dialog_close"),
            _wait_window_gone_step(title, "file_dialog_closed"),
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return {
        "plan": plan,
        "result_file": result_file,
        "pid_file": pid_file,
        "title": title,
        "save_file": save_file,
        "expected_save_text": expected_save_text,
        "expected_fragments": [
            f"open_path={input_file}",
            f"open_content={expected_open_text}",
            f"save_path={save_file}",
            f"save_content={expected_save_text}",
        ],
        "evidence_paths": [
            package_dir / "output" / "desktop-state" / "mac-mock-file-dialog-observe.json",
            package_dir / "output" / "desktop-screenshots" / "mac-open-dialog-window.png",
            package_dir / "output" / "desktop-screenshots" / "mac-save-dialog-window.png",
            package_dir / "output" / "desktop-elements" / "mac-file-dialog-save-status.json",
        ],
        "required_plan_steps": [
            _required_plan_step("open_dialog_button", action="desktop_element", type="invoke", name="MockMacFileDialogOpenButton"),
            _required_plan_step("wait_open_dialog", action="desktop_wait", type="window", state="exists", title_contains=open_dialog_title),
            _required_plan_step("open_dialog_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("open_set_path", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=0),
            _required_plan_step("open_confirm", action="desktop_element", type="invoke", name="MockMacFileDialogOpenConfirmButton"),
            _required_plan_step("save_dialog_button", action="desktop_element", type="invoke", name="MockMacFileDialogSaveButton"),
            _required_plan_step("wait_save_dialog", action="desktop_wait", type="window", state="exists", title_contains=save_dialog_title),
            _required_plan_step("save_dialog_screenshot", action="desktop_capture", type="screenshot", target="window"),
            _required_plan_step("save_set_path", action="desktop_element", type="set_text", control_type="AXTextField", element_match_index=0),
            _required_plan_step("save_confirm", action="desktop_element", type="invoke", name="MockMacFileDialogSaveConfirmButton"),
            _required_plan_step("assert_save_status", action="desktop_assert", type="element", text="Saved: {{expected_save_text}}"),
        ],
    }


def _compile_macos_mock_app(package_dir: Path) -> Path:
    source_path = package_dir / "resources" / "MacScenarioMockApp.swift"
    executable_path = package_dir / "resources" / "MacScenarioMockApp"
    source_path.write_text(_MACOS_MOCK_APP_SOURCE, encoding="utf-8")
    completed = subprocess.run(
        ["swiftc", str(source_path), "-o", str(executable_path), "-framework", "AppKit"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "swiftc failed"
        raise RuntimeError(f"failed to compile macOS scenario mock app: {message}")
    return executable_path


def _launch_step(
    executable: Path,
    scenario: str,
    title: str,
    popup_title: str,
    result_file: Path,
    pid_file: Path,
    output_as: str,
) -> dict[str, Any]:
    return {
        "action": "desktop_app",
        "desktop": "desktop",
        "type": "launch",
        "command": str(executable),
        "args": [
            "--scenario",
            scenario,
            "--title",
            title,
            "--popup-title",
            popup_title or title,
            "--result",
            str(result_file),
            "--pid",
            str(pid_file),
        ],
        "title_contains": title,
        "wait_for_window": True,
        "focus": True,
        "window_timeout_ms": 10000,
        "interval_ms": 100,
        "output": {"as": output_as},
    }


def _wait_window_step(title: str, output_as: str) -> dict[str, Any]:
    return {
        "action": "desktop_wait",
        "desktop": "desktop",
        "type": "window",
        "title_contains": title,
        "state": "exists",
        "timeout_ms": 10000,
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
        "timeout_ms": 5000,
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
        "max_depth": 6,
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
        "max_depth": 6,
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
        "max_depth": 6,
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
        "max_depth": 6,
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
        "max_depth": 6,
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


def _required_plan_step(step_name: str, *, min_count: int = 1, **match: Any) -> dict[str, Any]:
    return {
        "name": step_name,
        "min_count": min_count,
        "match": match,
    }


_MACOS_MOCK_APP_SOURCE = r'''
import AppKit
import Foundation

func argumentValue(_ name: String, default defaultValue: String = "") -> String {
    let args = CommandLine.arguments
    guard let index = args.firstIndex(of: name), index + 1 < args.count else {
        return defaultValue
    }
    return args[index + 1]
}

final class ScenarioAppDelegate: NSObject, NSApplicationDelegate {
    let scenario = argumentValue("--scenario")
    let title = argumentValue("--title")
    let popupTitle = argumentValue("--popup-title")
    let resultPath = argumentValue("--result")
    let pidPath = argumentValue("--pid")

    var window: NSWindow?
    var popupWindow: NSWindow?
    var statusLabel: NSTextField?
    var recipientInput: NSTextField?
    var messageInput: NSTextField?
    var recoveryInput: NSTextField?
    var sendCount = 0
    var rewardClaimed = false
    var dungeonRuns = 0
    var skillClicks = 0
    var battleComplete = false
    var popupClosed = false
    var restored = false
    var blockerWindow: NSWindow?
    var decoyWindow: NSWindow?
    var interferenceInput: NSTextField?
    var interferenceActive = false
    var moved = false
    var decoyTouched = false
    var openPath = ""
    var openContent = ""
    var savePath = ""
    var openDialogWindow: NSWindow?
    var saveDialogWindow: NSWindow?
    var openPathInput: NSTextField?
    var savePathInput: NSTextField?
    let fileDialogSaveContent = "desktop file dialog save payload"

    func applicationDidFinishLaunching(_ notification: Notification) {
        prepareFiles()
        switch scenario {
        case "chat":
            buildChatWindow()
        case "game":
            buildGameWindow()
        case "recovery":
            buildRecoveryWindow()
        case "interference":
            buildInterferenceWindow()
        case "fileDialog":
            buildFileDialogWindow()
        default:
            buildChatWindow()
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func prepareFiles() {
        if !resultPath.isEmpty {
            let resultURL = URL(fileURLWithPath: resultPath)
            try? FileManager.default.createDirectory(at: resultURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? "".write(to: resultURL, atomically: true, encoding: .utf8)
        }
        if !pidPath.isEmpty {
            let pidURL = URL(fileURLWithPath: pidPath)
            try? FileManager.default.createDirectory(at: pidURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? "\(ProcessInfo.processInfo.processIdentifier)".write(to: pidURL, atomically: true, encoding: .utf8)
        }
    }

    func makeWindow(width: CGFloat, height: CGFloat, x: CGFloat, y: CGFloat) -> NSWindow {
        let rect = NSRect(x: x, y: y, width: width, height: height)
        let created = NSWindow(
            contentRect: rect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        created.title = title
        created.level = .floating
        created.isReleasedWhenClosed = false
        created.contentView = NSView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        created.makeKeyAndOrderFront(nil)
        created.orderFrontRegardless()
        return created
    }

    func makeButton(_ name: String, frame: NSRect, action: Selector) -> NSButton {
        let button = NSButton(frame: frame)
        button.title = name
        button.bezelStyle = .rounded
        button.target = self
        button.action = action
        button.identifier = NSUserInterfaceItemIdentifier(name)
        button.setAccessibilityLabel(name)
        return button
    }

    func makeInput(_ name: String, frame: NSRect) -> NSTextField {
        let field = NSTextField(frame: frame)
        field.stringValue = ""
        field.placeholderString = name
        field.identifier = NSUserInterfaceItemIdentifier(name)
        field.setAccessibilityLabel(name)
        return field
    }

    func makeStatus(_ initial: String, frame: NSRect, name: String) -> NSTextField {
        let label = NSTextField(labelWithString: initial)
        label.frame = frame
        label.identifier = NSUserInterfaceItemIdentifier(name)
        label.setAccessibilityLabel(name)
        label.setAccessibilityValue(initial)
        return label
    }

    func setStatus(_ text: String) {
        statusLabel?.stringValue = text
        statusLabel?.setAccessibilityValue(text)
    }

    func addLabel(_ text: String, frame: NSRect, to view: NSView) {
        let label = NSTextField(labelWithString: text)
        label.frame = frame
        view.addSubview(label)
    }

    func writeResult(_ text: String) {
        guard !resultPath.isEmpty else { return }
        try? text.write(to: URL(fileURLWithPath: resultPath), atomically: true, encoding: .utf8)
    }

    func buildChatWindow() {
        let created = makeWindow(width: 640, height: 320, x: 180, y: 520)
        guard let view = created.contentView else { return }
        addLabel("Recipient", frame: NSRect(x: 24, y: 238, width: 90, height: 24), to: view)
        let recipient = makeInput("MockMacChatRecipientInput", frame: NSRect(x: 118, y: 234, width: 330, height: 28))
        let message = makeInput("MockMacChatMessageInput", frame: NSRect(x: 118, y: 188, width: 330, height: 28))
        let send = makeButton("MockMacChatSendButton", frame: NSRect(x: 464, y: 186, width: 142, height: 32), action: #selector(sendChat))
        let status = makeStatus("Ready", frame: NSRect(x: 118, y: 140, width: 480, height: 24), name: "MockMacChatStatusLabel")
        addLabel("Message", frame: NSRect(x: 24, y: 192, width: 90, height: 24), to: view)
        view.addSubview(recipient)
        view.addSubview(message)
        view.addSubview(send)
        view.addSubview(status)
        recipientInput = recipient
        messageInput = message
        statusLabel = status
        window = created
    }

    @objc func sendChat() {
        sendCount += 1
        let recipient = recipientInput?.stringValue ?? ""
        let message = messageInput?.stringValue ?? ""
        setStatus("Sent to \(recipient): \(message)")
        writeResult("recipient=\(recipient)\nmessage=\(message)\nsend_count=\(sendCount)")
    }

    func buildGameWindow() {
        let created = makeWindow(width: 660, height: 340, x: 220, y: 480)
        guard let view = created.contentView else { return }
        let status = makeStatus("Home", frame: NSRect(x: 24, y: 270, width: 560, height: 24), name: "MockMacGameStatusLabel")
        let reward = makeButton("MockMacGameRewardButton", frame: NSRect(x: 24, y: 212, width: 180, height: 34), action: #selector(claimReward))
        let dungeon = makeButton("MockMacGameDungeonButton", frame: NSRect(x: 224, y: 212, width: 180, height: 34), action: #selector(enterDungeon))
        let skill = makeButton("MockMacGameSkillButton", frame: NSRect(x: 424, y: 212, width: 180, height: 34), action: #selector(useSkill))
        let collect = makeButton("MockMacGameCollectButton", frame: NSRect(x: 24, y: 160, width: 180, height: 34), action: #selector(collectReward))
        view.addSubview(status)
        view.addSubview(reward)
        view.addSubview(dungeon)
        view.addSubview(skill)
        view.addSubview(collect)
        statusLabel = status
        window = created
    }

    @objc func claimReward() {
        rewardClaimed = true
        setStatus("Daily reward claimed")
    }

    @objc func enterDungeon() {
        skillClicks = 0
        battleComplete = false
        setStatus("Dungeon ready")
    }

    @objc func useSkill() {
        skillClicks += 1
        if skillClicks >= 3 {
            battleComplete = true
            setStatus("Battle complete")
        } else {
            setStatus("Battle stalled")
        }
    }

    @objc func collectReward() {
        if rewardClaimed && battleComplete {
            dungeonRuns += 1
            setStatus("Done: reward=true dungeon=1")
            writeResult("reward=true\ndungeon_runs=\(dungeonRuns)\nbattle_complete=true")
        } else {
            setStatus("Not ready")
        }
    }

    func buildRecoveryWindow() {
        let created = makeWindow(width: 660, height: 320, x: 260, y: 450)
        guard let view = created.contentView else { return }
        let status = makeStatus("Waiting for recovery", frame: NSRect(x: 24, y: 250, width: 560, height: 24), name: "MockMacRecoveryStatusLabel")
        addLabel("Payload", frame: NSRect(x: 24, y: 196, width: 90, height: 24), to: view)
        let input = makeInput("MockMacRecoveryInput", frame: NSRect(x: 118, y: 192, width: 330, height: 28))
        let action = makeButton("MockMacRecoveryActionButton", frame: NSRect(x: 464, y: 190, width: 160, height: 32), action: #selector(completeRecoveryAction))
        view.addSubview(status)
        view.addSubview(input)
        view.addSubview(action)
        statusLabel = status
        recoveryInput = input
        window = created
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            created.miniaturize(nil)
            self.showRecoveryPopup()
        }
    }

    func showRecoveryPopup() {
        let popup = NSWindow(
            contentRect: NSRect(x: 320, y: 540, width: 460, height: 190),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        popup.title = popupTitle
        popup.level = .floating
        popup.isReleasedWhenClosed = false
        popup.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 460, height: 190))
        if let view = popup.contentView {
            addLabel("Startup notice blocks automation until dismissed", frame: NSRect(x: 24, y: 122, width: 390, height: 24), to: view)
            let dismiss = makeButton("MockMacRecoveryPopupDismissButton", frame: NSRect(x: 154, y: 62, width: 160, height: 34), action: #selector(dismissRecoveryPopup))
            view.addSubview(dismiss)
        }
        popupWindow = popup
        popup.makeKeyAndOrderFront(nil)
        popup.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func dismissRecoveryPopup() {
        popupClosed = true
        restored = true
        popupWindow?.close()
        popupWindow = nil
        window?.deminiaturize(nil)
        window?.makeKeyAndOrderFront(nil)
        window?.orderFrontRegardless()
        setStatus("Ready after recovery")
    }

    @objc func completeRecoveryAction() {
        if !popupClosed {
            setStatus("Blocked by startup notice")
            return
        }
        let payload = recoveryInput?.stringValue ?? ""
        setStatus("Recovered action completed: \(payload)")
        writeResult("popup_closed=\(popupClosed)\nrestored=\(restored)\naction=completed\npayload=\(payload)")
    }

    func buildInterferenceWindow() {
        let created = makeWindow(width: 660, height: 330, x: 180, y: 420)
        guard let view = created.contentView else { return }
        let status = makeStatus("Ready", frame: NSRect(x: 24, y: 260, width: 560, height: 24), name: "MockMacInterferenceStatusLabel")
        addLabel("Payload", frame: NSRect(x: 24, y: 206, width: 90, height: 24), to: view)
        let input = makeInput("MockMacInterferenceInput", frame: NSRect(x: 118, y: 202, width: 320, height: 28))
        let prepare = makeButton("MockMacInterferencePrepareButton", frame: NSRect(x: 458, y: 200, width: 168, height: 32), action: #selector(prepareInterference))
        let action = makeButton("MockMacInterferenceActionButton", frame: NSRect(x: 458, y: 154, width: 168, height: 32), action: #selector(completeInterferenceAction))
        view.addSubview(status)
        view.addSubview(input)
        view.addSubview(prepare)
        view.addSubview(action)
        statusLabel = status
        interferenceInput = input
        window = created
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            self.showInterferenceDecoy()
        }
    }

    func showInterferenceDecoy() {
        let decoy = NSWindow(
            contentRect: NSRect(x: 70, y: 590, width: 540, height: 230),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        if title.hasSuffix(" Shared") {
            decoy.title = String(title.dropLast(" Shared".count)) + " Decoy"
        } else {
            decoy.title = title + " Decoy"
        }
        decoy.level = .floating
        decoy.isReleasedWhenClosed = false
        decoy.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 540, height: 230))
        if let view = decoy.contentView {
            addLabel("Decoy window must not receive target actions", frame: NSRect(x: 24, y: 164, width: 430, height: 24), to: view)
            let input = makeInput("MockMacInterferenceInput", frame: NSRect(x: 24, y: 118, width: 290, height: 28))
            let action = makeButton("MockMacInterferenceActionButton", frame: NSRect(x: 330, y: 116, width: 170, height: 32), action: #selector(touchInterferenceDecoy))
            view.addSubview(input)
            view.addSubview(action)
        }
        decoyWindow = decoy
        decoy.makeKeyAndOrderFront(nil)
        decoy.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func prepareInterference() {
        interferenceActive = true
        moved = true
        if let target = window {
            target.setFrame(NSRect(x: 430, y: 360, width: 660, height: 330), display: true)
        }
        setStatus("Interference active")
        showInterferenceBlocker()
    }

    func showInterferenceBlocker() {
        let blocker = NSWindow(
            contentRect: NSRect(x: 360, y: 520, width: 470, height: 190),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        blocker.title = popupTitle
        blocker.level = .floating
        blocker.isReleasedWhenClosed = false
        blocker.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 470, height: 190))
        if let view = blocker.contentView {
            addLabel("Topmost blocker stealing focus", frame: NSRect(x: 24, y: 118, width: 390, height: 24), to: view)
        }
        blockerWindow = blocker
        blocker.makeKeyAndOrderFront(nil)
        blocker.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func completeInterferenceAction() {
        let payload = interferenceInput?.stringValue ?? ""
        setStatus("Completed after interference: \(payload)")
        writeResult("interference_active=\(interferenceActive)\nmoved=\(moved)\nblocker_visible=\(blockerWindow?.isVisible ?? false)\ncompleted=true\npayload=\(payload)\ndecoy_touched=\(decoyTouched)")
    }

    @objc func touchInterferenceDecoy() {
        decoyTouched = true
        writeResult("decoy_touched=true")
    }

    func buildFileDialogWindow() {
        let created = makeWindow(width: 660, height: 300, x: 240, y: 430)
        guard let view = created.contentView else { return }
        let status = makeStatus("Ready", frame: NSRect(x: 24, y: 230, width: 580, height: 24), name: "MockMacFileDialogStatusLabel")
        let openButton = makeButton("MockMacFileDialogOpenButton", frame: NSRect(x: 24, y: 168, width: 210, height: 34), action: #selector(openFileDialog))
        let saveButton = makeButton("MockMacFileDialogSaveButton", frame: NSRect(x: 254, y: 168, width: 210, height: 34), action: #selector(saveFileDialog))
        view.addSubview(status)
        view.addSubview(openButton)
        view.addSubview(saveButton)
        statusLabel = status
        window = created
    }

    @objc func openFileDialog() {
        let dialog = NSWindow(
            contentRect: NSRect(x: 310, y: 520, width: 620, height: 220),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        dialog.title = popupTitle
        dialog.level = .floating
        dialog.isReleasedWhenClosed = false
        dialog.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 620, height: 220))
        if let view = dialog.contentView {
            addLabel("Open path", frame: NSRect(x: 24, y: 142, width: 100, height: 24), to: view)
            let input = makeInput("MockMacFileDialogOpenPathInput", frame: NSRect(x: 126, y: 138, width: 340, height: 28))
            let confirm = makeButton("MockMacFileDialogOpenConfirmButton", frame: NSRect(x: 482, y: 136, width: 112, height: 32), action: #selector(confirmOpenFileDialog))
            view.addSubview(input)
            view.addSubview(confirm)
            openPathInput = input
        }
        openDialogWindow = dialog
        dialog.makeKeyAndOrderFront(nil)
        dialog.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func confirmOpenFileDialog() {
        let path = openPathInput?.stringValue ?? ""
        openPath = path
        openContent = (try? String(contentsOfFile: path, encoding: .utf8)) ?? ""
        setStatus("Opened: \(openContent)")
        writeFileDialogResult()
        openDialogWindow?.close()
        openDialogWindow = nil
    }

    @objc func saveFileDialog() {
        let dialog = NSWindow(
            contentRect: NSRect(x: 340, y: 500, width: 620, height: 220),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        dialog.title = popupTitle.replacingOccurrences(of: "Open", with: "Save")
        dialog.level = .floating
        dialog.isReleasedWhenClosed = false
        dialog.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 620, height: 220))
        if let view = dialog.contentView {
            addLabel("Save path", frame: NSRect(x: 24, y: 142, width: 100, height: 24), to: view)
            let input = makeInput("MockMacFileDialogSavePathInput", frame: NSRect(x: 126, y: 138, width: 340, height: 28))
            let confirm = makeButton("MockMacFileDialogSaveConfirmButton", frame: NSRect(x: 482, y: 136, width: 112, height: 32), action: #selector(confirmSaveFileDialog))
            view.addSubview(input)
            view.addSubview(confirm)
            savePathInput = input
        }
        saveDialogWindow = dialog
        dialog.makeKeyAndOrderFront(nil)
        dialog.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func confirmSaveFileDialog() {
        let path = savePathInput?.stringValue ?? ""
        savePath = path
        try? fileDialogSaveContent.write(toFile: path, atomically: true, encoding: .utf8)
        setStatus("Saved: \(fileDialogSaveContent)")
        writeFileDialogResult()
        saveDialogWindow?.close()
        saveDialogWindow = nil
    }

    func writeFileDialogResult() {
        writeResult("open_path=\(openPath)\nopen_content=\(openContent)\nsave_path=\(savePath)\nsave_content=\(fileDialogSaveContent)")
    }
}

let app = NSApplication.shared
let delegate = ScenarioAppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
'''
