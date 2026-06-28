from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.backends.base import DesktopBackend
from ai_automate_contro.engine.desktop.coordinates import build_coordinate_diagnostics, build_coordinate_profile
from ai_automate_contro.engine.desktop.targeting import build_observation_targeting


MAX_OBSERVE_WINDOWS = 50
MAX_OBSERVE_ELEMENTS = 300
MAX_OBSERVE_DEPTH = 8


def build_desktop_observation(
    backend: DesktopBackend,
    *,
    desktop: str = "",
    current_window: dict[str, Any] | None = None,
    window_query: dict[str, Any] | None = None,
    element_locator: dict[str, Any] | None = None,
    output_path: Path | None = None,
    screenshot_path: Path | None = None,
    request_permissions: bool = False,
    include_windows: bool = True,
    include_invisible: bool = False,
    include_elements: bool = False,
    include_screenshot: bool = False,
    max_windows: int = 20,
    max_elements: int = 120,
    max_depth: int = 4,
    text_limit: int = 120,
) -> dict[str, Any]:
    started = time.monotonic()
    normalized_window_query = dict(window_query or {})
    normalized_element_locator = dict(element_locator or {})
    normalized_max_windows = _clamp_int(max_windows, minimum=1, maximum=MAX_OBSERVE_WINDOWS)
    normalized_max_elements = _clamp_int(max_elements, minimum=1, maximum=MAX_OBSERVE_ELEMENTS)
    normalized_max_depth = _clamp_int(max_depth, minimum=0, maximum=MAX_OBSERVE_DEPTH)
    normalized_text_limit = _clamp_int(text_limit, minimum=0, maximum=500)

    probe = backend.probe(request_permissions=bool(request_permissions))
    windows: list[dict[str, Any]] = []
    window_error = ""
    if include_windows or include_elements:
        try:
            windows = backend.list_windows(include_invisible=bool(include_invisible))
        except Exception as error:
            window_error = str(error)
            windows = []

    selected_window = _select_observation_window(
        windows,
        normalized_window_query,
        current_window=current_window or {},
    )
    elements_payload = _observe_elements(
        backend,
        include_elements=bool(include_elements),
        selected_window=selected_window,
        window_query=normalized_window_query,
        element_locator=normalized_element_locator,
        max_depth=normalized_max_depth,
        max_elements=normalized_max_elements,
        text_limit=normalized_text_limit,
    )
    screenshot_payload = _observe_screenshot(
        backend,
        include_screenshot=bool(include_screenshot),
        screenshot_path=screenshot_path,
    )

    compact_windows = [_compact_window(window) for window in windows[:normalized_max_windows]]
    capability_matrix = probe.get("capability_matrix") if isinstance(probe.get("capability_matrix"), dict) else {}
    coordinate_profile = (
        probe.get("coordinate_profile") if isinstance(probe.get("coordinate_profile"), dict) else {}
    )
    if not coordinate_profile:
        display = probe.get("display") if isinstance(probe.get("display"), dict) else {}
        coordinate_profile = build_coordinate_profile(
            platform=str(probe.get("platform") or getattr(backend, "platform_name", "")),
            backend=str(probe.get("backend") or getattr(backend, "backend_name", "")),
            display=display,
            source_kind="screen",
            source_bounds={
                "x": 0,
                "y": 0,
                "width": int(display.get("width", 0) or 0) if isinstance(display, dict) else 0,
                "height": int(display.get("height", 0) or 0) if isinstance(display, dict) else 0,
            },
            coordinate_space={
                "origin": "screen",
                "unit": "logical_px",
                "scale": display.get("scale") if isinstance(display, dict) else None,
            },
        )
    if isinstance(screenshot_payload, dict) and screenshot_payload.get("ok"):
        screenshot_payload = _attach_screenshot_coordinate_profile(
            screenshot_payload,
            coordinate_profile=coordinate_profile,
            source_kind="observe_screenshot",
        )
    targeting = build_observation_targeting(
        desktop=desktop,
        window_query=normalized_window_query,
        element_locator=normalized_element_locator,
        selected_window=selected_window,
        elements_payload=elements_payload,
        screenshot_payload=screenshot_payload,
        capability_matrix=capability_matrix,
    )
    payload = {
        "ok": True,
        "schema_version": 1,
        "kind": "desktop_observation",
        "desktop": desktop,
        "platform": getattr(backend, "platform_name", ""),
        "backend": getattr(backend, "backend_name", ""),
        "probe": probe,
        "capability_matrix": capability_matrix,
        "coordinate_profile": coordinate_profile,
        "permissions": probe.get("permissions", {}) if isinstance(probe.get("permissions"), dict) else {},
        "dependencies": probe.get("dependencies", {}) if isinstance(probe.get("dependencies"), dict) else {},
        "display": probe.get("display", {}) if isinstance(probe.get("display"), dict) else {},
        "window_query": normalized_window_query,
        "element_locator": normalized_element_locator,
        "include_windows": bool(include_windows),
        "include_invisible": bool(include_invisible),
        "include_elements": bool(include_elements),
        "include_screenshot": bool(include_screenshot),
        "current_window": _compact_window(current_window or {}) if isinstance(current_window, dict) else {},
        "selected_window": _compact_window(selected_window),
        "windows": compact_windows,
        "window_count": len(windows),
        "windows_truncated": len(windows) > len(compact_windows),
        "window_error": window_error or str(probe.get("window_list_error") or ""),
        "elements": elements_payload,
        "screenshot": screenshot_payload,
        "target_candidates": targeting,
        "summary": _observation_summary(
            capability_matrix=capability_matrix,
            windows=windows,
            selected_window=selected_window,
            elements_payload=elements_payload,
            screenshot_payload=screenshot_payload,
            targeting=targeting,
        ),
        "limits": {
            "max_windows": normalized_max_windows,
            "max_elements": normalized_max_elements,
            "max_depth": normalized_max_depth,
            "text_limit": normalized_text_limit,
        },
        "artifacts": {
            "path": str(output_path) if output_path else "",
            "screenshot_path": str(screenshot_path) if screenshot_path and screenshot_payload.get("ok") else "",
        },
        "next_actions": _observation_next_actions(
            include_elements=bool(include_elements),
            elements_payload=elements_payload,
            targeting=targeting,
            capability_matrix=capability_matrix,
            selected_window=selected_window,
        ),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    if output_path is not None:
        payload["path"] = str(output_path)
    return payload


def _observe_elements(
    backend: DesktopBackend,
    *,
    include_elements: bool,
    selected_window: dict[str, Any],
    window_query: dict[str, Any],
    element_locator: dict[str, Any],
    max_depth: int,
    max_elements: int,
    text_limit: int,
) -> dict[str, Any]:
    if not include_elements:
        return {}
    selected_query = dict(window_query)
    if not selected_query and selected_window:
        selected_id = str(selected_window.get("id") or "")
        if selected_id:
            selected_query = {"window_id": selected_id}
    if not selected_query:
        return {
            "ok": False,
            "skipped": True,
            "reason": "include_elements needs a window query or a selected/focused window.",
        }
    try:
        payload = backend.dump_elements(
            selected_query,
            locator=element_locator or None,
            max_depth=max_depth,
            max_elements=max_elements,
            include_tree=False,
            include_selector_hints=True,
            text_limit=text_limit,
        )
    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
            "window_query": selected_query,
            "element_locator": element_locator,
        }
    return _compact_elements_payload(payload)


