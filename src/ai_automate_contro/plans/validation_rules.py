from __future__ import annotations

from ai_automate_contro.ai.schemas import AI_TASK_TYPES


ACTION_TYPES: dict[str, set[str]] = {
    "variable": {"set", "set_many", "copy"},
    "page": {"open", "switch", "close"},
    "navigate": {"goto", "refresh", "back", "forward"},
    "element": {"click", "hover", "fill", "clear", "type", "focus", "press", "check", "uncheck", "select", "set_files"},
    "wait": {"time", "selector", "url", "text", "count"},
    "extract": {"text", "value", "attribute", "html", "count", "all_texts", "all_values", "table"},
    "keyboard": {"press", "type", "down", "up"},
    "scroll": {"into_view", "by"},
    "mouse": {"move", "click", "down", "up", "wheel"},
    "capture": {"screenshot", "html", "storage_state"},
    "dialog": {"accept", "dismiss"},
    "wait_for_network": {"request", "response"},
    "write": {"json", "text", "csv", "variables"},
    "read": {"json", "text", "csv", "storage_state"},
    "assert": {"selector", "text", "value", "url", "count"},
    "ai": AI_TASK_TYPES,
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "variable": ("type",),
    "run_sub_plan": ("path",),
    "open_browser": ("name",),
    "page": ("browser", "type"),
    "close_browser": ("browser",),
    "navigate": ("browser", "type"),
    "element": ("browser", "type", "selector"),
    "wait": ("browser",),
    "detect_challenge": ("browser", "save_as"),
    "ai": ("type", "input", "save_as"),
    "extract": ("browser", "type", "save_as"),
    "keyboard": ("browser", "type"),
    "scroll": ("browser",),
    "mouse": ("browser", "type"),
    "capture": ("browser", "type", "path"),
    "manual_confirm": (),
    "print": ("message",),
    "dialog": ("type",),
    "wait_for_download": ("browser", "path", "trigger"),
    "wait_for_popup": ("browser", "popup_page", "trigger"),
    "wait_for_network": ("browser", "type", "url", "trigger"),
    "write": ("type", "path"),
    "read": ("type", "path", "save_as"),
    "assert": ("browser", "type"),
    "if": ("condition",),
    "foreach": ("items", "steps"),
    "retry": ("steps",),
    "sleep": ("seconds",),
}

OUTPUT_ACTION_CATEGORIES: dict[tuple[str, str], str] = {
    ("capture", "screenshot"): "screenshots",
    ("capture", "html"): "html",
    ("capture", "storage_state"): "storage-states",
    ("wait_for_download", ""): "downloads",
    ("write", "json"): "json",
    ("write", "text"): "text",
    ("write", "csv"): "csv",
    ("write", "variables"): "variables",
    ("ai", "connectivity"): "ai",
    ("ai", "extract_data"): "ai",
    ("ai", "classify_text"): "ai",
    ("ai", "transform_data"): "ai",
    ("ai", "summarize_text"): "ai",
}

FORBIDDEN_OUTPUT_ROOTS = {"output", "resources", "docs", "sub-plans"}
