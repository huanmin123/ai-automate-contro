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
    browser_type = step.get("browser_type", "chromium")
    if browser_type not in {"chromium", "firefox", "webkit"}:
        raise ValueError(f"不支持的 browser_type：{browser_type}")
    browser_launcher = getattr(executor.state.playwright, browser_type)
    launch_kwargs: dict[str, Any] = {
        "headless": not config.headed,
        "slow_mo": config.slow_mo_ms,
    }
    if "proxy" in step:
        launch_kwargs["proxy"] = step["proxy"]
    if "channel" in step:
        if browser_type != "chromium":
            raise ValueError("channel 仅支持 Chromium 浏览器。")
        launch_kwargs["channel"] = step["channel"]
    if "args" in step:
        launch_kwargs["args"] = step["args"]
    browser = browser_launcher.launch(
        **launch_kwargs,
    )
    context_kwargs = _build_context_kwargs(executor, step)
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
    executor.state.logger.log("info", "browser opened", browser=name, headed=config.headed)


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
        locator.click(**_click_options(step))
        return
    if element_type == "dblclick":
        locator.dblclick(**_click_options(step))
        return
    if element_type == "right_click":
        options = _click_options(step)
        options["button"] = "right"
        locator.click(**options)
        return
    if element_type == "hover":
        locator.hover(**_hover_options(step))
        return
    if element_type == "tap":
        locator.tap(**_tap_options(step))
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
    if element_type == "drag_to":
        target_locator = executor._locator_for_selector(
            step,
            step["target_selector"],
            index_field="target_index",
        )
        locator.drag_to(target_locator, **_drag_options(step))
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


def _build_context_kwargs(executor: Any, step: dict[str, Any]) -> dict[str, Any]:
    context_kwargs: dict[str, Any] = {}
    if "device" in step:
        device_name = str(step["device"])
        devices = executor.state.playwright.devices
        if device_name not in devices:
            raise ValueError(f"未知的 Playwright 设备预设：{device_name}")
        context_kwargs.update(
            {
                key: value
                for key, value in devices[device_name].items()
                if key != "default_browser_type"
            }
        )
    passthrough_fields = {
        "viewport",
        "screen",
        "user_agent",
        "locale",
        "timezone_id",
        "geolocation",
        "permissions",
        "color_scheme",
        "reduced_motion",
        "forced_colors",
        "accept_downloads",
        "ignore_https_errors",
        "java_script_enabled",
        "bypass_csp",
        "device_scale_factor",
        "is_mobile",
        "has_touch",
        "extra_http_headers",
        "http_credentials",
        "base_url",
        "offline",
        "strict_selectors",
        "service_workers",
        "record_video_size",
        "record_har_omit_content",
        "record_har_url_filter",
        "record_har_mode",
        "record_har_content",
    }
    for field in passthrough_fields:
        if field in step:
            context_kwargs[field] = step[field]
    if "record_video_dir" in step:
        context_kwargs["record_video_dir"] = str(executor._resolve_output_path(step["record_video_dir"], category="videos"))
    if "record_har_path" in step:
        context_kwargs["record_har_path"] = str(executor._resolve_output_path(step["record_har_path"], category="har"))
    return context_kwargs


def _click_options(step: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for field in ("button", "modifiers", "position", "timeout", "trial"):
        if field in step:
            options[field] = step[field]
    if "click_count" in step:
        options["click_count"] = int(step["click_count"])
    if "delay_ms" in step:
        options["delay"] = int(step["delay_ms"])
    if "force" in step:
        options["force"] = bool(step["force"])
    return options


def _hover_options(step: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for field in ("modifiers", "position", "timeout", "trial"):
        if field in step:
            options[field] = step[field]
    if "force" in step:
        options["force"] = bool(step["force"])
    return options


def _tap_options(step: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for field in ("modifiers", "position", "timeout", "trial", "no_wait_after"):
        if field in step:
            options[field] = step[field]
    if "force" in step:
        options["force"] = bool(step["force"])
    return options


def _drag_options(step: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for field in ("source_position", "target_position", "timeout", "trial"):
        if field in step:
            options[field] = step[field]
    if "force" in step:
        options["force"] = bool(step["force"])
    return options