def _observe_screenshot(
    backend: DesktopBackend,
    *,
    include_screenshot: bool,
    screenshot_path: Path | None,
) -> dict[str, Any]:
    if not include_screenshot:
        return {}
    if screenshot_path is None:
        return {"ok": False, "skipped": True, "reason": "include_screenshot needs a screenshot path."}
    try:
        return backend.screenshot(screenshot_path)
    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
            "path": str(screenshot_path),
        }


def _attach_screenshot_coordinate_profile(
    screenshot_payload: dict[str, Any],
    *,
    coordinate_profile: dict[str, Any],
    source_kind: str,
) -> dict[str, Any]:
    source_bounds = {
        "x": 0,
        "y": 0,
        "width": int(screenshot_payload.get("width", 0) or 0),
        "height": int(screenshot_payload.get("height", 0) or 0),
    }
    space = (
        coordinate_profile.get("space")
        if isinstance(coordinate_profile.get("space"), dict)
        else {"origin": "screen", "unit": "logical_px", "scale": None}
    )
    profile = build_coordinate_profile(
        platform=str(coordinate_profile.get("platform") or ""),
        backend=str(coordinate_profile.get("backend") or ""),
        display=coordinate_profile.get("display") if isinstance(coordinate_profile.get("display"), dict) else {},
        source_kind=source_kind,
        source_bounds=source_bounds,
        source_size={"width": source_bounds["width"], "height": source_bounds["height"]},
        coordinate_space=space,
        screen_clickable=True,
    )
    return {
        **screenshot_payload,
        "source_bounds": source_bounds,
        "coordinate_space": space,
        "coordinate_profile": profile,
        "coordinate_diagnostics": build_coordinate_diagnostics(
            coordinate_profile=profile,
            source_bounds=source_bounds,
            source_size={"width": source_bounds["width"], "height": source_bounds["height"]},
            coordinate_space=space,
            region={},
        ),
    }


