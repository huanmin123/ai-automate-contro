from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from playwright.sync_api import Frame, FrameLocator, Locator, Page

from ai_automate_contro.engine.conditions import ConditionEvaluator
from ai_automate_contro.engine.runtime import RuntimeState
from ai_automate_contro.engine.template import render_value
from ai_automate_contro.plans.validation_rules import ACTIONS_BY_AUTOMATION_TYPE
from ai_automate_contro.support.platforms import current_platform_name, normalize_platform_name, platform_lookup_keys

from . import (
    ai_task,
    basic,
    browser_capture,
    browser_dialogs,
    browser_events,
    browser_flow,
    browser_input,
    browser_state,
    command,
    control_flow,
    desktop,
    extraction,
    failure_capture,
    http_client,
    mongo_client,
    redis_client,
    sql_client,
)


EXTERNAL_ACTION_MODULES = (
    ai_task,
    basic,
    browser_capture,
    browser_dialogs,
    browser_events,
    browser_flow,
    browser_input,
    browser_state,
    command,
    control_flow,
    desktop,
    extraction,
    http_client,
    mongo_client,
    redis_client,
    sql_client,
)


class ActionExecutor:
    def __init__(self, state: RuntimeState) -> None:
        self.state = state
        self.conditions = ConditionEvaluator(state)

    def run(self, steps: list[dict[str, Any]]) -> None:
        for raw_step in steps:
            self._raise_if_interrupted()
            self._run_step(raw_step)
            self._raise_if_interrupted()

    def _run_step(self, raw_step: dict[str, Any]) -> None:
        self._raise_if_interrupted()
        action = raw_step["action"]
        if action in {"if", "foreach", "retry", "trigger"}:
            step = raw_step
        else:
            step = render_value(raw_step, self.state.variables)
        step = self._apply_platform_overrides(step, action=str(action))
        step_number = self.state.next_step_number()
        step_name = step.get("name", action)
        step_summary = _step_progress_summary(action, step)
        self.state.logger.log(
            "info",
            f"step {step_number} start",
            step=step_number,
            action=action,
            step_name=step_name,
            step_summary=step_summary,
        )
        self.state.state_writer.mark_step_started(step=step_number, action=action, step_name=step_name)
        handler = self._resolve_action_handler(action)
        if handler is None:
            raise ValueError(f"Unsupported action: {action}")
        self._ensure_action_allowed(action)

        try:
            handler(step)
        except Exception as error:
            failure_capture.capture_failure_state(
                self.state,
                step_number=step_number,
                action=action,
                step_name=step_name,
                step_summary=step_summary,
                step=step,
                error=error,
            )
            self.state.logger.log(
                "error",
                f"step {step_number} failed",
                step=step_number,
                action=action,
                step_name=step_name,
                step_summary=step_summary,
                error=str(error),
            )
            raise

        self.state.logger.log(
            "info",
            f"step {step_number} finished",
            step=step_number,
            action=action,
            step_name=step_name,
            step_summary=step_summary,
        )
        self.state.state_writer.mark_step_finished(step=step_number, action=action, step_name=step_name)

    def _raise_if_interrupted(self) -> None:
        checker = getattr(self.state, "interrupt_requested", None)
        if callable(checker) and checker():
            raise KeyboardInterrupt("用户中断。")

    def _wait_for_timeout(self, page: Page, milliseconds: int, *, chunk_ms: int = 200) -> None:
        remaining = max(0, int(milliseconds))
        while remaining > 0:
            self._raise_if_interrupted()
            step_ms = min(remaining, max(1, int(chunk_ms)))
            page.wait_for_timeout(step_ms)
            remaining -= step_ms
        self._raise_if_interrupted()

    def _resolve_action_handler(self, action: str) -> Any | None:
        for module in EXTERNAL_ACTION_MODULES:
            if action in module.ACTION_HANDLERS:
                return (
                    lambda step, selected_module=module, selected_action=action: selected_module.ACTION_HANDLERS[
                        selected_action
                    ](self, step)
                )
        return getattr(self, f"_action_{action}", None)

    def _ensure_action_allowed(self, action: str) -> None:
        automation_type = getattr(self.state, "automation_type", "")
        allowed_actions = ACTIONS_BY_AUTOMATION_TYPE.get(automation_type)
        if allowed_actions is None or action in allowed_actions:
            return
        raise ValueError(f"automation_type={automation_type} 不支持 action：{action}")

    def _apply_platform_overrides(self, step: dict[str, Any], *, action: str) -> dict[str, Any]:
        if "platform_overrides" not in step:
            return step
        overrides = step.get("platform_overrides")
        base_step = {key: deepcopy(value) for key, value in step.items() if key != "platform_overrides"}
        if overrides in (None, ""):
            return base_step
        if not isinstance(overrides, Mapping):
            raise ValueError("platform_overrides 必须是对象，键为平台名，值为要覆盖的 step 字段。")
        platform_name = self._step_platform_name(base_step)
        selected_override: Any = None
        for key in platform_lookup_keys(platform_name):
            if key in overrides:
                selected_override = overrides[key]
                break
        if selected_override is None and "default" in overrides:
            selected_override = overrides["default"]
        if selected_override is None:
            return base_step
        if not isinstance(selected_override, Mapping):
            raise ValueError(f"platform_overrides.{platform_name} 必须是对象。")
        if "action" in selected_override and selected_override["action"] != action:
            raise ValueError("platform_overrides 不允许切换 action；请保持同一 action 名称并只覆盖参数。")
        return _merge_platform_override(base_step, selected_override, action=action, top_level=True)

    def _step_platform_name(self, step: dict[str, Any]) -> str:
        desktop_name = step.get("desktop")
        if isinstance(desktop_name, str) and desktop_name in self.state.desktop_sessions:
            return normalize_platform_name(self.state.desktop_sessions[desktop_name].platform)
        if step.get("action") == "open_desktop":
            raw_platform = step.get("platform", "auto")
            if str(raw_platform or "auto") == "auto":
                return current_platform_name()
            return normalize_platform_name(str(raw_platform))
        return current_platform_name()

    @staticmethod
    def external_action_handlers() -> set[str]:
        handlers: set[str] = set()
        for module in EXTERNAL_ACTION_MODULES:
            handlers.update(module.ACTION_HANDLERS)
        return handlers

    def _locator(self, step: dict[str, Any]) -> Locator:
        root = self._locator_root(step)
        locator = self._root_locator(root, step)
        if "index" in step:
            locator = locator.nth(int(step["index"]))
        return locator

    def _root_locator(self, root: Page | Frame | FrameLocator, step: dict[str, Any]) -> Locator:
        if "selector" in step:
            return root.locator(step["selector"])
        if "role" in step:
            options = _locator_options(step, "name", "exact")
            return root.get_by_role(step["role"], **options)
        if "text" in step:
            return root.get_by_text(str(step["text"]), exact=bool(step.get("exact", False)))
        if "label" in step:
            return root.get_by_label(str(step["label"]), exact=bool(step.get("exact", False)))
        if "placeholder" in step:
            return root.get_by_placeholder(str(step["placeholder"]), exact=bool(step.get("exact", False)))
        if "alt_text" in step:
            return root.get_by_alt_text(str(step["alt_text"]), exact=bool(step.get("exact", False)))
        if "title" in step:
            return root.get_by_title(str(step["title"]), exact=bool(step.get("exact", False)))
        if "test_id" in step:
            return root.get_by_test_id(str(step["test_id"]))
        raise ValueError("需要 selector 或一种语义定位字段。")

    def _locator_for_selector(
        self,
        step: dict[str, Any],
        selector: str,
        *,
        index_field: str = "index",
    ) -> Locator:
        root = self._locator_root(step)
        locator = root.locator(selector)
        if index_field in step:
            locator = locator.nth(int(step[index_field]))
        return locator

    def _locator_root(self, step: dict[str, Any]) -> Page | Frame | FrameLocator:
        page = self._page(step)
        frame_fields = [
            field
            for field in ("frame_selector", "frame_name", "frame_url", "frame_url_contains", "frame_index")
            if field in step
        ]
        if not frame_fields:
            return page
        if len(frame_fields) > 1:
            raise ValueError(f"只能同时使用一种 frame 定位字段，当前包含：{', '.join(frame_fields)}")
        if "frame_selector" in step:
            return page.frame_locator(step["frame_selector"])
        if "frame_name" in step:
            frame = page.frame(name=str(step["frame_name"]))
        elif "frame_url" in step:
            frame = page.frame(url=str(step["frame_url"]))
        elif "frame_url_contains" in step:
            expected = str(step["frame_url_contains"])
            frame = next((candidate for candidate in page.frames if expected in candidate.url), None)
        else:
            frame = _frame_by_index(page, int(step["frame_index"]))
        if frame is None:
            raise ValueError("未找到匹配的 frame。")
        return frame

    def _page(self, step: dict[str, Any]) -> Page:
        session = self.state.require_session(step["browser"])
        return session.require_page(step.get("page"))

    def _resolve_path(self, raw_path: str) -> Path:
        return self.state.resolve_path(raw_path)

    def _resolve_output_path(self, raw_path: str, category: str | None = None) -> Path:
        return self.state.resolve_output_path(raw_path, category=category)

    def _package_root(self) -> Path:
        return self.state.package_dir or self.state.plan_dir

    def _handle_dialog(self, dialog: Any) -> None:
        self.state.pending_dialog = dialog
        self.state.last_dialog_message = dialog.message
        self.state.logger.log("info", "dialog captured", dialog_type=dialog.type, dialog_message=dialog.message)


