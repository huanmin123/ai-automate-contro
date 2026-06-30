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
from ai_automate_contro.engine.desktop.annotations import capture_pointer_annotation
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
from ai_automate_contro.engine.desktop.targeting import confidence_meets, find_target_candidate, build_vision_targeting


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

WINDOW_CONTROL_TYPES = {"close", "minimize", "maximize", "restore"}
WINDOW_QUERY_REQUIRED_TYPES = {"find", "focus", "close", "minimize", "maximize", "restore"}
ELEMENT_LOCATOR_FIELDS = {
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
ELEMENT_REQUIRED_LOCATOR_FIELDS = ELEMENT_LOCATOR_FIELDS - {"element_match_index"}
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
DESKTOP_INTERACTION_GUARD_ATTEMPTS = 3
DESKTOP_INTERACTION_GUARD_RETRY_DELAY_SECONDS = 0.08


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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
    executor.state.logger.log(
        "info",
        "desktop opened",
        desktop=name,
        platform=platform_name,
        backend=backend.backend_name,
        save_as=step.get("save_as", ""),
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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
    executor.state.logger.log(
        "info",
        "desktop app launched",
        desktop=session.name,
        app=payload.get("app", ""),
        path=payload.get("path", ""),
        command=payload.get("command", ""),
        pid=payload.get("pid", ""),
        save_as=step.get("save_as", ""),
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop window found",
            desktop=session.name,
            matches=len(matches),
            path=payload.get("path", ""),
            save_as=step.get("save_as", ""),
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop active window read",
            desktop=session.name,
            title=window.get("title", "") if isinstance(window, dict) else "",
            window_id=window.get("id", "") if isinstance(window, dict) else "",
            save_as=step.get("save_as", ""),
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop window controlled",
            desktop=session.name,
            type=window_type,
            title=window.get("title", "") if isinstance(window, dict) else "",
            window_id=window.get("id", "") if isinstance(window, dict) else "",
            save_as=step.get("save_as", ""),
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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
    executor.state.logger.log(
        "info",
        DESKTOP_ELEMENT_MESSAGES[element_type],
        desktop=session.name,
        type=element_type,
        count=payload.get("count", payload.get("candidates_count", payload.get("length", ""))),
        method=payload.get("method", ""),
        fallback_used=payload.get("fallback_used", ""),
        path=payload.get("path", ""),
        save_as=step.get("save_as", ""),
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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
    executor.state.logger.log(
        "info",
        "desktop input sent",
        desktop=session.name,
        type=input_type,
        save_as=step.get("save_as", ""),
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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
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
            payload["relative_path"] = _output_relative_path(output_path)
            _with_profile_payload(payload, profile_payload)
            _write_json(output_path, payload)
            raise TimeoutError(
                f"desktop_vision.{vision_type} 未找到匹配目标："
                f"query={match_query or template_path} match_index={match_index}"
            )
        time.sleep(max(0.001, interval_ms / 1000))

    last_payload["path"] = str(output_path)
    last_payload["relative_path"] = _output_relative_path(output_path)
    _with_profile_payload(last_payload, profile_payload)
    _store_session_target_candidates(session, last_payload)
    _write_json(output_path, last_payload)
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = last_payload
    executor.state.logger.log(
        "info",
        "desktop vision located",
        desktop=session.name,
        type=vision_type,
        path=str(output_path),
        score=last_payload.get("match", {}).get("score", ""),
        save_as=step.get("save_as", ""),
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
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop assertion passed",
            desktop=session.name,
            type=assert_type,
            state=expected_state,
            matches=len(payload.get("matches", [])) if isinstance(payload.get("matches"), list) else "",
            save_as=step.get("save_as", ""),
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop assertion passed",
            desktop=session.name,
            type=assert_type,
            path=str(output_path),
            bytes=actual_bytes,
            save_as=step.get("save_as", ""),
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
        if "save_as" in step:
            executor.state.variables[str(step["save_as"])] = payload
        executor.state.logger.log(
            "info",
            "desktop element assertion passed",
            desktop=session.name,
            type=assert_type,
            state=expected_state,
            matches=len(payload.get("matches", [])) if isinstance(payload.get("matches"), list) else "",
            path=payload.get("path", ""),
            save_as=step.get("save_as", ""),
        )
        return

    raise ValueError(f"不支持的 desktop_assert.type：{assert_type}")


def _desktop_vision_artifact_paths(output_path: Path) -> dict[str, Path]:
    stem = output_path.stem or "vision"
    return {
        "source": output_path.with_name(f"{stem}-source.png"),
        "crop": output_path.with_name(f"{stem}-crop.png"),
        "annotation": output_path.with_name(f"{stem}-annotated.png"),
    }


def _desktop_vision_text_query(step: dict[str, Any]) -> dict[str, str]:
    query = {
        field: str(step[field])
        for field in ("text", "text_contains", "text_regex")
        if field in step and step[field] not in (None, "")
    }
    if not query:
        raise ValueError("desktop_vision.locate_text 需要 text、text_contains 或 text_regex 之一。")
    return query


def _source_coordinate_profile(
    session: DesktopSession,
    *,
    source_kind: str,
    source_bounds: dict[str, Any],
    source_size: dict[str, Any],
    coordinate_space: dict[str, Any],
    region: dict[str, Any] | None = None,
    screen_clickable: bool | None = None,
) -> dict[str, Any]:
    base = session.coordinate_profile if isinstance(session.coordinate_profile, dict) else {}
    display = base.get("display") if isinstance(base.get("display"), dict) else {}
    return build_coordinate_profile(
        platform=session.platform,
        backend=session.backend_name,
        display=display,
        source_kind=source_kind,
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region,
        screen_clickable=screen_clickable,
    )


def _coordinate_diagnostics(
    *,
    source_bounds: dict[str, Any],
    coordinate_space: dict[str, Any],
    source_size: dict[str, Any] | None = None,
    region: dict[str, Any] | None = None,
    coordinate_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = (
        coordinate_profile
        if isinstance(coordinate_profile, dict)
        else build_coordinate_profile(
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region,
        )
    )
    return build_coordinate_diagnostics(
        coordinate_profile=profile,
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region,
    )


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


def _locate_image_in_source(
    *,
    template_path: Path,
    source_path: Path,
    output_path: Path,
    artifacts: dict[str, Path],
    region: dict[str, Any] | None,
    threshold: float,
    match_index: int,
    max_matches: int,
    coordinate_origin: str,
    started: float,
    source_payload: dict[str, Any],
    source_bounds: dict[str, int],
    desktop: str,
) -> dict[str, Any]:
    if not template_path.exists():
        raise FileNotFoundError(f"desktop_vision.template_path 文件不存在：{template_path}")
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception as error:
        raise DesktopBackendError("desktop_vision.locate_image 需要 opencv-python、numpy 和 Pillow。") from error

    with Image.open(source_path) as raw_source, Image.open(template_path) as raw_template:
        source_image = raw_source.convert("RGB")
        template_image = raw_template.convert("RGB")
        search_image, region_payload = _desktop_vision_search_image(source_image, region)
        source_array = cv2.cvtColor(np.array(search_image), cv2.COLOR_RGB2BGR)
        template_array = cv2.cvtColor(np.array(template_image), cv2.COLOR_RGB2BGR)
        if template_array.shape[0] > source_array.shape[0] or template_array.shape[1] > source_array.shape[1]:
            matches: list[dict[str, Any]] = []
            diagnostics = {
                "method": "opencv.matchTemplate",
                "cv2_version": str(getattr(cv2, "__version__", "")),
                "reason": "template_larger_than_source",
                "source_size": {"width": source_image.width, "height": source_image.height},
                "template_size": {"width": template_image.width, "height": template_image.height},
            }
        else:
            result = cv2.matchTemplate(source_array, template_array, cv2.TM_CCOEFF_NORMED)
            raw_matches = _desktop_vision_template_matches(
                result,
                threshold=threshold,
                max_matches=max(1, max_matches),
                template_width=template_image.width,
                template_height=template_image.height,
                region=region_payload,
            )
            local_matches = raw_matches
            matches = _desktop_vision_global_matches(local_matches, source_bounds)
            diagnostics = {
                "method": "opencv.matchTemplate",
                "cv2_version": str(getattr(cv2, "__version__", "")),
                "max_score": float(result.max()) if result.size else 0.0,
                "candidate_count": len(matches),
                "source_size": {"width": source_image.width, "height": source_image.height},
                "template_size": {"width": template_image.width, "height": template_image.height},
            }

        local_matches = local_matches if "local_matches" in locals() else []
        local_selected = local_matches[match_index] if 0 <= match_index < len(local_matches) else None
        selected = matches[match_index] if "matches" in locals() and 0 <= match_index < len(matches) else None
        if local_selected is not None:
            _save_desktop_vision_crop(source_image, local_selected["bounds"], artifacts["crop"])
            _save_desktop_vision_annotation(source_image, local_matches, local_selected, artifacts["annotation"])

    source_profile = source_payload.get("coordinate_profile") if isinstance(source_payload.get("coordinate_profile"), dict) else {}
    coordinate_space = (
        source_profile.get("space")
        if isinstance(source_profile.get("space"), dict)
        else {"origin": coordinate_origin, "unit": "logical_px", "scale": None}
    )
    source_size = {"width": 0, "height": 0}
    if "diagnostics" in locals() and isinstance(diagnostics.get("source_size"), dict):
        source_size = dict(diagnostics["source_size"])
    if not source_profile:
        source_profile = build_coordinate_profile(
            source_kind=coordinate_origin,
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region_payload if "region_payload" in locals() else region if isinstance(region, dict) else None,
            screen_clickable=coordinate_origin not in {"source_path", "image", "offline_image"},
        )
    coordinate_diagnostics = _coordinate_diagnostics(
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region_payload if "region_payload" in locals() else region if isinstance(region, dict) else None,
        coordinate_profile=source_profile,
    )
    target_candidates = build_vision_targeting(
        desktop=desktop,
        vision_type="locate_image",
        template_path=str(template_path),
        source_target=str(source_payload.get("source_target", "")),
        source_bounds=source_bounds,
        coordinate_profile=source_profile,
        coordinate_diagnostics=coordinate_diagnostics,
        target_query=source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        locator=source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        matches=matches if "matches" in locals() else [],
        selected_match=selected or {},
    )
    payload = {
        "ok": selected is not None,
        "action": "desktop_vision",
        "type": "locate_image",
        "desktop": desktop,
        "source_target": str(source_payload.get("source_target", "")),
        "template_path": str(template_path),
        "source_path": str(source_path),
        "threshold": threshold,
        "match_index": match_index,
        "max_matches": max_matches,
        "coordinate_space": coordinate_space,
        "coordinate_profile": source_profile,
        "coordinate_diagnostics": coordinate_diagnostics,
        "source_bounds": source_bounds,
        "region": region_payload if "region_payload" in locals() else region or {},
        "target_query": source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        "locator": source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        "window": source_payload.get("window") if isinstance(source_payload.get("window"), dict) else {},
        "element": source_payload.get("element") if isinstance(source_payload.get("element"), dict) else {},
        "matches": matches if "matches" in locals() else [],
        "match": selected or {},
        "target_candidates": target_candidates,
        "artifacts": {
            "json_path": str(output_path),
            "json_relative_path": _output_relative_path(output_path),
            "source_path": str(artifacts["source"]),
            "source_relative_path": _output_relative_path(artifacts["source"]),
            "crop_path": str(artifacts["crop"]) if selected is not None else "",
            "crop_relative_path": _output_relative_path(artifacts["crop"]) if selected is not None else "",
            "annotation_path": str(artifacts["annotation"]) if selected is not None else "",
            "annotation_relative_path": _output_relative_path(artifacts["annotation"]) if selected is not None else "",
        },
        "diagnostics": diagnostics if "diagnostics" in locals() else {},
        "source": source_payload,
        "elapsed_ms": _elapsed_ms(started),
    }
    return payload


def _locate_text_in_source(
    *,
    source_path: Path,
    output_path: Path,
    artifacts: dict[str, Path],
    region: dict[str, Any] | None,
    match_query: dict[str, str],
    language: str,
    provider: str,
    min_confidence: float,
    case_sensitive: bool,
    match_index: int,
    max_matches: int,
    coordinate_origin: str,
    started: float,
    source_payload: dict[str, Any],
    source_bounds: dict[str, int],
    desktop: str,
    desktop_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except Exception as error:
        raise DesktopBackendError("desktop_vision.locate_text 需要 Pillow。") from error

    with Image.open(source_path) as raw_source:
        source_image = raw_source.convert("RGB")
        search_image, region_payload = _desktop_vision_search_image(source_image, region)
        raw_text, local_blocks, diagnostics = _desktop_vision_ocr_blocks(
            search_image,
            language=language,
            provider=provider,
            region=region_payload,
            desktop_config=desktop_config,
        )
        ocr_blocks = _desktop_vision_global_matches(local_blocks, source_bounds)
        local_matches = _desktop_vision_text_matches(
            local_blocks,
            match_query=match_query,
            min_confidence=min_confidence,
            max_matches=max_matches,
            case_sensitive=case_sensitive,
        )
        matches = _desktop_vision_global_matches(local_matches, source_bounds)
        local_selected = local_matches[match_index] if 0 <= match_index < len(local_matches) else None
        selected = matches[match_index] if 0 <= match_index < len(matches) else None
        if local_selected is not None:
            _save_desktop_vision_crop(source_image, local_selected["bounds"], artifacts["crop"])
            _save_desktop_vision_annotation(source_image, local_matches, local_selected, artifacts["annotation"])

    source_profile = source_payload.get("coordinate_profile") if isinstance(source_payload.get("coordinate_profile"), dict) else {}
    coordinate_space = (
        source_profile.get("space")
        if isinstance(source_profile.get("space"), dict)
        else {"origin": coordinate_origin, "unit": "logical_px", "scale": None}
    )
    source_size = {"width": int(source_image.width), "height": int(source_image.height)}
    if not source_profile:
        source_profile = build_coordinate_profile(
            source_kind=coordinate_origin,
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region_payload,
            screen_clickable=coordinate_origin not in {"source_path", "image", "offline_image"},
        )
    coordinate_diagnostics = _coordinate_diagnostics(
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region_payload,
        coordinate_profile=source_profile,
    )
    target_candidates = build_vision_targeting(
        desktop=desktop,
        vision_type="locate_text",
        match_query=match_query,
        source_target=str(source_payload.get("source_target", "")),
        source_bounds=source_bounds,
        coordinate_profile=source_profile,
        coordinate_diagnostics=coordinate_diagnostics,
        target_query=source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        locator=source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        matches=matches,
        selected_match=selected or {},
    )
    payload = {
        "ok": selected is not None,
        "action": "desktop_vision",
        "type": "locate_text",
        "desktop": desktop,
        "source_target": str(source_payload.get("source_target", "")),
        "source_path": str(source_path),
        "match_query": match_query,
        "language": language,
        "provider": diagnostics.get("provider", provider),
        "min_confidence": min_confidence,
        "case_sensitive": case_sensitive,
        "match_index": match_index,
        "max_matches": max_matches,
        "raw_text": raw_text,
        "ocr_blocks": ocr_blocks,
        "coordinate_space": coordinate_space,
        "coordinate_profile": source_profile,
        "coordinate_diagnostics": coordinate_diagnostics,
        "source_bounds": source_bounds,
        "region": region_payload,
        "target_query": source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        "locator": source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        "window": source_payload.get("window") if isinstance(source_payload.get("window"), dict) else {},
        "element": source_payload.get("element") if isinstance(source_payload.get("element"), dict) else {},
        "matches": matches,
        "match": selected or {},
        "target_candidates": target_candidates,
        "artifacts": {
            "json_path": str(output_path),
            "json_relative_path": _output_relative_path(output_path),
            "source_path": str(artifacts["source"]),
            "source_relative_path": _output_relative_path(artifacts["source"]),
            "crop_path": str(artifacts["crop"]) if selected is not None else "",
            "crop_relative_path": _output_relative_path(artifacts["crop"]) if selected is not None else "",
            "annotation_path": str(artifacts["annotation"]) if selected is not None else "",
            "annotation_relative_path": _output_relative_path(artifacts["annotation"]) if selected is not None else "",
        },
        "diagnostics": {
            **diagnostics,
            "candidate_count": len(matches),
            "ocr_block_count": len(ocr_blocks),
            "source_size": source_size,
            "match_query": match_query,
            "min_confidence": min_confidence,
        },
        "source": source_payload,
        "elapsed_ms": _elapsed_ms(started),
    }
    return payload


def _desktop_vision_ocr_blocks(
    image: Any,
    *,
    language: str,
    provider: str,
    region: dict[str, int],
    desktop_config: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    normalized_provider = "tesseract" if provider == "auto" else provider
    if normalized_provider != "tesseract":
        raise DesktopBackendError(f"desktop_vision.locate_text 不支持的 OCR provider：{provider}")
    tsv_text, diagnostics = _run_tesseract_tsv(image, language=language, desktop_config=desktop_config)
    word_blocks = _parse_tesseract_tsv_words(tsv_text, region=region)
    line_blocks = _merge_ocr_words_to_lines(word_blocks)
    raw_text = "\n".join(str(block.get("text", "")) for block in line_blocks if block.get("text"))
    diagnostics.update(
        {
            "provider": "tesseract",
            "language": language,
            "word_count": len(word_blocks),
            "line_count": len(line_blocks),
        }
    )
    return raw_text, line_blocks, diagnostics


def _run_tesseract_tsv(
    image: Any,
    *,
    language: str,
    desktop_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    tesseract_details = tesseract_binary_details(desktop_config)
    binary = resolve_tesseract_binary(desktop_config)
    if not binary:
        source = str(tesseract_details.get("source") or "PATH")
        configured_path = str(tesseract_details.get("configured_path") or "")
        configured_detail = f" 配置路径：{configured_path}" if configured_path else ""
        raise DesktopBackendError(
            "desktop_vision.locate_text 需要系统可执行的 tesseract 命令；"
            "请安装 Tesseract、加入 PATH，或在 config.json 的 desktop.ocr.tesseract_path 指定路径。"
            f" 当前探测来源：{source}.{configured_detail}"
        )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        image.save(temp_path)
        completed = subprocess.run(
            [
                binary,
                str(temp_path),
                "stdout",
                *tesseract_common_options(desktop_config),
                "-l",
                language,
                "--psm",
                "6",
                "tsv",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise DesktopBackendError(f"desktop_vision.locate_text OCR 失败：{message}")
    return completed.stdout, {
        "method": "tesseract.tsv",
        "tesseract_path": binary,
        "tesseract_source": str(tesseract_details.get("source") or ""),
        "configured_tesseract_path": str(tesseract_details.get("configured_path") or ""),
        "tessdata_dir": str(tesseract_details.get("tessdata_dir") or ""),
        "engine_version": _tesseract_version(binary),
    }


def _tesseract_version(binary: str) -> str:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    first_line = (completed.stdout or completed.stderr or "").splitlines()
    return first_line[0].strip() if first_line else ""


def _parse_tesseract_tsv_words(tsv_text: str, *, region: dict[str, int]) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    words: list[dict[str, Any]] = []
    for row in reader:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        confidence = _ocr_confidence(row.get("conf"))
        if confidence < 0:
            continue
        try:
            left = int(float(row.get("left", 0) or 0))
            top = int(float(row.get("top", 0) or 0))
            width = int(float(row.get("width", 0) or 0))
            height = int(float(row.get("height", 0) or 0))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        local_x = int(region.get("x", 0)) + left
        local_y = int(region.get("y", 0)) + top
        bounds = {"x": local_x, "y": local_y, "width": width, "height": height}
        words.append(
            {
                "index": len(words),
                "level": "word",
                "text": text,
                "confidence": confidence,
                "score": confidence,
                "bounds": bounds,
                "point": {"x": local_x + width // 2, "y": local_y + height // 2},
                "line_key": (
                    str(row.get("page_num", "")),
                    str(row.get("block_num", "")),
                    str(row.get("par_num", "")),
                    str(row.get("line_num", "")),
                ),
            }
        )
    return words


def _merge_ocr_words_to_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for word in words:
        grouped.setdefault(tuple(word.get("line_key", ("", "", "", ""))), []).append(word)
    lines: list[dict[str, Any]] = []
    for key, line_words in grouped.items():
        sorted_words = sorted(line_words, key=lambda item: (int(item.get("bounds", {}).get("y", 0)), int(item.get("bounds", {}).get("x", 0))))
        bounds = _union_bounds([word.get("bounds", {}) for word in sorted_words])
        confidence_values = [float(word.get("confidence", 0.0) or 0.0) for word in sorted_words]
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        text = " ".join(str(word.get("text", "")) for word in sorted_words if word.get("text"))
        point = {"x": bounds["x"] + bounds["width"] // 2, "y": bounds["y"] + bounds["height"] // 2}
        lines.append(
            {
                "index": len(lines),
                "level": "line",
                "line_key": list(key),
                "text": text,
                "confidence": confidence,
                "score": confidence,
                "bounds": bounds,
                "point": point,
                "words": [
                    {
                        "text": str(word.get("text", "")),
                        "confidence": float(word.get("confidence", 0.0) or 0.0),
                        "bounds": dict(word.get("bounds", {})),
                    }
                    for word in sorted_words
                ],
            }
        )
    return lines


def _desktop_vision_text_matches(
    blocks: list[dict[str, Any]],
    *,
    match_query: dict[str, str],
    min_confidence: float,
    max_matches: int,
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for block in blocks:
        confidence = float(block.get("confidence", 0.0) or 0.0)
        if confidence < min_confidence:
            continue
        if not _text_query_matches(str(block.get("text", "")), match_query, case_sensitive=case_sensitive):
            continue
        match = dict(block)
        match["index"] = len(matches)
        match["block_index"] = block.get("index")
        match["match_query"] = dict(match_query)
        match["score"] = confidence
        matches.append(match)
        if len(matches) >= max(1, max_matches):
            break
    return matches


def _text_query_matches(text: str, match_query: dict[str, str], *, case_sensitive: bool) -> bool:
    actual = text if case_sensitive else text.casefold()
    if "text" in match_query:
        expected = match_query["text"] if case_sensitive else match_query["text"].casefold()
        return actual == expected
    if "text_contains" in match_query:
        expected = match_query["text_contains"] if case_sensitive else match_query["text_contains"].casefold()
        return expected in actual
    if "text_regex" in match_query:
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(match_query["text_regex"], text, flags=flags) is not None
    return False


def _ocr_confidence(raw_confidence: Any) -> float:
    try:
        value = float(raw_confidence)
    except (TypeError, ValueError):
        return -1.0
    if value < 0:
        return -1.0
    return max(0.0, min(1.0, value / 100.0))


def _union_bounds(bounds_list: list[dict[str, Any]]) -> dict[str, int]:
    normalized = [
        {
            "x": int(bounds.get("x", 0) or 0),
            "y": int(bounds.get("y", 0) or 0),
            "width": int(bounds.get("width", 0) or 0),
            "height": int(bounds.get("height", 0) or 0),
        }
        for bounds in bounds_list
        if isinstance(bounds, dict)
    ]
    if not normalized:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    left = min(bounds["x"] for bounds in normalized)
    top = min(bounds["y"] for bounds in normalized)
    right = max(bounds["x"] + bounds["width"] for bounds in normalized)
    bottom = max(bounds["y"] + bounds["height"] for bounds in normalized)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _desktop_vision_search_image(source_image: Any, region: dict[str, Any] | None) -> tuple[Any, dict[str, int]]:
    if not region:
        return source_image, {"x": 0, "y": 0, "width": int(source_image.width), "height": int(source_image.height)}
    x = int(region.get("x", 0))
    y = int(region.get("y", 0))
    width = int(region.get("width", 0))
    height = int(region.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(f"desktop_vision.region 无效：{region}")
    if x < 0 or y < 0 or x + width > source_image.width or y + height > source_image.height:
        raise ValueError(
            "desktop_vision.region 超出截图范围："
            f"region={region} source={source_image.width}x{source_image.height}"
        )
    return source_image.crop((x, y, x + width, y + height)), {"x": x, "y": y, "width": width, "height": height}


def _desktop_vision_template_matches(
    result: Any,
    *,
    threshold: float,
    max_matches: int,
    template_width: int,
    template_height: int,
    region: dict[str, int],
) -> list[dict[str, Any]]:
    import cv2

    matches: list[dict[str, Any]] = []
    working = result.copy()
    normalized_threshold = float(threshold)
    for _ in range(max(1, max_matches)):
        _min_value, max_value, _min_location, max_location = cv2.minMaxLoc(working)
        score = float(max_value)
        if score < normalized_threshold:
            break
        local_x, local_y = int(max_location[0]), int(max_location[1])
        x = int(region["x"]) + local_x
        y = int(region["y"]) + local_y
        bounds = {"x": x, "y": y, "width": int(template_width), "height": int(template_height)}
        matches.append(
            {
                "index": len(matches),
                "score": score,
                "confidence": score,
                "bounds": bounds,
                "point": {"x": x + int(template_width) // 2, "y": y + int(template_height) // 2},
            }
        )
        suppress_left = max(0, local_x - int(template_width) // 2)
        suppress_top = max(0, local_y - int(template_height) // 2)
        suppress_right = min(working.shape[1], local_x + int(template_width) // 2 + 1)
        suppress_bottom = min(working.shape[0], local_y + int(template_height) // 2 + 1)
        working[suppress_top:suppress_bottom, suppress_left:suppress_right] = -1
    return matches


def _desktop_vision_global_matches(
    local_matches: list[dict[str, Any]],
    source_bounds: dict[str, int],
    *,
    coordinate_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    mapper = CoordinateMapper.from_profile(coordinate_profile or build_coordinate_profile(source_bounds=source_bounds))
    matches: list[dict[str, Any]] = []
    for match in local_matches:
        local_bounds = match.get("bounds") if isinstance(match.get("bounds"), dict) else {}
        local_point = match.get("point") if isinstance(match.get("point"), dict) else {}
        bounds = mapper.local_to_screen_bounds(local_bounds)
        point = mapper.local_to_screen_point(local_point)
        matches.append({**match, "local_bounds": dict(local_bounds), "local_point": dict(local_point), "bounds": bounds, "point": point})
    return matches


def _save_desktop_vision_crop(source_image: Any, bounds: dict[str, Any], path: Path) -> None:
    x = int(bounds["x"])
    y = int(bounds["y"])
    width = int(bounds["width"])
    height = int(bounds["height"])
    path.parent.mkdir(parents=True, exist_ok=True)
    source_image.crop((x, y, x + width, y + height)).save(path)


def _save_desktop_vision_annotation(source_image: Any, matches: list[dict[str, Any]], selected: dict[str, Any], path: Path) -> None:
    from PIL import ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    annotated = source_image.copy()
    draw = ImageDraw.Draw(annotated)
    for match in matches:
        bounds = match.get("bounds", {})
        try:
            x = int(bounds.get("x", 0))
            y = int(bounds.get("y", 0))
            width = int(bounds.get("width", 0))
            height = int(bounds.get("height", 0))
        except (TypeError, ValueError):
            continue
        color = (255, 64, 64) if match is selected else (64, 128, 255)
        draw.rectangle((x, y, x + width, y + height), outline=color, width=3)
        draw.text((x + 4, y + 4), f"{match.get('index', '')}:{float(match.get('score', 0.0)):.3f}", fill=color)
    point = selected.get("point", {}) if isinstance(selected.get("point"), dict) else {}
    if point:
        x = int(point.get("x", 0))
        y = int(point.get("y", 0))
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), outline=(255, 64, 64), width=4)
    annotated.save(path)


def _output_relative_path(path: Path) -> str:
    parts = path.parts
    if "output" in parts:
        index = len(parts) - 1 - list(reversed(parts)).index("output")
        return str(Path(*parts[index + 1 :]))
    return path.name


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
