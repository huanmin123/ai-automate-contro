from __future__ import annotations

import time
from typing import Any

from ai_automate_contro.engine.desktop import DesktopSession
from ai_automate_contro.engine.desktop.coordinates import (
    CoordinateMapper,
    build_coordinate_diagnostics,
    build_coordinate_profile,
    normalize_bounds,
)
from ai_automate_contro.engine.desktop.locators import (
    ELEMENT_LOCATOR_FIELDS,
    ELEMENT_REQUIRED_LOCATOR_FIELDS,
    WINDOW_QUERY_FIELDS,
)
from ai_automate_contro.engine.desktop.targeting import confidence_meets, find_target_candidate


DESKTOP_INTERACTION_GUARD_ATTEMPTS = 3
DESKTOP_INTERACTION_GUARD_RETRY_DELAY_SECONDS = 0.08


def _window_query(step: dict[str, Any]) -> dict[str, Any]:
    query = _optional_window_query(step)
    if not any(field in query for field in WINDOW_QUERY_FIELDS - {"match_index"}):
        raise ValueError("窗口操作需要至少一种窗口定位字段。")
    return query


def _optional_window_query(step: dict[str, Any]) -> dict[str, Any]:
    return {field: step[field] for field in WINDOW_QUERY_FIELDS if field in step and step[field] not in (None, "")}


def _window_list_diagnostics(session: DesktopSession, *, include_invisible: bool) -> dict[str, Any]:
    if not include_invisible:
        return {}
    include_invisible_supported = session.platform == "windows"
    diagnostics: dict[str, Any] = {
        "include_invisible_requested": True,
        "include_invisible_supported": include_invisible_supported,
    }
    if not include_invisible_supported:
        diagnostics["warnings"] = [
            f"include_invisible is not supported by the {session.platform}/{session.backend_name} desktop backend."
        ]
    return diagnostics


def _optional_element_locator(step: dict[str, Any]) -> dict[str, Any]:
    return {field: step[field] for field in ELEMENT_LOCATOR_FIELDS if field in step and step[field] not in (None, "")}


def _element_locator(step: dict[str, Any]) -> dict[str, Any]:
    locator = _optional_element_locator(step)
    if not any(field in locator for field in ELEMENT_REQUIRED_LOCATOR_FIELDS):
        raise ValueError("控件操作需要至少一种控件定位字段。")
    return locator


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} 必须是非空字符串数组。")
    result = [str(item) for item in value]
    if any(not item for item in result):
        raise ValueError(f"{field} 每一项必须是非空字符串。")
    return result


