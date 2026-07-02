from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.browser import BrowserConfig
from ai_automate_contro.engine.runtime import BrowserSession
from ai_automate_contro.engine.actions.browser_challenge import detect_challenge
from ai_automate_contro.engine.actions.browser_waits import wait
from ai_automate_contro.support.playwright_browsers import (
    format_playwright_browser_missing_message,
    is_playwright_browser_missing_error,
)
from ai_automate_contro.support.utils import ensure_directory


PLAN_PROFILE_DIR = "profiles/browser"
UNSUPPORTED_PROFILE_FIELDS = {"profile_dir", "profile_name", "user_data_dir"}


def open_browser(executor: Any, step: dict[str, Any]) -> None:
    name = step["name"]
    if name in executor.state.sessions:
        raise ValueError(f"浏览器会话已存在：{name}")
    unsupported_fields = sorted(field for field in UNSUPPORTED_PROFILE_FIELDS if field in step)
    if unsupported_fields:
        raise ValueError(
            "open_browser 不支持自定义 profile 路径或名称；"
            f"当前 plan 包只允许一套浏览器状态 profiles/browser。包含字段：{', '.join(unsupported_fields)}"
        )
    raw_use_profile = step.get("use_profile", False)
    if not isinstance(raw_use_profile, bool):
        raise ValueError("open_browser.use_profile 必须是布尔值。")
    use_profile = raw_use_profile
    if use_profile and "storage_state_path" in step:
        raise ValueError("open_browser.use_profile=true 时不能同时使用 storage_state_path。")
    if use_profile and any(session.persistent_profile for session in executor.state.sessions.values()):
        raise ValueError("当前运行已经打开 plan 级浏览器状态会话；同一时间只能打开一个 use_profile=true 浏览器。")

    config = BrowserConfig(
        headed=bool(step.get("headed", False)),
        slow_mo_ms=int(step.get("slow_mo_ms", 0)),
        timeout_ms=int(step.get("timeout_ms", 15_000)),
    )
    if executor.state.playwright is None:
        raise RuntimeError("当前运行没有 Playwright runtime；请确认 plan.automation_type=browser 后再使用浏览器 action。")
    browser_type = step.get("browser_type", "chromium")
    if browser_type not in {"chromium", "firefox", "webkit"}:
        raise ValueError(f"不支持的 browser_type：{browser_type}")
    if use_profile and browser_type != "chromium":
        raise ValueError("open_browser.use_profile=true 仅支持 browser_type=chromium；Chrome/Edge 请使用 channel。")
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
    context_kwargs = _build_context_kwargs(executor, step)
    try:
        if use_profile:
            profile_dir = ensure_directory(executor._package_root() / PLAN_PROFILE_DIR)
            context = browser_launcher.launch_persistent_context(
                str(profile_dir),
                **launch_kwargs,
                **context_kwargs,
            )
            browser = None
        else:
            browser = browser_launcher.launch(
                **launch_kwargs,
            )
            if "storage_state_path" in step:
                context_kwargs["storage_state"] = str(executor._resolve_path(step["storage_state_path"]))
            context = browser.new_context(**context_kwargs)
    except Exception as error:
        if is_playwright_browser_missing_error(error):
            raise RuntimeError(format_playwright_browser_missing_message(browser_type, error)) from error
        raise
    context.set_default_timeout(config.timeout_ms)
    page = context.pages[0] if context.pages else context.new_page()
    session = BrowserSession(
        name=name,
        browser=browser,
        context=context,
        headed=config.headed,
        persistent_profile=use_profile,
    )
    session.register_page("main", page, switch=True)
    executor.state.sessions[name] = session
    context.on("dialog", executor._handle_dialog)
    executor.state.logger.log(
        "info",
        "browser opened",
        browser=name,
        headed=config.headed,
        use_profile=use_profile,
        profile_dir=PLAN_PROFILE_DIR if use_profile else "",
    )


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
    if session.browser is not None:
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
        if executor.state.playwright is None:
            raise RuntimeError("当前运行没有 Playwright runtime；不能使用 Playwright 设备预设。")
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
