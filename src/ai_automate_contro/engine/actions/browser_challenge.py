from __future__ import annotations

from typing import Any


def detect_challenge(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    matches: list[dict[str, Any]] = []
    for rule in step.get("rules", []):
        rule_type = rule.get("type", "selector_visible")
        label = rule.get("label", rule_type)
        matched = False

        if rule_type == "selector_visible":
            locator = target_page.locator(rule["selector"])
            if locator.count() > 0:
                target = locator.nth(int(rule["index"])) if "index" in rule else locator.first
                matched = target.is_visible()
        elif rule_type == "selector_exists":
            matched = target_page.locator(rule["selector"]).count() > 0
        elif rule_type == "text_contains":
            locator = target_page.locator(rule.get("selector", "body"))
            if locator.count() > 0:
                matched = str(rule["text"]) in locator.first.inner_text()
        elif rule_type == "url_contains":
            matched = str(rule["value"]) in target_page.url
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
    executor.state.variables[step["save_as"]] = result
    if "save_detected_as" in step:
        executor.state.variables[step["save_detected_as"]] = result["matched"]
    if "save_label_as" in step:
        executor.state.variables[step["save_label_as"]] = result["labels"][0] if result["labels"] else ""
    executor.state.logger.log(
        "info",
        "challenge detected",
        matched=result["matched"],
        labels=result["labels"],
        save_as=step["save_as"],
    )
