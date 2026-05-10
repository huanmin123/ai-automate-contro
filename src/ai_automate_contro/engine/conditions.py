from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.runtime import RuntimeState


class ConditionEvaluator:
    def __init__(self, state: RuntimeState) -> None:
        self.state = state

    def evaluate(self, condition: Any) -> bool:
        if isinstance(condition, bool):
            return condition
        if condition is None:
            return False
        if not isinstance(condition, dict):
            return bool(condition)

        condition_type = condition.get("type", "truthy")

        if condition_type == "truthy":
            return bool(condition.get("value"))
        if condition_type == "equals":
            return condition.get("left") == condition.get("right")
        if condition_type == "not_equals":
            return condition.get("left") != condition.get("right")
        if condition_type == "contains":
            return condition.get("value") in condition.get("container", [])
        if condition_type == "exists":
            return condition.get("name") in self.state.variables
        if condition_type == "all":
            return all(self.evaluate(item) for item in condition.get("conditions", []))
        if condition_type == "any":
            return any(self.evaluate(item) for item in condition.get("conditions", []))
        if condition_type == "not":
            return not self.evaluate(condition.get("condition"))
        if condition_type == "selector_exists":
            session = self.state.require_session(condition["browser"])
            page = session.require_page(condition.get("page"))
            return page.locator(condition["selector"]).count() > 0
        if condition_type == "selector_visible":
            session = self.state.require_session(condition["browser"])
            page = session.require_page(condition.get("page"))
            locator = page.locator(condition["selector"])
            if "index" in condition:
                return locator.nth(int(condition["index"])).is_visible()
            if locator.count() == 0:
                return False
            return locator.first.is_visible()

        raise ValueError(f"Unsupported condition type: {condition_type}")
