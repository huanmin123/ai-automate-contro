from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop import DesktopSession
from ai_automate_contro.engine.desktop.annotations import capture_pointer_annotation
from ai_automate_contro.engine.desktop.backends import DesktopBackendError, NativeDesktopBackend


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


def open_desktop(executor: Any, step: dict[str, Any]) -> None:
    name = str(step["name"])
    if name in executor.state.desktop_sessions:
        raise ValueError(f"桌面会话已存在：{name}")
    platform_name = _resolve_platform_name(str(step.get("platform", "auto")))
    backend_name = str(step.get("backend", "auto"))
    backend = _create_backend(platform_name=platform_name, backend_name=backend_name)
    started = time.monotonic()
    probe = backend.probe(request_permissions=bool(step.get("request_permissions", False)))
    capability_matrix = probe.get("capability_matrix") if isinstance(probe.get("capability_matrix"), dict) else {}
    session = DesktopSession(
        name=name,
        backend=backend,
        platform=platform_name,
        backend_name=backend.backend_name,
        permissions=dict(probe.get("permissions", {})) if isinstance(probe.get("permissions"), dict) else {},
        capability_matrix=dict(capability_matrix),
    )
    executor.state.desktop_sessions[name] = session
    payload = {
        "ok": True,
        "desktop": name,
        "platform": platform_name,
        "backend": backend.backend_name,
        "probe": probe,
        "capability_matrix": capability_matrix,
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
    payload = {
        **payload,
        "desktop": session.name,
        "type": app_type,
        "elapsed_ms": _elapsed_ms(started),
    }
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
    window_type = str(step["type"])
    started = time.monotonic()
    if window_type == "list":
        windows = session.backend.list_windows(include_invisible=bool(step.get("include_invisible", False)))
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": window_type,
            "count": len(windows),
            "windows": windows,
            "elapsed_ms": _elapsed_ms(started),
        }
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-windows")
            _write_json(output_path, payload)
            payload["path"] = str(output_path)
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
        _write_json(output_path, payload)
        payload["path"] = str(output_path)
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
    input_type = str(step["type"])
    started = time.monotonic()
    annotation_points: list[dict[str, Any]] = []
    annotation_bounds: list[dict[str, Any]] = []
    annotation_target: dict[str, Any] = {}
    annotation_connect = False
    if input_type == "type_text":
        payload = session.backend.type_text(
            str(step["value"]),
            method=str(step.get("method", "auto")),
            delay_ms=int(step.get("delay_ms", 0)),
            preserve_clipboard=bool(step.get("preserve_clipboard", True)),
        )
    elif input_type == "hotkey":
        payload = session.backend.hotkey([str(key) for key in step["keys"]])
    elif input_type == "click":
        x, y, target = _resolve_input_coordinates(session, step, action_label="click")
        payload = session.backend.click(
            x=x,
            y=y,
            button=str(step.get("button", "left")),
            clicks=int(step.get("clicks", 1)),
            interval_ms=int(step.get("interval_ms", 0)),
        )
        if target:
            payload["target"] = target
        annotation_points = [_annotation_point(x, y, "click")]
        annotation_bounds = _input_annotation_bounds(session, step, target)
        annotation_target = _input_annotation_target(step, target=target)
    elif input_type == "double_click":
        x, y, target = _resolve_input_coordinates(session, step, action_label="double_click")
        payload = session.backend.double_click(
            x=x,
            y=y,
            interval_ms=int(step.get("interval_ms", 0)),
        )
        if target:
            payload["target"] = target
        annotation_points = [_annotation_point(x, y, "double_click")]
        annotation_bounds = _input_annotation_bounds(session, step, target)
        annotation_target = _input_annotation_target(step, target=target)
    elif input_type == "right_click":
        x, y, target = _resolve_input_coordinates(session, step, action_label="right_click")
        payload = session.backend.right_click(x=x, y=y)
        if target:
            payload["target"] = target
        annotation_points = [_annotation_point(x, y, "right_click")]
        annotation_bounds = _input_annotation_bounds(session, step, target)
        annotation_target = _input_annotation_target(step, target=target)
    elif input_type == "scroll":
        x, y, target = _resolve_input_coordinates(session, step, action_label="scroll")
        payload = session.backend.scroll(x=x, y=y, amount=int(step["amount"]))
        if target:
            payload["target"] = target
        annotation_points = [_annotation_point(x, y, "scroll")]
        annotation_bounds = _input_annotation_bounds(session, step, target)
        annotation_target = _input_annotation_target(step, target=target)
    elif input_type == "drag":
        start_x, start_y, end_x, end_y, target = _resolve_drag_coordinates(session, step)
        payload = session.backend.drag(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            button=str(step.get("button", "left")),
            duration_ms=int(step.get("duration_ms", 0)),
        )
        if target:
            payload["target"] = target
        annotation_points = [_annotation_point(start_x, start_y, "start"), _annotation_point(end_x, end_y, "end")]
        annotation_bounds = _input_annotation_bounds(session, step, target)
        annotation_target = _input_annotation_target(step, target=target)
        annotation_connect = True
    else:
        raise ValueError(f"不支持的 desktop_input.type：{input_type}")
    payload = {
        **payload,
        "desktop": session.name,
        "type": input_type,
        "elapsed_ms": _elapsed_ms(started),
    }
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
        payload = {
            **payload,
            "target": target,
            "source_bounds": source_bounds,
            "coordinate_space": {"origin": "screen", "unit": "logical_px", "scale": None},
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
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": capture_type,
            "path": str(output_path),
            "current_window": session.current_window or {},
            "capability_matrix": capability_matrix,
            "snapshot": payload,
            "elapsed_ms": _elapsed_ms(started),
        }
        _write_json(output_path, payload)
    else:
        raise ValueError(f"不支持的 desktop_capture.type：{capture_type}")
    payload = {
        **payload,
        "desktop": session.name,
        "type": capture_type,
        "elapsed_ms": _elapsed_ms(started),
    }
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload
    executor.state.logger.log(
        "info",
        "desktop capture saved",
        desktop=session.name,
        type=capture_type,
        path=payload.get("path", str(output_path)),
    )


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
        return "window", region, {"target_query": query, "window": window, "locator": {}}
    if raw_target == "element":
        if explicit_region:
            raise ValueError("desktop_capture.screenshot target=element 不能同时使用 region。")
        query = _window_query(step)
        locator = _element_locator(step)
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
        return "element", region, {"target_query": query, "locator": locator, "window": window, "element": element}
    raise ValueError(f"不支持的 desktop_capture.screenshot target：{raw_target}")


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
    vision_type = str(step["type"])
    if vision_type != "locate_image":
        raise ValueError(f"不支持的 desktop_vision.type：{vision_type}")
    started = time.monotonic()
    output_path = executor._resolve_output_path(step["path"], category="desktop-vision")
    template_path = executor._resolve_path(str(step["template_path"]))
    source_input_path = executor._resolve_path(str(step["source_path"])) if step.get("source_path") else None
    if source_input_path is not None and step.get("source_target"):
        raise ValueError("desktop_vision.locate_image 不能同时使用 source_path 和 source_target。")
    threshold = float(step.get("threshold", 0.85))
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
        last_payload = payload
        if payload.get("ok"):
            break
        if source_input_path is not None or time.monotonic() >= deadline:
            _write_json(output_path, payload)
            raise TimeoutError(
                "desktop_vision.locate_image 未找到匹配图像："
                f"template_path={template_path} threshold={threshold} match_index={match_index}"
            )
        time.sleep(max(0.001, interval_ms / 1000))

    _write_json(output_path, last_payload)
    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = last_payload
    executor.state.logger.log(
        "info",
        "desktop image located",
        desktop=session.name,
        path=str(output_path),
        score=last_payload.get("match", {}).get("score", ""),
        save_as=step.get("save_as", ""),
    )


