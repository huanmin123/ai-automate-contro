from __future__ import annotations

import csv
import io
import json
import platform
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop import DesktopSession
from ai_automate_contro.engine.desktop.action_annotations import (
    _annotation_point,
    _capture_desktop_annotation,
    _capture_element_annotation,
    _input_annotation_bounds,
    _input_annotation_target,
)
from ai_automate_contro.engine.desktop.backends import DesktopBackendError, NativeDesktopBackend
from ai_automate_contro.engine.desktop.backends.capabilities import (
    resolve_tesseract_binary,
    tesseract_binary_details,
    tesseract_common_options,
)
from ai_automate_contro.engine.desktop.coordinates import (
    CoordinateMapper,
    build_coordinate_diagnostics,
    build_coordinate_profile,
    normalize_bounds,
)
from ai_automate_contro.engine.desktop.observation import build_desktop_observation
from ai_automate_contro.engine.desktop.profiles import apply_desktop_app_profile
from ai_automate_contro.engine.desktop.input_resolution import (
    _bool_flag,
    _bounds_center,
    _bool_config,
    _coordinate,
    _coordinate_safety_check,
    _current_window_bounds,
    _element_locator,
    _ensure_input_inside_interaction_window,
    _ensure_interaction_window_active,
    _foreground_protection_config,
    _has_window_query,
    _input_resolution,
    _optional_element_locator,
    _optional_window_query,
    _positive_int_config,
    _resolve_drag_coordinates,
    _resolve_input_coordinates,
    _store_session_target_candidates,
    _string_list,
    _window_list_diagnostics,
    _window_matches_query,
    _window_query,
)
from ai_automate_contro.engine.desktop.locators import (
    ELEMENT_LOCATOR_FIELDS,
    ELEMENT_REQUIRED_LOCATOR_FIELDS,
    WINDOW_QUERY_FIELDS,
)
from ai_automate_contro.engine.desktop.output_paths import output_relative_path
from ai_automate_contro.engine.desktop.targeting import confidence_meets, find_target_candidate
from ai_automate_contro.engine.desktop.vision import (
    _coordinate_diagnostics,
    _desktop_vision_artifact_paths,
    _desktop_vision_text_query,
    _locate_image_in_source,
    _locate_text_in_source,
    _source_coordinate_profile,
)
from ai_automate_contro.engine.output_contract import publish_step_output


WINDOW_CONTROL_TYPES = {"close", "minimize", "maximize", "restore"}
WINDOW_QUERY_REQUIRED_TYPES = {"find", "focus", "close", "minimize", "maximize", "restore"}
DESKTOP_ELEMENT_MESSAGES = {
    "list": "desktop elements listed",
    "dump": "desktop element tree dumped",
    "find": "desktop element resolved",
    "wait": "desktop element wait completed",
    "get_text": "desktop element text read",
    "get_state": "desktop element state read",
    "click": "desktop element clicked",
    "set_text": "desktop element text set",
    "invoke": "desktop element invoked",
    "select": "desktop element selected",
    "get_table": "desktop table read",
    "select_cell": "desktop table cell selected",
    "get_tree": "desktop tree read",
    "expand_tree": "desktop tree expanded",
    "collapse_tree": "desktop tree collapsed",
    "select_tree": "desktop tree selected",
    "invoke_menu": "desktop menu invoked",
    "scroll_element": "desktop element scrolled",
}
DESKTOP_INPUT_COORDINATE_TYPES = {"click", "double_click", "right_click", "scroll", "drag"}


def open_desktop(executor: Any, step: dict[str, Any]) -> None:
    name = str(step["name"])
    if name in executor.state.desktop_sessions:
        raise ValueError(f"桌面会话已存在：{name}")
    platform_name = _resolve_platform_name(str(step.get("platform", "auto")))
    backend_name = str(step.get("backend", "auto"))
    desktop_config = _desktop_runtime_config(executor)
    backend = _create_backend(platform_name=platform_name, backend_name=backend_name, desktop_config=desktop_config)
    started = time.monotonic()
    probe = backend.probe(request_permissions=bool(step.get("request_permissions", False)))
    capability_matrix = probe.get("capability_matrix") if isinstance(probe.get("capability_matrix"), dict) else {}
    coordinate_profile = (
        probe.get("coordinate_profile") if isinstance(probe.get("coordinate_profile"), dict) else {}
    )
    session = DesktopSession(
        name=name,
        backend=backend,
        platform=platform_name,
        backend_name=backend.backend_name,
        permissions=dict(probe.get("permissions", {})) if isinstance(probe.get("permissions"), dict) else {},
        capability_matrix=dict(capability_matrix),
        coordinate_profile=dict(coordinate_profile),
        runtime_config=desktop_config,
    )
    executor.state.desktop_sessions[name] = session
    payload = {
        "ok": True,
        "desktop": name,
        "platform": platform_name,
        "backend": backend.backend_name,
        "probe": probe,
        "capability_matrix": capability_matrix,
        "coordinate_profile": coordinate_profile,
        "elapsed_ms": _elapsed_ms(started),
    }
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop opened",
        desktop=name,
        platform=platform_name,
        backend=backend.backend_name,
        output=step.get("output", {}),
    )


def close_desktop(executor: Any, step: dict[str, Any]) -> None:
    name = str(step["desktop"])
    session = executor.state.require_desktop_session(name)
    session.close()
    del executor.state.desktop_sessions[name]
    executor.state.logger.log("info", "desktop closed", desktop=name)


