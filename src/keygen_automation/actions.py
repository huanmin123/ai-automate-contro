from __future__ import annotations

import csv
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from keygen_automation.ai_registry import data_url_to_bytes, upload_image_to_ocr
from keygen_automation.browser import BrowserConfig
from keygen_automation.conditions import ConditionEvaluator
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

    def _capture_failure_state(self, step_number: int, action: str, step_name: str) -> None:
        screenshot_dir = self.state.output_dir / "failure-screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        for browser_name, session in self.state.sessions.items():
            for page_name, page in session.pages.items():
                screenshot_path = screenshot_dir / f"step-{step_number:03d}-{browser_name}-{page_name}-{action}.png"
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

    def _action_set_variable(self, step: dict[str, Any]) -> None:
        name = step["name"]
        value = step["value"]
        self.state.variables[name] = value
        self.state.logger.log("info", "variable set", name=name, value=value)

    def _action_set_variables(self, step: dict[str, Any]) -> None:
        values = step["values"]
        for key, value in values.items():
            self.state.variables[key] = value
        self.state.logger.log("info", "variables set", names=list(values.keys()))

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
            context_kwargs["storage_state"] = str(self._resolve_output_path(step["storage_state_path"]))
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

    def _action_open_new_page(self, step: dict[str, Any]) -> None:
        session = self.state.require_session(step["browser"])
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

    def _action_switch_page(self, step: dict[str, Any]) -> None:
        session = self.state.require_session(step["browser"])
        session.switch_page(step["page"])
        self.state.logger.log("info", "page switched", browser=step["browser"], page=step["page"])

    def _action_close_page(self, step: dict[str, Any]) -> None:
        session = self.state.require_session(step["browser"])
        closed_page = session.close_page(step.get("page"))
        self.state.logger.log("info", "page closed", browser=step["browser"], page=closed_page)

    def _action_close_browser(self, step: dict[str, Any]) -> None:
        session_name = step["browser"]
        session = self.state.require_session(session_name)
        session.context.close()
        session.browser.close()
        del self.state.sessions[session_name]
        self.state.logger.log("info", "browser closed", browser=session_name)

    def _action_goto(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.goto(step["url"], wait_until=step.get("wait_until", "domcontentloaded"))

    def _action_refresh(self, step: dict[str, Any]) -> None:
        self._page(step).reload(wait_until=step.get("wait_until", "domcontentloaded"))

    def _action_go_back(self, step: dict[str, Any]) -> None:
        self._page(step).go_back(wait_until=step.get("wait_until", "domcontentloaded"))

    def _action_go_forward(self, step: dict[str, Any]) -> None:
        self._page(step).go_forward(wait_until=step.get("wait_until", "domcontentloaded"))

    def _action_click(self, step: dict[str, Any]) -> None:
        self._locator(step).click()

    def _action_hover(self, step: dict[str, Any]) -> None:
        self._locator(step).hover()

    def _action_fill(self, step: dict[str, Any]) -> None:
        self._locator(step).fill(str(step["value"]))

    def _action_clear(self, step: dict[str, Any]) -> None:
        self._locator(step).fill("")

    def _action_type(self, step: dict[str, Any]) -> None:
        self._locator(step).type(str(step["value"]), delay=int(step.get("delay_ms", 50)))

    def _action_focus(self, step: dict[str, Any]) -> None:
        self._locator(step).focus()

    def _action_wait_for_selector(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        selector = step["selector"]
        state = step.get("state", "visible")
        if "index" in step:
            page.locator(selector).nth(int(step["index"])).wait_for(state=state)
            return
        page.wait_for_selector(selector, state=state)

    def _action_wait(self, step: dict[str, Any]) -> None:
        self._page(step).wait_for_timeout(int(float(step.get("seconds", 1)) * 1000))

    def _action_wait_for_url(self, step: dict[str, Any]) -> None:
        self._page(step).wait_for_url(step["url"])

    def _action_wait_for_text(self, step: dict[str, Any]) -> None:
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

    def _action_wait_for_count(self, step: dict[str, Any]) -> None:
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

    def _action_extract_text(self, step: dict[str, Any]) -> None:
        text = self._locator(step).inner_text()
        self.state.variables[step["save_as"]] = text
        self.state.logger.log("info", "text extracted", save_as=step["save_as"], value=text)

    def _action_extract_value(self, step: dict[str, Any]) -> None:
        value = self._locator(step).input_value()
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "value extracted", save_as=step["save_as"], value=value)

    def _action_extract_attribute(self, step: dict[str, Any]) -> None:
        value = self._locator(step).get_attribute(step["attribute"])
        self.state.variables[step["save_as"]] = value
        self.state.logger.log(
            "info",
            "attribute extracted",
            save_as=step["save_as"],
            attribute=step["attribute"],
            value=value,
        )

    def _action_extract_html(self, step: dict[str, Any]) -> None:
        value = self._locator(step).inner_html()
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "html extracted", save_as=step["save_as"])

    def _action_extract_count(self, step: dict[str, Any]) -> None:
        value = self._page(step).locator(step["selector"]).count()
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "count extracted", save_as=step["save_as"], value=value)

    def _action_extract_nth_text(self, step: dict[str, Any]) -> None:
        selector = step["selector"]
        index = int(step.get("index", 0))
        locator = self._page(step).locator(selector).nth(index)
        text = locator.inner_text()
        self.state.variables[step["save_as"]] = text
        self.state.logger.log(
            "info",
            "nth text extracted",
            selector=selector,
            index=index,
            save_as=step["save_as"],
            value=text,
        )

    def _action_extract_all_texts(self, step: dict[str, Any]) -> None:
        locator = self._page(step).locator(step["selector"])
        values = [item.strip() for item in locator.all_inner_texts()]
        if step.get("skip_empty", True):
            values = [item for item in values if item]
        self.state.variables[step["save_as"]] = values
        self.state.logger.log("info", "all texts extracted", save_as=step["save_as"], count=len(values))

    def _action_extract_all_values(self, step: dict[str, Any]) -> None:
        locator = self._page(step).locator(step["selector"])
        values = []
        for index in range(locator.count()):
            values.append(locator.nth(index).input_value())
        self.state.variables[step["save_as"]] = values
        self.state.logger.log("info", "all values extracted", save_as=step["save_as"], count=len(values))

    def _action_extract_table(self, step: dict[str, Any]) -> None:
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

        self.state.variables[step["save_as"]] = rows
        self.state.logger.log("info", "table extracted", save_as=step["save_as"], count=len(rows))

    def _action_press(self, step: dict[str, Any]) -> None:
        self._locator(step).press(step["key"])

    def _action_keyboard_press(self, step: dict[str, Any]) -> None:
        self._page(step).keyboard.press(step["key"])

    def _action_keyboard_type(self, step: dict[str, Any]) -> None:
        self._page(step).keyboard.type(str(step["value"]), delay=int(step.get("delay_ms", 50)))

    def _action_keyboard_down(self, step: dict[str, Any]) -> None:
        self._page(step).keyboard.down(step["key"])

    def _action_keyboard_up(self, step: dict[str, Any]) -> None:
        self._page(step).keyboard.up(step["key"])

    def _action_scroll_into_view(self, step: dict[str, Any]) -> None:
        self._locator(step).scroll_into_view_if_needed()

    def _action_scroll_by(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        delta_x = int(step.get("delta_x", 0))
        delta_y = int(step.get("delta_y", 0))
        page.evaluate(
            "(args) => window.scrollBy(args.deltaX, args.deltaY)",
            {"deltaX": delta_x, "deltaY": delta_y},
        )

    def _action_mouse_move(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.mouse.move(float(step["x"]), float(step["y"]))

    def _action_mouse_click_at(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.mouse.click(
            float(step["x"]),
            float(step["y"]),
            button=step.get("button", "left"),
            click_count=int(step.get("click_count", 1)),
        )

    def _action_mouse_down(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.mouse.down(button=step.get("button", "left"))

    def _action_mouse_up(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.mouse.up(button=step.get("button", "left"))

    def _action_mouse_wheel(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        page.mouse.wheel(float(step.get("delta_x", 0)), float(step.get("delta_y", 0)))

    def _action_check(self, step: dict[str, Any]) -> None:
        self._locator(step).check()

    def _action_uncheck(self, step: dict[str, Any]) -> None:
        self._locator(step).uncheck()

    def _action_select_option(self, step: dict[str, Any]) -> None:
        locator = self._locator(step)
        if "value" in step:
            locator.select_option(value=str(step["value"]))
            return
        if "label" in step:
            locator.select_option(label=str(step["label"]))
            return
        if "index_value" in step:
            locator.select_option(index=int(step["index_value"]))
            return
        raise ValueError("select_option requires one of: value, label, index_value")

    def _action_set_input_files(self, step: dict[str, Any]) -> None:
        locator = self._locator(step)
        files = step["files"]
        if isinstance(files, str):
            files = [files]
        resolved_files = [str(self._resolve_output_path(file_path)) for file_path in files]
        locator.set_input_files(resolved_files)

    def _action_screenshot(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._page(step).screenshot(
            path=str(output_path),
            full_page=bool(step.get("full_page", False)),
        )
        self.state.logger.log("info", "screenshot saved", path=str(output_path))

    def _action_manual_confirm(self, step: dict[str, Any]) -> None:
        prompt = step.get("prompt", "Continue? Input y to proceed: ")
        answer = input(prompt).strip().lower()
        if answer != "y":
            raise RuntimeError("Manual confirmation was not accepted.")

    def _action_print(self, step: dict[str, Any]) -> None:
        self.state.logger.log("info", str(step["message"]))

    def _action_dump_variables(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(self.state.variables, file, ensure_ascii=False, indent=2)
        self.state.logger.log("info", "variables dumped", path=str(output_path))

    def _action_save_page_html(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html = self._page(step).content()
        with output_path.open("w", encoding="utf-8") as file:
            file.write(html)
        self.state.logger.log("info", "page html saved", path=str(output_path))

    def _action_ocr_image(self, step: dict[str, Any]) -> None:
        if self.state.ai_registry is None:
            raise RuntimeError("AI registry is not initialized.")
        service = self.state.ai_registry.get_ocr_service(step["service"])

        image_bytes: bytes
        content_type = "image/png"
        filename = step.get("filename", "ocr-input.png")

        if "path" in step:
            source_path = self._resolve_output_path(step["path"])
            image_bytes = source_path.read_bytes()
            content_type = mimetypes.guess_type(str(source_path))[0] or content_type
            filename = source_path.name
        elif "data_url" in step:
            image_bytes, content_type = data_url_to_bytes(str(step["data_url"]))
        elif "selector" in step:
            output_path = self._resolve_output_path(
                step.get("capture_path", str(self.state.output_dir / "ocr-captures" / f"{step['save_as']}.png"))
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._locator(step).screenshot(path=str(output_path))
            image_bytes = output_path.read_bytes()
            content_type = "image/png"
            filename = output_path.name
        else:
            raise ValueError("ocr_image requires one of: path, data_url, selector")

        result = upload_image_to_ocr(service, image_bytes, filename, content_type)
        self.state.variables[step["save_as"]] = result
        if "save_text_as" in step:
            self.state.variables[step["save_text_as"]] = result.get("text", "")
        self.state.logger.log(
            "info",
            "ocr completed",
            service=step["service"],
            save_as=step["save_as"],
            text_length=len(str(result.get("text", ""))),
        )

    def _action_llm_chat(self, step: dict[str, Any]) -> None:
        if self.state.ai_registry is None:
            raise RuntimeError("AI registry is not initialized.")
        service = self.state.ai_registry.get_llm_service(step["service"])
        client = self.state.ai_registry.build_llm_client(service)
        response = client.chat.completions.create(
            model=step.get("model", service.model),
            messages=step["messages"],
            temperature=float(step.get("temperature", 0)),
        )
        payload = response.model_dump()
        self.state.variables[step["save_as"]] = payload
        if "save_text_as" in step:
            text = ""
            if response.choices:
                text = response.choices[0].message.content or ""
            self.state.variables[step["save_text_as"]] = text
        self.state.logger.log(
            "info",
            "llm chat completed",
            service=step["service"],
            model=step.get("model", service.model),
            save_as=step["save_as"],
        )

    def _action_llm_extract_json(self, step: dict[str, Any]) -> None:
        if self.state.ai_registry is None:
            raise RuntimeError("AI registry is not initialized.")
        service = self.state.ai_registry.get_llm_service(step["service"])
        client = self.state.ai_registry.build_llm_client(service)

        schema = step.get("schema_description", "")
        input_text = str(step["input"])
        system_prompt = str(
            step.get(
                "system_prompt",
                "你是一个结构化信息提取助手。请严格只输出 JSON 对象，不要输出解释、Markdown 或代码块。",
            )
        )
        user_prompt = (
            f"请从下面内容中提取结构化信息，并严格输出 JSON 对象。\n"
            f"目标结构说明：{schema}\n"
            f"原始内容：\n{input_text}"
        )

        response = client.chat.completions.create(
            model=step.get("model", service.model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(step.get("temperature", 0)),
        )

        raw_text = ""
        if response.choices:
            raw_text = response.choices[0].message.content or ""
        parsed = self._extract_json_from_text(raw_text)

        self.state.variables[step["save_as"]] = parsed
        if "save_text_as" in step:
            self.state.variables[step["save_text_as"]] = raw_text
        self.state.logger.log(
            "info",
            "llm json extracted",
            service=step["service"],
            model=step.get("model", service.model),
            save_as=step["save_as"],
        )

    def _action_save_storage_state(self, step: dict[str, Any]) -> None:
        session = self.state.require_session(step["browser"])
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        session.context.storage_state(path=str(output_path))
        self.state.logger.log("info", "storage state saved", browser=step["browser"], path=str(output_path))

    def _action_load_storage_state(self, step: dict[str, Any]) -> None:
        source_path = self._resolve_output_path(step["path"])
        self.state.variables[step["save_as"]] = str(source_path)
        self.state.logger.log("info", "storage state path loaded", save_as=step["save_as"], path=str(source_path))

    def _action_accept_dialog(self, step: dict[str, Any]) -> None:
        trigger = step.get("trigger")
        if trigger:
            page = self._page(step)
            prompt_text = step.get("prompt_text")

            def handler(dialog: Any) -> None:
                self.state.last_dialog_message = dialog.message
                self.state.logger.log(
                    "info",
                    "dialog auto-accepted",
                    dialog_type=dialog.type,
                    dialog_message=dialog.message,
                )
                dialog.accept(prompt_text)

            page.once("dialog", handler)
            self.run([trigger])
            self.state.pending_dialog = None
            return

        if self.state.pending_dialog is None:
            raise RuntimeError("No pending dialog to accept.")
        prompt_text = step.get("prompt_text")
        self.state.pending_dialog.accept(prompt_text)
        self.state.logger.log("info", "dialog accepted", message=self.state.last_dialog_message)
        self.state.pending_dialog = None

    def _action_dismiss_dialog(self, step: dict[str, Any]) -> None:
        trigger = step.get("trigger")
        if trigger:
            page = self._page(step)

            def handler(dialog: Any) -> None:
                self.state.last_dialog_message = dialog.message
                self.state.logger.log(
                    "info",
                    "dialog auto-dismissed",
                    dialog_type=dialog.type,
                    dialog_message=dialog.message,
                )
                dialog.dismiss()

            page.once("dialog", handler)
            self.run([trigger])
            self.state.pending_dialog = None
            return

        if self.state.pending_dialog is None:
            raise RuntimeError("No pending dialog to dismiss.")
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
        output_path = self._resolve_output_path(step["path"])
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

    def _action_wait_for_request(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        trigger = step.get("trigger")
        if not trigger:
            raise ValueError("wait_for_request requires a trigger step.")
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

    def _action_wait_for_response(self, step: dict[str, Any]) -> None:
        page = self._page(step)
        trigger = step.get("trigger")
        if not trigger:
            raise ValueError("wait_for_response requires a trigger step.")
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

    def _action_write_json(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        value = step["value"]
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=int(step.get("indent", 2)))
        self.state.logger.log("info", "json written", path=str(output_path))

    def _action_write_text(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            file.write(str(step["content"]))
        self.state.logger.log("info", "text written", path=str(output_path))

    def _action_append_text(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as file:
            file.write(str(step["content"]))
        self.state.logger.log("info", "text appended", path=str(output_path))

    def _action_write_csv(self, step: dict[str, Any]) -> None:
        output_path = self._resolve_output_path(step["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = step["rows"]
        headers = step.get("headers")

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

    def _action_assert_selector(self, step: dict[str, Any]) -> None:
        try:
            self._locator(step).wait_for(state=step.get("state", "visible"))
        except PlaywrightTimeoutError as error:
            raise AssertionError(
                f"Selector assertion failed for '{step['selector']}'"
            ) from error

    def _action_assert_text(self, step: dict[str, Any]) -> None:
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

    def _action_assert_value(self, step: dict[str, Any]) -> None:
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

    def _action_assert_url_contains(self, step: dict[str, Any]) -> None:
        actual = self._page(step).url
        expected = str(step["expected"])
        if expected not in actual:
            raise AssertionError(f"URL assertion failed. expected to contain {expected!r}, actual={actual!r}")

    def _action_assert_count(self, step: dict[str, Any]) -> None:
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

    def _action_load_json(self, step: dict[str, Any]) -> None:
        path = self._resolve_output_path(step["path"])
        with path.open("r", encoding="utf-8") as file:
            self.state.variables[step["save_as"]] = json.load(file)
        self.state.logger.log("info", "json loaded", path=str(path), save_as=step["save_as"])

    def _action_load_txt(self, step: dict[str, Any]) -> None:
        path = self._resolve_output_path(step["path"])
        with path.open("r", encoding="utf-8") as file:
            content = file.read()
        if step.get("split_lines", False):
            value = [line.strip() for line in content.splitlines() if line.strip()]
        else:
            value = content
        self.state.variables[step["save_as"]] = value
        self.state.logger.log("info", "text loaded", path=str(path), save_as=step["save_as"])

    def _action_load_csv(self, step: dict[str, Any]) -> None:
        path = self._resolve_output_path(step["path"])
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
        self.state.variables[step["save_as"]] = rows
        self.state.logger.log("info", "csv loaded", path=str(path), save_as=step["save_as"], count=len(rows))

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

    def _action_copy_variable(self, step: dict[str, Any]) -> None:
        source = step["source"]
        target = step["target"]
        if source not in self.state.variables:
            raise KeyError(f"Variable '{source}' is not defined.")
        self.state.variables[target] = self.state.variables[source]
        self.state.logger.log("info", "variable copied", source=source, target=target)

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

    def _resolve_output_path(self, raw_path: str) -> Path:
        return self.state.resolve_path(raw_path)

    def _handle_dialog(self, dialog: Any) -> None:
        self.state.pending_dialog = dialog
        self.state.last_dialog_message = dialog.message
        self.state.logger.log("info", "dialog captured", dialog_type=dialog.type, dialog_message=dialog.message)

    def _extract_json_from_text(self, raw_text: str) -> Any:
        text = raw_text.strip()
        if not text:
            raise ValueError("Model returned empty text, cannot extract JSON.")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
        if fenced_match:
            return json.loads(fenced_match.group(1))

        object_match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
        if object_match:
            return json.loads(object_match.group(1))

        raise ValueError("Could not extract JSON object from model response.")