def desktop_wait(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
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
        if expected_text is not None:
            mode = str(step.get("mode", "equals"))
            _assert_text(actual_text, str(expected_text), mode=mode)
            text_assertion = {
                "expected": str(expected_text),
                "actual": actual_text,
                "mode": mode,
                "text_source": text_source,
            }
        payload = {
            **payload,
            "ok": True,
            "desktop": session.name,
            "type": assert_type,
            "query": query,
            "locator": locator,
            "state": expected_state,
            "text_assertion": text_assertion,
            "elapsed_ms": _elapsed_ms(started),
        }
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        if window:
            session.current_window = dict(window)
        if "path" in step:
            output_path = executor._resolve_output_path(step["path"], category="desktop-elements")
            _write_json(output_path, payload)
            payload["path"] = str(output_path)
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
                "target_query": {},
                "locator": {},
            }
        return source_artifact_path, payload, source_bounds, "image"

    source_target = raw_source_target or "screen"
    if source_target not in {"screen", "window", "element"}:
        raise ValueError(f"不支持的 desktop_vision.locate_image source_target：{source_target}")
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
    payload = {
        **payload,
        "source": "desktop_screenshot",
        "source_target": source_target,
        "window_match_index": step.get("window_match_index", ""),
        "source_bounds": source_bounds,
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
        "coordinate_space": {"origin": coordinate_origin, "unit": "logical_px", "scale": None},
        "source_bounds": source_bounds,
        "region": region_payload if "region_payload" in locals() else region or {},
        "target_query": source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        "locator": source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        "window": source_payload.get("window") if isinstance(source_payload.get("window"), dict) else {},
        "element": source_payload.get("element") if isinstance(source_payload.get("element"), dict) else {},
        "matches": matches if "matches" in locals() else [],
        "match": selected or {},
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
) -> list[dict[str, Any]]:
    origin_x = int(source_bounds.get("x", 0) or 0)
    origin_y = int(source_bounds.get("y", 0) or 0)
    matches: list[dict[str, Any]] = []
    for match in local_matches:
        local_bounds = match.get("bounds") if isinstance(match.get("bounds"), dict) else {}
        local_point = match.get("point") if isinstance(match.get("point"), dict) else {}
        bounds = {
            "x": origin_x + int(local_bounds.get("x", 0) or 0),
            "y": origin_y + int(local_bounds.get("y", 0) or 0),
            "width": int(local_bounds.get("width", 0) or 0),
            "height": int(local_bounds.get("height", 0) or 0),
        }
        point = {
            "x": origin_x + int(local_point.get("x", 0) or 0),
            "y": origin_y + int(local_point.get("y", 0) or 0),
        }
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


