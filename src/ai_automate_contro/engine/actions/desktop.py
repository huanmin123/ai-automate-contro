from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop import DesktopSession
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


def open_desktop(executor: Any, step: dict[str, Any]) -> None:
    name = str(step["name"])
    if name in executor.state.desktop_sessions:
        raise ValueError(f"桌面会话已存在：{name}")
    platform_name = _resolve_platform_name(str(step.get("platform", "auto")))
    backend_name = str(step.get("backend", "auto"))
    backend = _create_backend(platform_name=platform_name, backend_name=backend_name)
    started = time.monotonic()
    probe = backend.probe(request_permissions=bool(step.get("request_permissions", False)))
    session = DesktopSession(
        name=name,
        backend=backend,
        platform=platform_name,
        backend_name=backend.backend_name,
        permissions=dict(probe.get("permissions", {})) if isinstance(probe.get("permissions"), dict) else {},
    )
    executor.state.desktop_sessions[name] = session
    payload = {
        "ok": True,
        "desktop": name,
        "platform": platform_name,
        "backend": backend.backend_name,
        "probe": probe,
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
    raise ValueError(f"不支持的 desktop_window.type：{window_type}")


def desktop_input(executor: Any, step: dict[str, Any]) -> None:
    session = executor.state.require_desktop_session(str(step["desktop"]))
    input_type = str(step["type"])
    started = time.monotonic()
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
        x, y, target = _resolve_click_coordinates(session, step)
        payload = session.backend.click(
            x=x,
            y=y,
            button=str(step.get("button", "left")),
            clicks=int(step.get("clicks", 1)),
            interval_ms=int(step.get("interval_ms", 0)),
        )
        if target:
            payload["target"] = target
    else:
        raise ValueError(f"不支持的 desktop_input.type：{input_type}")
    payload = {
        **payload,
        "desktop": session.name,
        "type": input_type,
        "elapsed_ms": _elapsed_ms(started),
    }
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
        payload = session.backend.screenshot(
            output_path,
            region=step.get("region") if isinstance(step.get("region"), dict) else None,
            include_cursor=bool(step.get("include_cursor", False)),
        )
    elif capture_type == "snapshot":
        output_path = executor._resolve_output_path(step["path"], category="desktop-state")
        payload = session.backend.snapshot(
            include_windows=bool(step.get("include_windows", True)),
            include_displays=bool(step.get("include_displays", True)),
        )
        payload = {
            "ok": True,
            "desktop": session.name,
            "type": capture_type,
            "path": str(output_path),
            "current_window": session.current_window or {},
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

    raise ValueError(f"不支持的 desktop_assert.type：{assert_type}")


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


def _resolve_click_coordinates(session: DesktopSession, step: dict[str, Any]) -> tuple[int, int, str]:
    if "x" in step and "y" in step:
        return _coordinate(step["x"], field="x"), _coordinate(step["y"], field="y"), ""
    target = str(step.get("target", ""))
    if target in {"current_window_center", "focused_window_center"}:
        window = session.current_window or {}
        bounds = window.get("bounds") if isinstance(window, dict) else None
        if not isinstance(bounds, dict):
            raise ValueError(f"desktop_input.click target={target} 需要先聚焦或等待到带 bounds 的窗口。")
        x = _coordinate(bounds.get("x", 0), field="bounds.x")
        y = _coordinate(bounds.get("y", 0), field="bounds.y")
        width = _coordinate(bounds.get("width", 0), field="bounds.width")
        height = _coordinate(bounds.get("height", 0), field="bounds.height")
        if width <= 0 or height <= 0:
            raise ValueError(f"desktop_input.click target={target} 的窗口 bounds 无效：{bounds}")
        return x + width // 2, y + height // 2, target
    raise ValueError("desktop_input.click 需要 target 或 x/y")


def _coordinate(value: Any, *, field: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"desktop_input.click {field} 必须是数字：{value!r}") from error


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


ACTION_HANDLERS = {
    "close_desktop": close_desktop,
    "desktop_capture": desktop_capture,
    "desktop_input": desktop_input,
    "desktop_assert": desktop_assert,
    "desktop_wait": desktop_wait,
    "desktop_window": desktop_window,
    "open_desktop": open_desktop,
}
