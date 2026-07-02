from __future__ import annotations

import json
from typing import Any

from ai_automate_contro.engine.desktop.targeting import build_failure_targeting
from ai_automate_contro.engine.desktop.coordinates import build_coordinate_profile
from ai_automate_contro.engine.runtime import RuntimeState


def capture_failure_state(
    state: RuntimeState,
    *,
    step_number: int,
    action: str,
    step_name: str,
    step_summary: str = "",
    step: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    screenshot_dir = state.output_dir / "failure-screenshots"
    html_dir = state.output_dir / "failure-html"
    page_state_dir = state.output_dir / "failure-page-state"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    page_state_dir.mkdir(parents=True, exist_ok=True)
    for browser_name, session in state.sessions.items():
        for page_name, page in session.pages.items():
            file_stem = f"step-{step_number:03d}-{browser_name}-{page_name}-{action}"
            screenshot_path = screenshot_dir / f"{file_stem}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                state.failure_screenshots.append(str(screenshot_path))
                state.logger.log(
                    "warning",
                    "failure screenshot captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(screenshot_path),
                )
            except Exception as screenshot_error:
                state.logger.log(
                    "warning",
                    "failure screenshot capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(screenshot_error),
                )
            html_path = html_dir / f"{file_stem}.html"
            try:
                html_path.write_text(page.content(), encoding="utf-8")
                state.failure_htmls.append(str(html_path))
                state.logger.log(
                    "warning",
                    "failure html captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(html_path),
                )
            except Exception as html_error:
                state.logger.log(
                    "warning",
                    "failure html capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(html_error),
                )
            page_state_path = page_state_dir / f"{file_stem}.json"
            try:
                page_state = _page_state_payload(
                    step_number=step_number,
                    action=action,
                    step_name=step_name,
                    browser_name=browser_name,
                    page_name=page_name,
                    page=page,
                    screenshot=str(screenshot_path) if screenshot_path.exists() else "",
                    html=str(html_path) if html_path.exists() else "",
                )
                with page_state_path.open("w", encoding="utf-8") as file:
                    json.dump(page_state, file, ensure_ascii=False, indent=2)
                state.failure_page_states.append(str(page_state_path))
                state.logger.log(
                    "warning",
                    "failure page state captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(page_state_path),
                )
            except Exception as page_state_error:
                state.logger.log(
                    "warning",
                    "failure page state capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(page_state_error),
                )
    capture_desktop_failure_state(
        state,
        step_number=step_number,
        action=action,
        step_name=step_name,
        step_summary=step_summary,
        step=step,
        error=error,
    )


def capture_desktop_failure_state(
    state: RuntimeState,
    *,
    step_number: int,
    action: str,
    step_name: str,
    step_summary: str = "",
    step: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    if not state.desktop_sessions:
        return
    screenshot_dir = state.output_dir / "failure-desktop-screenshots"
    desktop_state_dir = state.output_dir / "failure-desktop-state"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    desktop_state_dir.mkdir(parents=True, exist_ok=True)
    for desktop_name, session in state.desktop_sessions.items():
        file_stem = f"step-{step_number:03d}-{desktop_name}-{action}"
        screenshot_path = screenshot_dir / f"{file_stem}.png"
        try:
            session.backend.screenshot(screenshot_path)
            state.failure_desktop_screenshots.append(str(screenshot_path))
            state.logger.log(
                "warning",
                "failure desktop screenshot captured",
                step=step_number,
                step_name=step_name,
                desktop=desktop_name,
                path=str(screenshot_path),
            )
        except Exception as screenshot_error:
            state.logger.log(
                "warning",
                "failure desktop screenshot capture failed",
                step=step_number,
                step_name=step_name,
                desktop=desktop_name,
                error=str(screenshot_error),
            )
        desktop_state_path = desktop_state_dir / f"{file_stem}.json"
        try:
            window_diagnostics = _desktop_window_diagnostics(session, step or {})
            element_diagnostics = _desktop_element_diagnostics(session, step or {})
            snapshot = session.backend.snapshot()
            active_window = _desktop_active_window(session)
            pointer_position = _desktop_pointer_position()
            capability_matrix = _desktop_capability_matrix(session, snapshot)
            coordinate_profile = (
                snapshot.get("coordinate_profile")
                if isinstance(snapshot.get("coordinate_profile"), dict)
                else session.coordinate_profile
                if isinstance(getattr(session, "coordinate_profile", {}), dict)
                else {}
            )
            if not coordinate_profile:
                display = snapshot.get("display") if isinstance(snapshot.get("display"), dict) else {}
                coordinate_profile = build_coordinate_profile(
                    platform=session.platform,
                    backend=session.backend_name,
                    display=display,
                    source_kind="failure_state",
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
            target_payload = _desktop_target_payload(step or {})
            screenshot = str(screenshot_path) if screenshot_path.exists() else ""
            target_candidates = build_failure_targeting(
                desktop=desktop_name,
                target=target_payload,
                window_diagnostics=window_diagnostics,
                element_diagnostics=element_diagnostics,
                capability_matrix=capability_matrix,
                screenshot_path=screenshot,
            )
            desktop_state = {
                "step": step_number,
                "action": action,
                "step_name": step_name,
                "step_summary": step_summary,
                "error": str(error) if error is not None else "",
                "error_type": type(error).__name__ if error is not None else "",
                "target": target_payload,
                "desktop": desktop_name,
                "platform": session.platform,
                "backend": session.backend_name,
                "capability_matrix": capability_matrix,
                "coordinate_profile": coordinate_profile,
                "current_window": session.current_window or {},
                "active_window": active_window,
                "pointer_position": pointer_position,
                "screenshot": screenshot,
                "element_diagnostics": element_diagnostics,
                "window_diagnostics": window_diagnostics,
                "target_candidates": target_candidates,
                "diagnostics": {
                    "window": window_diagnostics,
                    "element": element_diagnostics,
                    "target_candidates": target_candidates,
                    "permissions": getattr(session, "permissions", {}) or {},
                    "capability_matrix": capability_matrix,
                    "coordinate_profile": coordinate_profile,
                    "current_window": session.current_window or {},
                    "active_window": active_window,
                    "pointer_position": pointer_position,
                    "snapshot": snapshot,
                },
                "artifacts": {
                    "screenshot_path": screenshot,
                    "state_path": str(desktop_state_path),
                },
                "snapshot": snapshot,
            }
            with desktop_state_path.open("w", encoding="utf-8") as file:
                json.dump(desktop_state, file, ensure_ascii=False, indent=2)
            state.failure_desktop_states.append(str(desktop_state_path))
            state.logger.log(
                "warning",
                "failure desktop state captured",
                step=step_number,
                step_name=step_name,
                desktop=desktop_name,
                path=str(desktop_state_path),
            )
        except Exception as desktop_state_error:
            state.logger.log(
                "warning",
                "failure desktop state capture failed",
                step=step_number,
                step_name=step_name,
                desktop=desktop_name,
                error=str(desktop_state_error),
            )


def _page_state_payload(
    *,
    step_number: int,
    action: str,
    step_name: str,
    browser_name: str,
    page_name: str,
    page: Any,
    screenshot: str,
    html: str,
) -> dict[str, Any]:
    return {
        "step": step_number,
        "action": action,
        "step_name": step_name,
        "browser": browser_name,
        "page": page_name,
        "url": page.url,
        "title": page.title(),
        "screenshot": screenshot,
        "html": html,
    }


def _desktop_capability_matrix(session: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    session_matrix = getattr(session, "capability_matrix", {}) or {}
    if isinstance(session_matrix, dict) and session_matrix:
        return dict(session_matrix)
    snapshot_matrix = snapshot.get("capability_matrix") if isinstance(snapshot, dict) else {}
    return dict(snapshot_matrix) if isinstance(snapshot_matrix, dict) else {}


DESKTOP_TARGET_FIELDS = {
    "action",
    "type",
    "desktop",
    "title",
    "title_contains",
    "title_regex",
    "app",
    "command",
    "args",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "match_index",
    "element_id",
    "automation_id",
    "name",
    "name_contains",
    "name_regex",
    "text",
    "text_contains",
    "text_regex",
    "control_type",
    "role",
    "element_class_name",
    "element_match_index",
    "max_depth",
    "max_elements",
    "state",
    "value",
    "option_index",
    "expected",
    "mode",
    "text_source",
    "preserve_clipboard",
    "include_tree",
    "include_selector_hints",
    "text_limit",
    "method",
    "operation",
    "timeout_ms",
    "interval_ms",
    "wait",
    "path",
    "region",
    "output",
    "target",
    "x",
    "y",
    "offset_x",
    "offset_y",
    "bounds",
    "button",
    "clicks",
    "keys",
    "delay_ms",
    "amount",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
    "delta_x",
    "delta_y",
    "duration_ms",
}

DESKTOP_WINDOW_QUERY_FIELDS = {
    "title",
    "title_contains",
    "title_regex",
    "app",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "match_index",
}

DESKTOP_ELEMENT_LOCATOR_FIELDS = {
    "element_id",
    "automation_id",
    "name",
    "name_contains",
    "name_regex",
    "text",
    "text_contains",
    "text_regex",
    "control_type",
    "role",
    "element_class_name",
    "element_match_index",
}


def _desktop_target_payload(step: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in DESKTOP_TARGET_FIELDS:
        value = step.get(field)
        if value in (None, ""):
            continue
        payload[field] = _compact_target_value(value)
    return payload


def _desktop_window_diagnostics(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    query = {
        field: step[field]
        for field in DESKTOP_WINDOW_QUERY_FIELDS
        if field in step and step.get(field) not in (None, "")
    }
    current_window = session.current_window or {}
    if not query:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing window query",
            "query": {},
            "current_window": current_window,
        }
    try:
        diagnose_window = getattr(session.backend, "diagnose_window", None)
        if callable(diagnose_window):
            payload = diagnose_window(query)
        else:
            windows = session.backend.list_windows()
            payload = {"query": query, "total_windows": len(windows), "windows": windows[:5]}
        if isinstance(payload, dict):
            return {**payload, "current_window": current_window}
        return {"ok": False, "query": query, "current_window": current_window, "payload": payload}
    except Exception as error:
        return {
            "ok": False,
            "query": query,
            "current_window": current_window,
            "error": str(error),
            "error_type": type(error).__name__,
        }


def _desktop_active_window(session: Any) -> dict[str, Any]:
    try:
        get_active_window = getattr(session.backend, "get_active_window", None)
        if callable(get_active_window):
            payload = get_active_window()
            return dict(payload) if isinstance(payload, dict) else {}
        windows = session.backend.list_windows(include_invisible=True)
        focused = next((window for window in windows if bool(window.get("focused"))), None)
        return dict(focused) if isinstance(focused, dict) else {}
    except Exception as error:
        return {"ok": False, "error": str(error), "error_type": type(error).__name__}


def _desktop_pointer_position() -> dict[str, Any]:
    try:
        import pyautogui

        position = pyautogui.position()
        return {"ok": True, "x": int(position.x), "y": int(position.y)}
    except Exception as error:
        return {"ok": False, "error": str(error), "error_type": type(error).__name__}


def _desktop_element_diagnostics(session: Any, step: dict[str, Any]) -> dict[str, Any]:
    action = str(step.get("action") or "")
    step_type = str(step.get("type") or "")
    if action == "desktop_assert" and step_type != "element":
        return {}
    if action not in {"desktop_element", "desktop_assert"}:
        return {}
    window_query = {
        field: step[field]
        for field in DESKTOP_WINDOW_QUERY_FIELDS
        if field in step and step.get(field) not in (None, "")
    }
    locator = {
        field: step[field]
        for field in DESKTOP_ELEMENT_LOCATOR_FIELDS
        if field in step and step.get(field) not in (None, "")
    }
    diagnostic_base = {"window_query": window_query, "locator": locator}
    if not window_query:
        return {**diagnostic_base, "ok": False, "skipped": True, "reason": "missing window query"}
    try:
        max_depth = max(0, int(step.get("max_depth", 4)))
    except (TypeError, ValueError):
        max_depth = 4
    try:
        max_elements = min(max(1, int(step.get("max_elements", 120))), 120)
    except (TypeError, ValueError):
        max_elements = 120
    try:
        payload = session.backend.dump_elements(
            window_query,
            locator=locator or None,
            max_depth=max_depth,
            max_elements=max_elements,
            include_tree=False,
            include_selector_hints=True,
            text_limit=120,
        )
        if isinstance(payload, dict):
            return {**payload, **diagnostic_base}
        return {**diagnostic_base, "ok": False, "payload": payload}
    except Exception as error:
        return {**diagnostic_base, "ok": False, "error": str(error), "error_type": type(error).__name__}


def _compact_target_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _compact_target_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact_target_value(item) for item in value[:8]]
    if isinstance(value, str) and len(value) > 240:
        return value[:237].rstrip() + "..."
    return value