def _create_backend(*, platform_name: str, backend_name: str) -> NativeDesktopBackend:
    if platform_name not in {"windows", "macos"}:
        raise DesktopBackendError(f"桌面控制 Phase 0 仅支持 Windows 和 macOS：{platform_name}")
    current = _current_platform_name()
    if platform_name != current:
        raise DesktopBackendError(f"当前系统是 {current}，不能打开 platform={platform_name} 的桌面会话。")
    if backend_name in {"auto", "native"}:
        return NativeDesktopBackend(platform_name=platform_name)
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
    query = {field: step[field] for field in WINDOW_QUERY_FIELDS if field in step and step[field] not in (None, "")}
    if not any(field in query for field in WINDOW_QUERY_FIELDS - {"match_index"}):
        raise ValueError("窗口操作需要至少一种窗口定位字段。")
    return query


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


def _resolve_input_coordinates(
    session: DesktopSession,
    step: dict[str, Any],
    *,
    action_label: str,
) -> tuple[int, int, str]:
    if "x" in step and "y" in step:
        return (
            _coordinate(step["x"], field="x", action_label=action_label),
            _coordinate(step["y"], field="y", action_label=action_label),
            "",
        )
    target = str(step.get("target", ""))
    if target in {"current_window_center", "focused_window_center"}:
        return (*_bounds_center(_current_window_bounds(session, target, action_label), action_label=action_label), target)
    if target in {"current_window_offset", "focused_window_offset"}:
        bounds = _current_window_bounds(session, target, action_label)
        x = _coordinate(bounds.get("x", 0), field="bounds.x", action_label=action_label)
        y = _coordinate(bounds.get("y", 0), field="bounds.y", action_label=action_label)
        offset_x = _coordinate(step.get("offset_x", 0), field="offset_x", action_label=action_label)
        offset_y = _coordinate(step.get("offset_y", 0), field="offset_y", action_label=action_label)
        return x + offset_x, y + offset_y, target
    if target == "bounds_center":
        bounds = step.get("bounds")
        if not isinstance(bounds, dict):
            raise ValueError(f"desktop_input.{action_label} target=bounds_center 需要 bounds 对象。")
        return (*_bounds_center(bounds, action_label=action_label), target)
    if target == "element_center":
        query = _window_query(step)
        locator = _element_locator(step)
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
        return (*_bounds_center(bounds, action_label=action_label), target)
    raise ValueError(f"desktop_input.{action_label} 需要 target 或 x/y")


def _resolve_drag_coordinates(session: DesktopSession, step: dict[str, Any]) -> tuple[int, int, int, int, str]:
    if "target" in step:
        start_x, start_y, target = _resolve_input_coordinates(session, step, action_label="drag")
        delta_x = _coordinate(step.get("delta_x", 0), field="delta_x", action_label="drag")
        delta_y = _coordinate(step.get("delta_y", 0), field="delta_y", action_label="drag")
        return start_x, start_y, start_x + delta_x, start_y + delta_y, target
    required = ("start_x", "start_y", "end_x", "end_y")
    if not all(field in step for field in required):
        raise ValueError("desktop_input.drag 需要 target+delta_x/delta_y 或 start_x/start_y/end_x/end_y")
    return (
        _coordinate(step["start_x"], field="start_x", action_label="drag"),
        _coordinate(step["start_y"], field="start_y", action_label="drag"),
        _coordinate(step["end_x"], field="end_x", action_label="drag"),
        _coordinate(step["end_y"], field="end_y", action_label="drag"),
        "",
    )


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


def _input_annotation_bounds(session: DesktopSession, step: dict[str, Any], target: str) -> list[dict[str, Any]]:
    if target in {"current_window_center", "focused_window_center", "current_window_offset", "focused_window_offset"}:
        window = session.current_window or {}
        bounds = window.get("bounds") if isinstance(window, dict) else None
        return [dict(bounds)] if isinstance(bounds, dict) else []
    if target == "bounds_center" and isinstance(step.get("bounds"), dict):
        return [dict(step["bounds"])]
    return []


def _input_annotation_target(step: dict[str, Any], *, target: str) -> dict[str, Any]:
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
    )
    payload = {field: step[field] for field in fields if field in step and step[field] not in (None, "")}
    if target:
        payload["resolved_target"] = target
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
