from __future__ import annotations

import base64
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


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
                    "output": {"as": "entry_window_vision"},
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
                    "output": {"as": "entry_element_vision"},
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
                        "output": {"as": "clipboard_seed"},
                    },
                    {
                        "action": "desktop_input",
                        "desktop": "desktop",
                        "type": "type_text",
                        "value": "{{clipboard_text}}",
                        "method": "clipboard",
                        "preserve_clipboard": True,
                        "output": {"as": "clipboard_type_text"},
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
                        "output": {"as": "clipboard_after"},
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
                        "output": {"as": "clipboard_assertion"},
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
                "output": {"as": "agree_checkbox"},
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
                        "output": {"as": "context_menu_invoke"},
                    },
                    {
                        "action": "desktop_element",
                        "desktop": "desktop",
                        "type": "click",
                        "title_contains": title,
                        **checkbox_locator,
                        "output": {"as": "agree_checkbox_click"},
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
                        "output": {"as": "mouse_panel_focus_click"},
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
                        "output": {"as": "mouse_panel_double_click"},
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
                        "output": {"as": "mouse_panel_right_click"},
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
                        "output": {"as": "mouse_panel_scroll"},
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
                        "output": {"as": "mouse_panel_drag"},
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
                    "output": {"as": "mode_combo_state"},
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
                    "output": {"as": "mode_combo_select"},
                    "max_depth": 5,
                    "max_elements": 200,
                },
                {
                    "action": "desktop_element",
                    "desktop": "desktop",
                    "type": "find",
                    "title_contains": title,
                    **list_locator,
                    "output": {"as": "options_list"},
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
                    "output": {"as": "options_list_select"},
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
                    "output": {"as": "orders_table"},
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
                    "output": {"as": "orders_cell"},
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
                    "output": {"as": "nav_tree"},
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
                    "output": {"as": "nav_tree_expand"},
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
                    "output": {"as": "nav_tree_select"},
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
                    "output": {"as": "nav_tree_collapse"},
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
                    "output": {"as": "menu_invoke"},
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
                        "output": {"as": "scroll_panel"},
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
                        "output": {"as": "scroll_target_state"},
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
                "output": {"as": "status_assertion"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {"action": "write", "type": "json", "path": "desktop-probe.json", "value": "{{desktop_probe}}"},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": app_command,
                "args": app_args,
                "output": {"as": "app_launch"},
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
                "output": {"as": "app_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_focus"},
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
                "output": {"as": "form_observation"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "candidate",
                "candidate_source": "latest",
                "candidate_id": "{{form_observation.target_candidates.best_candidate.candidate_id}}",
                "min_confidence": "medium",
                "output": {"as": "entry_latest_candidate_click"},
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
                "output": {"as": "form_window_capture"},
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
                "output": {"as": "form_entry_capture"},
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
                "output": {"as": "form_vision_capture"},
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
                "output": {"as": "form_elements"},
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
                "output": {"as": "form_elements_dump"},
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
                "output": {"as": "entry_candidate_click"},
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
                "output": {"as": "entry_bounds_center_click"},
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
                "output": {"as": "entry_set_text"},
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
                "output": {"as": "entry_assertion"},
                "max_depth": 5,
                "max_elements": 200,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "output": {"as": "save_button_invoke"},
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
                "output": {"as": "content_assertion"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "output": {"as": "app_close"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "output": {"as": "app_closed"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": app_args,
                "output": {"as": "app_launch"},
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
                "output": {"as": "app_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_focus"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "wpf-elements.json",
                "output": {"as": "wpf_elements"},
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
                "output": {"as": "wpf_entry_dump"},
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
                "output": {"as": "wpf_window_capture"},
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
                "output": {"as": "wpf_entry_capture"},
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
                "output": {"as": "wpf_entry_set_text"},
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
                "output": {"as": "wpf_entry_state"},
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
                "output": {"as": "wpf_entry_assertion"},
                "max_depth": 8,
                "max_elements": 600,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": title,
                **checkbox_locator,
                "output": {"as": "wpf_agree_click"},
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
                "output": {"as": "wpf_mode_select"},
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
                "output": {"as": "wpf_options_select"},
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
                "output": {"as": "wpf_orders_table"},
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
                "output": {"as": "wpf_orders_cell"},
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
                "output": {"as": "wpf_nav_tree"},
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
                "output": {"as": "wpf_nav_tree_expand"},
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
                "output": {"as": "wpf_nav_tree_select"},
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
                "output": {"as": "wpf_nav_tree_collapse"},
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
                "output": {"as": "wpf_menu_invoke"},
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
                "output": {"as": "wpf_context_menu_invoke"},
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
                "output": {"as": "wpf_scroll_viewer"},
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
                "output": {"as": "wpf_scroll_target_state"},
                "max_depth": 10,
                "max_elements": 1000,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "output": {"as": "wpf_save_invoke"},
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
                "output": {"as": "wpf_content_assertion"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "output": {"as": "wpf_app_close"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "output": {"as": "wpf_app_closed"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "command",
                "type": "run",
                "command": (
                    f"$file = {_powershell_string(absolute_assertion_file)}; "
                    "Set-Content -LiteralPath $file -Value ''; "
                    "Write-Output $file"
                ),
                "timeout_ms": 10000,
                "output": {"as": "app_file_created"},
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
                "output": {"as": "app_launch"},
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
                "output": {"as": "active_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "title_contains": title,
                "path": "real-app-window-find.json",
                "output": {"as": "found_window"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "exists",
                "timeout_ms": 8000,
                "output": {"as": "app_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_focus"},
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": title,
                "timeout_ms": 2000,
                "output": {"as": "app_focused_assertion"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "maximize",
                "title_contains": title,
                "output": {"as": "app_maximize"},
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": title,
                "path": "real-app-maximized-window.png",
                "output": {"as": "app_maximized_screenshot"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "minimize",
                "title_contains": title,
                "output": {"as": "app_minimize"},
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "restore",
                "title_contains": title,
                "output": {"as": "app_restore"},
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_refocus_after_restore"},
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": title,
                "timeout_ms": 2000,
                "output": {"as": "app_restored_focused_assertion"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "active",
                "path": "real-app-restored-active-window.json",
                "output": {"as": "restored_active_window"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "real-app-elements.json",
                "output": {"as": "app_elements"},
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "title_contains": title,
                **textbox_locator,
                "output": {"as": "app_textbox_element"},
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": title,
                **textbox_locator,
                "output": {"as": "app_textbox_state"},
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "set_text",
                "title_contains": title,
                **textbox_locator,
                "value": "{{expected_text}}",
                "output": {"as": "app_textbox_set_text"},
                "max_depth": 4,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "invoke",
                "title_contains": title,
                **button_locator,
                "output": {"as": "app_save_invoke"},
                "max_depth": 4,
            },
            {"action": "sleep", "seconds": 0.2},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "output": {"as": "app_screenshot"},
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
                "output": {"as": "app_close"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "output": {"as": "app_closed"},
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
                "output": {"as": "content_assertion"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
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
                "output": {"as": "explorer_launch"},
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
                "output": {"as": "explorer_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "output": {"as": "explorer_focus"},
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
                "output": {"as": "explorer_focused"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "list",
                "path": "explorer-windows.json",
                "output": {"as": "explorer_windows"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "path": "explorer-window-find.json",
                "output": {"as": "explorer_found_window"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "explorer",
                "title_contains": "{{folder_name}}",
                "path": "explorer-elements.json",
                "output": {"as": "explorer_elements"},
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
                "output": {"as": "explorer_sample_file"},
                "max_depth": 6,
                "max_elements": 500,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "explorer-screen.png",
                "output": {"as": "explorer_screen"},
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
                "output": {"as": "explorer_close"},
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
                "output": {"as": "explorer_closed"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
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
                "output": {"as": "terminal_launch"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "find",
                "title_contains": "{{terminal_title}}",
                "path": "terminal-window-find.json",
                "output": {"as": "terminal_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "active",
                "path": "terminal-active-window.json",
                "output": {"as": "terminal_active"},
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "title_contains": "{{terminal_title}}",
                "state": "focused",
                "timeout_ms": 3000,
                "interval_ms": 100,
                "output": {"as": "terminal_focused"},
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "target": "window",
                "title_contains": "{{terminal_title}}",
                "path": "terminal-window.png",
                "output": {"as": "terminal_screenshot"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "current_window_center",
                "output": {"as": "terminal_click"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": typed_command,
                "method": "clipboard",
                "preserve_clipboard": False,
                "output": {"as": "terminal_command_typed"},
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
                "output": {"as": "terminal_closed"},
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
                "output": {"as": "terminal_result_assertion"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "command": powershell,
                "args": app_args,
                "output": {"as": "app_launch"},
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
                "output": {"as": "app_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_focus"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "output": {"as": "app_focus_click"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": title,
                "path": "file-dialog-form-elements.json",
                "output": {"as": "form_elements"},
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_refocus_before_open"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "output": {"as": "app_focus_click_before_open"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["ctrl", "o"],
                "output": {"as": "open_button_click"},
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
                "output": {"as": "open_dialog_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "output": {"as": "open_dialog_focus"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "file_dialog_open",
                "title_contains": open_dialog_title,
                "path": "open-dialog-elements.json",
                "output": {"as": "open_dialog_elements"},
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
                "output": {"as": "open_dialog_screen"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{input_file}}",
                "method": "clipboard",
                "preserve_clipboard": False,
                "output": {"as": "open_dialog_path_typed"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["enter"],
                "output": {"as": "open_dialog_accept"},
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
                "output": {"as": "open_dialog_closed"},
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
                "output": {"as": "open_status_assertion"},
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": title,
                "output": {"as": "app_refocus_before_save"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "bounds_center",
                "bounds": {"x": 160, "y": 160, "width": 660, "height": 260},
                "output": {"as": "app_focus_click_before_save"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["ctrl", "s"],
                "output": {"as": "save_button_click"},
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
                "output": {"as": "save_dialog_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "output": {"as": "save_dialog_focus"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "profile": "file_dialog_save",
                "title_contains": save_dialog_title,
                "path": "save-dialog-elements.json",
                "output": {"as": "save_dialog_elements"},
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
                "output": {"as": "save_dialog_screen"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{save_file}}",
                "method": "clipboard",
                "preserve_clipboard": False,
                "output": {"as": "save_dialog_path_typed"},
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "hotkey",
                "keys": ["enter"],
                "output": {"as": "save_dialog_accept"},
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
                "output": {"as": "save_dialog_closed"},
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
                "output": {"as": "save_status_assertion"},
                "max_depth": 5,
                "max_elements": 250,
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "file-dialog-final-screen.png",
                "output": {"as": "file_dialog_screenshot"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "close",
                "title_contains": title,
                "output": {"as": "app_close"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": title,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "output": {"as": "app_closed"},
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
            {"action": "open_desktop", "name": "desktop", "backend": "auto", "output": {"as": "desktop_probe"}},
            {
                "action": "command",
                "type": "run",
                "command": (
                    f"file=\"{absolute_assertion_file}\"; "
                    ": > \"$file\"; "
                    "printf '%s\\n' \"$file\""
                ),
                "timeout_ms": 10000,
                "output": {"as": "app_file_created"},
            },
            {
                "action": "desktop_app",
                "desktop": "desktop",
                "type": "launch",
                "app": "TextEdit",
                "args": [absolute_assertion_file],
                "output": {"as": "app_launch"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": file_name,
                "state": "exists",
                "timeout_ms": 10000,
                "output": {"as": "app_window"},
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "focus",
                "title_contains": file_name,
                "output": {"as": "app_focus"},
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "window",
                "state": "focused",
                "title_contains": file_name,
                "timeout_ms": 2000,
                "output": {"as": "app_focused_assertion"},
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "list",
                "title_contains": file_name,
                "path": "real-app-elements.json",
                "output": {"as": "app_elements"},
                "max_depth": 4,
                "max_elements": 250,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "find",
                "title_contains": file_name,
                "name_contains": file_name,
                "output": {"as": "app_window_element"},
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_text",
                "title_contains": file_name,
                "name_contains": file_name,
                "output": {"as": "app_window_element_text"},
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "get_state",
                "title_contains": file_name,
                "name_contains": file_name,
                "output": {"as": "app_window_element_state"},
                "max_depth": 2,
            },
            {
                "action": "desktop_element",
                "desktop": "desktop",
                "type": "click",
                "title_contains": file_name,
                "name_contains": file_name,
                "output": {"as": "app_element_click"},
                "max_depth": 2,
            },
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "click",
                "target": "current_window_center",
                "output": {"as": "app_click"},
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["command", "a"]},
            {
                "action": "desktop_input",
                "desktop": "desktop",
                "type": "type_text",
                "value": "{{expected_text}}",
                "method": "clipboard",
                "output": {"as": "typed_text"},
            },
            {"action": "desktop_input", "desktop": "desktop", "type": "hotkey", "keys": ["command", "s"]},
            {"action": "sleep", "seconds": 0.5},
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "real-app-screen.png",
                "output": {"as": "app_screenshot"},
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
                "output": {"as": "app_close"},
            },
            {
                "action": "desktop_wait",
                "desktop": "desktop",
                "type": "window",
                "title_contains": file_name,
                "state": "not_exists",
                "timeout_ms": 4000,
                "interval_ms": 100,
                "output": {"as": "app_closed"},
            },
            {
                "action": "command",
                "type": "run",
                "command": (
                    "content=$(cat resources/desktop-textedit-input.txt); "
                    "case \"$content\" in *\"{{expected_text}}\"*) exit 0;; *) echo \"typed text missing: $content\" >&2; exit 7;; esac"
                ),
                "timeout_ms": 10000,
                "output": {"as": "content_assertion"},
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


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False