def desktop_app(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    app_type = str(step["type"])
    if app_type != "launch":
        raise ValueError(f"不支持的 desktop_app.type：{app_type}")
    args = _desktop_app_args(step.get("args", []))
    app = _desktop_app_text(step.get("app", ""), "app")
    path = _desktop_app_text(step.get("path", ""), "path")
    command = _desktop_app_text(step.get("command", ""), "command")
    target_fields = [name for name, value in (("app", app), ("path", path), ("command", command)) if value]
    if not target_fields:
        raise ValueError("desktop_app.launch 需要 app、path 或 command 之一。")
    if len(target_fields) > 1:
        raise ValueError("desktop_app.launch 只能同时使用 app、path 或 command 之一。")
    started = time.monotonic()
    payload = session.backend.launch_app(
        app=app,
        path=path,
        command=command,
        args=args,
        wait=bool(step.get("wait", False)),
        timeout_ms=int(step.get("timeout_ms", 10_000)),
    )
    window_query = _optional_window_query(step)
    wait_payload: dict[str, Any] = {}
    focus_payload: dict[str, Any] = {}
    if bool(step.get("wait_for_window", False)):
        if not any(field in window_query for field in WINDOW_QUERY_FIELDS - {"match_index"}):
            raise ValueError("desktop_app.launch wait_for_window=true 需要至少一种窗口定位字段。")
        wait_payload = session.backend.wait_window(
            window_query,
            state="exists",
            timeout_ms=int(step.get("window_timeout_ms", step.get("timeout_ms", 10_000))),
            interval_ms=int(step.get("interval_ms", 250)),
        )
        window = wait_payload.get("window") if isinstance(wait_payload.get("window"), dict) else {}
        if window:
            session.current_window = dict(window)
        if bool(step.get("focus", False)):
            focus_query = {"window_id": window.get("id")} if window.get("id") not in (None, "") else window_query
            focus_payload = session.backend.focus_window(focus_query)
            session.current_window = dict(focus_payload)
    payload = {
        **payload,
        "desktop": session.name,
        "type": app_type,
        "wait_for_window": bool(step.get("wait_for_window", False)),
        "focus": bool(step.get("focus", False)),
        "window_query": window_query,
        "window": wait_payload.get("window") if isinstance(wait_payload.get("window"), dict) else {},
        "window_wait": wait_payload,
        "window_focus": focus_payload,
        "elapsed_ms": _elapsed_ms(started),
    }
    if profile_payload:
        payload["profile"] = profile_payload
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop app launched",
        desktop=session.name,
        app=payload.get("app", ""),
        path=payload.get("path", ""),
        command=payload.get("command", ""),
        pid=payload.get("pid", ""),
        output=step.get("output", {}),
    )


def desktop_window(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    window_type = str(step["type"])
    started = time.monotonic()
    if window_type == "list":
        query = _optional_window_query(step)
        include_invisible = bool(step.get("include_invisible", False))
        windows = (
            session.backend.find_windows(query, include_invisible=include_invisible)
            if any(field in query for field in WINDOW_QUERY_FIELDS - {"match_index"})
            else session.backend.list_windows(include_invisible=include_invisible)
        )
        total_count = len(windows)
        max_windows = int(step.get("max_windows", 0) or 0)
        output_windows = windows[:max_windows] if max_windows > 0 else windows
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": window_type,
            "query": query,
            "count": len(output_windows),
            "total_count": total_count,
            "windows": output_windows,
            "truncated": max_windows > 0 and total_count > len(output_windows),
            "elapsed_ms": _elapsed_ms(started),
        }
        diagnostics = _window_list_diagnostics(session, include_invisible=include_invisible)
        if diagnostics:
            payload["diagnostics"] = diagnostics
        _with_profile_payload(payload, profile_payload)
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-windows")
            payload["path"] = str(output_path)
            _write_json(output_path, payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop windows listed",
            desktop=session.name,
            count=len(windows),
            path=payload.get("path", ""),
        )
        return
    if window_type == "find":
        query = _window_query(step)
        include_invisible = bool(step.get("include_invisible", False))
        matches = session.backend.find_windows(query, include_invisible=include_invisible)
        match_index = int(query.get("match_index", 0) or 0)
        selected_window = matches[match_index] if 0 <= match_index < len(matches) else {}
        max_windows = int(step.get("max_windows", 0) or 0)
        output_matches = matches[:max_windows] if max_windows > 0 else matches
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": window_type,
            "query": query,
            "count": len(output_matches),
            "match_count": len(matches),
            "matches": output_matches,
            "selected_window": selected_window,
            "truncated": max_windows > 0 and len(matches) > len(output_matches),
            "elapsed_ms": _elapsed_ms(started),
        }
        diagnostics = _window_list_diagnostics(session, include_invisible=include_invisible)
        if diagnostics:
            payload["diagnostics"] = diagnostics
        _with_profile_payload(payload, profile_payload)
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-windows")
            payload["path"] = str(output_path)
            _write_json(output_path, payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop window found",
            desktop=session.name,
            matches=len(matches),
            path=payload.get("path", ""),
            output=step.get("output", {}),
        )
        return
    if window_type == "active":
        window = session.backend.get_active_window()
        if window:
            session.current_window = dict(window)
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": window_type,
            "found": bool(window),
            "window": window,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-windows")
            payload["path"] = str(output_path)
            _write_json(output_path, payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop active window read",
            desktop=session.name,
            title=window.get("title", "") if isinstance(window, dict) else "",
            window_id=window.get("id", "") if isinstance(window, dict) else "",
            output=step.get("output", {}),
        )
        return
    if window_type == "focus":
        query = _window_query(step)
        window = session.backend.focus_window(query)
        session.current_window = dict(window)
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": window_type,
            "query": query,
            "window": window,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop window focused",
            desktop=session.name,
            title=window.get("title", ""),
            window_id=window.get("id", ""),
        )
        return
    if window_type in WINDOW_CONTROL_TYPES:
        query = _window_query(step)
        payload = session.backend.control_window(query, window_type)
        payload = {
            **payload,
            "desktop": session.name,
            "type": window_type,
            "query": query,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if window_type == "close":
            session.current_window = None
        elif isinstance(window, dict):
            session.current_window = dict(window)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop window controlled",
            desktop=session.name,
            type=window_type,
            title=window.get("title", "") if isinstance(window, dict) else "",
            window_id=window.get("id", "") if isinstance(window, dict) else "",
            output=step.get("output", {}),
        )
        return
    raise ValueError(f"不支持的 desktop_window.type：{window_type}")