def _select_observation_window(
    windows: list[dict[str, Any]],
    query: dict[str, Any],
    *,
    current_window: dict[str, Any],
) -> dict[str, Any]:
    if query:
        matches = _matching_windows(windows, query)
        match_index = _clamp_int(query.get("match_index", 0), minimum=0, maximum=max(0, len(matches)))
        if matches and match_index < len(matches):
            return dict(matches[match_index])
        return {}
    current_id = str(current_window.get("id") or "")
    if current_id:
        for window in windows:
            if str(window.get("id") or "") == current_id:
                return dict(window)
    focused = next((window for window in windows if bool(window.get("focused"))), None)
    if isinstance(focused, dict):
        return dict(focused)
    visible = next((window for window in windows if bool(window.get("visible", True))), None)
    if isinstance(visible, dict):
        return dict(visible)
    return dict(windows[0]) if windows else {}


def _matching_windows(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    return [window for window in windows if _window_matches(window, query)]


def _window_matches(window: dict[str, Any], query: dict[str, Any]) -> bool:
    if "window_id" in query and str(window.get("id")) != str(query.get("window_id")):
        return False
    if "title" in query and str(window.get("title", "")) != str(query.get("title")):
        return False
    if "title_contains" in query and str(query.get("title_contains")) not in str(window.get("title", "")):
        return False
    if "title_regex" in query:
        try:
            if not re.search(str(query.get("title_regex")), str(window.get("title", ""))):
                return False
        except re.error:
            return False
    for query_field, window_field in (
        ("app", "app"),
        ("process", "process_name"),
        ("process_name", "process_name"),
        ("class_name", "class_name"),
    ):
        if query_field in query and str(query.get(query_field)).lower() not in str(window.get(window_field, "")).lower():
            return False
    return True


def _compact_windows(value: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_compact_window(window) for window in value[:limit] if isinstance(window, dict)]


def _compact_window(window: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(window, dict) or not window:
        return {}
    return {
        "id": window.get("id", ""),
        "title": _limit_text(str(window.get("title") or ""), 160),
        "app": window.get("app", ""),
        "process_name": window.get("process_name", ""),
        "class_name": window.get("class_name", ""),
        "pid": window.get("pid", ""),
        "focused": bool(window.get("focused")),
        "visible": bool(window.get("visible", True)),
        "bounds": window.get("bounds", {}) if isinstance(window.get("bounds"), dict) else {},
    }


def _compact_elements_payload(payload: dict[str, Any]) -> dict[str, Any]:
    elements = payload.get("elements") if isinstance(payload.get("elements"), list) else []
    matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
    return {
        "ok": bool(payload.get("ok")),
        "window": _compact_window(payload.get("window", {})) if isinstance(payload.get("window"), dict) else {},
        "locator": payload.get("locator", {}) if isinstance(payload.get("locator"), dict) else {},
        "count": int(payload.get("count", 0) or 0),
        "match_count": int(payload.get("match_count", 0) or 0),
        "total_count": int(payload.get("total_count", 0) or 0),
        "truncated": bool(payload.get("truncated", False)),
        "elements": [_compact_element(element) for element in elements[:80] if isinstance(element, dict)],
        "matches": [_compact_element(element) for element in matches[:20] if isinstance(element, dict)],
        "near_matches": payload.get("near_matches", []) if isinstance(payload.get("near_matches"), list) else [],
        "selector_hints": payload.get("selector_hints", []) if isinstance(payload.get("selector_hints"), list) else [],
        "diagnostics": payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), dict) else {},
    }


