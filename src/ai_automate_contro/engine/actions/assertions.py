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
    _assert_string(actual, str(step["expected"]), step.get("mode", "equals"), "Text")


def assert_value(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._locator(step).input_value()
    _assert_string(actual, str(step["expected"]), step.get("mode", "equals"), "Value")


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
    actual = executor._locator_for_selector(step, step["selector"], index_field="count_index").count()
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


def assert_attribute(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._locator(step).get_attribute(step["attribute"])
    _assert_string(actual or "", str(step["expected"]), step.get("mode", "equals"), "Attribute")


def assert_css(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._locator(step).evaluate(
        "(element, propertyName) => window.getComputedStyle(element).getPropertyValue(propertyName)",
        step["property"],
    )
    _assert_string(str(actual).strip(), str(step["expected"]), step.get("mode", "equals"), "CSS")


def assert_checked(executor: Any, step: dict[str, Any]) -> None:
    if not executor._locator(step).is_checked():
        raise AssertionError("Checked assertion failed.")


def assert_unchecked(executor: Any, step: dict[str, Any]) -> None:
    if executor._locator(step).is_checked():
        raise AssertionError("Unchecked assertion failed.")


def assert_enabled(executor: Any, step: dict[str, Any]) -> None:
    if not executor._locator(step).is_enabled():
        raise AssertionError("Enabled assertion failed.")


def assert_disabled(executor: Any, step: dict[str, Any]) -> None:
    if not executor._locator(step).is_disabled():
        raise AssertionError("Disabled assertion failed.")


def assert_visible(executor: Any, step: dict[str, Any]) -> None:
    if not executor._locator(step).is_visible():
        raise AssertionError("Visible assertion failed.")


def assert_hidden(executor: Any, step: dict[str, Any]) -> None:
    if not executor._locator(step).is_hidden():
        raise AssertionError("Hidden assertion failed.")


def assert_title(executor: Any, step: dict[str, Any]) -> None:
    actual = executor._page(step).title()
    _assert_string(actual, str(step["expected"]), step.get("mode", "contains"), "Title")


def _assert_string(actual: str, expected: str, mode: str, label: str) -> None:
    if mode == "equals" and actual == expected:
        return
    if mode == "contains" and expected in actual:
        return
    if mode == "not_contains" and expected not in actual:
        return
    raise AssertionError(f"{label} assertion failed. mode={mode}, expected={expected!r}, actual={actual!r}")