def desktop_element(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    element_type = str(step["type"])
    if element_type not in DESKTOP_ELEMENT_MESSAGES:
        raise ValueError(f"不支持的 desktop_element.type：{element_type}")
    started = time.monotonic()
    window_query = _window_query(step)
    locator = _optional_element_locator(step)
    max_depth = int(step.get("max_depth", 6))
    max_elements = int(step.get("max_elements", 200))
    timeout_ms = int(step.get("timeout_ms", 1_000))
    interval_ms = int(step.get("interval_ms", 100))
    interaction_guard: dict[str, Any] = {}
    if element_type in {
        "click",
        "set_text",
        "invoke",
        "select",
        "select_cell",
        "expand_tree",
        "collapse_tree",
        "select_tree",
        "invoke_menu",
        "scroll_element",
    }:
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label=f"desktop_element.{element_type}",
            window_query=window_query,
        )

    if element_type == "list":
        payload = session.backend.list_elements(
            window_query,
            locator=locator or None,
            max_depth=max_depth,
            max_elements=max_elements,
        )
    elif element_type == "dump":
        payload = session.backend.dump_elements(
            window_query,
            locator=locator or None,
            max_depth=max_depth,
            max_elements=max_elements,
            include_tree=bool(step.get("include_tree", True)),
            include_selector_hints=bool(step.get("include_selector_hints", True)),
            text_limit=int(step.get("text_limit", 160)),
        )
    elif element_type == "invoke_menu":
        open_context_menu = step.get("open_context_menu") is True
        locator = _element_locator(step) if open_context_menu else {}
        payload = session.backend.invoke_menu(
            window_query,
            locator=locator or None,
            menu_path=_string_list(step.get("menu_path", []), field="menu_path"),
            open_context_menu=open_context_menu,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=max_depth,
            max_elements=max_elements,
        )
    else:
        locator = _element_locator(step)
        if element_type in {"find", "wait"}:
            payload = session.backend.find_element(
                window_query,
                locator,
                state=str(step.get("state", "exists")),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "get_text":
            payload = session.backend.get_element_text(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "get_state":
            payload = session.backend.get_element_state(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "click":
            payload = session.backend.click_element(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "set_text":
            payload = session.backend.set_element_text(
                window_query,
                locator,
                str(step["value"]),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
                preserve_clipboard=bool(step.get("preserve_clipboard", True)),
            )
        elif element_type == "invoke":
            payload = session.backend.invoke_element(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "select":
            payload = session.backend.select_element(
                window_query,
                locator,
                str(step.get("value", "")),
                option_index=step.get("option_index"),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "get_table":
            payload = session.backend.get_table(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
                max_rows=int(step.get("max_rows", 50)),
                max_columns=int(step.get("max_columns", 20)),
                text_limit=int(step.get("text_limit", 160)),
                visible_only=bool(step.get("visible_only", True)),
            )
        elif element_type == "select_cell":
            payload = session.backend.select_table_cell(
                window_query,
                locator,
                row=int(step["row"]),
                column=str(step.get("column", "")),
                column_index=step.get("column_index"),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "get_tree":
            payload = session.backend.get_tree(
                window_query,
                locator,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
                max_nodes=int(step.get("max_nodes", 200)),
                text_limit=int(step.get("text_limit", 160)),
            )
        elif element_type in {"expand_tree", "collapse_tree", "select_tree"}:
            payload = session.backend.tree_element_action(
                window_query,
                locator,
                operation=element_type,
                tree_path=_string_list(step.get("tree_path", []), field="tree_path"),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        elif element_type == "scroll_element":
            payload = session.backend.scroll_element(
                window_query,
                locator,
                amount=int(step["amount"]) if "amount" in step else None,
                scroll_to=str(step.get("scroll_to", "")),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                max_depth=max_depth,
                max_elements=max_elements,
            )
        else:
            raise ValueError(f"不支持的 desktop_element.type：{element_type}")

    payload = {
        **payload,
        "desktop": session.name,
        "type": element_type,
        "query": window_query,
        "elapsed_ms": _elapsed_ms(started),
    }
    if interaction_guard:
        payload["interaction_guard"] = interaction_guard
    _with_profile_payload(payload, profile_payload)
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    if window:
        session.current_window = dict(window)
    if element_type in {
        "click",
        "set_text",
        "invoke",
        "select",
        "select_cell",
        "expand_tree",
        "collapse_tree",
        "select_tree",
        "invoke_menu",
        "scroll_element",
    }:
        annotation = _capture_element_annotation(
            executor,
            session,
            element_type=element_type,
            payload=payload,
            query=window_query,
            locator=locator if isinstance(locator, dict) else {},
        )
        if annotation:
            payload["annotation"] = annotation
    if "path" in step:
        output_path = executor._resolve_output_path(step["path"], category="desktop-elements")
        payload["path"] = str(output_path)
        _write_json(output_path, payload)
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        DESKTOP_ELEMENT_MESSAGES[element_type],
        desktop=session.name,
        type=element_type,
        count=payload.get("count", payload.get("candidates_count", payload.get("length", ""))),
        method=payload.get("method", ""),
        fallback_used=payload.get("fallback_used", ""),
        path=payload.get("path", ""),
        output=step.get("output", {}),
    )


def desktop_input(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    input_type = str(step["type"])
    started = time.monotonic()
    annotation_points: list[dict[str, Any]] = []
    annotation_bounds: list[dict[str, Any]] = []
    annotation_target: dict[str, Any] = {}
    annotation_connect = False
    if input_type == "type_text":
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.type_text",
            step=step,
        )
        payload = session.backend.type_text(
            str(step["value"]),
            method=str(step.get("method", "auto")),
            delay_ms=int(step.get("delay_ms", 0)),
            preserve_clipboard=bool(step.get("preserve_clipboard", True)),
        )
        payload["interaction_guard"] = interaction_guard
    elif input_type == "hotkey":
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.hotkey",
            step=step,
        )
        payload = session.backend.hotkey([str(key) for key in step["keys"]])
        payload["interaction_guard"] = interaction_guard
    elif input_type == "click":
        x, y, target, resolution = _resolve_input_coordinates(session, step, action_label="click")
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.click",
            step=step,
            resolution=resolution,
        )
        window_safety_check = _ensure_input_inside_interaction_window(
            session,
            action_label="desktop_input.click",
            resolution=resolution,
            interaction_guard=interaction_guard,
            allow_outside_window=_bool_flag(step.get("allow_outside_window", False)),
        )
        payload = session.backend.click(
            x=x,
            y=y,
            button=str(step.get("button", "left")),
            clicks=int(step.get("clicks", 1)),
            interval_ms=int(step.get("interval_ms", 0)),
        )
        payload["interaction_guard"] = interaction_guard
        payload["window_safety_check"] = window_safety_check
        if target:
            payload["target"] = target
        payload["input_resolution"] = resolution
        payload["safety_check"] = resolution.get("safety_check", {})
        annotation_points = [_annotation_point(x, y, "click")]
        annotation_bounds = _input_annotation_bounds(session, step, target, resolution)
        annotation_target = _input_annotation_target(step, target=target, resolution=resolution)
    elif input_type == "double_click":
        x, y, target, resolution = _resolve_input_coordinates(session, step, action_label="double_click")
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.double_click",
            step=step,
            resolution=resolution,
        )
        window_safety_check = _ensure_input_inside_interaction_window(
            session,
            action_label="desktop_input.double_click",
            resolution=resolution,
            interaction_guard=interaction_guard,
            allow_outside_window=_bool_flag(step.get("allow_outside_window", False)),
        )
        payload = session.backend.double_click(
            x=x,
            y=y,
            interval_ms=int(step.get("interval_ms", 0)),
        )
        payload["interaction_guard"] = interaction_guard
        payload["window_safety_check"] = window_safety_check
        if target:
            payload["target"] = target
        payload["input_resolution"] = resolution
        payload["safety_check"] = resolution.get("safety_check", {})
        annotation_points = [_annotation_point(x, y, "double_click")]
        annotation_bounds = _input_annotation_bounds(session, step, target, resolution)
        annotation_target = _input_annotation_target(step, target=target, resolution=resolution)
    elif input_type == "right_click":
        x, y, target, resolution = _resolve_input_coordinates(session, step, action_label="right_click")
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.right_click",
            step=step,
            resolution=resolution,
        )
        window_safety_check = _ensure_input_inside_interaction_window(
            session,
            action_label="desktop_input.right_click",
            resolution=resolution,
            interaction_guard=interaction_guard,
            allow_outside_window=_bool_flag(step.get("allow_outside_window", False)),
        )
        payload = session.backend.right_click(x=x, y=y)
        payload["interaction_guard"] = interaction_guard
        payload["window_safety_check"] = window_safety_check
        if target:
            payload["target"] = target
        payload["input_resolution"] = resolution
        payload["safety_check"] = resolution.get("safety_check", {})
        annotation_points = [_annotation_point(x, y, "right_click")]
        annotation_bounds = _input_annotation_bounds(session, step, target, resolution)
        annotation_target = _input_annotation_target(step, target=target, resolution=resolution)
    elif input_type == "scroll":
        x, y, target, resolution = _resolve_input_coordinates(session, step, action_label="scroll")
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.scroll",
            step=step,
            resolution=resolution,
        )
        window_safety_check = _ensure_input_inside_interaction_window(
            session,
            action_label="desktop_input.scroll",
            resolution=resolution,
            interaction_guard=interaction_guard,
            allow_outside_window=_bool_flag(step.get("allow_outside_window", False)),
        )
        payload = session.backend.scroll(x=x, y=y, amount=int(step["amount"]))
        payload["interaction_guard"] = interaction_guard
        payload["window_safety_check"] = window_safety_check
        if target:
            payload["target"] = target
        payload["input_resolution"] = resolution
        payload["safety_check"] = resolution.get("safety_check", {})
        annotation_points = [_annotation_point(x, y, "scroll")]
        annotation_bounds = _input_annotation_bounds(session, step, target, resolution)
        annotation_target = _input_annotation_target(step, target=target, resolution=resolution)
    elif input_type == "drag":
        start_x, start_y, end_x, end_y, target, resolution = _resolve_drag_coordinates(session, step)
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_input.drag",
            step=step,
            resolution=resolution,
        )
        window_safety_check = _ensure_input_inside_interaction_window(
            session,
            action_label="desktop_input.drag",
            resolution=resolution,
            interaction_guard=interaction_guard,
            allow_outside_window=_bool_flag(step.get("allow_outside_window", False)),
            include_end_point=True,
        )
        payload = session.backend.drag(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            button=str(step.get("button", "left")),
            duration_ms=int(step.get("duration_ms", 0)),
        )
        payload["interaction_guard"] = interaction_guard
        payload["window_safety_check"] = window_safety_check
        if target:
            payload["target"] = target
        payload["input_resolution"] = resolution
        payload["safety_check"] = resolution.get("safety_check", {})
        annotation_points = [_annotation_point(start_x, start_y, "start"), _annotation_point(end_x, end_y, "end")]
        annotation_bounds = _input_annotation_bounds(session, step, target, resolution)
        annotation_target = _input_annotation_target(step, target=target, resolution=resolution)
        annotation_connect = True
    else:
        raise ValueError(f"不支持的 desktop_input.type：{input_type}")
    payload = {
        **payload,
        "desktop": session.name,
        "type": input_type,
        "elapsed_ms": _elapsed_ms(started),
    }
    _with_profile_payload(payload, profile_payload)
    if annotation_points:
        payload["annotation"] = _capture_desktop_annotation(
            executor,
            session,
            action=f"desktop_input.{input_type}",
            points=annotation_points,
            bounds=annotation_bounds,
            connect_points=annotation_connect,
            label=f"desktop_input.{input_type}",
            target=annotation_target,
        )
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop input sent",
        desktop=session.name,
        type=input_type,
        output=step.get("output", {}),
    )


