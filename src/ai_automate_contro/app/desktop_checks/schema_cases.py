from __future__ import annotations

from typing import Any


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
                        "output": {"as": "launch_result"},
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
