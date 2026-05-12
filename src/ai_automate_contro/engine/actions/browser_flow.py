from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.browser import BrowserConfig
from ai_automate_contro.engine.runtime import BrowserSession
from ai_automate_contro.engine.actions.browser_challenge import detect_challenge
from ai_automate_contro.engine.actions.browser_waits import wait


def open_browser(executor: Any, step: dict[str, Any]) -> None:
    name = step["name"]
    if name in executor.state.sessions:
        raise ValueError(f"浏览器会话已存在：{name}")

    config = BrowserConfig(
        headed=bool(step.get("headed", False)),
        slow_mo_ms=int(step.get("slow_mo_ms", 0)),
        timeout_ms=int(step.get("timeout_ms", 15_000)),
    )
    browser = executor.state.playwright.chromium.launch(
        headless=not config.headed,
        slow_mo=config.slow_mo_ms,
    )
    context_kwargs: dict[str, Any] = {}
    if "storage_state_path" in step:
        context_kwargs["storage_state"] = str(executor._resolve_path(step["storage_state_path"]))
    context = browser.new_context(**context_kwargs)
    context.set_default_timeout(config.timeout_ms)
    page = context.new_page()
    session = BrowserSession(
        name=name,
        browser=browser,
        context=context,
    )
    session.register_page("main", page, switch=True)
    executor.state.sessions[name] = session
    context.on("dialog", executor._handle_dialog)
    executor.state.logger.log("info", "browser opened", browser=name)


def page(executor: Any, step: dict[str, Any]) -> None:
    page_type = step["type"]
    session = executor.state.require_session(step["browser"])
    if page_type == "open":
        page_name = step["page"]
        new_page = session.context.new_page()
        session.register_page(page_name, new_page, switch=bool(step.get("switch", True)))
        if "url" in step:
            new_page.goto(step["url"], wait_until=step.get("wait_until", "domcontentloaded"))
        executor.state.logger.log(
            "info",
            "new page opened",
            browser=step["browser"],
            page=page_name,
        )
        return
    if page_type == "switch":
        session.switch_page(step["page"])
        executor.state.logger.log("info", "page switched", browser=step["browser"], page=step["page"])
        return
    if page_type == "close":
        closed_page = session.close_page(step.get("page"))
        executor.state.logger.log("info", "page closed", browser=step["browser"], page=closed_page)
        return
    raise ValueError(f"不支持的 page type：{page_type}")


def close_browser(executor: Any, step: dict[str, Any]) -> None:
    session_name = step["browser"]
    session = executor.state.require_session(session_name)
    session.context.close()
    session.browser.close()
    del executor.state.sessions[session_name]
    executor.state.logger.log("info", "browser closed", browser=session_name)


def navigate(executor: Any, step: dict[str, Any]) -> None:
    navigate_type = step["type"]
    target_page = executor._page(step)
    wait_until = step.get("wait_until", "domcontentloaded")
    if navigate_type == "goto":
        target_page.goto(step["url"], wait_until=wait_until)
        return
    if navigate_type == "refresh":
        target_page.reload(wait_until=wait_until)
        return
    if navigate_type == "back":
        target_page.go_back(wait_until=wait_until)
        return
    if navigate_type == "forward":
        target_page.go_forward(wait_until=wait_until)
        return
    raise ValueError(f"不支持的 navigate type：{navigate_type}")


def element(executor: Any, step: dict[str, Any]) -> None:
    element_type = step["type"]
    locator = executor._locator(step)
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
        _select_option(locator, step)
        return
    if element_type == "set_files":
        files = step["files"]
        if isinstance(files, str):
            files = [files]
        resolved_files = [str(executor._resolve_path(file_path)) for file_path in files]
        locator.set_input_files(resolved_files)
        return
    raise ValueError(f"不支持的 element type：{element_type}")


ACTION_HANDLERS = {
    "close_browser": close_browser,
    "detect_challenge": detect_challenge,
    "element": element,
    "navigate": navigate,
    "open_browser": open_browser,
    "page": page,
    "wait": wait,
}


def _select_option(locator: Any, step: dict[str, Any]) -> None:
    if "value" in step:
        locator.select_option(value=str(step["value"]))
        return
    if "label" in step:
        locator.select_option(label=str(step["label"]))
        return
    if "index_value" in step:
        locator.select_option(index=int(step["index_value"]))
        return
    raise ValueError("element type=select 需要 value、label 或 index_value 之一。")