def desktop_capture(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    capture_type = str(step["type"])
    started = time.monotonic()
    if capture_type == "screenshot":
        output_path = executor._resolve_output_path(step["path"], category="desktop-screenshots")
        target, region, target_payload = _resolve_capture_region(session, step)
        payload = session.backend.screenshot(
            output_path,
            region=region,
            include_cursor=bool(step.get("include_cursor", False)),
        )
        source_bounds = _capture_source_bounds(payload, region)
        coordinate_space = {"origin": "screen", "unit": "logical_px", "scale": None}
        source_size = {"width": payload.get("width", 0), "height": payload.get("height", 0)}
        coordinate_profile = _source_coordinate_profile(
            session,
            source_kind=target,
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region,
            screen_clickable=True,
        )
        payload = {
            **payload,
            "target": target,
            "source_bounds": source_bounds,
            "coordinate_space": coordinate_space,
            "coordinate_profile": coordinate_profile,
            "coordinate_diagnostics": _coordinate_diagnostics(
                source_bounds=source_bounds,
                source_size=source_size,
                coordinate_space=coordinate_space,
                region=region,
                coordinate_profile=coordinate_profile,
            ),
            **target_payload,
        }
    elif capture_type == "snapshot":
        output_path = executor._resolve_output_path(step["path"], category="desktop-state")
        payload = session.backend.snapshot(
            include_windows=bool(step.get("include_windows", True)),
            include_displays=bool(step.get("include_displays", True)),
        )
        capability_matrix = payload.get("capability_matrix") if isinstance(payload.get("capability_matrix"), dict) else {}
        if capability_matrix:
            session.capability_matrix = dict(capability_matrix)
        coordinate_profile = (
            payload.get("coordinate_profile") if isinstance(payload.get("coordinate_profile"), dict) else {}
        )
        if coordinate_profile:
            session.coordinate_profile = dict(coordinate_profile)
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": capture_type,
            "path": str(output_path),
            "current_window": session.current_window or {},
            "capability_matrix": capability_matrix,
            "coordinate_profile": coordinate_profile,
            "snapshot": payload,
            "elapsed_ms": _elapsed_ms(started),
        }
        _write_json(output_path, payload)
    elif capture_type == "observe":
        output_path = executor._resolve_output_path(step["path"], category="desktop-state")
        screenshot_path = _desktop_observe_screenshot_path(output_path) if bool(step.get("include_screenshot", False)) else None
        interaction_guard = _capture_interaction_guard(
            session,
            action_label="desktop_capture.observe",
            step=step,
            enabled=bool(step.get("include_screenshot", False)),
        )
        payload = build_desktop_observation(
            session.backend,
            desktop=session.name,
            current_window=session.current_window or {},
            window_query=_optional_window_query(step),
            element_locator=_optional_element_locator(step),
            output_path=output_path,
            screenshot_path=screenshot_path,
            request_permissions=bool(step.get("request_permissions", False)),
            include_windows=bool(step.get("include_windows", True)),
            include_invisible=bool(step.get("include_invisible", False)),
            include_elements=bool(step.get("include_elements", False)),
            include_screenshot=bool(step.get("include_screenshot", False)),
            max_windows=int(step.get("max_windows", 20)),
            max_elements=int(step.get("max_elements", 120)),
            max_depth=int(step.get("max_depth", 4)),
            text_limit=int(step.get("text_limit", 120)),
        )
        if isinstance(payload.get("coordinate_profile"), dict):
            session.coordinate_profile = dict(payload["coordinate_profile"])
        capability_matrix = payload.get("capability_matrix") if isinstance(payload.get("capability_matrix"), dict) else {}
        if capability_matrix:
            session.capability_matrix = dict(capability_matrix)
        selected_window = payload.get("selected_window") if isinstance(payload.get("selected_window"), dict) else {}
        if selected_window:
            session.current_window = dict(selected_window)
        _store_session_target_candidates(session, payload)
        payload = {
            **payload,
            "action": "desktop_capture",
            "type": capture_type,
            "path": str(output_path),
            "elapsed_ms": _elapsed_ms(started),
        }
        if interaction_guard:
            payload["interaction_guard"] = interaction_guard
        _write_json(output_path, payload)
    else:
        raise ValueError(f"不支持的 desktop_capture.type：{capture_type}")
    payload = {
        **payload,
        "desktop": session.name,
        "type": capture_type,
        "elapsed_ms": _elapsed_ms(started),
    }
    _with_profile_payload(payload, profile_payload)
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop capture saved",
        desktop=session.name,
        type=capture_type,
        path=payload.get("path", str(output_path)),
    )


