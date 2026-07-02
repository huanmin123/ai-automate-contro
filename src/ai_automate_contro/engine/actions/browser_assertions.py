from __future__ import annotations

from typing import Any

from . import assertions


def action_assert(executor: Any, step: dict[str, Any]) -> None:
    assert_type = step["type"]
    if assert_type == "selector":
        assertions.assert_selector(executor, step)
        return
    if assert_type == "text":
        assertions.assert_text(executor, step)
        return
    if assert_type == "value":
        assertions.assert_value(executor, step)
        return
    if assert_type == "url":
        assertions.assert_url(executor, step)
        return
    if assert_type == "count":
        assertions.assert_count(executor, step)
        return
    if assert_type == "attribute":
        assertions.assert_attribute(executor, step)
        return
    if assert_type == "css":
        assertions.assert_css(executor, step)
        return
    if assert_type == "checked":
        assertions.assert_checked(executor, step)
        return
    if assert_type == "unchecked":
        assertions.assert_unchecked(executor, step)
        return
    if assert_type == "enabled":
        assertions.assert_enabled(executor, step)
        return
    if assert_type == "disabled":
        assertions.assert_disabled(executor, step)
        return
    if assert_type == "visible":
        assertions.assert_visible(executor, step)
        return
    if assert_type == "hidden":
        assertions.assert_hidden(executor, step)
        return
    if assert_type == "title":
        assertions.assert_title(executor, step)
        return
    raise ValueError(f"不支持的 assert type：{assert_type}")
