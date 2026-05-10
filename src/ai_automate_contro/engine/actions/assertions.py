from __future__ import annotations

from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def assert_selector(executor: Any, step: dict[str, Any]) -> None:
    try:
        executor._locator(step).wait_for(state=step.get("state", "visible"))
    except PlaywrightTimeoutError as error:
        raise AssertionError(
            f"Selector assertion failed for '{step['selector']}'"
        ) from error


def assert_text(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._locator(step).inner_text().strip()
    expected = str(step["expected"])
    mode = step.get("mode", "equals")
    if mode == "equals" and actual == expected:
        return
    if mode == "contains" and expected in actual:
        return
    raise AssertionError(
        f"Text assertion failed. mode={mode}, expected={expected!r}, actual={actual!r}"
    )


def assert_value(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._locator(step).input_value()
    expected = str(step["expected"])
    mode = step.get("mode", "equals")
    if mode == "equals" and actual == expected:
        return
    if mode == "contains" and expected in actual:
        return
    raise AssertionError(
        f"Value assertion failed. mode={mode}, expected={expected!r}, actual={actual!r}"
    )


def assert_url(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._page(step).url
    expected = str(step["expected"])
    mode = step.get("mode", "contains")
    if mode == "contains" and expected in actual:
        return
    if mode == "equals" and actual == expected:
        return
    if mode == "not_contains" and expected not in actual:
        return
    raise AssertionError(f"URL assertion failed. expected to contain {expected!r}, actual={actual!r}")


def assert_count(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._page(step).locator(step["selector"]).count()
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