def _desktop_observe_screenshot_path(output_path: Path) -> Path:
    suffix = output_path.suffix or ".json"
    return output_path.with_name(f"{output_path.name.removesuffix(suffix)}.png")


def _resolve_capture_region(
    session: DesktopSession,
    step: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    raw_target = str(step.get("target", "") or "")
    explicit_region = step.get("region") if isinstance(step.get("region"), dict) else None
    timeout_ms = int(step.get("timeout_ms", 1_000))
    interval_ms = int(step.get("interval_ms", 100))

    if raw_target in {"", "screen"}:
        if explicit_region:
            return "region", dict(explicit_region), {"target_query": {}, "locator": {}}
        return "screen", None, {"target_query": {}, "locator": {}}
    if raw_target == "region":
        if not explicit_region:
            raise ValueError("desktop_capture.screenshot target=region 需要 region。")
        return "region", dict(explicit_region), {"target_query": {}, "locator": {}}
    if raw_target == "window":
        if explicit_region:
            raise ValueError("desktop_capture.screenshot target=window 不能同时使用 region。")
        query = _window_query(step)
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_capture.screenshot target=window",
            window_query=query,
            strict=False,
        )
        payload = session.backend.wait_window(
            query,
            state="exists",
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if not window:
            raise ValueError(f"desktop_capture.screenshot target=window 未找到窗口：{query}")
        session.current_window = dict(window)
        region = _region_from_bounds(window.get("bounds"), action_label="desktop_capture.screenshot target=window")
        return "window", region, {"target_query": query, "window": window, "locator": {}, "interaction_guard": interaction_guard}
    if raw_target == "element":
        if explicit_region:
            raise ValueError("desktop_capture.screenshot target=element 不能同时使用 region。")
        query = _window_query(step)
        locator = _element_locator(step)
        interaction_guard = _ensure_interaction_window_active(
            session,
            action_label="desktop_capture.screenshot target=element",
            window_query=query,
            strict=False,
        )
        payload = session.backend.find_element(
            query,
            locator,
            state=str(step.get("state", "exists")),
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            max_depth=int(step.get("max_depth", 6)),
            max_elements=int(step.get("max_elements", 200)),
        )
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        if window:
            session.current_window = dict(window)
        if not element:
            raise ValueError(f"desktop_capture.screenshot target=element 未找到控件：locator={locator}")
        region = _region_from_bounds(element.get("bounds"), action_label="desktop_capture.screenshot target=element")
        return "element", region, {"target_query": query, "locator": locator, "window": window, "element": element, "interaction_guard": interaction_guard}
    raise ValueError(f"不支持的 desktop_capture.screenshot target：{raw_target}")


def _capture_interaction_guard(
    session: DesktopSession,
    *,
    action_label: str,
    step: dict[str, Any],
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {}
    query = _optional_window_query(step)
    if not _has_window_query(query):
        return {}
    return _ensure_interaction_window_active(session, action_label=action_label, window_query=query, strict=False)


def _region_from_bounds(bounds: Any, *, action_label: str) -> dict[str, int]:
    if not isinstance(bounds, dict):
        raise ValueError(f"{action_label} 需要目标 bounds。")
    region = {
        "x": _int_coordinate(bounds.get("x", 0), field="bounds.x", action_label=action_label),
        "y": _int_coordinate(bounds.get("y", 0), field="bounds.y", action_label=action_label),
        "width": _int_coordinate(bounds.get("width", 0), field="bounds.width", action_label=action_label),
        "height": _int_coordinate(bounds.get("height", 0), field="bounds.height", action_label=action_label),
    }
    if region["width"] <= 0 or region["height"] <= 0:
        raise ValueError(f"{action_label} bounds 无效：{bounds}")
    return region


def _capture_source_bounds(payload: dict[str, Any], region: dict[str, Any] | None) -> dict[str, int]:
    if region:
        return _region_from_bounds(region, action_label="desktop_capture.screenshot source_bounds")
    return {
        "x": 0,
        "y": 0,
        "width": _int_coordinate(payload.get("width", 0), field="width", action_label="desktop_capture.screenshot"),
        "height": _int_coordinate(payload.get("height", 0), field="height", action_label="desktop_capture.screenshot"),
    }


def _int_coordinate(value: Any, *, field: str, action_label: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{action_label} {field} 必须是数字：{value!r}") from error


def desktop_vision(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    vision_type = str(step["type"])
    if vision_type not in {"locate_image", "locate_text"}:
        raise ValueError(f"不支持的 desktop_vision.type：{vision_type}")
    started = time.monotonic()
    output_path = executor._resolve_output_path(step["path"], category="desktop-vision")
    template_path = executor._resolve_path(str(step["template_path"])) if vision_type == "locate_image" else None
    source_input_path = executor._resolve_path(str(step["source_path"])) if step.get("source_path") else None
    if source_input_path is not None and step.get("source_target"):
        raise ValueError(f"desktop_vision.{vision_type} 不能同时使用 source_path 和 source_target。")
    threshold = float(step.get("threshold", 0.85))
    match_query = _desktop_vision_text_query(step) if vision_type == "locate_text" else {}
    language = str(step.get("language", "eng"))
    provider = str(step.get("provider", "auto"))
    min_confidence = float(step.get("min_confidence", 0.60))
    case_sensitive = bool(step.get("case_sensitive", False))
    match_index = int(step.get("match_index", 0))
    max_matches = int(step.get("max_matches", 10))
    timeout_ms = int(step.get("timeout_ms", 3_000))
    interval_ms = int(step.get("interval_ms", 250))
    deadline = time.monotonic() + max(0.001, timeout_ms / 1000)
    artifacts = _desktop_vision_artifact_paths(output_path)
    last_payload: dict[str, Any] = {}

    while True:
        source_path, source_payload, source_bounds, coordinate_origin = _prepare_desktop_vision_source(
            session,
            step=step,
            source_input_path=source_input_path,
            source_artifact_path=artifacts["source"],
            include_cursor=bool(step.get("include_cursor", False)),
        )
        if vision_type == "locate_image":
            if template_path is None:
                raise ValueError("desktop_vision.locate_image 需要 template_path。")
            payload = _locate_image_in_source(
                template_path=template_path,
                source_path=source_path,
                output_path=output_path,
                artifacts=artifacts,
                region=step.get("region") if isinstance(step.get("region"), dict) else None,
                threshold=threshold,
                match_index=match_index,
                max_matches=max_matches,
                coordinate_origin=coordinate_origin,
                started=started,
                source_payload=source_payload,
                source_bounds=source_bounds,
                desktop=session.name,
            )
        else:
            payload = _locate_text_in_source(
                source_path=source_path,
                output_path=output_path,
                artifacts=artifacts,
                region=step.get("region") if isinstance(step.get("region"), dict) else None,
                match_query=match_query,
                language=language,
                provider=provider,
                min_confidence=min_confidence,
                case_sensitive=case_sensitive,
                match_index=match_index,
                max_matches=max_matches,
                coordinate_origin=coordinate_origin,
                started=started,
                source_payload=source_payload,
                source_bounds=source_bounds,
                desktop=session.name,
                desktop_config=_desktop_runtime_config(executor),
            )
        last_payload = payload
        if payload.get("ok"):
            break
        if source_input_path is not None or time.monotonic() >= deadline:
            payload["path"] = str(output_path)
            payload["relative_path"] = output_relative_path(output_path)
            _with_profile_payload(payload, profile_payload)
            _write_json(output_path, payload)
            raise TimeoutError(
                f"desktop_vision.{vision_type} 未找到匹配目标："
                f"query={match_query or template_path} match_index={match_index}"
            )
        time.sleep(max(0.001, interval_ms / 1000))

    last_payload["path"] = str(output_path)
    last_payload["relative_path"] = output_relative_path(output_path)
    _with_profile_payload(last_payload, profile_payload)
    _store_session_target_candidates(session, last_payload)
    _write_json(output_path, last_payload)
    publish_step_output(executor, step, last_payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop vision located",
        desktop=session.name,
        type=vision_type,
        path=str(output_path),
        score=last_payload.get("match", {}).get("score", ""),
        output=step.get("output", {}),
    )


def desktop_wait(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    wait_type = str(step["type"])
    if wait_type != "window":
        raise ValueError(f"不支持的 desktop_wait.type：{wait_type}")
    query = _window_query(step)
    payload = session.backend.wait_window(
        query,
        state=str(step.get("state", "exists")),
        timeout_ms=int(step.get("timeout_ms", 10_000)),
        interval_ms=int(step.get("interval_ms", 250)),
    )
    payload = {**payload, "desktop": session.name, "type": wait_type, "query": query}
    _with_profile_payload(payload, profile_payload)
    if isinstance(payload.get("window"), dict):
        session.current_window = dict(payload["window"])
    publish_step_output(executor, step, payload, action=str(step["action"]))
    executor.state.logger.log(
        "info",
        "desktop wait completed",
        desktop=session.name,
        state=payload.get("state", ""),
        matches=len(payload.get("matches", [])) if isinstance(payload.get("matches"), list) else "",
    )


def desktop_assert(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    step, profile_payload = _apply_desktop_profile(executor, session, step)
    assert_type = str(step["type"])
    started = time.monotonic()
    if assert_type == "window":
        query = _window_query(step)
        expected_state = str(step.get("state", "exists"))
        try:
            payload = session.backend.wait_window(
                query,
                state=expected_state,
                timeout_ms=int(step.get("timeout_ms", 1_000)),
                interval_ms=int(step.get("interval_ms", 100)),
            )
        except TimeoutError as error:
            raise AssertionError(f"桌面窗口断言失败：state={expected_state} query={query}") from error
        if isinstance(payload.get("window"), dict):
            session.current_window = dict(payload["window"])
        payload = {
            **payload,
            "desktop": session.name,
            "type": assert_type,
            "query": query,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop assertion passed",
            desktop=session.name,
            type=assert_type,
            state=expected_state,
            matches=len(payload.get("matches", [])) if isinstance(payload.get("matches"), list) else "",
            output=step.get("output", {}),
        )
        return

    if assert_type == "screenshot":
        output_path = executor._resolve_output_path(step["path"], category="desktop-screenshots")
        min_bytes = int(step.get("min_bytes", 1))
        actual_bytes = output_path.stat().st_size if output_path.exists() and output_path.is_file() else 0
        if actual_bytes < min_bytes:
            raise AssertionError(
                f"桌面截图断言失败：path={output_path} bytes={actual_bytes} min_bytes={min_bytes}"
            )
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": assert_type,
            "path": str(output_path),
            "bytes": actual_bytes,
            "min_bytes": min_bytes,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop assertion passed",
            desktop=session.name,
            type=assert_type,
            path=str(output_path),
            bytes=actual_bytes,
            output=step.get("output", {}),
        )
        return

    if assert_type == "element":
        query = _window_query(step)
        locator = _element_locator(step)
        expected_state = str(step.get("state", "exists"))
        try:
            payload = session.backend.find_element(
                query,
                locator,
                state=expected_state,
                timeout_ms=int(step.get("timeout_ms", 1_000)),
                interval_ms=int(step.get("interval_ms", 100)),
                max_depth=int(step.get("max_depth", 6)),
                max_elements=int(step.get("max_elements", 200)),
            )
        except TimeoutError as error:
            raise AssertionError(f"桌面控件断言失败：state={expected_state} query={query} locator={locator}") from error
        element = payload.get("element") if isinstance(payload.get("element"), dict) else {}
        text_source = str(step.get("text_source", "auto"))
        actual_text = _element_text(element, source=text_source) if isinstance(element, dict) else ""
        expected_text = step.get("expected")
        text_assertion: dict[str, Any] = {}
        count_assertion = _assert_element_count(payload, step)
        property_assertion: dict[str, Any] = {}
        if expected_text is not None:
            mode = str(step.get("mode", "equals"))
            _assert_text(actual_text, str(expected_text), mode=mode)
            text_assertion = {
                "expected": str(expected_text),
                "actual": actual_text,
                "mode": mode,
                "text_source": text_source,
            }
        if "property" in step:
            property_assertion = _assert_element_property(element, step)
        payload = {
            **payload,
            "ok": True,
            "desktop": session.name,
            "type": assert_type,
            "query": query,
            "locator": locator,
            "state": expected_state,
            "text_assertion": text_assertion,
            "count_assertion": count_assertion,
            "property_assertion": property_assertion,
            "elapsed_ms": _elapsed_ms(started),
        }
        _with_profile_payload(payload, profile_payload)
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if window:
            session.current_window = dict(window)
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-elements")
            payload["path"] = str(output_path)
            _write_json(output_path, payload)
        publish_step_output(executor, step, payload, action=str(step["action"]))
        executor.state.logger.log(
            "info",
            "desktop element assertion passed",
            desktop=session.name,
            type=assert_type,
            state=expected_state,
            matches=len(payload.get("matches", [])) if isinstance(payload.get("matches"), list) else "",
            path=payload.get("path", ""),
            output=step.get("output", {}),
        )
        return

    raise ValueError(f"不支持的 desktop_assert.type：{assert_type}")




def _prepare_desktop_vision_source(
    session: DesktopSession,
    *,
    step: dict[str, Any],
    source_input_path: Path | None,
    source_artifact_path: Path,
    include_cursor: bool,
) -> tuple[Path, dict[str, Any], dict[str, int], str]:
    raw_source_target = str(step.get("source_target", "") or "")
    if source_input_path is not None:
        if not source_input_path.exists():
            raise FileNotFoundError(f"desktop_vision.source_path 文件不存在：{source_input_path}")
        from PIL import Image

        source_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_input_path) as image:
            image.convert("RGB").save(source_artifact_path)
            source_bounds = {"x": 0, "y": 0, "width": int(image.width), "height": int(image.height)}
            coordinate_space = {"origin": "source_path", "unit": "logical_px", "scale": None}
            source_size = {"width": image.width, "height": image.height}
            coordinate_profile = _source_coordinate_profile(
                session,
                source_kind="source_path",
                source_bounds=source_bounds,
                source_size=source_size,
                coordinate_space=coordinate_space,
                region=step.get("region") if isinstance(step.get("region"), dict) else None,
                screen_clickable=False,
            )
            payload = {
                "ok": True,
                "path": str(source_artifact_path),
                "input_path": str(source_input_path),
                "width": image.width,
                "height": image.height,
                "region": step.get("region") if isinstance(step.get("region"), dict) else {},
                "include_cursor": False,
                "source": "source_path",
                "source_target": "source_path",
                "source_bounds": source_bounds,
                "coordinate_space": coordinate_space,
                "coordinate_profile": coordinate_profile,
                "coordinate_diagnostics": _coordinate_diagnostics(
                    source_bounds=source_bounds,
                    source_size=source_size,
                    coordinate_space=coordinate_space,
                    region=step.get("region") if isinstance(step.get("region"), dict) else None,
                    coordinate_profile=coordinate_profile,
                ),
                "target_query": {},
                "locator": {},
            }
        return source_artifact_path, payload, source_bounds, "source_path"

    source_target = raw_source_target or "screen"
    if source_target not in {"screen", "window", "element"}:
        raise ValueError(f"不支持的 desktop_vision source_target：{source_target}")
    region: dict[str, Any] | None = None
    source_target_payload: dict[str, Any] = {"target_query": {}, "locator": {}}
    if source_target in {"window", "element"}:
        capture_step = dict(step)
        capture_step["target"] = source_target
        capture_step.pop("source_target", None)
        capture_step.pop("region", None)
        if "window_match_index" in capture_step:
            capture_step["match_index"] = capture_step["window_match_index"]
        else:
            capture_step.pop("match_index", None)
        capture_step.pop("window_match_index", None)
        _target, region, source_target_payload = _resolve_capture_region(session, capture_step)

    payload = session.backend.screenshot(source_artifact_path, region=region, include_cursor=include_cursor)
    source_bounds = _capture_source_bounds(payload, region)
    coordinate_space = {"origin": "screen", "unit": "logical_px", "scale": None}
    source_size = {"width": payload.get("width", 0), "height": payload.get("height", 0)}
    coordinate_profile = _source_coordinate_profile(
        session,
        source_kind=source_target,
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region,
        screen_clickable=True,
    )
    payload = {
        **payload,
        "source": "desktop_screenshot",
        "source_target": source_target,
        "window_match_index": step.get("window_match_index", ""),
        "source_bounds": source_bounds,
        "coordinate_space": coordinate_space,
        "coordinate_profile": coordinate_profile,
        "coordinate_diagnostics": _coordinate_diagnostics(
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region,
            coordinate_profile=coordinate_profile,
        ),
        **source_target_payload,
    }
    return source_artifact_path, payload, source_bounds, "screen"


def _desktop_runtime_config(executor: Any) -> dict[str, Any]:
    config = executor.state.variables.get("config") if hasattr(executor, "state") else {}
    return dict(config) if isinstance(config, dict) else {}


def _apply_desktop_profile(
    executor: Any,
    session: DesktopSession,
    step: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not (step.get("profile") or step.get("app_profile")):
        return step, {}
    return apply_desktop_app_profile(
        step,
        platform_name=session.platform,
        desktop_config=_desktop_runtime_config(executor),
    )


def _with_profile_payload(payload: dict[str, Any], profile_payload: dict[str, Any]) -> dict[str, Any]:
    if profile_payload:
        payload["profile"] = profile_payload
    return payload


def _create_backend(
    *,
    platform_name: str,
    backend_name: str,
    desktop_config: dict[str, Any] | None = None,
) -> NativeDesktopBackend:
    if platform_name not in {"windows", "macos"}:
        raise DesktopBackendError(f"桌面控制 Phase 0 仅支持 Windows 和 macOS：{platform_name}")
    current = _current_platform_name()
    if platform_name != current:
        raise DesktopBackendError(f"当前系统是 {current}，不能打开 platform={platform_name} 的桌面会话。")
    if backend_name in {"auto", "native"}:
        return NativeDesktopBackend(platform_name=platform_name, desktop_config=desktop_config)
    raise DesktopBackendError(f"桌面 backend 尚未接入：{backend_name}。Phase 0 请使用 backend=auto 或 backend=native。")


def _resolve_platform_name(raw_platform: str) -> str:
    if raw_platform == "auto":
        return _current_platform_name()
    if raw_platform in {"windows", "macos"}:
        return raw_platform
    raise DesktopBackendError(f"不支持的 desktop platform：{raw_platform}")


def _current_platform_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return system.lower() or "unknown"




def _element_text(element: dict[str, Any], *, source: str = "auto") -> str:
    fields = ("text", "value", "name") if source == "auto" else (source,)
    for field in fields:
        value = str(element.get(field) or "")
        if value:
            return value
    return ""


def _assert_text(actual: str, expected: str, *, mode: str) -> None:
    if mode == "equals":
        ok = actual == expected
    elif mode == "contains":
        ok = expected in actual
    elif mode == "not_contains":
        ok = expected not in actual
    else:
        raise ValueError(f"不支持的 desktop_assert.element.mode：{mode}")
    if not ok:
        raise AssertionError(f"桌面控件文本断言失败：mode={mode} expected={expected!r} actual={actual!r}")


def _assert_element_count(payload: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    if not any(field in step for field in ("expected_count", "min_count", "max_count")):
        return {}
    matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
    actual = int(payload.get("candidates_count", len(matches)) or 0)
    assertion: dict[str, Any] = {"actual": actual}
    if "expected_count" in step:
        expected = int(step["expected_count"])
        assertion["expected_count"] = expected
        if actual != expected:
            raise AssertionError(f"桌面控件数量断言失败：expected_count={expected} actual={actual}")
    if "min_count" in step:
        minimum = int(step["min_count"])
        assertion["min_count"] = minimum
        if actual < minimum:
            raise AssertionError(f"桌面控件数量断言失败：min_count={minimum} actual={actual}")
    if "max_count" in step:
        maximum = int(step["max_count"])
        assertion["max_count"] = maximum
        if actual > maximum:
            raise AssertionError(f"桌面控件数量断言失败：max_count={maximum} actual={actual}")
    assertion["ok"] = True
    return assertion


def _assert_element_property(element: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(element, dict) or not element:
        raise AssertionError("桌面控件属性断言失败：未命中控件，无法读取属性。")
    property_name = str(step.get("property") or "")
    if not property_name:
        raise ValueError("desktop_assert.element property 不能为空。")
    if "property_expected" not in step:
        raise ValueError("desktop_assert.element 使用 property 时必须提供 property_expected。")
    actual = _element_property_value(element, property_name)
    expected = step.get("property_expected")
    mode = str(step.get("property_mode", "equals"))
    if mode == "equals":
        ok = actual == expected or str(actual) == str(expected)
    elif mode == "contains":
        ok = str(expected) in str(actual)
    elif mode == "not_contains":
        ok = str(expected) not in str(actual)
    else:
        raise ValueError(f"不支持的 desktop_assert.element.property_mode：{mode}")
    if not ok:
        raise AssertionError(
            "桌面控件属性断言失败："
            f"property={property_name!r} mode={mode} expected={expected!r} actual={actual!r}"
        )
    return {
        "ok": True,
        "property": property_name,
        "expected": expected,
        "actual": actual,
        "mode": mode,
    }


def _element_property_value(element: dict[str, Any], property_name: str) -> Any:
    normalized = property_name.strip()
    if normalized == "class_name":
        return element.get("class_name", element.get("element_class_name", ""))
    if normalized == "element_class_name":
        return element.get("element_class_name", element.get("class_name", ""))
    if normalized == "bounds":
        return normalize_bounds(element.get("bounds")) if isinstance(element.get("bounds"), dict) else {}
    return element.get(normalized, "")




def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _desktop_app_args(raw_args: Any) -> list[str]:
    if raw_args is None:
        return []
    if not isinstance(raw_args, list):
        raise ValueError("desktop_app.args 必须是字符串数组。")
    args: list[str] = []
    for index, raw_arg in enumerate(raw_args):
        if not isinstance(raw_arg, str) or not raw_arg:
            raise ValueError(f"desktop_app.args[{index}] 必须是非空字符串。")
        args.append(raw_arg)
    return args


def _desktop_app_text(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError(f"desktop_app.{field} 必须是字符串。")
    return value


ACTION_HANDLERS = {
    "close_desktop": close_desktop,
    "desktop_app": desktop_app,
    "desktop_capture": desktop_capture,
    "desktop_element": desktop_element,
    "desktop_input": desktop_input,
    "desktop_assert": desktop_assert,
    "desktop_vision": desktop_vision,
    "desktop_wait": desktop_wait,
    "desktop_window": desktop_window,
    "open_desktop": open_desktop,
}
