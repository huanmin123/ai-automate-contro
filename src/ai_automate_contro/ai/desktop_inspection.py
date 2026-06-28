from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project
from ai_automate_contro.engine.desktop.backends import DesktopBackendError, NativeDesktopBackend
from ai_automate_contro.plans.config import load_plan_config


MAX_DESKTOP_INSPECTION_WINDOWS = 50
MAX_DESKTOP_INSPECTION_ELEMENTS = 300
MAX_DESKTOP_INSPECTION_DEPTH = 8
WINDOW_QUERY_FIELDS = {
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


def inspect_desktop_tool(
    project_root: str | Path,
    *,
    platform_name: str = "auto",
    backend: str = "auto",
    request_permissions: bool = False,
    include_windows: bool = True,
    include_invisible: bool = False,
    include_elements: bool = False,
    include_screenshot: bool = False,
    title: str = "",
    title_contains: str = "",
    title_regex: str = "",
    app: str = "",
    process: str = "",
    process_name: str = "",
    class_name: str = "",
    window_id: str = "",
    match_index: int = 0,
    element_locator: dict[str, Any] | None = None,
    max_windows: int = 20,
    max_elements: int = 120,
    max_depth: int = 4,
    text_limit: int = 120,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_platform = _resolve_platform_name(platform_name)
    resolved_backend = str(backend or "auto").strip().lower()
    if resolved_backend not in {"auto", "native"}:
        raise DesktopBackendError("inspect_desktop 当前只支持 backend=auto/native。")
    current_platform = _current_platform_name()
    if resolved_platform != current_platform:
        raise DesktopBackendError(f"当前系统是 {current_platform}，不能探测 platform={resolved_platform}。")

    normalized_max_windows = _clamp_int(max_windows, minimum=1, maximum=MAX_DESKTOP_INSPECTION_WINDOWS)
    normalized_max_elements = _clamp_int(max_elements, minimum=1, maximum=MAX_DESKTOP_INSPECTION_ELEMENTS)
    normalized_max_depth = _clamp_int(max_depth, minimum=0, maximum=MAX_DESKTOP_INSPECTION_DEPTH)
    normalized_text_limit = _clamp_int(text_limit, minimum=0, maximum=500)
    window_query = _window_query_from_args(
        title=title,
        title_contains=title_contains,
        title_regex=title_regex,
        app=app,
        process=process,
        process_name=process_name,
        class_name=class_name,
        window_id=window_id,
        match_index=match_index,
    )

    started = time.monotonic()
    backend_instance = NativeDesktopBackend(
        platform_name=resolved_platform,
        desktop_config=_desktop_config_from_project(root),
    )
    screenshot_payload: dict[str, Any] = {}
    elements_payload: dict[str, Any] = {}
    windows: list[dict[str, Any]] = []
    window_error = ""
    try:
        probe = backend_instance.probe(request_permissions=bool(request_permissions))
        if include_windows or include_elements:
            try:
                windows = backend_instance.list_windows(include_invisible=bool(include_invisible))
            except Exception as error:
                window_error = str(error)
                windows = []
        selected_window_query = dict(window_query)
        if include_elements:
            if not selected_window_query:
                selected = _default_window_for_elements(windows)
                if not selected:
                    elements_payload = {
                        "ok": False,
                        "skipped": True,
                        "reason": "include_elements 需要窗口定位字段，且当前没有可用窗口可作为默认目标。",
                    }
                else:
                    selected_window_query = {"window_id": str(selected.get("id") or "")}
            if selected_window_query:
                try:
                    elements_payload = backend_instance.dump_elements(
                        selected_window_query,
                        locator=dict(element_locator or {}) or None,
                        max_depth=normalized_max_depth,
                        max_elements=normalized_max_elements,
                        include_tree=False,
                        include_selector_hints=True,
                        text_limit=normalized_text_limit,
                    )
                    elements_payload = _compact_elements_payload(elements_payload)
                except Exception as error:
                    elements_payload = {
                        "ok": False,
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "window_query": selected_window_query,
                        "element_locator": dict(element_locator or {}),
                    }
        if include_screenshot:
            screenshot_path = _inspection_screenshot_path(root)
            try:
                screenshot_payload = backend_instance.screenshot(screenshot_path)
            except Exception as error:
                screenshot_payload = {
                    "ok": False,
                    "error": str(error),
                    "error_type": type(error).__name__,
                }
    finally:
        backend_instance.close()

    compact_windows = [_compact_window(window) for window in windows[:normalized_max_windows]]
    capability_matrix = probe.get("capability_matrix") if isinstance(probe.get("capability_matrix"), dict) else {}
    return {
        "ok": True,
        "tool": "inspect_desktop",
        "platform": resolved_platform,
        "backend": "native",
        "probe": probe,
        "capability_matrix": capability_matrix,
        "window_query": window_query,
        "include_windows": bool(include_windows),
        "include_invisible": bool(include_invisible),
        "windows": compact_windows,
        "window_count": len(windows),
        "windows_truncated": len(windows) > len(compact_windows),
        "window_error": window_error or str(probe.get("window_list_error") or ""),
        "elements": elements_payload,
        "screenshot": screenshot_payload,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "next_actions": _next_actions(
            request_permissions=bool(request_permissions),
            include_elements=bool(include_elements),
            elements_payload=elements_payload,
            window_query=window_query,
        ),
    }


def _resolve_platform_name(raw_platform: str) -> str:
    text = str(raw_platform or "auto").strip().lower()
    if text == "auto":
        return _current_platform_name()
    if text in {"windows", "macos"}:
        return text
    raise DesktopBackendError(f"不支持的 desktop platform：{raw_platform}")


def _desktop_config_from_project(project_root: Path) -> dict[str, Any]:
    try:
        config = load_plan_config(project_root, default_ai_config_dir_for_project(project_root))
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _current_platform_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return system.lower() or "unknown"


def _window_query_from_args(**kwargs: Any) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for field in WINDOW_QUERY_FIELDS:
        value = kwargs.get(field)
        if value in (None, ""):
            continue
        if field == "match_index":
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                numeric = 0
            if numeric > 0:
                query[field] = numeric
            continue
        query[field] = value
    return query


def _default_window_for_elements(windows: list[dict[str, Any]]) -> dict[str, Any]:
    focused = next((window for window in windows if bool(window.get("focused"))), None)
    if isinstance(focused, dict):
        return focused
    visible = next((window for window in windows if bool(window.get("visible", True))), None)
    if isinstance(visible, dict):
        return visible
    return windows[0] if windows else {}


def _compact_windows(value: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_compact_window(window) for window in value[:limit] if isinstance(window, dict)]


def _compact_window(window: dict[str, Any]) -> dict[str, Any]:
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


def _inspection_screenshot_path(project_root: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return project_root / ".keygen" / "desktop-inspections" / f"desktop-{timestamp}.png"


def _next_actions(
    *,
    request_permissions: bool,
    include_elements: bool,
    elements_payload: dict[str, Any],
    window_query: dict[str, Any],
) -> list[str]:
    actions = [
        "Read capability_matrix before choosing semantic desktop_element actions, mouse/keyboard input, screenshot, or permission-sensitive steps.",
        "Use window id/title/app/process_name from windows as evidence before writing desktop_window or desktop_element steps.",
        "For stable desktop plans, prefer desktop_element list/dump/find/get_text/get_state/assert over coordinate clicks.",
    ]
    if not request_permissions:
        actions.insert(0, "If permissions are uncertain, rerun inspect_desktop with request_permissions=true or use open_desktop.request_permissions=true in a headed user flow.")
    if include_elements and bool(elements_payload.get("ok")):
        actions.append("Use selector_hints from elements/matches to write desktop_element locator fields.")
    elif include_elements and not window_query:
        actions.append("Pass title_contains/app/process_name/window_id before include_elements when the focused/default window is not the intended target.")
    return actions


def _limit_text(value: str, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = minimum
    return max(minimum, min(maximum, numeric))
