from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page

from ai_automate_contro.engine.conditions import ConditionEvaluator
from ai_automate_contro.engine.runtime import RuntimeState
from ai_automate_contro.engine.template import render_value

from . import ai_task, basic, browser_flow, browser_io, control_flow, extraction, failure_capture


EXTERNAL_ACTION_MODULES = (
    ai_task,
    basic,
    browser_flow,
    browser_io,
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
        page = self._page(step)
        locator = page.locator(step["selector"])
        if "index" in step:
            locator = locator.nth(int(step["index"]))
        return locator

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
