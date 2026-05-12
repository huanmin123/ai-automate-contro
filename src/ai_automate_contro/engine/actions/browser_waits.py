from __future__ import annotations

from typing import Any


def wait(executor: Any, step: dict[str, Any]) -> None:
    wait_type = step.get("type", "time")
    if wait_type == "time":
        if any(field in step for field in ("selector", "url", "text", "expected")):
            raise ValueError("wait 带 selector/url/text/expected 时必须显式设置非 time 的 type。")
        executor._page(step).wait_for_timeout(int(float(step.get("seconds", 1)) * 1000))
        return
    if wait_type == "selector":
        _wait_for_selector(executor, step)
        return
    if wait_type == "url":
        executor._page(step).wait_for_url(step["url"])
        return
    if wait_type == "text":
        _wait_for_text(executor, step)
        return
    if wait_type == "count":
        _wait_for_count(executor, step)
        return
    raise ValueError(f"不支持的 wait type：{wait_type}")


def _wait_for_selector(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    selector = step["selector"]
    state = step.get("state", "visible")
    if "index" in step:
        target_page.locator(selector).nth(int(step["index"])).wait_for(state=state)
        return
    target_page.wait_for_selector(selector, state=state)


def _wait_for_text(executor: Any, step: dict[str, Any]) -> None:
    locator = executor._locator(step)
    expected = str(step["text"])
    mode = step.get("mode", "contains")
    locator.wait_for(state=step.get("state", "visible"))
    actual = locator.inner_text()
    if mode == "contains" and expected in actual:
        return
    if mode == "equals" and actual.strip() == expected:
        return
    raise AssertionError(f"wait_for_text 失败。mode={mode}，expected={expected!r}，actual={actual!r}")


def _wait_for_count(executor: Any, step: dict[str, Any]) -> None:
    selector = step["selector"]
    expected = int(step["expected"])
    mode = step.get("mode", "equals")
    target_page = executor._page(step)
    timeout_ms = int(step.get("timeout_ms", 15_000))
    start = target_page.evaluate("Date.now()")
    while True:
        actual = target_page.locator(selector).count()
        if mode == "equals" and actual == expected:
            return
        if mode == "gte" and actual >= expected:
            return
        if mode == "lte" and actual <= expected:
            return
        now = target_page.evaluate("Date.now()")
        if int(now) - int(start) >= timeout_ms:
            raise AssertionError(f"wait_for_count 失败。mode={mode}，expected={expected}，actual={actual}")
        target_page.wait_for_timeout(200)