def _locator_options(step: dict[str, Any], *allowed_fields: str) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for field in allowed_fields:
        if field in step:
            options[field] = step[field]
    return options


def _merge_platform_override(
    base: dict[str, Any],
    override: Mapping[str, Any],
    *,
    action: str,
    top_level: bool = False,
) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if key == "platform_overrides":
            continue
        if top_level and key == "action":
            if value != action:
                raise ValueError("platform_overrides 不允许切换 action；请保持同一 action 名称并只覆盖参数。")
            continue
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _merge_platform_override(current, value, action=action)
        else:
            merged[key] = deepcopy(value)
    if top_level:
        merged["action"] = action
    return merged


def _step_progress_summary(action: str, step: dict[str, Any]) -> str:
    safe_fields_by_action = {
        "open_browser": ("name", "headed", "browser_type", "device", "use_profile"),
        "navigate": ("browser", "page", "type", "url", "wait_until"),
        "page": ("browser", "type", "page", "url"),
        "element": (
            "browser",
            "page",
            "type",
            "selector",
            "role",
            "name",
            "text",
            "label",
            "placeholder",
            "test_id",
            "key",
            "index",
        ),
        "wait": ("browser", "page", "type", "selector", "text", "url", "timeout_ms", "state"),
        "capture": ("browser", "page", "type", "path", "full_page"),
        "read": ("type", "path", "sheet", "sheets", "range", "offset_rows", "limit_rows", "preview_rows", "max_cells", "output"),
        "write": ("type", "path", "sheet", "sheets", "range", "start_cell", "formula_columns"),
        "assert": ("browser", "page", "type", "selector", "text", "url", "expected"),
        "extract": ("browser", "page", "type", "selector", "output"),
        "input": (
            "browser",
            "page",
            "device",
            "type",
            "selector",
            "role",
            "name",
            "text",
            "test_id",
            "key",
            "value",
            "x",
            "y",
            "delta_x",
            "delta_y",
        ),
        "manual_confirm": ("browser", "prompt"),
        "run_sub_plan": ("path",),
        "trigger": ("type", "name", "every_seconds", "max_runs", "duration_seconds", "path", "output"),
        "http": ("type", "method", "url", "output", "response_body_path"),
        "sql": ("type", "connection", "table", "source_path", "target_path", "output", "rows_path", "result_path"),
        "mongo": ("type", "connection", "database", "collection", "output", "result_path"),
        "redis": ("type", "connection", "key", "command", "output", "result_path"),
        "command": ("type", "output", "cwd", "stdout_path", "stderr_path"),
        "table": (
            "type",
            "output",
            "column",
            "columns",
            "into",
            "sources",
            "by",
            "index",
            "values",
            "agg",
            "keep",
            "on",
            "left_on",
            "right_on",
            "threshold",
            "score_column",
        ),
        "open_desktop": ("name", "platform", "backend", "request_permissions", "output"),
        "close_desktop": ("desktop",),
        "desktop_app": (
            "desktop",
            "type",
            "app",
            "path",
            "command",
            "args",
            "wait",
            "timeout_ms",
            "wait_for_window",
            "focus",
            "title",
            "title_contains",
            "title_regex",
            "app",
            "process",
            "process_name",
            "class_name",
            "window_id",
            "match_index",
            "window_timeout_ms",
            "interval_ms",
            "output",
        ),
        "desktop_window": (
            "desktop",
            "type",
            "title",
            "title_contains",
            "title_regex",
            "app",
            "process",
            "process_name",
            "class_name",
            "window_id",
            "match_index",
            "include_invisible",
            "max_windows",
            "timeout_ms",
            "interval_ms",
            "x",
            "y",
            "width",
            "height",
            "focus",
            "tolerance_px",
            "path",
            "output",
        ),
        "desktop_element": (
            "desktop",
            "type",
            "title",
            "title_contains",
            "app",
            "process_name",
            "window_id",
            "name",
            "name_contains",
            "text",
            "text_contains",
            "automation_id",
            "control_type",
            "role",
            "state",
            "value",
            "option_index",
            "preserve_clipboard",
            "include_tree",
            "include_selector_hints",
            "text_limit",
            "path",
            "output",
        ),
        "desktop_input": (
            "desktop",
            "type",
            "target",
            "candidate_id",
            "target_candidate_id",
            "min_confidence",
            "x",
            "y",
            "offset_x",
            "offset_y",
            "bounds",
            "title_contains",
            "app",
            "process_name",
            "window_id",
            "name",
            "name_contains",
            "automation_id",
            "control_type",
            "button",
            "clicks",
            "interval_ms",
            "method",
            "value",
            "keys",
            "delay_ms",
            "preserve_clipboard",
            "amount",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "delta_x",
            "delta_y",
            "duration_ms",
            "output",
        ),
        "desktop_capture": (
            "desktop",
            "type",
            "path",
            "target",
            "region",
            "include_cursor",
            "title",
            "title_contains",
            "title_regex",
            "app",
            "process",
            "process_name",
            "class_name",
            "window_id",
            "element_id",
            "automation_id",
            "name",
            "name_contains",
            "name_regex",
            "text",
            "text_contains",
            "text_regex",
            "control_type",
            "role",
            "element_class_name",
            "element_match_index",
            "state",
            "timeout_ms",
            "interval_ms",
            "max_depth",
            "max_elements",
            "output",
        ),
        "desktop_vision": (
            "desktop",
            "type",
            "template_path",
            "source_path",
            "source_target",
            "region",
            "include_cursor",
            "title",
            "title_contains",
            "title_regex",
            "app",
            "process",
            "process_name",
            "class_name",
            "window_id",
            "window_match_index",
            "match_index",
            "element_id",
            "automation_id",
            "name",
            "name_contains",
            "name_regex",
            "text",
            "text_contains",
            "text_regex",
            "control_type",
            "role",
            "element_class_name",
            "element_match_index",
            "state",
            "threshold",
            "max_matches",
            "timeout_ms",
            "interval_ms",
            "max_depth",
            "max_elements",
            "path",
            "output",
        ),
        "desktop_wait": ("desktop", "type", "state", "title", "title_contains", "app", "timeout_ms", "output"),
        "desktop_assert": (
            "desktop",
            "type",
            "state",
            "title",
            "title_contains",
            "app",
            "name",
            "name_contains",
            "text",
            "text_contains",
            "automation_id",
            "control_type",
            "role",
            "expected",
            "mode",
            "text_source",
            "path",
            "output",
        ),
        "sleep": ("seconds",),
        "ai": ("type", "output"),
    }
    fields = safe_fields_by_action.get(action, ("type", "browser", "page", "path", "output"))
    parts: list[str] = []
    for field in fields:
        if field not in step:
            continue
        value = step.get(field)
        if value is None or value == "":
            continue
        if field == "prompt":
            value = _compact_step_value(value, limit=96)
        else:
            value = _compact_step_value(value)
        if value:
            parts.append(f"{field}={value}")
    return ", ".join(parts)


def _compact_step_value(value: Any, *, limit: int = 72) -> str:
    if isinstance(value, (list, tuple)):
        text = "[" + ", ".join(_compact_step_value(item, limit=24) for item in list(value)[:3]) + "]"
        if len(value) > 3:
            text += "..."
    elif isinstance(value, dict):
        text = "{...}"
    else:
        text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[: max(0, limit - 3)].rstrip() + "..."
    return text


def _frame_by_index(page: Page, index: int) -> Frame:
    frames = page.frames
    if index < 0 or index >= len(frames):
        raise ValueError(f"frame_index 超出范围：{index}")
    return frames[index]
