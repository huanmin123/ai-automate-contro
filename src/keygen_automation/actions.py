from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from keygen_automation.ai import build_ai_schema, run_ai_task, service_config_for_artifact
from keygen_automation.browser import BrowserConfig
from keygen_automation.conditions import ConditionEvaluator
from keygen_automation.plan_loader import load_plan
from keygen_automation.runtime import BrowserSession, RuntimeState
from keygen_automation.template import render_value


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
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            raise ValueError(f"Unsupported action: {action}")

        try:
            handler(step)
        except Exception as error:
            self._capture_failure_state(step_number, action, step_name)
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

    def _capture_failure_state(self, step_number: int, action: str, step_name: str) -> None:
        screenshot_dir = self.state.output_dir / "failure-screenshots"
        html_dir = self.state.output_dir / "failure-html"
        page_state_dir = self.state.output_dir / "failure-page-state"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        html_dir.mkdir(parents=True, exist_ok=True)
        page_state_dir.mkdir(parents=True, exist_ok=True)
        for browser_name, session in self.state.sessions.items():
            for page_name, page in session.pages.items():
                file_stem = f"step-{step_number:03d}-{browser_name}-{page_name}-{action}"
                screenshot_path = screenshot_dir / f"{file_stem}.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    self.state.failure_screenshots.append(str(screenshot_path))
                    self.state.logger.log(
                        "warning",
                        "failure screenshot captured",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        path=str(screenshot_path),
                    )
                except Exception as screenshot_error:
                    self.state.logger.log(
                        "warning",
                        "failure screenshot capture failed",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        error=str(screenshot_error),
                    )
                html_path = html_dir / f"{file_stem}.html"
                try:
                    html_path.write_text(page.content(), encoding="utf-8")
                    self.state.failure_htmls.append(str(html_path))
                    self.state.logger.log(
                        "warning",
                        "failure html captured",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        path=str(html_path),
                    )
                except Exception as html_error:
                    self.state.logger.log(
                        "warning",
                        "failure html capture failed",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        error=str(html_error),
                    )
                page_state_path = page_state_dir / f"{file_stem}.json"
                try:
                    page_state = {
                        "step": step_number,
                        "action": action,
                        "step_name": step_name,
                        "browser": browser_name,
                        "page": page_name,
                        "url": page.url,
                        "title": page.title(),
                        "screenshot": str(screenshot_path) if screenshot_path.exists() else "",
                        "html": str(html_path) if html_path.exists() else "",
                    }
                    with page_state_path.open("w", encoding="utf-8") as file:
                        json.dump(page_state, file, ensure_ascii=False, indent=2)
                    self.state.failure_page_states.append(str(page_state_path))
                    self.state.logger.log(
                        "warning",
                        "failure page state captured",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        path=str(page_state_path),
                    )
                except Exception as page_state_error:
                    self.state.logger.log(
                        "warning",
                        "failure page state capture failed",
                        step=step_number,
                        step_name=step_name,
                        browser=browser_name,
                        page=page_name,
                        error=str(page_state_error),
                    )

    def _action_variable(self, step: dict[str, Any]) -> None:
        variable_type = step["type"]
        if variable_type == "set":
            name = step["name"]
            value = step["value"]
            self.state.variables[name] = value
            self.state.logger.log("info", "variable set", name=name, value=value)
            return
        if variable_type == "set_many":
            values = step["values"]
            for key, value in values.items():
                self.state.variables[key] = value
            self.state.logger.log("info", "variables set", names=list(values.keys()))
            return
        if variable_type == "copy":
            source = step["source"]
            target = step["target"]
            if source not in self.state.variables:
                raise KeyError(f"Variable '{source}' is not defined.")
            self.state.variables[target] = self.state.variables[source]
            self.state.logger.log("info", "variable copied", source=source, target=target)
            return
        raise ValueError(f"Unsupported variable type: {variable_type}")

    def _action_run_sub_plan(self, step: dict[str, Any]) -> None:
        raw_path = str(step["path"])
        sub_plan_path = self._resolve_sub_plan_path(raw_path)
        sub_plan = load_plan(sub_plan_path)
        if "steps" not in sub_plan:
            raise ValueError(f"Sub plan must be a plan document with steps: {sub_plan_path}")

        previous_plan_path = self.state.plan_path
        self.state.plan_path = sub_plan_path
        self.state.sub_plan_stack.append(sub_plan_path)
        self.state.logger.log("info", "sub plan started", path=str(sub_plan_path))
        try:
            self.run(sub_plan.get("steps", []))
        finally:
            self.state.logger.log("info", "sub plan finished", path=str(sub_plan_path))
            self.state.sub_plan_stack.pop()
            self.state.plan_path = previous_plan_path

    def _action_open_browser(self, step: dict[str, Any]) -> None:
        name = step["name"]
        if name in self.state.sessions:
            raise ValueError(f"Browser session '{name}' already exists.")

        config = BrowserConfig(
            headed=bool(step.get("headed", False)),
            slow_mo_ms=int(step.get("slow_mo_ms", 0)),
            timeout_ms=int(step.get("timeout_ms", 15_000)),
        )
        browser = self.state.playwright.chromium.launch(
            headless=not config.headed,
            slow_mo=config.slow_mo_ms,
        )
        context_kwargs: dict[str, Any] = {}
        if "storage_state_path" in step:
            context_kwargs["storage_state"] = str(self._resolve_path(step["storage_state_path"]))
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(config.timeout_ms)
        page = context.new_page()
        session = BrowserSession(
            name=name,
            browser=browser,
            context=context,
        )
        session.register_page("main", page, switch=True)
        self.state.sessions[name] = session
        context.on("dialog", self._handle_dialog)
        self.state.logger.log("info", "browser opened", browser=name)

    def _action_page(self, step: dict[str, Any]) -> None:
        page_type = step["type"]
        session = self.state.require_session(step["browser"])
        if page_type == "open":
            page_name = step["page"]
            page = session.context.new_page()
            session.register_page(page_name, page, switch=bool(step.get("switch", True)))
            if "url" in step:
                page.goto(step["url"], wait_until=step.get("wait_until", "domcontentloaded"))
            self.state.logger.log(
                "info",
                "new page opened",
                browser=step["browser"],
                page=page_name,
            )
            return
        if page_type == "switch":
            session.switch_page(step["page"])
            self.state.logger.log("info", "page switched", browser=step["browser"], page=step["page"])
            return
        if page_type == "close":
            closed_page = session.close_page(step.get("page"))
            self.state.logger.log("info", "page closed", browser=step["browser"], page=closed_page)
            return
        raise ValueError(f"Unsupported page type: {page_type}")

    def _action_close_browser(self, step: dict[str, Any]) -> None:
        session_name = step["browser"]
        session = self.state.require_session(session_name)
        session.context.close()
        session.browser.close()
        del self.state.sessions[session_name]
        self.state.logger.log("info", "browser closed", browser=session_name)

    def _action_navigate(self, step: dict[str, Any]) -> None:
        navigate_type = step["type"]
        page = self._page(step)
        wait_until = step.get("wait_until", "domcontentloaded")
        if navigate_type == "goto":
            page.goto(step["url"], wait_until=wait_until)
            return
        if navigate_type == "refresh":
            page.reload(wait_until=wait_until)
            return
        if navigate_type == "back":
            page.go_back(wait_until=wait_until)
            return
        if navigate_type == "forward":
            page.go_forward(wait_until=wait_until)
            return
        raise ValueError(f"Unsupported navigate type: {navigate_type}")

    def _action_element(self, step: dict[str, Any]) -> None:
        element_type = step["type"]
        locator = self._locator(step)
        if element_type == "click":
            locator.click()
            return
        if element_type == "hover":
            locator.hover()
            return
        if element_type == "fill":
            locator.fill(str(step["value"]))
            return
        if element_type == "clear":
            locator.fill("")
            return
        if element_type == "type":
            locator.type(str(step["value"]), delay=int(step.get("delay_ms", 50)))
            return
        if element_type == "focus":
            locator.focus()
            return
        if element_type == "press":
            locator.press(step["key"])
            return
        if element_type == "check":
            locator.check()
            return
        if element_type == "uncheck":
            locator.uncheck()
            return
        if element_type == "select":
            if "value" in step:
                locator.select_option(value=str(step["value"]))
                return
            if "label" in step:
                locator.select_option(label=str(step["label"]))
                return
            if "index_value" in step:
                locator.select_option(index=int(step["index_value"]))
                return
            raise ValueError("element type 'select' requires one of: value, label, index_value")
        if element_type == "set_files":
            files = step["files"]
            if isinstance(files, str):
                files = [files]
            resolved_files = [str(self._resolve_path(file_path)) for file_path in files]
            locator.set_input_files(resolved_files)
            return
        raise ValueError(f"Unsupported element type: {element_type}")

    def _action_wait(self, step: dict[str, Any]) -> None:
        wait_type = step.get("type", "time")
        if wait_type == "time":
            self._page(step).wait_for_timeout(int(float(step.get("seconds", 1)) * 1000))
            return
        if wait_type == "selector":
            self._wait_for_selector(step)
            return
        if wait_type == "url":
            self._page(step).wait_for_url(step["url"])
            return
        if wait_type == "text":
            self._wait_for_text(step)
            return
        if wait_type == "count":
            self._wait_for_count(step)
            return
        raise ValueError(f"Unsupported wait type: {wait_type}")

    def _wait_for_selector(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        selector = step["selector"]
        state = step.get("state", "visible")
        if "index" in step:
            page.locator(selector).nth(int(step["index"])).wait_for(state=state)
            return
        page.wait_for_selector(selector, state=state)

    def _wait_for_text(self, step: dict[str, Any]) -> None:
        locator = self._locator(step)
        expected = str(step["text"])
        mode = step.get("mode", "contains")
        locator.wait_for(state=step.get("state", "visible"))
        actual = locator.inner_text()
        if mode == "contains" and expected in actual:
            return
        if mode == "equals" and actual.strip() == expected:
            return
        raise AssertionError(
            f"wait_for_text failed. mode={mode}, expected={expected!r}, actual={actual!r}"
        )

    def _wait_for_count(self, step: dict[str, Any]) -> None:
        selector = step["selector"]
        expected = int(step["expected"])
        mode = step.get("mode", "equals")
        page = self._page(step)
        timeout_ms = int(step.get("timeout_ms", 15_000))
        start = page.evaluate("Date.now()")
        while True:
            actual = page.locator(selector).count()
            if mode == "equals" and actual == expected:
                return
            if mode == "gte" and actual >= expected:
                return
            if mode == "lte" and actual <= expected:
                return
            now = page.evaluate("Date.now()")
            if int(now) - int(start) >= timeout_ms:
                raise AssertionError(
                    f"wait_for_count failed. mode={mode}, expected={expected}, actual={actual}"
                )
            page.wait_for_timeout(200)

    def _action_detect_challenge(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        matches: list[dict[str, Any]] = []
        for rule in step.get("rules", []):
            rule_type = rule.get("type", "selector_visible")
            label = rule.get("label", rule_type)
            matched = False

            if rule_type == "selector_visible":
                locator = page.locator(rule["selector"])
                if locator.count() > 0:
                    target = locator.nth(int(rule["index"])) if "index" in rule else locator.first
                    matched = target.is_visible()
            elif rule_type == "selector_exists":
                matched = page.locator(rule["selector"]).count() > 0
            elif rule_type == "text_contains":
                locator = page.locator(rule.get("selector", "body"))
                if locator.count() > 0:
                    matched = str(rule["text"]) in locator.first.inner_text()
            elif rule_type == "url_contains":
                matched = str(rule["value"]) in page.url
            else:
                raise ValueError(f"Unsupported challenge rule type: {rule_type}")

            if matched:
                matches.append(
                    {
                        "label": label,
                        "type": rule_type,
                        "selector": rule.get("selector"),
                        "text": rule.get("text"),
                        "value": rule.get("value"),
                    }
                )

        result = {
            "matched": bool(matches),
            "labels": [item["label"] for item in matches],
            "matches": matches,
        }
        self.state.variables[step["save_as"]] = result
        if "save_detected_as" in step:
            self.state.variables[step["save_detected_as"]] = result["matched"]
        if "save_label_as" in step:
            self.state.variables[step["save_label_as"]] = result["labels"][0] if result["labels"] else ""
        self.state.logger.log(
            "info",
            "challenge detected",
            save_as=step["save_as"],
            matched=result["matched"],
            labels=result["labels"],
        )

    def _action_ai(self, step: dict[str, Any]) -> None:
        ai_type = step["type"]
        service_name = step.get("service", "default")
        ai_services = self.state.variables.get("config", {}).get("ai_services", {})
        if not isinstance(ai_services, dict):
            raise ValueError("config.ai_services must be a JSON object.")
        service_config = ai_services.get(service_name)
        if not isinstance(service_config, dict):
            raise KeyError(f"AI service is not configured: {service_name}")

        schema = build_ai_schema(ai_type, step.get("schema"), labels=step.get("labels"))
        instruction = str(step.get("instruction", ""))
        input_value = step.get("input", "")
        result = run_ai_task(
            service_name=str(service_name),
            service_config=service_config,
            task_type=ai_type,
            input_value=input_value,
            instruction=instruction,
            schema=schema,
            labels=step.get("labels"),
        )
        self.state.variables[step["save_as"]] = result.parsed

        artifact_path = self._resolve_output_path(step.get("path", f"{ai_type}/{step['save_as']}.json"), category="ai")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "type": ai_type,
            "service": str(service_name),
            "service_config": service_config_for_artifact(service_config),
            "instruction": instruction,
            "input": input_value,
            "schema": result.schema,
            "response_format": result.response_format,
            "attempts": result.attempts,
            "parsed": result.parsed,
            "raw_text": result.raw_text,
            "raw_response": result.raw_response,
        }
        with artifact_path.open("w", encoding="utf-8") as file:
            json.dump(artifact, file, ensure_ascii=False, indent=2)
        self.state.logger.log(
            "info",
            "ai task completed",
            type=ai_type,
            service=str(service_name),
            save_as=step["save_as"],
            path=str(artifact_path),
        )

    def _action_extract(self, step: dict[str, Any]) -> None:
        extract_type = step["type"]
        value: Any
        if extract_type == "text":
            value = self._locator(step).inner_text()
        elif extract_type == "value":
            value = self._locator(step).input_value()
        elif extract_type == "attribute":
            value = self._locator(step).get_attribute(step["attribute"])
        elif extract_type == "html":
            value = self._locator(step).inner_html()
        elif extract_type == "count":
            value = self._page(step).locator(step["selector"]).count()
        elif extract_type == "all_texts":
            values = [item.strip() for item in self._page(step).locator(step["selector"]).all_inner_texts()]
            value = [item for item in values if item] if step.get("skip_empty", True) else values
        elif extract_type == "all_values":
            locator = self._page(step).locator(step["selector"])
            value = [locator.nth(index).input_value() for index in range(locator.count())]
        elif extract_type == "table":
            value = self._extract_table_value(step)
        else:
            raise ValueError(f"Unsupported extract type: {extract_type}")
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "value extracted", type=extract_type, save_as=step["save_as"], value=value)

    def _extract_table_value(self, step: dict[str, Any]) -> list[Any]:
        page = self._page(step)
        row_locator = page.locator(step["row_selector"])
        cell_selector = step.get("cell_selector", "td")
        include_header = bool(step.get("include_header", False))
        headers: list[str] = []

        if include_header and step.get("header_selector"):
            header_locator = page.locator(step["header_selector"])
            headers = [item.strip() for item in header_locator.all_inner_texts()]

        rows: list[Any] = []
        for row_index in range(row_locator.count()):
            cell_locator = row_locator.nth(row_index).locator(cell_selector)
            values = [cell_locator.nth(cell_index).inner_text().strip() for cell_index in range(cell_locator.count())]
            if headers:
                rows.append(
                    {
                        headers[index]: values[index] if index < len(values) else ""
                        for index in range(len(headers))
                    }
                )
            else:
                rows.append(values)

        return rows

    def _action_keyboard(self, step: dict[str, Any]) -> None:
        keyboard_type = step["type"]
        keyboard = self._page(step).keyboard
        if keyboard_type == "press":
            keyboard.press(step["key"])
            return
        if keyboard_type == "type":
            keyboard.type(str(step["value"]), delay=int(step.get("delay_ms", 50)))
            return
        if keyboard_type == "down":
            keyboard.down(step["key"])
            return
        if keyboard_type == "up":
            keyboard.up(step["key"])
            return
        raise ValueError(f"Unsupported keyboard type: {keyboard_type}")

    def _action_scroll(self, step: dict[str, Any]) -> None:
        scroll_type = step.get("type", "by")
        if scroll_type == "into_view":
            self._locator(step).scroll_into_view_if_needed()
            return
        if scroll_type == "by":
            page = self._page(step)
            delta_x = int(step.get("delta_x", 0))
            delta_y = int(step.get("delta_y", 0))
            page.evaluate(
                "(args) => window.scrollBy(args.deltaX, args.deltaY)",
                {"deltaX": delta_x, "deltaY": delta_y},
            )
            return
        raise ValueError(f"Unsupported scroll type: {scroll_type}")

    def _action_mouse(self, step: dict[str, Any]) -> None:
        mouse_type = step["type"]
        mouse = self._page(step).mouse
        if mouse_type == "move":
            mouse.move(float(step["x"]), float(step["y"]))
            return
        if mouse_type == "click":
            mouse.click(
                float(step["x"]),
                float(step["y"]),
                button=step.get("button", "left"),
                click_count=int(step.get("click_count", 1)),
            )
            return
        if mouse_type == "down":
            mouse.down(button=step.get("button", "left"))
            return
        if mouse_type == "up":
            mouse.up(button=step.get("button", "left"))
            return
        if mouse_type == "wheel":
            mouse.wheel(float(step.get("delta_x", 0)), float(step.get("delta_y", 0)))
            return
        raise ValueError(f"Unsupported mouse type: {mouse_type}")

    def _action_capture(self, step: dict[str, Any]) -> None:
        capture_type = step["type"]
        if capture_type == "screenshot":
            output_path = self._resolve_output_path(step["path"], category="screenshots")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._page(step).screenshot(
                path=str(output_path),
                full_page=bool(step.get("full_page", False)),
            )
            self.state.logger.log("info", "screenshot saved", path=str(output_path))
            return
        if capture_type == "html":
            output_path = self._resolve_output_path(step["path"], category="html")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            html = self._page(step).content()
            with output_path.open("w", encoding="utf-8") as file:
                file.write(html)
            self.state.logger.log("info", "page html saved", path=str(output_path))
            return
        if capture_type == "storage_state":
            session = self.state.require_session(step["browser"])
            output_path = self._resolve_output_path(step["path"], category="storage-states")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            session.context.storage_state(path=str(output_path))
            self.state.logger.log("info", "storage state saved", browser=step["browser"], path=str(output_path))
            return
        raise ValueError(f"Unsupported capture type: {capture_type}")

    def _action_manual_confirm(self, step: dict[str, Any]) -> None:
        prompt = step.get("prompt", "Continue? Input y to proceed: ")
        if self.state.manual_confirmation_handler is not None:
            self.state.logger.log("info", "waiting for manual confirmation", prompt=str(prompt))
            self.state.state_writer.mark_waiting(prompt=str(prompt))
            accepted = self.state.manual_confirmation_handler(str(prompt))
            if not accepted:
                raise RuntimeError("Manual confirmation was not accepted.")
            self.state.state_writer.mark_resumed()
            self.state.logger.log("info", "manual confirmation accepted", prompt=str(prompt))
            return
        answer = input(prompt).strip().lower()
        if answer != "y":
            raise RuntimeError("Manual confirmation was not accepted.")

    def _action_print(self, step: dict[str, Any]) -> None:
        self.state.logger.log("info", str(step["message"]))

    def _action_dialog(self, step: dict[str, Any]) -> None:
        dialog_type = step["type"]
        if dialog_type == "accept":
            self._handle_dialog_action(step, accept=True)
            return
        if dialog_type == "dismiss":
            self._handle_dialog_action(step, accept=False)
            return
        raise ValueError(f"Unsupported dialog type: {dialog_type}")

    def _handle_dialog_action(self, step: dict[str, Any], *, accept: bool) -> None:
        trigger = step.get("trigger")
        if trigger:
            page = self._page(step)
            prompt_text = step.get("prompt_text")

            def handler(dialog: Any) -> None:
                self.state.last_dialog_message = dialog.message
                self.state.logger.log(
                    "info",
                    "dialog auto-accepted" if accept else "dialog auto-dismissed",
                    dialog_type=dialog.type,
                    dialog_message=dialog.message,
                )
                if accept:
                    dialog.accept(prompt_text)
                else:
                    dialog.dismiss()

            page.once("dialog", handler)
            self.run([trigger])
            self.state.pending_dialog = None
            return

        if self.state.pending_dialog is None:
            raise RuntimeError("No pending dialog to handle.")
        if accept:
            prompt_text = step.get("prompt_text")
            self.state.pending_dialog.accept(prompt_text)
            self.state.logger.log("info", "dialog accepted", message=self.state.last_dialog_message)
        else:
            self.state.pending_dialog.dismiss()
            self.state.logger.log("info", "dialog dismissed", message=self.state.last_dialog_message)
        self.state.pending_dialog = None

    def _action_wait_for_download(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        trigger = step.get("trigger")
        if not trigger:
            raise ValueError("wait_for_download requires a trigger step.")
        with page.expect_download() as download_info:
            self.run([trigger])
        download = download_info.value
        output_path = self._resolve_output_path(step["path"], category="downloads")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(str(output_path))
        self.state.downloads.append(str(output_path))
        if "save_as" in step:
            self.state.variables[step["save_as"]] = str(output_path)
        self.state.logger.log("info", "download saved", path=str(output_path))

    def _action_wait_for_popup(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        session = self.state.require_session(step["browser"])
        trigger = step.get("trigger")
        popup_name = step["popup_page"]
        if not trigger:
            raise ValueError("wait_for_popup requires a trigger step.")
        with page.expect_popup() as popup_info:
            self.run([trigger])
        popup_page = popup_info.value
        session.register_page(popup_name, popup_page, switch=bool(step.get("switch", True)))
        if "save_as" in step:
            self.state.variables[step["save_as"]] = popup_name
        self.state.logger.log(
            "info",
            "popup captured",
            browser=step["browser"],
            page=popup_name,
            url=popup_page.url,
        )

    def _action_wait_for_network(self, step: dict[str, Any]) -> None:
        network_type = step["type"]
        if network_type == "request":
            self._wait_for_request(step)
            return
        if network_type == "response":
            self._wait_for_response(step)
            return
        raise ValueError(f"Unsupported wait_for_network type: {network_type}")

    def _wait_for_request(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        trigger = step.get("trigger")
        if not trigger:
            raise ValueError("wait_for_network type 'request' requires a trigger step.")
        with page.expect_request(step["url"]) as request_info:
            self.run([trigger])
        request = request_info.value
        payload = {
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
        }
        if "save_as" in step:
            self.state.variables[step["save_as"]] = payload
        self.state.logger.log(
            "info",
            "request captured",
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
        )

    def _wait_for_response(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        trigger = step.get("trigger")
        if not trigger:
            raise ValueError("wait_for_network type 'response' requires a trigger step.")
        with page.expect_response(step["url"]) as response_info:
            self.run([trigger])
        response = response_info.value
        payload = {
            "url": response.url,
            "status": response.status,
            "ok": response.ok,
        }
        if "save_as" in step:
            self.state.variables[step["save_as"]] = payload
        self.state.logger.log(
            "info",
            "response captured",
            url=response.url,
            status=response.status,
            ok=response.ok,
        )

    def _action_write(self, step: dict[str, Any]) -> None:
        file_type = step["type"]
        if file_type == "json":
            self._write_json_file(step["path"], step["value"], indent=int(step.get("indent", 2)))
            return
        if file_type == "text":
            self._write_text_file(step["path"], str(step["value"]), append=bool(step.get("append", False)))
            return
        if file_type == "csv":
            self._write_csv_file(step["path"], step["value"], step.get("headers"))
            return
        if file_type == "variables":
            self._write_json_file(step["path"], self.state.variables, category="variables", indent=int(step.get("indent", 2)))
            return
        raise ValueError(f"Unsupported write type: {file_type}")

    def _action_read(self, step: dict[str, Any]) -> None:
        file_type = step["type"]
        path = self._resolve_path(step["path"])
        if file_type == "json":
            with path.open("r", encoding="utf-8") as file:
                value = json.load(file)
        elif file_type == "text":
            with path.open("r", encoding="utf-8") as file:
                content = file.read()
            if step.get("split_lines", False):
                value = [line.strip() for line in content.splitlines() if line.strip()]
            else:
                value = content
        elif file_type == "csv":
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                value = list(reader)
        elif file_type == "storage_state":
            value = str(path)
        else:
            raise ValueError(f"Unsupported read type: {file_type}")
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "file read", type=file_type, path=str(path), save_as=step["save_as"])

    def _action_assert(self, step: dict[str, Any]) -> None:
        assert_type = step["type"]
        if assert_type == "selector":
            self._assert_selector(step)
            return
        if assert_type == "text":
            self._assert_text(step)
            return
        if assert_type == "value":
            self._assert_value(step)
            return
        if assert_type == "url":
            self._assert_url(step)
            return
        if assert_type == "count":
            self._assert_count(step)
            return
        raise ValueError(f"Unsupported assert type: {assert_type}")

    def _assert_selector(self, step: dict[str, Any]) -> None:
        try:
            self._locator(step).wait_for(state=step.get("state", "visible"))
        except PlaywrightTimeoutError as error:
            raise AssertionError(
                f"Selector assertion failed for '{step['selector']}'"
            ) from error

    def _assert_text(self, step: dict[str, Any]) -> None:
        actual = self._locator(step).inner_text().strip()
        expected = str(step["expected"])
        mode = step.get("mode", "equals")
        if mode == "equals" and actual == expected:
            return
        if mode == "contains" and expected in actual:
            return
        raise AssertionError(
            f"Text assertion failed. mode={mode}, expected={expected!r}, actual={actual!r}"
        )

    def _assert_value(self, step: dict[str, Any]) -> None:
        actual = self._locator(step).input_value()
        expected = str(step["expected"])
        mode = step.get("mode", "equals")
        if mode == "equals" and actual == expected:
            return
        if mode == "contains" and expected in actual:
            return
        raise AssertionError(
            f"Value assertion failed. mode={mode}, expected={expected!r}, actual={actual!r}"
        )

    def _assert_url(self, step: dict[str, Any]) -> None:
        actual = self._page(step).url
        expected = str(step["expected"])
        mode = step.get("mode", "contains")
        if mode == "contains" and expected in actual:
            return
        if mode == "equals" and actual == expected:
            return
        if mode == "not_contains" and expected not in actual:
            return
        else:
            raise AssertionError(f"URL assertion failed. expected to contain {expected!r}, actual={actual!r}")

    def _assert_count(self, step: dict[str, Any]) -> None:
        actual = self._page(step).locator(step["selector"]).count()
        expected = int(step["expected"])
        mode = step.get("mode", "equals")
        if mode == "equals" and actual == expected:
            return
        if mode == "gte" and actual >= expected:
            return
        if mode == "lte" and actual <= expected:
            return
        raise AssertionError(
            f"Count assertion failed. mode={mode}, expected={expected}, actual={actual}"
        )

    def _action_if(self, step: dict[str, Any]) -> None:
        rendered_condition = render_value(step.get("condition"), self.state.variables)
        matched = self.conditions.evaluate(rendered_condition)
        raw_branch = step.get("then", []) if matched else step.get("else", [])
        self.state.logger.log("info", "if evaluated", matched=matched)
        self.run(raw_branch)

    def _action_foreach(self, step: dict[str, Any]) -> None:
        items = render_value(step["items"], self.state.variables)
        loop_var = step.get("item_var", "item")
        index_var = step.get("index_var", "index")
        body = step.get("steps", [])
        total = len(items)
        self.state.logger.log("info", "foreach start", loop_var=loop_var, total=total)
        for index, item in enumerate(items):
            self.state.variables[loop_var] = item
            self.state.variables[index_var] = index
            self.state.logger.log("info", "foreach item", index=index, loop_var=loop_var, value=item)
            self.run(body)
        self.state.logger.log("info", "foreach finished", total=total)

    def _action_retry(self, step: dict[str, Any]) -> None:
        attempts = int(step.get("attempts", 3))
        wait_seconds = float(step.get("wait_seconds", 1))
        body = step.get("steps", [])
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self.state.logger.log("info", "retry attempt", attempt=attempt, attempts=attempts)
                self.run(body)
                return
            except Exception as error:
                last_error = error
                self.state.logger.log("warning", "retry failed", attempt=attempt, error=str(error))
                if attempt < attempts:
                    for session in self.state.sessions.values():
                        session.require_page().wait_for_timeout(int(wait_seconds * 1000))
        if last_error is not None:
            raise last_error

    def _action_sleep(self, step: dict[str, Any]) -> None:
        if self.state.sessions:
            first_session = next(iter(self.state.sessions.values()))
            first_session.require_page().wait_for_timeout(int(float(step.get("seconds", 1)) * 1000))
            return
        raise RuntimeError("sleep requires at least one opened browser session in current version.")

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

    def _write_json_file(
        self,
        raw_path: str,
        value: Any,
        *,
        category: str = "json",
        indent: int = 2,
    ) -> None:
        output_path = self._resolve_output_path(raw_path, category=category)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=indent)
        self.state.logger.log("info", "json written", path=str(output_path))

    def _write_text_file(self, raw_path: str, content: str, *, append: bool) -> None:
        output_path = self._resolve_output_path(raw_path, category="text")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with output_path.open(mode, encoding="utf-8") as file:
            file.write(content)
        log_message = "text appended" if append else "text written"
        self.state.logger.log("info", log_message, path=str(output_path))

    def _write_csv_file(self, raw_path: str, rows: list[Any], headers: list[str] | None = None) -> None:
        output_path = self._resolve_output_path(raw_path, category="csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as file:
            if headers:
                writer = csv.writer(file)
                writer.writerow(headers)
                for row in rows:
                    if isinstance(row, dict):
                        writer.writerow([row.get(header, "") for header in headers])
                    else:
                        writer.writerow(row)
            else:
                if not rows:
                    file.write("")
                elif isinstance(rows[0], dict):
                    fieldnames = list(rows[0].keys())
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                else:
                    writer = csv.writer(file)
                    writer.writerows(rows)
        self.state.logger.log("info", "csv written", path=str(output_path))

    def _resolve_sub_plan_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            raise ValueError("run_sub_plan path must be relative to the current plan package.")
        package_root = self._package_root().resolve()
        resolved_path = (package_root / path).resolve()
        sub_plans_dir = (package_root / "sub-plans").resolve()
        if not _is_relative_to(resolved_path, package_root):
            raise ValueError(f"Sub plan must stay inside the current plan package: {raw_path}")
        if not path.parts or path.parts[0] != "sub-plans":
            raise ValueError("Sub plan paths must be placed under 'sub-plans/'.")
        if not _is_relative_to(resolved_path, sub_plans_dir):
            raise ValueError("Sub plan paths must resolve under 'sub-plans/'.")
        if resolved_path.name == "plan.json":
            raise ValueError("run_sub_plan cannot reference another entry plan named 'plan.json'.")
        if not resolved_path.name.endswith("-plan.json"):
            raise ValueError("Sub plan filenames must use the '*-plan.json' pattern.")
        if not resolved_path.exists():
            raise FileNotFoundError(f"Sub plan not found: {resolved_path}")
        return resolved_path

    def _package_root(self) -> Path:
        return self.state.package_dir or self.state.plan_dir

    def _handle_dialog(self, dialog: Any) -> None:
        self.state.pending_dialog = dialog
        self.state.last_dialog_message = dialog.message
        self.state.logger.log("info", "dialog captured", dialog_type=dialog.type, dialog_message=dialog.message)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
