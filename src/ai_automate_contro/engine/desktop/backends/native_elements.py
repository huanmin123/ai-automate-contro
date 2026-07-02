from __future__ import annotations

import json
import re
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackendError


def _normalize_element(element: dict[str, Any], *, index: int) -> dict[str, Any]:
    bounds = element.get("bounds") if isinstance(element.get("bounds"), dict) else {}
    normalized_bounds = {
        "x": _safe_int(bounds.get("x"), default=0),
        "y": _safe_int(bounds.get("y"), default=0),
        "width": _safe_int(bounds.get("width"), default=0),
        "height": _safe_int(bounds.get("height"), default=0),
    }
    element_id = str(element.get("id") or element.get("runtime_id") or f"element:{index}")
    return {
        "id": element_id,
        "runtime_id": str(element.get("runtime_id") or element_id),
        "name": str(element.get("name") or ""),
        "value": str(element.get("value") or ""),
        "text": str(element.get("text") or element.get("value") or element.get("name") or ""),
        "automation_id": str(element.get("automation_id") or ""),
        "control_type": str(element.get("control_type") or ""),
        "localized_control_type": str(element.get("localized_control_type") or ""),
        "role": str(element.get("role") or element.get("control_type") or ""),
        "class_name": str(element.get("class_name") or ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": normalized_bounds,
        "depth": _safe_int(element.get("depth"), default=0),
        "parent_id": str(element.get("parent_id") or ""),
    }


def _matching_elements(elements: list[dict[str, Any]], locator: dict[str, Any]) -> list[dict[str, Any]]:
    return [element for element in elements if _element_matches(element, locator)]


def _select_option_element(
    elements: list[dict[str, Any]],
    *,
    option_value: str,
    option_index: int | None,
) -> dict[str, Any]:
    candidates = [
        element
        for element in elements
        if _element_type_matches_any(element, {"listitem", "dataitem", "menuitem", "treeitem", "text"})
    ]
    if option_index is not None and 0 <= option_index < len(candidates):
        return dict(candidates[option_index])
    if option_value:
        for element in candidates:
            if option_value in {str(element.get("name") or ""), str(element.get("text") or ""), str(element.get("value") or "")}:
                return dict(element)
    return {}


def _element_type_matches_any(element: dict[str, Any], expected_values: set[str]) -> bool:
    candidates = (
        str(element.get("control_type", "")),
        str(element.get("localized_control_type", "")),
        str(element.get("role", "")),
    )
    return any(candidate.lower() in expected_values for candidate in candidates if candidate)


def _diagnostic_element(
    element: dict[str, Any],
    *,
    index: int,
    all_elements: list[dict[str, Any]],
    matched: bool,
    include_selector_hints: bool,
    text_limit: int,
) -> dict[str, Any]:
    text = _limit_text(_element_text(element), text_limit)
    diagnostic = {
        "index": index,
        "id": str(element.get("id") or ""),
        "runtime_id": str(element.get("runtime_id") or ""),
        "parent_id": str(element.get("parent_id") or ""),
        "depth": _safe_int(element.get("depth"), default=0),
        "name": _limit_text(str(element.get("name") or ""), text_limit),
        "value": _limit_text(str(element.get("value") or ""), text_limit),
        "text": text,
        "automation_id": str(element.get("automation_id") or ""),
        "control_type": str(element.get("control_type") or ""),
        "localized_control_type": str(element.get("localized_control_type") or ""),
        "role": str(element.get("role") or ""),
        "class_name": str(element.get("class_name") or ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": element.get("bounds") if isinstance(element.get("bounds"), dict) else {},
        "matched": bool(matched),
    }
    if include_selector_hints:
        diagnostic["selector_hints"] = _selector_hints_for_element(element, all_elements)
    return diagnostic


def _selector_hints_for_element(element: dict[str, Any], all_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    automation_id = str(element.get("automation_id") or "")
    name = str(element.get("name") or "")
    text = _element_text(element)
    control_type = str(element.get("control_type") or "")
    role = str(element.get("role") or control_type or "")
    class_name = str(element.get("class_name") or "")
    element_id = str(element.get("id") or "")

    if automation_id:
        candidates.append({"locator": {"automation_id": automation_id}, "stability": "high"})
        if control_type:
            candidates.append({"locator": {"automation_id": automation_id, "control_type": control_type}, "stability": "high"})
    if name:
        locator = {"name": name}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "medium"})
    if text and text != name:
        locator = {"text": text}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "medium"})
    if role and role != control_type:
        candidates.append({"locator": {"role": role, "name": name} if name else {"role": role}, "stability": "medium"})
    if class_name:
        locator = {"element_class_name": class_name}
        if control_type:
            locator["control_type"] = control_type
        candidates.append({"locator": locator, "stability": "low"})
    if element_id:
        candidates.append({"locator": {"element_id": element_id}, "stability": "session"})

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        locator = candidate.get("locator") if isinstance(candidate.get("locator"), dict) else {}
        if not locator:
            continue
        key = json.dumps(locator, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        matches = _matching_elements(all_elements, locator)
        enriched = {
            **candidate,
            "match_count": len(matches),
            "unique": len(matches) == 1,
        }
        unique.append(enriched)
    unique.sort(key=lambda item: (_stability_rank(str(item.get("stability") or "")), 0 if item.get("unique") else 1, int(item.get("match_count", 0))))
    return unique[:8]


def _near_matches_for_locator(elements: list[dict[str, Any]], locator: dict[str, Any]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for element in elements:
        score, matched_fields, missing_fields, reasons = _locator_match_score(element, locator)
        if score <= 0:
            continue
        scored.append(
            {
                "score": score,
                "matched_fields": matched_fields,
                "missing_fields": missing_fields,
                "reasons": reasons,
                "element": _near_match_element(element),
            }
        )
    scored.sort(key=lambda item: (-int(item.get("score", 0)), len(item.get("missing_fields", []))))
    return scored[:8]


def _locator_match_score(element: dict[str, Any], locator: dict[str, Any]) -> tuple[int, list[str], list[str], list[str]]:
    checks: list[tuple[str, bool, str]] = []
    if "element_id" in locator:
        checks.append(("element_id", str(element.get("id")) == str(locator.get("element_id")), "element_id differs"))
    if "automation_id" in locator:
        checks.append(
            ("automation_id", str(element.get("automation_id")) == str(locator.get("automation_id")), "automation_id differs")
        )
    if "name" in locator:
        checks.append(("name", str(element.get("name", "")) == str(locator.get("name")), "name differs"))
    if "name_contains" in locator:
        checks.append(
            ("name_contains", str(locator.get("name_contains")) in str(element.get("name", "")), "name does not contain expected text")
        )
    if "name_regex" in locator:
        checks.append(
            ("name_regex", _regex_matches(str(locator.get("name_regex")), str(element.get("name", ""))), "name_regex does not match")
        )
    element_text = _element_text(element)
    if "text" in locator:
        checks.append(("text", element_text == str(locator.get("text")), "text differs"))
    if "text_contains" in locator:
        checks.append(("text_contains", str(locator.get("text_contains")) in element_text, "text does not contain expected text"))
    if "text_regex" in locator:
        checks.append(("text_regex", _regex_matches(str(locator.get("text_regex")), element_text), "text_regex does not match"))
    if "control_type" in locator:
        checks.append(
            ("control_type", _element_type_matches(element, str(locator.get("control_type"))), "control_type differs")
        )
    if "role" in locator:
        checks.append(("role", _element_type_matches(element, str(locator.get("role"))), "role differs"))
    if "element_class_name" in locator:
        expected = str(locator.get("element_class_name")).lower()
        checks.append(
            (
                "element_class_name",
                expected in str(element.get("class_name", "")).lower(),
                "element_class_name differs",
            )
        )
    matched_fields = [field for field, ok, _reason in checks if ok]
    missing_fields = [field for field, ok, _reason in checks if not ok]
    reasons = [reason for _field, ok, reason in checks if not ok]
    score = len(matched_fields) * 10 - len(missing_fields) * 2
    if not checks and "element_match_index" in locator:
        score = 1
        reasons.append("element_match_index alone is not a stable selector")
    return score, matched_fields, missing_fields, reasons


def _near_match_element(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": element.get("index", 0),
        "id": element.get("id", ""),
        "name": element.get("name", ""),
        "text": element.get("text", ""),
        "automation_id": element.get("automation_id", ""),
        "control_type": element.get("control_type", ""),
        "role": element.get("role", ""),
        "class_name": element.get("class_name", ""),
        "bounds": element.get("bounds", {}),
        "selector_hints": element.get("selector_hints", []),
    }


def _element_dump_limitations(platform_name: str) -> list[str]:
    if platform_name == "macos":
        return [
            "macOS native backend currently enumerates the target window and its direct UI elements.",
            "Accessibility permission is required for AX element data.",
        ]
    if platform_name == "windows":
        return [
            "Windows runtime_id is only stable within the current UIA session; prefer automation_id/name/control_type hints.",
        ]
    return [f"Desktop element dump is not specialized for platform={platform_name}."]


def _element_dump_recommendations(
    *,
    locator: dict[str, Any],
    match_count: int,
    near_matches: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    if not locator:
        recommendations.append("Use selector_hints from a unique target element to build a stable Element Locator.")
        recommendations.append("Prefer automation_id + control_type when available; use element_id only for same-session debugging.")
        return recommendations
    if match_count == 0:
        recommendations.append("No exact element matched the locator; inspect near_matches for the closest controls.")
        if near_matches:
            recommendations.append("Start from the first near_match.selector_hints entry marked unique=true.")
    elif match_count > 1:
        recommendations.append("Locator is ambiguous; add automation_id, control_type, role, name, or text to make it unique.")
    else:
        recommendations.append("Locator matched one element; prefer a selector_hints entry with stability=high or unique=true.")
    if set(locator.keys()) <= {"element_match_index"}:
        recommendations.append("element_match_index alone is order-dependent and should not be used as a durable selector.")
    return recommendations


def _element_tree(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for element in elements:
        element_id = str(element.get("id") or element.get("runtime_id") or f"element:{element.get('index', len(nodes_by_id))}")
        node = {
            "id": element_id,
            "index": element.get("index", 0),
            "name": element.get("name", ""),
            "text": element.get("text", ""),
            "control_type": element.get("control_type", ""),
            "role": element.get("role", ""),
            "automation_id": element.get("automation_id", ""),
            "bounds": element.get("bounds", {}),
            "matched": bool(element.get("matched", False)),
            "children": [],
        }
        nodes_by_id[element_id] = node
    for element in elements:
        element_id = str(element.get("id") or element.get("runtime_id") or "")
        node = nodes_by_id.get(element_id)
        if node is None:
            continue
        parent_id = str(element.get("parent_id") or "")
        parent = nodes_by_id.get(parent_id)
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def _select_element(elements: list[dict[str, Any]], locator: dict[str, Any]) -> dict[str, Any] | None:
    match_index = int(locator.get("element_match_index", 0) or 0)
    if not elements:
        return None
    if match_index >= len(elements):
        return None
    return dict(elements[match_index])


def _element_matches(element: dict[str, Any], locator: dict[str, Any]) -> bool:
    if "element_id" in locator and str(element.get("id")) != str(locator.get("element_id")):
        return False
    if "automation_id" in locator and str(element.get("automation_id")) != str(locator.get("automation_id")):
        return False
    if "name" in locator and str(element.get("name", "")) != str(locator.get("name")):
        return False
    if "name_contains" in locator and str(locator.get("name_contains")) not in str(element.get("name", "")):
        return False
    if "name_regex" in locator and not _regex_matches(str(locator.get("name_regex")), str(element.get("name", ""))):
        return False
    element_text = _element_text(element)
    if "text" in locator and element_text != str(locator.get("text")):
        return False
    if "text_contains" in locator and str(locator.get("text_contains")) not in element_text:
        return False
    if "text_regex" in locator and not _regex_matches(str(locator.get("text_regex")), element_text):
        return False
    if "control_type" in locator and not _element_type_matches(element, str(locator.get("control_type"))):
        return False
    if "role" in locator and not _element_type_matches(element, str(locator.get("role"))):
        return False
    if "element_class_name" in locator:
        expected = str(locator.get("element_class_name")).lower()
        if expected not in str(element.get("class_name", "")).lower():
            return False
    return True


def _element_type_matches(element: dict[str, Any], expected: str) -> bool:
    expected_text = expected.lower()
    candidates = (
        str(element.get("control_type", "")),
        str(element.get("localized_control_type", "")),
        str(element.get("role", "")),
    )
    return any(candidate.lower() == expected_text or expected_text in candidate.lower() for candidate in candidates)


def _element_state_matches(element: dict[str, Any] | None, state: str) -> bool:
    if state == "not_exists":
        return element is None
    if element is None:
        return False
    if state == "exists":
        return True
    if state == "enabled":
        return bool(element.get("enabled"))
    if state == "disabled":
        return not bool(element.get("enabled", True))
    if state == "focused":
        return bool(element.get("focused"))
    return False


def _element_text(element: dict[str, Any]) -> str:
    for field in ("text", "value", "name"):
        value = str(element.get(field) or "")
        if value:
            return value
    return ""


def _regex_matches(pattern: str, value: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


def _limit_text(value: str, limit: int) -> str:
    text = str(value or "")
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _stability_rank(value: str) -> int:
    ranks = {"high": 0, "medium": 1, "low": 2, "session": 3}
    return ranks.get(value, 9)


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _element_center(element: dict[str, Any], *, locator: dict[str, Any]) -> tuple[int, int]:
    bounds = element.get("bounds") if isinstance(element, dict) else None
    if not isinstance(bounds, dict):
        raise DesktopBackendError(f"控件缺少 bounds，无法计算中心点：locator={locator}")
    width = _safe_int(bounds.get("width"), default=0)
    height = _safe_int(bounds.get("height"), default=0)
    if width <= 0 or height <= 0:
        raise DesktopBackendError(f"控件 bounds 无效，无法计算中心点：bounds={bounds}")
    return (
        _safe_int(bounds.get("x"), default=0) + width // 2,
        _safe_int(bounds.get("y"), default=0) + height // 2,
    )


def _fallback_scroll_amount(amount: int | None, scroll_to: str) -> int:
    if amount:
        return int(amount)
    if scroll_to in {"end", "bottom", "right"}:
        return -8
    if scroll_to in {"start", "top", "left"}:
        return 8
    return -5


def _compact_near_element_matches(raw_near_matches: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_near_matches, list):
        return []
    compacted: list[dict[str, Any]] = []
    for item in raw_near_matches[:5]:
        if not isinstance(item, dict):
            continue
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        selector_hints = element.get("selector_hints", []) if isinstance(element, dict) else []
        compacted.append(
            {
                "score": item.get("score", 0),
                "matched_fields": item.get("matched_fields", []),
                "missing_fields": item.get("missing_fields", []),
                "reasons": item.get("reasons", []),
                "element": {
                    **_near_match_element(element),
                    "selector_hints": selector_hints[:3] if isinstance(selector_hints, list) else [],
                },
            }
        )
    return compacted


def _region_to_bbox(region: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not region:
        return None
    x = int(region["x"])
    y = int(region["y"])
    width = int(region["width"])
    height = int(region["height"])
    return (x, y, x + width, y + height)


def _normalized_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": str(payload.get("operation") or ""),
        "method": str(payload.get("method") or ""),
        "fallback_required": bool(payload.get("fallback_required", False)),
    }
    if payload.get("fallback_error") not in (None, ""):
        result["fallback_error"] = str(payload.get("fallback_error"))
    if payload.get("search_scope") not in (None, ""):
        result["search_scope"] = str(payload.get("search_scope"))
    if isinstance(payload.get("open_methods"), list):
        result["open_methods"] = [str(method) for method in payload.get("open_methods", [])]
    native_element = payload.get("element")
    if isinstance(native_element, dict):
        result["action_element"] = _normalize_element(native_element, index=0)
    return result


def _normalized_table_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": str(payload.get("operation") or ""),
        "method": str(payload.get("method") or ""),
        "fallback_required": bool(payload.get("fallback_required", False)),
    }
    if payload.get("fallback_error") not in (None, ""):
        result["fallback_error"] = str(payload.get("fallback_error"))
    native_element = payload.get("element")
    if isinstance(native_element, dict):
        result["action_element"] = _normalize_element(native_element, index=0)
    table = payload.get("table")
    if isinstance(table, dict):
        result["table"] = _normalize_table(table)
    selected_cell = payload.get("selected_cell")
    if isinstance(selected_cell, dict):
        result["selected_cell"] = _normalize_table_cell(selected_cell)
    return result


def _normalized_tree_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": str(payload.get("operation") or ""),
        "method": str(payload.get("method") or ""),
        "fallback_required": bool(payload.get("fallback_required", False)),
    }
    if payload.get("fallback_error") not in (None, ""):
        result["fallback_error"] = str(payload.get("fallback_error"))
    native_element = payload.get("element")
    if isinstance(native_element, dict):
        result["action_element"] = _normalize_element(native_element, index=0)
    tree = payload.get("tree")
    if isinstance(tree, dict):
        result["tree"] = _normalize_tree(tree)
    tree_node = payload.get("tree_node")
    if isinstance(tree_node, dict):
        result["tree_node"] = _normalize_tree_node(tree_node, index=0)
    return result


def _normalize_tree(tree: dict[str, Any]) -> dict[str, Any]:
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    normalized_nodes = [_normalize_tree_node(node, index=index) for index, node in enumerate(nodes) if isinstance(node, dict)]
    return {
        "nodes": normalized_nodes,
        "root_nodes": _tree_roots_from_flat(normalized_nodes),
        "count": _safe_int(tree.get("count"), default=len(normalized_nodes)),
        "max_nodes": _safe_int(tree.get("max_nodes"), default=len(normalized_nodes)),
        "truncated": bool(tree.get("truncated", False)),
    }


def _normalize_tree_node(node: dict[str, Any], *, index: int) -> dict[str, Any]:
    bounds = node.get("bounds") if isinstance(node.get("bounds"), dict) else {}
    raw_path = node.get("path") if isinstance(node.get("path"), list) else []
    return {
        "index": index,
        "id": str(node.get("id") or node.get("runtime_id") or f"tree-node:{index}"),
        "runtime_id": str(node.get("runtime_id") or node.get("id") or ""),
        "parent_id": str(node.get("parent_id") or ""),
        "depth": _safe_int(node.get("depth"), default=0),
        "name": str(node.get("name") or ""),
        "text": str(node.get("text") or node.get("name") or ""),
        "automation_id": str(node.get("automation_id") or ""),
        "control_type": str(node.get("control_type") or ""),
        "role": str(node.get("role") or node.get("control_type") or ""),
        "class_name": str(node.get("class_name") or ""),
        "enabled": bool(node.get("enabled", False)),
        "visible": bool(node.get("visible", False)),
        "focused": bool(node.get("focused", False)),
        "expanded": bool(node.get("expanded", False)),
        "leaf": bool(node.get("leaf", False)),
        "selected": bool(node.get("selected", False)),
        "path": [str(part) for part in raw_path],
        "bounds": {
            "x": _safe_int(bounds.get("x"), default=0),
            "y": _safe_int(bounds.get("y"), default=0),
            "width": _safe_int(bounds.get("width"), default=0),
            "height": _safe_int(bounds.get("height"), default=0),
        },
    }


def _tree_roots_from_flat(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or node.get("runtime_id") or "")
        by_id[node_id] = {**node, "children": []}
    for node in nodes:
        node_id = str(node.get("id") or node.get("runtime_id") or "")
        copy = by_id.get(node_id)
        if copy is None:
            continue
        parent = by_id.get(str(node.get("parent_id") or ""))
        if parent is not None and parent is not copy:
            parent["children"].append(copy)
        else:
            roots.append(copy)
    return roots


def _normalize_table(table: dict[str, Any]) -> dict[str, Any]:
    columns = table.get("columns") if isinstance(table.get("columns"), list) else []
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    cells = table.get("cells") if isinstance(table.get("cells"), list) else []
    return {
        "row_count": _safe_int(table.get("row_count"), default=0),
        "column_count": _safe_int(table.get("column_count"), default=0),
        "read_row_count": _safe_int(table.get("read_row_count"), default=_safe_int(table.get("row_count"), default=0)),
        "read_column_count": _safe_int(
            table.get("read_column_count"),
            default=_safe_int(table.get("column_count"), default=0),
        ),
        "columns": [str(column) for column in columns],
        "rows": [_normalize_table_row(row) for row in rows if isinstance(row, dict)],
        "cells": [_normalize_table_cell(cell) for cell in cells if isinstance(cell, dict)],
        "visible_only": bool(table.get("visible_only", False)),
        "truncated": bool(table.get("truncated", False)),
    }


def _normalize_table_row(row: dict[str, Any]) -> dict[str, Any]:
    cells = row.get("cells") if isinstance(row.get("cells"), list) else []
    return {
        "index": _safe_int(row.get("index"), default=0),
        "cells": [_normalize_table_cell(cell) for cell in cells if isinstance(cell, dict)],
    }


def _normalize_table_cell(cell: dict[str, Any]) -> dict[str, Any]:
    bounds = cell.get("bounds") if isinstance(cell.get("bounds"), dict) else {}
    return {
        "row": _safe_int(cell.get("row"), default=0),
        "column_index": _safe_int(cell.get("column_index"), default=0),
        "row_name": str(cell.get("row_name") or ""),
        "name": str(cell.get("name") or ""),
        "value": str(cell.get("value") or ""),
        "text": str(cell.get("text") or cell.get("value") or cell.get("name") or ""),
        "automation_id": str(cell.get("automation_id") or ""),
        "control_type": str(cell.get("control_type") or ""),
        "runtime_id": str(cell.get("runtime_id") or ""),
        "enabled": bool(cell.get("enabled", False)),
        "visible": bool(cell.get("visible", False)),
        "focused": bool(cell.get("focused", False)),
        "bounds": {
            "x": _safe_int(bounds.get("x"), default=0),
            "y": _safe_int(bounds.get("y"), default=0),
            "width": _safe_int(bounds.get("width"), default=0),
            "height": _safe_int(bounds.get("height"), default=0),
        },
    }
