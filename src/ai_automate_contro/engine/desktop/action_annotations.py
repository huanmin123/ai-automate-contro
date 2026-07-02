from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.desktop import DesktopSession
from ai_automate_contro.engine.desktop.annotations import capture_pointer_annotation


def _capture_element_annotation(
    executor: Any,
    session: DesktopSession,
    *,
    element_type: str,
    payload: dict[str, Any],
    query: dict[str, Any],
    locator: dict[str, Any],
) -> dict[str, Any]:
    element: dict[str, Any] = {}
    for key in ("selected_cell", "tree_node", "menu_item", "scroll_target", "action_element", "element"):
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            element = candidate
            break
    bounds = element.get("bounds") if isinstance(element.get("bounds"), dict) else {}
    points: list[dict[str, Any]] = []
    if "x" in payload and "y" in payload:
        points.append(_annotation_point(payload.get("x"), payload.get("y"), element_type))
    elif bounds:
        center = _annotation_center_from_bounds(bounds)
        if center:
            points.append(_annotation_point(center[0], center[1], element_type))
    normalized_bounds = [dict(bounds)] if bounds else []
    if not points and not normalized_bounds:
        return {}
    return _capture_desktop_annotation(
        executor,
        session,
        action=f"desktop_element.{element_type}",
        points=points,
        bounds=normalized_bounds,
        connect_points=False,
        label=f"desktop_element.{element_type}",
        target={
            "query": query,
            "locator": locator,
            "method": payload.get("method", ""),
            "fallback_used": bool(payload.get("fallback_used", False)),
        },
    )


def _capture_desktop_annotation(
    executor: Any,
    session: DesktopSession,
    *,
    action: str,
    points: list[dict[str, Any]],
    bounds: list[dict[str, Any]],
    connect_points: bool,
    label: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    try:
        return capture_pointer_annotation(
            session.backend,
            output_dir=executor.state.output_dir,
            step_number=int(getattr(executor.state, "step_counter", 0) or 0),
            desktop=session.name,
            action=action,
            points=points,
            bounds=bounds,
            connect_points=connect_points,
            label=label,
            target=target,
            coordinate_profile=session.coordinate_profile,
        )
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "desktop annotation capture failed",
            desktop=session.name,
            action=action,
            error=str(error),
            error_type=type(error).__name__,
        )
        return {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
        }


def _annotation_point(x: Any, y: Any, label: str) -> dict[str, Any]:
    return {"x": int(float(x)), "y": int(float(y)), "label": label}


def _input_annotation_bounds(
    session: DesktopSession,
    step: dict[str, Any],
    target: str,
    resolution: dict[str, Any],
) -> list[dict[str, Any]]:
    resolved_bounds = resolution.get("bounds") if isinstance(resolution.get("bounds"), dict) else {}
    if resolved_bounds:
        return [dict(resolved_bounds)]
    if target in {"current_window_center", "focused_window_center", "current_window_offset", "focused_window_offset"}:
        window = session.current_window or {}
        bounds = window.get("bounds") if isinstance(window, dict) else None
        return [dict(bounds)] if isinstance(bounds, dict) else []
    if target == "bounds_center" and isinstance(step.get("bounds"), dict):
        return [dict(step["bounds"])]
    return []


def _input_annotation_target(step: dict[str, Any], *, target: str, resolution: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "target",
        "x",
        "y",
        "offset_x",
        "offset_y",
        "amount",
        "start_x",
        "start_y",
        "end_x",
        "end_y",
        "delta_x",
        "delta_y",
        "button",
        "candidate_id",
        "min_confidence",
    )
    payload = {field: step[field] for field in fields if field in step and step[field] not in (None, "")}
    if target:
        payload["resolved_target"] = target
    if resolution:
        payload["input_resolution"] = {
            "mode": resolution.get("mode", ""),
            "target": resolution.get("target", ""),
            "point": resolution.get("point", {}) if isinstance(resolution.get("point"), dict) else {},
            "candidate": resolution.get("candidate", {}) if isinstance(resolution.get("candidate"), dict) else {},
            "safety_check": resolution.get("safety_check", {}) if isinstance(resolution.get("safety_check"), dict) else {},
        }
    return payload


def _annotation_center_from_bounds(bounds: dict[str, Any]) -> tuple[int, int] | None:
    try:
        x = int(float(bounds.get("x", 0)))
        y = int(float(bounds.get("y", 0)))
        width = int(float(bounds.get("width", 0)))
        height = int(float(bounds.get("height", 0)))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return x + width // 2, y + height // 2