def _ensure_interaction_window_active(
    session: DesktopSession,
    *,
    action_label: str,
    step: dict[str, Any] | None = None,
    window_query: dict[str, Any] | None = None,
    window: dict[str, Any] | None = None,
    resolution: dict[str, Any] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    protection = _foreground_protection_config(session)
    query = _interaction_window_query(
        session,
        step=step,
        window_query=window_query,
        window=window,
        resolution=resolution,
    )
    if not _has_window_query(query):
        raise ValueError(
            f"{action_label} 发送真实桌面输入前无法确定目标窗口。"
            "请先执行 desktop_window focus、desktop_wait window，或在当前 action 中提供 Window Query。"
        )
    if not protection["enabled"]:
        return {
            "ok": True,
            "mode": "foreground_protection_disabled",
            "query": query,
            "attempt_count": 0,
            "max_attempts": 0,
        }
    attempts: list[dict[str, Any]] = []
    last_error: Exception | None = None
    max_attempts = int(protection["activation_attempts"])
    retry_delay_seconds = float(protection["retry_delay_ms"]) / 1000
    strict = bool(strict and protection["strict"])
    for attempt_index in range(1, max_attempts + 1):
        focused_window: dict[str, Any] = {}
        active_window: dict[str, Any] = {}
        try:
            focused_window = session.backend.focus_window(query)
            time.sleep(retry_delay_seconds)
            active_window = session.backend.get_active_window()
        except Exception as error:
            last_error = error
            attempts.append(
                {
                    "attempt": attempt_index,
                    "ok": False,
                    "query": query,
                    "window": _compact_guard_window(focused_window),
                    "active_window": _compact_guard_window(active_window),
                    "error": str(error),
                    "error_type": type(error).__name__,
                }
            )
            if attempt_index < max_attempts:
                time.sleep(retry_delay_seconds)
            continue
        verified = _window_matches_expected_active(active_window, focused_window, query)
        attempt_payload = {
            "attempt": attempt_index,
            "ok": verified,
            "query": query,
            "window": _compact_guard_window(focused_window),
            "active_window": _compact_guard_window(active_window),
        }
        if not verified:
            attempt_payload["reason"] = "active_window_mismatch"
        attempts.append(attempt_payload)
        if verified:
            current = active_window if isinstance(active_window, dict) and active_window else focused_window
            if isinstance(current, dict) and current:
                session.current_window = dict(current)
            return {
                "ok": True,
                "mode": "restore_focus_verify",
                "query": query,
                "attempt_count": attempt_index,
                "max_attempts": max_attempts,
                "retry_delay_ms": int(protection["retry_delay_ms"]),
                "window": _compact_guard_window(focused_window),
                "active_window": _compact_guard_window(active_window),
                "attempts": attempts,
            }
        if attempt_index < max_attempts:
            time.sleep(retry_delay_seconds)
    payload = {
        "ok": False,
        "mode": "restore_focus_verify",
        "query": query,
        "attempt_count": max_attempts,
        "max_attempts": max_attempts,
        "retry_delay_ms": int(protection["retry_delay_ms"]),
        "window": _compact_guard_window(focused_window),
        "active_window": _compact_guard_window(active_window),
        "attempts": attempts,
    }
    if last_error is not None:
        payload["error"] = str(last_error)
        payload["error_type"] = type(last_error).__name__
        payload["reason"] = "activation_error"
        if strict:
            raise ValueError(
                f"{action_label} 发送真实桌面输入前无法激活目标窗口：query={query} attempts={attempts}"
            ) from last_error
        return payload
    payload["reason"] = "active_window_mismatch"
    if strict:
        raise ValueError(
            f"{action_label} 发送真实桌面输入前目标窗口未成为前台窗口："
            f"query={query} attempts={attempts}"
        )
    return payload


def _foreground_protection_config(session: DesktopSession) -> dict[str, Any]:
    config = session.runtime_config if isinstance(session.runtime_config, dict) else {}
    desktop = config.get("desktop") if isinstance(config.get("desktop"), dict) else {}
    raw = desktop.get("foreground_protection") if isinstance(desktop.get("foreground_protection"), dict) else {}
    return {
        "enabled": _bool_config(raw.get("enabled"), default=True),
        "strict": _bool_config(raw.get("strict"), default=True),
        "activation_attempts": _positive_int_config(
            raw.get("activation_attempts"),
            default=DESKTOP_INTERACTION_GUARD_ATTEMPTS,
        ),
        "retry_delay_ms": _non_negative_int_config(
            raw.get("retry_delay_ms"),
            default=int(DESKTOP_INTERACTION_GUARD_RETRY_DELAY_SECONDS * 1000),
        ),
    }


def _bool_config(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _positive_int_config(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


def _non_negative_int_config(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def _interaction_window_query(
    session: DesktopSession,
    *,
    step: dict[str, Any] | None = None,
    window_query: dict[str, Any] | None = None,
    window: dict[str, Any] | None = None,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _has_window_query(window_query or {}):
        return dict(window_query or {})
    if isinstance(resolution, dict):
        resolved_query = resolution.get("window_query") if isinstance(resolution.get("window_query"), dict) else {}
        if _has_window_query(resolved_query):
            return dict(resolved_query)
        candidate = resolution.get("candidate") if isinstance(resolution.get("candidate"), dict) else {}
        candidate_query = candidate.get("window_query") if isinstance(candidate.get("window_query"), dict) else {}
        if _has_window_query(candidate_query):
            return dict(candidate_query)
    if isinstance(step, dict):
        step_query = _optional_window_query(step)
        if _has_window_query(step_query):
            return step_query
    if isinstance(window, dict) and window:
        query = _window_query_from_window(window)
        if _has_window_query(query):
            return query
    if isinstance(session.current_window, dict) and session.current_window:
        query = _window_query_from_window(session.current_window)
        if _has_window_query(query):
            return query
    return {}


def _has_window_query(query: dict[str, Any]) -> bool:
    return any(field in query and query[field] not in (None, "") for field in WINDOW_QUERY_FIELDS - {"match_index"})


def _window_query_from_window(window: dict[str, Any]) -> dict[str, Any]:
    if window.get("id") not in (None, ""):
        return {"window_id": window.get("id")}
    query: dict[str, Any] = {}
    if window.get("title"):
        query["title"] = window.get("title")
    if window.get("process_name"):
        query["process_name"] = window.get("process_name")
    elif window.get("app"):
        query["app"] = window.get("app")
    if window.get("class_name"):
        query["class_name"] = window.get("class_name")
    return query


def _window_matches_expected_active(
    active_window: dict[str, Any],
    focused_window: dict[str, Any],
    query: dict[str, Any],
) -> bool:
    if not isinstance(active_window, dict) or not active_window:
        return False
    if focused_window.get("id") not in (None, "") and active_window.get("id") not in (None, ""):
        return str(active_window.get("id")) == str(focused_window.get("id"))
    return _window_matches_query(active_window, query)


def _window_matches_query(window: dict[str, Any], query: dict[str, Any]) -> bool:
    if "window_id" in query and str(window.get("id")) != str(query.get("window_id")):
        return False
    if "title" in query and str(window.get("title", "")) != str(query.get("title")):
        return False
    if "title_contains" in query and str(query.get("title_contains")) not in str(window.get("title", "")):
        return False
    if "title_regex" in query and not re.search(str(query.get("title_regex")), str(window.get("title", ""))):
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


def _compact_guard_window(window: Any) -> dict[str, Any]:
    if not isinstance(window, dict):
        return {}
    return {
        "id": window.get("id", ""),
        "title": str(window.get("title", ""))[:160],
        "app": window.get("app", ""),
        "process_name": window.get("process_name", ""),
        "class_name": window.get("class_name", ""),
        "focused": bool(window.get("focused")),
        "visible": bool(window.get("visible", True)),
        "bounds": window.get("bounds", {}) if isinstance(window.get("bounds"), dict) else {},
    }


def _ensure_input_inside_interaction_window(
    session: DesktopSession,
    *,
    action_label: str,
    resolution: dict[str, Any],
    interaction_guard: dict[str, Any],
    allow_outside_window: bool,
    include_end_point: bool = False,
) -> dict[str, Any]:
    guard_window = (
        interaction_guard.get("active_window")
        if isinstance(interaction_guard.get("active_window"), dict)
        else {}
    )
    if not guard_window:
        guard_window = (
            interaction_guard.get("window")
            if isinstance(interaction_guard.get("window"), dict)
            else {}
        )
    window_bounds = normalize_bounds(guard_window.get("bounds") if isinstance(guard_window, dict) else {})
    points = [_named_resolution_point(resolution, "point", action_label=action_label)]
    if include_end_point and isinstance(resolution.get("end_point"), dict):
        points.append(_named_resolution_point(resolution, "end_point", action_label=action_label))
    checked_points = [
        {
            **point,
            "inside_window": _point_inside_bounds(point, window_bounds),
            "ownership": _point_window_ownership(session, point, interaction_guard),
        }
        for point in points
    ]
    outside_points = [point for point in checked_points if not point["inside_window"]]
    ownership_failures = [
        point
        for point in checked_points
        if _point_ownership_checked(point.get("ownership")) and not _point_ownership_ok(point.get("ownership"))
    ]
    ok = bool(window_bounds) and not outside_points and not ownership_failures
    reason = ""
    if not window_bounds:
        reason = "active_window_bounds_unavailable"
    elif outside_points:
        reason = "point_outside_active_window"
    elif ownership_failures:
        reason = "point_hits_different_window"
    if allow_outside_window:
        return {
            "ok": True,
            "mode": "active_window_bounds_and_point_ownership",
            "allow_outside_window": True,
            "window_bounds": window_bounds,
            "points": checked_points,
            "bypassed_reason": reason,
        }
    payload = {
        "ok": ok,
        "mode": "active_window_bounds_and_point_ownership",
        "allow_outside_window": False,
        "window_bounds": window_bounds,
        "points": checked_points,
        "reason": reason,
    }
    if not ok:
        raise ValueError(
            f"{action_label} 输入前窗口范围检查失败：reason={reason} "
            f"window_bounds={window_bounds} points={checked_points}；"
            "确需窗口外坐标、跨窗口坐标或目标窗口外弹层时请显式设置 allow_outside_window=true。"
        )
    return payload


def _point_window_ownership(
    session: DesktopSession,
    point: dict[str, Any],
    interaction_guard: dict[str, Any],
) -> dict[str, Any]:
    inspector = getattr(session.backend, "window_from_point", None)
    if not callable(inspector):
        return {
            "ok": True,
            "checked": False,
            "available": False,
            "reason": "backend_window_from_point_unavailable",
        }
    try:
        hit = inspector(x=int(point["x"]), y=int(point["y"]))
    except Exception as error:
        return {
            "ok": True,
            "checked": False,
            "available": False,
            "reason": "window_from_point_error",
            "error": str(error),
            "error_type": type(error).__name__,
        }
    if not isinstance(hit, dict) or not bool(hit.get("available", False)):
        return {
            "ok": True,
            "checked": False,
            "available": False,
            "reason": str(hit.get("reason") if isinstance(hit, dict) else "") or "window_from_point_unavailable",
            "hit": hit if isinstance(hit, dict) else {},
        }
    expected = _expected_interaction_windows(interaction_guard)
    hit_windows = _hit_test_windows(hit)
    expected_ids = {str(window.get("id")) for window in expected if window.get("id") not in (None, "")}
    hit_ids = {str(window.get("id")) for window in hit_windows if window.get("id") not in (None, "")}
    query = interaction_guard.get("query") if isinstance(interaction_guard.get("query"), dict) else {}
    belongs = bool(expected_ids and expected_ids.intersection(hit_ids))
    if not belongs and query:
        belongs = any(_window_matches_query(window, query) for window in hit_windows if isinstance(window, dict))
    reason = "" if belongs else "hit_window_not_expected"
    if not hit_windows:
        reason = "no_window_at_point"
    return {
        "ok": belongs,
        "checked": True,
        "available": True,
        "mode": "window_from_point",
        "belongs_to_expected_window": belongs,
        "reason": reason,
        "expected_window_ids": sorted(expected_ids),
        "hit_window_ids": sorted(hit_ids),
        "expected_windows": [_compact_guard_window(window) for window in expected],
        "hit_windows": [_compact_guard_window(window) for window in hit_windows],
        "hit": {
            "window": _compact_guard_window(hit.get("window")),
            "root_window": _compact_guard_window(hit.get("root_window")),
            "root_owner_window": _compact_guard_window(hit.get("root_owner_window")),
        },
    }


def _expected_interaction_windows(interaction_guard: dict[str, Any]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for field in ("active_window", "window"):
        value = interaction_guard.get(field) if isinstance(interaction_guard.get(field), dict) else {}
        if isinstance(value, dict) and value:
            windows.append(dict(value))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for window in windows:
        key = str(window.get("id") or window.get("title") or len(unique))
        if key in seen:
            continue
        seen.add(key)
        unique.append(window)
    return unique


def _hit_test_windows(hit: dict[str, Any]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for field in ("window", "root_window", "root_owner_window"):
        value = hit.get(field) if isinstance(hit.get(field), dict) else {}
        if isinstance(value, dict) and value:
            windows.append(dict(value))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for window in windows:
        key = str(window.get("id") or window.get("title") or len(unique))
        if key in seen:
            continue
        seen.add(key)
        unique.append(window)
    return unique


def _point_ownership_checked(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("checked"))


def _point_ownership_ok(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("belongs_to_expected_window", value.get("ok")))


def _named_resolution_point(
    resolution: dict[str, Any],
    field: str,
    *,
    action_label: str,
) -> dict[str, Any]:
    value = resolution.get(field) if isinstance(resolution.get(field), dict) else {}
    return {
        "name": field,
        "x": _coordinate(value.get("x"), field=f"{field}.x", action_label=action_label),
        "y": _coordinate(value.get("y"), field=f"{field}.y", action_label=action_label),
    }


def _point_inside_bounds(point: dict[str, Any], bounds: dict[str, int]) -> bool:
    if not bounds:
        return False
    x = int(point["x"])
    y = int(point["y"])
    return bounds["x"] <= x < bounds["x"] + bounds["width"] and bounds["y"] <= y < bounds["y"] + bounds["height"]


def _bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _resolve_input_coordinates(
    session: DesktopSession,
    step: dict[str, Any],
    *,
    action_label: str,
) -> tuple[int, int, str, dict[str, Any]]:
    if "x" in step and "y" in step:
        x = _coordinate(step["x"], field="x", action_label=action_label)
        y = _coordinate(step["y"], field="y", action_label=action_label)
        resolution = _input_resolution(
            session,
            action_label=action_label,
            target="xy",
            point={"x": x, "y": y},
            mode="raw_xy",
        )
        return x, y, "", resolution
    target = str(step.get("target", ""))
    if target == "candidate":
        return _resolve_candidate_coordinates(session, step, action_label=action_label)
    if target in {"current_window_center", "focused_window_center"}:
        _ensure_interaction_window_active(session, action_label=f"desktop_input.{action_label}", step=step)
        bounds = _current_window_bounds(session, target, action_label)
        x, y = _bounds_center(bounds, action_label=action_label)
        resolution = _input_resolution(
            session,
            action_label=action_label,
            target=target,
            point={"x": x, "y": y},
            bounds=bounds,
            mode="window_center",
        )
        return x, y, target, resolution
    if target in {"current_window_offset", "focused_window_offset"}:
        _ensure_interaction_window_active(session, action_label=f"desktop_input.{action_label}", step=step)
        bounds = _current_window_bounds(session, target, action_label)
        x = _coordinate(bounds.get("x", 0), field="bounds.x", action_label=action_label)
        y = _coordinate(bounds.get("y", 0), field="bounds.y", action_label=action_label)
        offset_x = _coordinate(step.get("offset_x", 0), field="offset_x", action_label=action_label)
        offset_y = _coordinate(step.get("offset_y", 0), field="offset_y", action_label=action_label)
        point = {"x": x + offset_x, "y": y + offset_y}
        resolution = _input_resolution(
            session,
            action_label=action_label,
            target=target,
            point=point,
            bounds=bounds,
            mode="window_offset",
            extra={"offset": {"x": offset_x, "y": offset_y}},
        )
        return point["x"], point["y"], target, resolution
    if target == "bounds_center":
        bounds = step.get("bounds")
        if not isinstance(bounds, dict):
            raise ValueError(f"desktop_input.{action_label} target=bounds_center 需要 bounds 对象。")
        x, y = _bounds_center(bounds, action_label=action_label)
        resolution = _input_resolution(
            session,
            action_label=action_label,
            target=target,
            point={"x": x, "y": y},
            bounds=bounds,
            mode="bounds_center",
        )
        return x, y, target, resolution
    if target == "element_center":
        query = _window_query(step)
        locator = _element_locator(step)
        _ensure_interaction_window_active(
            session,
            action_label=f"desktop_input.{action_label}",
            window_query=query,
        )
        payload = session.backend.find_element(
            query,
            locator,
            state=str(step.get("state", "exists")),
            timeout_ms=int(step.get("timeout_ms", 1_000)),
            interval_ms=int(step.get("interval_ms", 100)),
            max_depth=int(step.get("max_depth", 6)),
            max_elements=int(step.get("max_elements", 200)),
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if window:
            session.current_window = dict(window)
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        bounds = element.get("bounds") if isinstance(element, dict) else None
        if not isinstance(bounds, dict):
            raise ValueError(f"desktop_input.{action_label} target=element_center 的控件缺少 bounds：locator={locator}")
        x, y = _bounds_center(bounds, action_label=action_label)
        resolution = _input_resolution(
            session,
            action_label=action_label,
            target=target,
            point={"x": x, "y": y},
            bounds=bounds,
            mode="element_center",
            extra={
                "window_query": query,
                "locator": locator,
                "element": _compact_input_element(element),
            },
        )
        return x, y, target, resolution
    raise ValueError(f"desktop_input.{action_label} 需要 target 或 x/y")


def _resolve_drag_coordinates(session: DesktopSession, step: dict[str, Any]) -> tuple[int, int, int, int, str, dict[str, Any]]:
    if "target" in step:
        start_x, start_y, target, resolution = _resolve_input_coordinates(session, step, action_label="drag")
        delta_x = _coordinate(step.get("delta_x", 0), field="delta_x", action_label="drag")
        delta_y = _coordinate(step.get("delta_y", 0), field="delta_y", action_label="drag")
        end_point = {"x": start_x + delta_x, "y": start_y + delta_y}
        end_safety = _coordinate_safety_check(
            session,
            action_label="drag",
            target=target or "xy",
            point=end_point,
            bounds=resolution.get("bounds") if isinstance(resolution.get("bounds"), dict) else None,
        )
        resolution["delta"] = {"x": delta_x, "y": delta_y}
        resolution["end_point"] = end_point
        resolution["end_safety_check"] = end_safety
        return start_x, start_y, end_point["x"], end_point["y"], target, resolution
    required = ("start_x", "start_y", "end_x", "end_y")
    if not all(field in step for field in required):
        raise ValueError("desktop_input.drag 需要 target+delta_x/delta_y 或 start_x/start_y/end_x/end_y")
    start_point = {
        "x": _coordinate(step["start_x"], field="start_x", action_label="drag"),
        "y": _coordinate(step["start_y"], field="start_y", action_label="drag"),
    }
    end_point = {
        "x": _coordinate(step["end_x"], field="end_x", action_label="drag"),
        "y": _coordinate(step["end_y"], field="end_y", action_label="drag"),
    }
    resolution = _input_resolution(
        session,
        action_label="drag",
        target="xy",
        point=start_point,
        mode="raw_xy",
    )
    resolution["end_point"] = end_point
    resolution["end_safety_check"] = _coordinate_safety_check(
        session,
        action_label="drag",
        target="xy",
        point=end_point,
    )
    return start_point["x"], start_point["y"], end_point["x"], end_point["y"], "", resolution


def _resolve_candidate_coordinates(
    session: DesktopSession,
    step: dict[str, Any],
    *,
    action_label: str,
) -> tuple[int, int, str, dict[str, Any]]:
    candidate_id = str(step.get("candidate_id") or step.get("target_candidate_id") or "")
    if not candidate_id:
        raise ValueError(f"desktop_input.{action_label} target=candidate 需要 candidate_id。")
    source = _resolve_candidate_source(session, step)
    candidate = find_target_candidate(source, candidate_id)
    if not candidate and isinstance(step.get("candidate"), dict):
        raw_candidate = step["candidate"]
        if candidate_id in {"best", "best_candidate", str(raw_candidate.get("id") or ""), str(raw_candidate.get("candidate_id") or "")}:
            candidate = dict(raw_candidate)
    if not candidate:
        raise ValueError(f"desktop_input.{action_label} target=candidate 未找到 candidate_id={candidate_id!r}。")
    minimum_confidence = str(step.get("min_confidence") or "medium")
    if not confidence_meets(candidate, minimum_confidence):
        raise ValueError(
            f"desktop_input.{action_label} target=candidate 置信度不足："
            f"candidate_id={candidate_id!r} confidence={candidate.get('confidence')!r} min_confidence={minimum_confidence!r}"
        )
    strategy = str(candidate.get("strategy") or "")
    if strategy == "semantic_locator":
        return _resolve_semantic_candidate_coordinates(session, step, candidate, action_label=action_label)
    if strategy == "visual_bounds":
        return _resolve_visual_candidate_coordinates(session, step, candidate, action_label=action_label)
    raise ValueError(
        f"desktop_input.{action_label} target=candidate 不支持 strategy={strategy!r}；"
        "仅 semantic_locator 和 screen_clickable=true 的 visual_bounds 可直接执行。"
    )


def _resolve_semantic_candidate_coordinates(
    session: DesktopSession,
    step: dict[str, Any],
    candidate: dict[str, Any],
    *,
    action_label: str,
) -> tuple[int, int, str, dict[str, Any]]:
    query = candidate.get("window_query") if isinstance(candidate.get("window_query"), dict) else {}
    locator = candidate.get("locator") if isinstance(candidate.get("locator"), dict) else {}
    if not query or not locator:
        raise ValueError(
            f"desktop_input.{action_label} target=candidate 的 semantic_locator 缺少 window_query 或 locator："
            f"candidate_id={_candidate_id(candidate)!r}"
        )
    _ensure_interaction_window_active(
        session,
        action_label=f"desktop_input.{action_label}",
        window_query=query,
    )
    payload = session.backend.find_element(
        query,
        locator,
        state=str(step.get("state", "exists")),
        timeout_ms=int(step.get("timeout_ms", 1_000)),
        interval_ms=int(step.get("interval_ms", 100)),
        max_depth=int(step.get("max_depth", 6)),
        max_elements=int(step.get("max_elements", 200)),
    )
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    if window:
        session.current_window = dict(window)
    element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
    bounds = element.get("bounds") if isinstance(element.get("bounds"), dict) else {}
    if not bounds:
        raise ValueError(
            f"desktop_input.{action_label} target=candidate 的 semantic_locator 实时控件缺少 bounds："
            f"candidate_id={_candidate_id(candidate)!r} locator={locator}"
        )
    x, y = _bounds_center(bounds, action_label=action_label)
    resolution = _input_resolution(
        session,
        action_label=action_label,
        target="candidate",
        point={"x": x, "y": y},
        bounds=bounds,
        mode="candidate_semantic_locator",
        candidate=candidate,
        extra={
            "window_query": query,
            "locator": locator,
            "refreshed": True,
            "element": _compact_input_element(element),
        },
    )
    return x, y, "candidate", resolution


def _store_session_target_candidates(session: DesktopSession, payload: dict[str, Any]) -> None:
    target_candidates = payload.get("target_candidates") if isinstance(payload, dict) else {}
    if isinstance(target_candidates, dict) and target_candidates.get("kind") == "desktop_target_candidates":
        session.target_candidates = dict(target_candidates)


def _resolve_candidate_source(session: DesktopSession, step: dict[str, Any]) -> Any:
    if "target_candidates" in step:
        return step.get("target_candidates")
    if "candidate_source" not in step:
        return {}
    source = step.get("candidate_source")
    if isinstance(source, str) and source in {"latest", "last", "session", "latest_target_candidates"}:
        return dict(session.target_candidates)
    return source


def _resolve_visual_candidate_coordinates(
    session: DesktopSession,
    step: dict[str, Any],
    candidate: dict[str, Any],
    *,
    action_label: str,
) -> tuple[int, int, str, dict[str, Any]]:
    if not _candidate_screen_clickable(candidate):
        raise ValueError(
            f"desktop_input.{action_label} target=candidate 的 visual_bounds 不可直接点击："
            f"candidate_id={_candidate_id(candidate)!r} screen_clickable=false"
        )
    coordinate_profile = candidate.get("coordinate_profile") if isinstance(candidate.get("coordinate_profile"), dict) else {}
    source = coordinate_profile.get("source") if isinstance(coordinate_profile.get("source"), dict) else {}
    if str(source.get("kind") or "") in {"source_path", "image", "offline_image"}:
        raise ValueError(
            f"desktop_input.{action_label} target=candidate 来自离线图片 source_kind={source.get('kind')!r}，只能作为证据，不能直接点击。"
        )
    _ensure_interaction_window_active(
        session,
        action_label=f"desktop_input.{action_label}",
        resolution={"candidate": candidate},
    )
    bounds = candidate.get("bounds") if isinstance(candidate.get("bounds"), dict) else {}
    x, y = _bounds_center(bounds, action_label=action_label)
    resolution = _input_resolution(
        session,
        action_label=action_label,
        target="candidate",
        point={"x": x, "y": y},
        bounds=bounds,
        mode="candidate_visual_bounds",
        candidate=candidate,
        extra={
            "screen_clickable": True,
            "coordinate_profile": coordinate_profile,
            "coordinate_diagnostics": (
                candidate.get("coordinate_diagnostics") if isinstance(candidate.get("coordinate_diagnostics"), dict) else {}
            ),
        },
    )
    return x, y, "candidate", resolution


def _input_resolution(
    session: DesktopSession,
    *,
    action_label: str,
    target: str,
    point: dict[str, int],
    mode: str,
    bounds: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": mode,
        "target": target,
        "point": {"x": int(point["x"]), "y": int(point["y"])},
        "safety_check": _coordinate_safety_check(
            session,
            action_label=action_label,
            target=target,
            point=point,
            bounds=bounds,
            candidate=candidate,
        ),
    }
    normalized_bounds = normalize_bounds(bounds or {})
    if normalized_bounds:
        payload["bounds"] = normalized_bounds
    if candidate:
        payload["candidate"] = _compact_input_candidate(candidate)
    if extra:
        payload.update(extra)
    return payload


def _coordinate_safety_check(
    session: DesktopSession,
    *,
    action_label: str,
    target: str,
    point: dict[str, Any],
    bounds: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    x = _coordinate(point.get("x"), field="point.x", action_label=action_label)
    y = _coordinate(point.get("y"), field="point.y", action_label=action_label)
    candidate_strategy = str(candidate.get("strategy") or "") if candidate else ""
    candidate_screen_clickable = _candidate_screen_clickable(candidate) if candidate_strategy == "visual_bounds" else None
    if candidate and candidate_strategy == "visual_bounds" and not _candidate_screen_clickable(candidate):
        payload = {
            "ok": False,
            "target": target,
            "point": {"x": x, "y": y},
            "display_virtual_bounds": {},
            "warnings": [],
            "reason": "candidate_not_screen_clickable",
        }
        payload["candidate_id"] = _candidate_id(candidate)
        payload["candidate_strategy"] = candidate.get("strategy", "")
        payload["candidate_confidence"] = candidate.get("confidence", "")
        payload["screen_clickable"] = False
        raise ValueError(
            f"desktop_input.{action_label} 输入前安全检查失败：reason=candidate_not_screen_clickable "
            f"target={target} point={{'x': {x}, 'y': {y}}} virtual_bounds={{}}"
        )
    profile = session.coordinate_profile if isinstance(session.coordinate_profile, dict) else {}
    if candidate and isinstance(candidate.get("coordinate_profile"), dict):
        profile = candidate["coordinate_profile"]
    mapper = CoordinateMapper.from_profile(profile)
    payload = mapper.safety_check(
        {"x": x, "y": y},
        target=target,
        bounds=bounds,
        screen_clickable=candidate_screen_clickable if candidate_screen_clickable is not None else None,
    )
    payload = {
        **payload,
        "target": target,
        "point": {"x": x, "y": y},
    }
    if candidate:
        payload["candidate_id"] = _candidate_id(candidate)
        payload["candidate_strategy"] = candidate.get("strategy", "")
        payload["candidate_confidence"] = candidate.get("confidence", "")
        payload["screen_clickable"] = _candidate_screen_clickable(candidate)
    if not payload.get("ok"):
        raise ValueError(
            f"desktop_input.{action_label} 输入前安全检查失败：reason={payload.get('reason', '')} "
            f"target={target} point={{'x': {x}, 'y': {y}}} virtual_bounds={payload.get('display_virtual_bounds', {})}"
        )
    return payload


def _candidate_screen_clickable(candidate: dict[str, Any]) -> bool:
    if "screen_clickable" in candidate:
        return bool(candidate.get("screen_clickable"))
    profile = candidate.get("coordinate_profile") if isinstance(candidate.get("coordinate_profile"), dict) else {}
    source = profile.get("source") if isinstance(profile.get("source"), dict) else {}
    if isinstance(source, dict) and "screen_clickable" in source:
        return bool(source.get("screen_clickable"))
    return False


def _candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("id") or "")


def _compact_input_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(candidate.get("id") or ""),
        "candidate_id": _candidate_id(candidate),
        "source": str(candidate.get("source") or ""),
        "strategy": str(candidate.get("strategy") or ""),
        "confidence": str(candidate.get("confidence") or ""),
        "score": candidate.get("score", 0),
        "screen_clickable": _candidate_screen_clickable(candidate),
        "window_query": candidate.get("window_query", {}) if isinstance(candidate.get("window_query"), dict) else {},
        "locator": candidate.get("locator", {}) if isinstance(candidate.get("locator"), dict) else {},
        "bounds": normalize_bounds(candidate.get("bounds")) if isinstance(candidate.get("bounds"), dict) else {},
        "point": candidate.get("point", {}) if isinstance(candidate.get("point"), dict) else {},
        "reason": str(candidate.get("reason") or ""),
    }


def _compact_input_element(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "automation_id": str(element.get("automation_id") or ""),
        "name": str(element.get("name") or ""),
        "text": str(element.get("text") or ""),
        "control_type": str(element.get("control_type") or ""),
        "role": str(element.get("role") or ""),
        "bounds": normalize_bounds(element.get("bounds")) if isinstance(element.get("bounds"), dict) else {},
    }


def _coordinate(value: Any, *, field: str, action_label: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"desktop_input.{action_label} {field} 必须是数字：{value!r}") from error


def _current_window_bounds(session: DesktopSession, target: str, action_label: str) -> dict[str, Any]:
    window = session.current_window or {}
    bounds = window.get("bounds") if isinstance(window, dict) else None
    if not isinstance(bounds, dict):
        raise ValueError(f"desktop_input.{action_label} target={target} 需要先聚焦或等待到带 bounds 的窗口。")
    return bounds


def _bounds_center(bounds: dict[str, Any], *, action_label: str) -> tuple[int, int]:
    x = _coordinate(bounds.get("x", 0), field="bounds.x", action_label=action_label)
    y = _coordinate(bounds.get("y", 0), field="bounds.y", action_label=action_label)
    width = _coordinate(bounds.get("width", 0), field="bounds.width", action_label=action_label)
    height = _coordinate(bounds.get("height", 0), field="bounds.height", action_label=action_label)
    if width <= 0 or height <= 0:
        raise ValueError(f"desktop_input.{action_label} bounds 无效：{bounds}")
    return x + width // 2, y + height // 2
