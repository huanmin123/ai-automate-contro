from __future__ import annotations

from typing import Any


def action_extract(executor: Any, step: dict[str, Any]) -> None:
    extract_type = step["type"]
    value: Any
    if extract_type == "text":
        value = executor._locator(step).inner_text()
    elif extract_type == "value":
        value = executor._locator(step).input_value()
    elif extract_type == "attribute":
        value = executor._locator(step).get_attribute(step["attribute"])
    elif extract_type == "html":
        value = executor._locator(step).inner_html()
    elif extract_type == "count":
        value = executor._locator_for_selector(step, step["selector"], index_field="count_index").count()
    elif extract_type == "all_texts":
        values = [
            item.strip()
            for item in executor._locator_for_selector(
                step,
                step["selector"],
                index_field="all_texts_index",
            ).all_inner_texts()
        ]
        value = [item for item in values if item] if step.get("skip_empty", True) else values
    elif extract_type == "all_values":
        locator = executor._locator_for_selector(step, step["selector"], index_field="all_values_index")
        value = [locator.nth(index).input_value() for index in range(locator.count())]
    elif extract_type == "table":
        value = _extract_table_value(executor, step)
    elif extract_type == "frames":
        value = _extract_frames_value(executor, step)
    elif extract_type == "url":
        value = executor._page(step).url
    elif extract_type == "title":
        value = executor._page(step).title()
    elif extract_type == "bounding_box":
        value = executor._locator(step).bounding_box()
    elif extract_type == "css":
        value = executor._locator(step).evaluate(
            "(element, propertyName) => window.getComputedStyle(element).getPropertyValue(propertyName)",
            step["property"],
        )
    elif extract_type == "aria_snapshot":
        options: dict[str, Any] = {}
        for field in ("timeout", "depth", "mode"):
            if field in step:
                options[field] = step[field]
        value = executor._locator(step).aria_snapshot(**options)
    else:
        raise ValueError(f"Unsupported extract type: {extract_type}")
    executor.state.variables[step["save_as"]] = value
    executor.state.logger.log("info", "value extracted", type=extract_type, save_as=step["save_as"], value=value)


def _extract_table_value(executor: Any, step: dict[str, Any]) -> list[Any]:
    row_locator = executor._locator_for_selector(step, step["row_selector"], index_field="row_index")
    cell_selector = step.get("cell_selector", "td")
    include_header = bool(step.get("include_header", False))
    headers: list[str] = []

    if include_header and step.get("header_selector"):
        header_locator = executor._locator_for_selector(step, step["header_selector"], index_field="header_index")
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

    return rows


def _extract_frames_value(executor: Any, step: dict[str, Any]) -> list[dict[str, Any]]:
    frames = executor._page(step).frames
    frame_indexes = {frame: index for index, frame in enumerate(frames)}
    result: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        parent = frame.parent_frame
        item = {
            "index": index,
            "name": frame.name,
            "url": frame.url,
            "parent_index": frame_indexes.get(parent) if parent is not None else None,
            "child_count": len(frame.child_frames),
            "is_detached": frame.is_detached(),
        }
        if _frame_matches(item, step):
            result.append(item)
    return result


def _frame_matches(item: dict[str, Any], step: dict[str, Any]) -> bool:
    if "frame_name" in step and item["name"] != str(step["frame_name"]):
        return False
    if "frame_url" in step and item["url"] != str(step["frame_url"]):
        return False
    if "frame_url_contains" in step and str(step["frame_url_contains"]) not in item["url"]:
        return False
    return "frame_index" not in step or item["index"] == int(step["frame_index"])


ACTION_HANDLERS = {
    "extract": action_extract,
}
