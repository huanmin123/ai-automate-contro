from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Frame, FrameLocator, Locator, Page

from ai_automate_contro.engine.conditions import ConditionEvaluator
from ai_automate_contro.engine.runtime import RuntimeState
from ai_automate_contro.engine.template import render_value

from . import (
    ai_task,
    basic,
    browser_capture,
    browser_dialogs,
    browser_events,
    browser_flow,
    browser_input,
    browser_state,
    control_flow,
    extraction,
    failure_capture,
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
    control_flow,
    extraction,
)


class ActionExecutor:
    def __init__(self, state: RuntimeState) -> None:
        self.state = state
        self.conditions = ConditionEvaluator(state)

    def run(self, steps: list[dict[str, Any]]) -> None:
        for raw_step in steps:
            self._run_step(raw_step)

    def _run_step(self, raw_step: dict[str, Any]) -> None:
        action = raw_step["action"]
        if action in {"if", "foreach", "retry"}:
            step = raw_step
        else:
            step = render_value(raw_step, self.state.variables)
        step_number = self.state.next_step_number()
        step_name = step.get("name", action)
        self.state.logger.log(
            "info",
            f"step {step_number} start",
            step=step_number,
            action=action,
            step_name=step_name,
        )
        self.state.state_writer.mark_step_started(step=step_number, action=action, step_name=step_name)
        handler = self._resolve_action_handler(action)
        if handler is None:
            raise ValueError(f"Unsupported action: {action}")

        try:
            handler(step)
        except Exception as error:
            failure_capture.capture_failure_state(
                self.state,
                step_number=step_number,
                action=action,
                step_name=step_name,
            )
            self.state.logger.log(
                "error",
                f"step {step_number} failed",
                step=step_number,
                action=action,
                step_name=step_name,
                error=str(error),
            )
            raise

        self.state.logger.log(
            "info",
            f"step {step_number} finished",
            step=step_number,
            action=action,
            step_name=step_name,
        )
        self.state.state_writer.mark_step_finished(step=step_number, action=action, step_name=step_name)

    def _resolve_action_handler(self, action: str) -> Any | None:
        for module in EXTERNAL_ACTION_MODULES:
            if action in module.ACTION_HANDLERS:
                return (
                    lambda step, selected_module=module, selected_action=action: selected_module.ACTION_HANDLERS[
                        selected_action
                    ](self, step)
                )
        return getattr(self, f"_action_{action}", None)

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


def _frame_by_index(page: Page, index: int) -> Frame:
    frames = page.frames
    if index < 0 or index >= len(frames):
        raise ValueError(f"frame_index 超出范围：{index}")
    return frames[index]