def _compact_element(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": element.get("index", ""),
        "id": element.get("id", ""),
        "name": _limit_text(str(element.get("name") or ""), 160),
        "text": _limit_text(str(element.get("text") or ""), 160),
        "value": _limit_text(str(element.get("value") or ""), 160),
        "automation_id": element.get("automation_id", ""),
        "control_type": element.get("control_type", ""),
        "role": element.get("role", ""),
        "class_name": element.get("class_name", ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": element.get("bounds", {}) if isinstance(element.get("bounds"), dict) else {},
        "depth": element.get("depth", 0),
        "parent_id": element.get("parent_id", ""),
        "selector_hints": element.get("selector_hints", []) if isinstance(element.get("selector_hints"), list) else [],
    }


def _observation_summary(
    *,
    capability_matrix: dict[str, Any],
    windows: list[dict[str, Any]],
    selected_window: dict[str, Any],
    elements_payload: dict[str, Any],
    screenshot_payload: dict[str, Any],
    targeting: dict[str, Any],
) -> dict[str, Any]:
    capabilities = capability_matrix.get("capabilities") if isinstance(capability_matrix.get("capabilities"), dict) else {}
    limitations = capability_matrix.get("limitations") if isinstance(capability_matrix.get("limitations"), list) else []
    focused_window = next((window for window in windows if bool(window.get("focused"))), {})
    return {
        "window_count": len(windows),
        "focused_window": _compact_window(focused_window),
        "selected_window": _compact_window(selected_window),
        "element_count": int(elements_payload.get("count", 0) or 0) if elements_payload else 0,
        "element_match_count": int(elements_payload.get("match_count", 0) or 0) if elements_payload else 0,
        "screenshot_path": str(screenshot_payload.get("path") or "") if screenshot_payload else "",
        "target_candidate_count": int(targeting.get("candidate_count", 0) or 0) if targeting else 0,
        "best_target_strategy": str(targeting.get("summary", {}).get("best_strategy", "")) if isinstance(targeting.get("summary"), dict) else "",
        "best_target_confidence": str(targeting.get("summary", {}).get("best_confidence", "")) if isinstance(targeting.get("summary"), dict) else "",
        "limitations": [str(item) for item in limitations],
        "semantic_available": bool(
            isinstance(capabilities.get("semantic"), dict) and capabilities["semantic"].get("elements")
        ),
        "screenshot_available": bool(
            isinstance(capabilities.get("screenshot"), dict) and capabilities["screenshot"].get("full_screen")
        ),
        "ocr_available": bool(isinstance(capabilities.get("vision"), dict) and capabilities["vision"].get("ocr")),
    }


def _observation_next_actions(
    *,
    include_elements: bool,
    elements_payload: dict[str, Any],
    targeting: dict[str, Any],
    capability_matrix: dict[str, Any],
    selected_window: dict[str, Any],
) -> list[str]:
    actions = [
        "Use selected_window/window ids as evidence before desktop_window or desktop_element steps.",
        "Prefer desktop_element semantic locators before coordinate mouse input.",
    ]
    limitations = capability_matrix.get("limitations") if isinstance(capability_matrix.get("limitations"), list) else []
    if limitations:
        actions.append("Resolve capability_matrix.limitations before relying on unavailable desktop capabilities.")
    if include_elements and bool(elements_payload.get("ok")):
        actions.append("Use elements.selector_hints or matches[].selector_hints to write stable desktop_element locators.")
    elif include_elements:
        actions.append("If elements are missing, pass a narrower Window Query or use screenshot/desktop_vision/manual_confirm.")
    if isinstance(targeting, dict) and int(targeting.get("candidate_count", 0) or 0) > 0:
        actions.append("Read target_candidates.best_candidate before choosing semantic locator, visual bounds, or manual confirmation.")
    if not selected_window:
        actions.append("No selected window was resolved; pass title_contains/app/process_name/window_id for app-specific plans.")
    return actions


def _limit_text(value: str, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _clamp_int(value: Any, *, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = minimum
    return max(minimum, min(maximum, numeric))
