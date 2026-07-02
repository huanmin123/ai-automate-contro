from __future__ import annotations

import base64
import json
from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output


def network(executor: Any, step: dict[str, Any]) -> None:
    network_type = step["type"]
    session = executor.state.require_session(step["browser"])
    if network_type == "route":
        url = step["url"]
        session.context.route(url, _build_route_handler(executor, step))
        executor.state.logger.log("info", "network route registered", browser=step["browser"], url=url)
        return
    if network_type == "unroute":
        url = step["url"]
        session.context.unroute(url)
        executor.state.logger.log("info", "network route removed", browser=step["browser"], url=url)
        return
    if network_type == "set_extra_http_headers":
        session.context.set_extra_http_headers(step["headers"])
        executor.state.logger.log("info", "extra http headers set", browser=step["browser"])
        return
    if network_type == "route_from_har":
        target = _network_route_target(session, step)
        kwargs: dict[str, Any] = {}
        for field in ("url", "not_found", "update", "update_content", "update_mode"):
            if field in step:
                kwargs[field] = step[field]
        target.route_from_har(str(executor._resolve_path(step["path"])), **kwargs)
        executor.state.logger.log(
            "info",
            "HAR route registered",
            browser=step["browser"],
            path=step["path"],
            scope=step.get("scope", "context"),
        )
        return
    if network_type == "route_web_socket":
        target = _network_route_target(session, step)
        target.route_web_socket(step["url"], _build_websocket_route_handler(executor, step))
        executor.state.logger.log(
            "info",
            "WebSocket route registered",
            browser=step["browser"],
            url=step["url"],
            scope=step.get("scope", "context"),
        )
        return
    raise ValueError(f"不支持的 network type：{network_type}")


def script(executor: Any, step: dict[str, Any]) -> None:
    script_type = step["type"]
    if script_type == "evaluate":
        page = executor._page(step)
        result = page.evaluate(step["js"], step["arg"]) if "arg" in step else page.evaluate(step["js"])
        publish_step_output(executor, step, result, action="script")
        executor.state.logger.log("info", "page script evaluated", output=step.get("output", {}))
        return
    if script_type == "add_init_script":
        session = executor.state.require_session(step["browser"])
        session.context.add_init_script(script=step["js"])
        executor.state.logger.log("info", "init script registered", browser=step["browser"])
        return
    raise ValueError(f"不支持的 script type：{script_type}")


def storage(executor: Any, step: dict[str, Any]) -> None:
    storage_type = step["type"]
    session = executor.state.require_session(step["browser"])
    page = session.require_page(step.get("page"))
    if storage_type == "cookies":
        urls = step.get("urls")
        cookies = session.context.cookies(urls) if urls is not None else session.context.cookies()
        publish_step_output(executor, step, cookies, action="storage")
        executor.state.logger.log("info", "cookies read", browser=step["browser"], output=step.get("output", {}))
        return
    if storage_type == "set_cookies":
        session.context.add_cookies(step["cookies"])
        executor.state.logger.log("info", "cookies set", browser=step["browser"])
        return
    if storage_type == "clear_cookies":
        session.context.clear_cookies()
        executor.state.logger.log("info", "cookies cleared", browser=step["browser"])
        return
    if storage_type == "local_storage":
        value = page.evaluate("(key) => window.localStorage.getItem(key)", step["key"])
        publish_step_output(executor, step, value, action="storage")
        executor.state.logger.log("info", "local storage read", browser=step["browser"], key=step["key"])
        return
    if storage_type == "set_local_storage":
        page.evaluate(
            "([key, value]) => window.localStorage.setItem(key, value)",
            [step["key"], str(step["value"])],
        )
        executor.state.logger.log("info", "local storage set", browser=step["browser"], key=step["key"])
        return
    if storage_type == "remove_local_storage":
        page.evaluate("(key) => window.localStorage.removeItem(key)", step["key"])
        executor.state.logger.log("info", "local storage removed", browser=step["browser"], key=step["key"])
        return
    if storage_type == "clear_local_storage":
        page.evaluate("() => window.localStorage.clear()")
        executor.state.logger.log("info", "local storage cleared", browser=step["browser"])
        return
    if storage_type == "session_storage":
        value = page.evaluate("(key) => window.sessionStorage.getItem(key)", step["key"])
        publish_step_output(executor, step, value, action="storage")
        executor.state.logger.log("info", "session storage read", browser=step["browser"], key=step["key"])
        return
    if storage_type == "set_session_storage":
        page.evaluate(
            "([key, value]) => window.sessionStorage.setItem(key, value)",
            [step["key"], str(step["value"])],
        )
        executor.state.logger.log("info", "session storage set", browser=step["browser"], key=step["key"])
        return
    if storage_type == "remove_session_storage":
        page.evaluate("(key) => window.sessionStorage.removeItem(key)", step["key"])
        executor.state.logger.log("info", "session storage removed", browser=step["browser"], key=step["key"])
        return
    if storage_type == "clear_session_storage":
        page.evaluate("() => window.sessionStorage.clear()")
        executor.state.logger.log("info", "session storage cleared", browser=step["browser"])
        return
    raise ValueError(f"不支持的 storage type：{storage_type}")


def trace(executor: Any, step: dict[str, Any]) -> None:
    trace_type = step["type"]
    session = executor.state.require_session(step["browser"])
    if trace_type == "start":
        session.context.tracing.start(
            screenshots=bool(step.get("screenshots", True)),
            snapshots=bool(step.get("snapshots", True)),
            sources=bool(step.get("sources", True)),
        )
        executor.state.logger.log("info", "trace started", browser=step["browser"])
        return
    if trace_type == "stop":
        output_path = executor._resolve_output_path(step["path"], category="traces")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        session.context.tracing.stop(path=str(output_path))
        executor.state.logger.log("info", "trace saved", browser=step["browser"], path=str(output_path))
        return
    raise ValueError(f"不支持的 trace type：{trace_type}")


def event(executor: Any, step: dict[str, Any]) -> None:
    event_type = step["type"]
    if event_type == "start":
        session = executor.state.require_session(step["browser"])
        page = executor._page(step)
        key = _event_key(step)
        _remove_event_handlers(executor, key)
        executor.state.browser_events[key] = []
        executor.state.browser_event_options[key] = {
            "eventsource": bool(step.get("eventsource", False)),
            "serviceworker": bool(step.get("serviceworker", False)),
            "webrtc": bool(step.get("webrtc", False)),
            "websocket_frames": bool(step.get("websocket_frames", False)),
        }
        if bool(step.get("eventsource", False)):
            _install_eventsource_observer(executor, page)
        if bool(step.get("webrtc", False)):
            _install_webrtc_observer(executor, page, step)
        if bool(step.get("serviceworker", False)):
            _install_serviceworker_observer(executor, key, session.context, page)
        if bool(step.get("console", True)):
            _add_event_handler(
                executor,
                key,
                page,
                "console",
                lambda message, event_key=key: _record_console(executor, event_key, message),
            )
        if bool(step.get("pageerror", True)):
            _add_event_handler(
                executor,
                key,
                page,
                "pageerror",
                lambda error, event_key=key: _record_page_error(executor, event_key, error),
            )
        if bool(step.get("requestfailed", True)):
            _add_event_handler(
                executor,
                key,
                page,
                "requestfailed",
                lambda request, event_key=key: _record_request_failed(executor, event_key, request),
            )
        if bool(step.get("websocket", True)):
            _add_event_handler(
                executor,
                key,
                page,
                "websocket",
                lambda websocket, event_key=key, include_frames=bool(
                    step.get("websocket_frames", False)
                ): _record_websocket(executor, event_key, websocket, include_frames=include_frames),
            )
        executor.state.logger.log("info", "browser event capture started", browser=step["browser"], key=key)
        return
    if event_type == "stop":
        page = executor._page(step)
        key = _event_key(step)
        event_options = executor.state.browser_event_options.get(key, {})
        if bool(event_options.get("eventsource", False)):
            _collect_eventsource_events(executor, key, page)
        if bool(event_options.get("webrtc", False)):
            _collect_browser_observer_events(executor, key, page, "__aiAutomateWebRTCEvents")
        if bool(event_options.get("serviceworker", False)):
            _collect_browser_observer_events(executor, key, page, "__aiAutomateServiceWorkerEvents")
        output_path = executor._resolve_output_path(step["path"], category="json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(executor.state.browser_events.get(key, []), file, ensure_ascii=False, indent=2)
        publish_step_output(executor, step, executor.state.browser_events.get(key, []), action="event")
        _remove_event_handlers(executor, key)
        executor.state.browser_event_options.pop(key, None)
        executor.state.logger.log("info", "browser event capture saved", browser=step["browser"], path=str(output_path))
        return
    if event_type == "clear":
        key = _event_key(step)
        executor.state.browser_events[key] = []
        event_options = executor.state.browser_event_options.get(key, {})
        if bool(event_options.get("eventsource", False)):
            _clear_eventsource_events(executor, executor._page(step))
        if bool(event_options.get("webrtc", False)):
            _clear_browser_observer_events(executor, executor._page(step), "__aiAutomateWebRTCEvents")
        if bool(event_options.get("serviceworker", False)):
            _clear_browser_observer_events(executor, executor._page(step), "__aiAutomateServiceWorkerEvents")
        executor.state.logger.log("info", "browser event capture cleared", browser=step["browser"])
        return
    raise ValueError(f"不支持的 event type：{event_type}")


def coverage(executor: Any, step: dict[str, Any]) -> None:
    coverage_type = step["type"]
    key = _event_key(step)
    if coverage_type == "start":
        if key in executor.state.browser_coverage_sessions:
            raise ValueError(f"coverage 已经启动：{key}")
        page = executor._page(step)
        try:
            session = page.context.new_cdp_session(page)
        except Exception as error:
            raise RuntimeError("coverage 采集依赖 Chromium CDP，当前浏览器不支持。") from error

        include_js = bool(step.get("js", True))
        include_css = bool(step.get("css", True))
        if not include_js and not include_css:
            raise ValueError("coverage.start 至少需要启用 js 或 css 之一。")

        if include_js:
            session.send("Profiler.enable")
            session.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
        if include_css:
            session.send("DOM.enable")
            session.send("CSS.enable")
            session.send("CSS.startRuleUsageTracking")

        executor.state.browser_coverage_sessions[key] = {
            "session": session,
            "js": include_js,
            "css": include_css,
        }
        executor.state.logger.log("info", "coverage started", browser=step["browser"], key=key)
        return

    if coverage_type == "stop":
        coverage_state = executor.state.browser_coverage_sessions.pop(key, None)
        if coverage_state is None:
            raise ValueError(f"coverage 尚未启动：{key}")
        session = coverage_state["session"]
        payload: dict[str, Any] = {
            "browser": step["browser"],
            "page": step.get("page"),
            "summary": {},
        }
        if bool(coverage_state.get("js", False)):
            js_payload = session.send("Profiler.takePreciseCoverage")
            session.send("Profiler.stopPreciseCoverage")
            session.send("Profiler.disable")
            payload["js"] = js_payload
            payload["summary"]["js"] = _summarize_js_coverage(js_payload)
        if bool(coverage_state.get("css", False)):
            css_payload = session.send("CSS.stopRuleUsageTracking")
            session.send("CSS.disable")
            session.send("DOM.disable")
            payload["css"] = css_payload
            payload["summary"]["css"] = _summarize_css_coverage(css_payload)
        _detach_cdp_session(session)

        output_path = executor._resolve_output_path(step["path"], category="json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        publish_step_output(executor, step, payload, action="coverage")
        executor.state.logger.log("info", "coverage saved", browser=step["browser"], path=str(output_path))
        return

    if coverage_type == "clear":
        coverage_state = executor.state.browser_coverage_sessions.pop(key, None)
        if coverage_state is not None:
            _detach_cdp_session(coverage_state["session"])
        executor.state.logger.log("info", "coverage cleared", browser=step["browser"], key=key)
        return

    raise ValueError(f"不支持的 coverage type：{coverage_type}")


def _build_route_handler(executor: Any, step: dict[str, Any]) -> Any:
    mode = step.get("mode", "fulfill" if any(field in step for field in ("json", "body", "path")) else "continue")

    def handler(route: Any) -> None:
        if mode == "abort":
            route.abort(error_code=step.get("error_code", "failed"))
            return
        if mode == "continue":
            kwargs: dict[str, Any] = {}
            for field in ("url", "method", "headers", "post_data"):
                if field in step and field != "url":
                    kwargs[field] = step[field]
            if "continue_url" in step:
                kwargs["url"] = step["continue_url"]
            route.continue_(**kwargs)
            return
        if mode == "fulfill":
            kwargs = {"status": int(step.get("status", 200))}
            for field in ("headers", "body", "json"):
                if field in step:
                    kwargs[field] = step[field]
            if "path" in step:
                kwargs["path"] = str(executor._resolve_path(step["path"]))
            if "content_type" in step:
                kwargs["content_type"] = step["content_type"]
            route.fulfill(**kwargs)
            return
        raise ValueError(f"不支持的 network route mode：{mode}")

    return handler


def _network_route_target(session: Any, step: dict[str, Any]) -> Any:
    scope = step.get("scope", "context")
    if scope == "context":
        return session.context
    if scope == "page":
        return session.require_page(step.get("page"))
    raise ValueError(f"不支持的 network scope：{scope}")


def _build_websocket_route_handler(executor: Any, step: dict[str, Any]) -> Any:
    key = _event_key(step)

    def handler(websocket_route: Any) -> None:
        _append_event_if_active(
            executor,
            key,
            {
                "type": "websocket",
                "source": "route",
                "url": websocket_route.url,
            },
        )
        for message in step.get("server_messages", []):
            _send_websocket_route_message(executor, key, websocket_route, message, "server_to_client")

        def on_message(message: Any) -> None:
            _append_event_if_active(
                executor,
                key,
                {
                    "type": "websocket_frame",
                    "source": "route",
                    "url": websocket_route.url,
                    "direction": "client_to_server",
                    "payload": _serialize_payload(message),
                },
            )
            if bool(step.get("echo", False)):
                _send_websocket_route_message(executor, key, websocket_route, message, "server_to_client")
            if "response" in step:
                _send_websocket_route_message(executor, key, websocket_route, step["response"], "server_to_client")
            if bool(step.get("close_after_response", False)):
                _close_websocket_route(websocket_route, step)

        websocket_route.on_message(on_message)
        if bool(step.get("close_on_connect", False)):
            _close_websocket_route(websocket_route, step)

    return handler


def _send_websocket_route_message(
    executor: Any,
    key: str,
    websocket_route: Any,
    message: Any,
    direction: str,
) -> None:
    payload = _normalize_websocket_message(message)
    websocket_route.send(payload)
    _append_event_if_active(
        executor,
        key,
        {
            "type": "websocket_frame",
            "source": "route",
            "url": websocket_route.url,
            "direction": direction,
            "payload": _serialize_payload(payload),
        },
    )


def _normalize_websocket_message(message: Any) -> str | bytes:
    if isinstance(message, (str, bytes)):
        return message
    return json.dumps(message, ensure_ascii=False)


def _close_websocket_route(websocket_route: Any, step: dict[str, Any]) -> None:
    kwargs: dict[str, Any] = {}
    if "close_code" in step:
        kwargs["code"] = int(step["close_code"])
    if "close_reason" in step:
        kwargs["reason"] = step["close_reason"]
    websocket_route.close(**kwargs)


ACTION_HANDLERS = {
    "coverage": coverage,
    "event": event,
    "network": network,
    "script": script,
    "storage": storage,
    "trace": trace,
}


def _event_key(step: dict[str, Any]) -> str:
    return f"{step['browser']}:{step.get('page', '')}"


def _append_event(executor: Any, key: str, payload: dict[str, Any]) -> None:
    executor.state.browser_events.setdefault(key, []).append(payload)


def _add_event_handler(executor: Any, key: str, page: Any, event_name: str, handler: Any) -> None:
    page.on(event_name, handler)
    executor.state.browser_event_handlers.setdefault(key, []).append((page, event_name, handler))


def _remove_event_handlers(executor: Any, key: str) -> None:
    handlers = executor.state.browser_event_handlers.pop(key, [])
    for page, event_name, handler in handlers:
        try:
            page.remove_listener(event_name, handler)
        except Exception as error:
            executor.state.logger.log(
                "warning",
                "browser event handler remove failed",
                event=event_name,
                error=str(error),
                error_type=type(error).__name__,
            )


def _record_console(executor: Any, key: str, message: Any) -> None:
    _append_event(
        executor,
        key,
        {
            "type": "console",
            "level": message.type,
            "text": message.text,
            "location": message.location,
        },
    )


def _record_page_error(executor: Any, key: str, error: Any) -> None:
    _append_event(
        executor,
        key,
        {
            "type": "pageerror",
            "message": str(error),
            "error_type": type(error).__name__,
        },
    )


def _record_request_failed(executor: Any, key: str, request: Any) -> None:
    failure = request.failure
    _append_event(
        executor,
        key,
        {
            "type": "requestfailed",
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "failure": failure,
        },
    )


def _record_websocket(executor: Any, key: str, websocket: Any, *, include_frames: bool = False) -> None:
    _append_event(
        executor,
        key,
        {
            "type": "websocket",
            "url": websocket.url,
        },
    )
    if not include_frames:
        return
    _add_event_handler(
        executor,
        key,
        websocket,
        "framesent",
        lambda payload, event_key=key, target=websocket: _record_websocket_frame(
            executor,
            event_key,
            target,
            "client_to_server",
            payload,
        ),
    )
    _add_event_handler(
        executor,
        key,
        websocket,
        "framereceived",
        lambda payload, event_key=key, target=websocket: _record_websocket_frame(
            executor,
            event_key,
            target,
            "server_to_client",
            payload,
        ),
    )
    _add_event_handler(
        executor,
        key,
        websocket,
        "socketerror",
        lambda error, event_key=key, target=websocket: _append_event(
            executor,
            event_key,
            {
                "type": "websocket_error",
                "url": target.url,
                "message": str(error),
            },
        ),
    )
    _add_event_handler(
        executor,
        key,
        websocket,
        "close",
        lambda *_, event_key=key, target=websocket: _append_event(
            executor,
            event_key,
            {
                "type": "websocket_close",
                "url": target.url,
            },
        ),
    )


def _record_websocket_frame(
    executor: Any,
    key: str,
    websocket: Any,
    direction: str,
    payload: Any,
) -> None:
    _append_event(
        executor,
        key,
        {
            "type": "websocket_frame",
            "url": websocket.url,
            "direction": direction,
            "payload": _serialize_payload(payload),
        },
    )


def _append_event_if_active(executor: Any, key: str, payload: dict[str, Any]) -> None:
    if key in executor.state.browser_events:
        _append_event(executor, key, payload)


def _serialize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, bytes):
        return {
            "kind": "bytes",
            "base64": base64.b64encode(payload).decode("ascii"),
            "size": len(payload),
        }
    if isinstance(payload, dict):
        opcode = payload.get("opcode")
        data = payload.get("data")
        if isinstance(data, bytes):
            return {
                "kind": "bytes",
                "opcode": opcode,
                "base64": base64.b64encode(data).decode("ascii"),
                "size": len(data),
            }
        return {
            "kind": "text",
            "opcode": opcode,
            "text": "" if data is None else str(data),
        }
    return {
        "kind": "text",
        "text": "" if payload is None else str(payload),
    }


def _install_webrtc_observer(executor: Any, page: Any, step: dict[str, Any]) -> None:
    page.add_init_script(script=_WEBRTC_OBSERVER_SCRIPT)
    page.add_init_script(
        script=(
            "window.__aiAutomateWebRTCIncludeSdp = "
            f"{json.dumps(bool(step.get('webrtc_include_sdp', False)))};"
            "window.__aiAutomateWebRTCIncludeCandidate = "
            f"{json.dumps(bool(step.get('webrtc_include_candidate', False)))};"
        )
    )
    try:
        page.evaluate(_WEBRTC_OBSERVER_SCRIPT)
        page.evaluate(
            "([includeSdp, includeCandidate]) => {"
            "window.__aiAutomateWebRTCIncludeSdp = includeSdp;"
            "window.__aiAutomateWebRTCIncludeCandidate = includeCandidate;"
            "}",
            [bool(step.get("webrtc_include_sdp", False)), bool(step.get("webrtc_include_candidate", False))],
        )
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "webrtc observer install failed on current page",
            error=str(error),
            error_type=type(error).__name__,
        )


def _install_serviceworker_observer(executor: Any, key: str, context: Any, page: Any) -> None:
    page.add_init_script(script=_SERVICEWORKER_OBSERVER_SCRIPT)
    try:
        page.evaluate(_SERVICEWORKER_OBSERVER_SCRIPT)
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "serviceworker observer install failed on current page",
            error=str(error),
            error_type=type(error).__name__,
        )
    _add_event_handler(
        executor,
        key,
        context,
        "serviceworker",
        lambda worker, event_key=key: _record_service_worker(executor, event_key, worker),
    )
    _add_event_handler(
        executor,
        key,
        context,
        "request",
        lambda request, event_key=key: _record_service_worker_request(executor, event_key, request),
    )
    _add_event_handler(
        executor,
        key,
        context,
        "response",
        lambda response, event_key=key: _record_service_worker_response(executor, event_key, response),
    )
    for worker in context.service_workers:
        _record_service_worker(executor, key, worker)


def _install_eventsource_observer(executor: Any, page: Any) -> None:
    page.add_init_script(script=_EVENTSOURCE_OBSERVER_SCRIPT)
    try:
        page.evaluate(_EVENTSOURCE_OBSERVER_SCRIPT)
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "eventsource observer install failed on current page",
            error=str(error),
            error_type=type(error).__name__,
        )


def _collect_eventsource_events(executor: Any, key: str, page: Any) -> None:
    _collect_browser_observer_events(executor, key, page, "__aiAutomateEventSourceEvents")


def _clear_eventsource_events(executor: Any, page: Any) -> None:
    _clear_browser_observer_events(executor, page, "__aiAutomateEventSourceEvents")


def _record_service_worker(executor: Any, key: str, worker: Any) -> None:
    _append_event_if_active(
        executor,
        key,
        {
            "type": "serviceworker",
            "event": "created",
            "url": worker.url,
        },
    )
    _add_event_handler(
        executor,
        key,
        worker,
        "console",
        lambda message, event_key=key, target=worker: _append_event_if_active(
            executor,
            event_key,
            {
                "type": "serviceworker",
                "event": "console",
                "url": target.url,
                "level": message.type,
                "text": message.text,
                "location": message.location,
            },
        ),
    )
    _add_event_handler(
        executor,
        key,
        worker,
        "close",
        lambda *_, event_key=key, target=worker: _append_event_if_active(
            executor,
            event_key,
            {
                "type": "serviceworker",
                "event": "close",
                "url": target.url,
            },
        ),
    )


def _record_service_worker_request(executor: Any, key: str, request: Any) -> None:
    try:
        worker = request.service_worker
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "service worker request read failed",
            error=str(error),
            error_type=type(error).__name__,
        )
        return
    if worker is None:
        return
    _append_event_if_active(
        executor,
        key,
        {
            "type": "serviceworker",
            "event": "request",
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "service_worker_url": worker.url,
        },
    )


def _record_service_worker_response(executor: Any, key: str, response: Any) -> None:
    try:
        from_service_worker = bool(response.from_service_worker)
    except Exception:
        from_service_worker = False
    if not from_service_worker:
        return
    _append_event_if_active(
        executor,
        key,
        {
            "type": "serviceworker",
            "event": "response",
            "url": response.url,
            "status": response.status,
            "ok": response.ok,
            "from_service_worker": True,
        },
    )


def _collect_browser_observer_events(executor: Any, key: str, page: Any, variable_name: str) -> None:
    try:
        events = page.evaluate(
            "(name) => {"
            "const events = Array.isArray(window[name]) ? window[name] : [];"
            "window[name] = [];"
            "return events;"
            "}",
            variable_name,
        )
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "browser observer events collect failed",
            variable=variable_name,
            error=str(error),
            error_type=type(error).__name__,
        )
        return
    if not isinstance(events, list):
        return
    for event in events:
        if isinstance(event, dict):
            _append_event(executor, key, event)


def _clear_browser_observer_events(executor: Any, page: Any, variable_name: str) -> None:
    try:
        page.evaluate("(name) => { window[name] = []; }", variable_name)
    except Exception as error:
        executor.state.logger.log(
            "warning",
            "browser observer events clear failed",
            variable=variable_name,
            error=str(error),
            error_type=type(error).__name__,
        )


def _summarize_js_coverage(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("result", [])
    total_bytes = 0
    used_bytes = 0
    for entry in entries:
        ranges: list[tuple[int, int]] = []
        all_ranges: list[tuple[int, int]] = []
        for function in entry.get("functions", []):
            for coverage_range in function.get("ranges", []):
                start = int(coverage_range.get("startOffset", 0))
                end = int(coverage_range.get("endOffset", 0))
                all_ranges.append((start, end))
                if int(coverage_range.get("count", 0)) > 0:
                    ranges.append((start, end))
        total_bytes += _merged_range_length(all_ranges)
        used_bytes += _merged_range_length(ranges)
    return {
        "entry_count": len(entries),
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "used_ratio": _ratio(used_bytes, total_bytes),
    }


def _summarize_css_coverage(payload: dict[str, Any]) -> dict[str, Any]:
    raw_ranges = payload.get("ruleUsage", [])
    grouped_total: dict[str, list[tuple[int, int]]] = {}
    grouped_used: dict[str, list[tuple[int, int]]] = {}
    for coverage_range in raw_ranges:
        style_sheet_id = str(coverage_range.get("styleSheetId", ""))
        start = int(coverage_range.get("startOffset", 0))
        end = int(coverage_range.get("endOffset", 0))
        grouped_total.setdefault(style_sheet_id, []).append((start, end))
        if bool(coverage_range.get("used", False)):
            grouped_used.setdefault(style_sheet_id, []).append((start, end))
    total_bytes = sum(_merged_range_length(ranges) for ranges in grouped_total.values())
    used_bytes = sum(_merged_range_length(ranges) for ranges in grouped_used.values())
    return {
        "range_count": len(raw_ranges),
        "stylesheet_count": len(grouped_total),
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "used_ratio": _ratio(used_bytes, total_bytes),
    }


def _merged_range_length(ranges: list[tuple[int, int]]) -> int:
    normalized = sorted((start, end) for start, end in ranges if end > start)
    if not normalized:
        return 0
    merged: list[tuple[int, int]] = [normalized[0]]
    for start, end in normalized[1:]:
        current_start, current_end = merged[-1]
        if start <= current_end:
            merged[-1] = (current_start, max(current_end, end))
        else:
            merged.append((start, end))
    return sum(end - start for start, end in merged)


def _ratio(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(used / total, 4)


def _detach_cdp_session(session: Any) -> None:
    detach = getattr(session, "detach", None)
    if detach is not None:
        detach()


_EVENTSOURCE_OBSERVER_SCRIPT = r"""
(() => {
  window.__aiAutomateEventSourceEvents = window.__aiAutomateEventSourceEvents || [];
  if (window.__aiAutomateEventSourcePatched) {
    return;
  }
  window.__aiAutomateEventSourcePatched = true;
  const NativeEventSource = window.EventSource;
  if (!NativeEventSource) {
    return;
  }
  const record = (url, eventName, event) => {
    window.__aiAutomateEventSourceEvents.push({
      type: "eventsource",
      url: String(url),
      event: String(eventName),
      data: "data" in event ? event.data : null,
      last_event_id: "lastEventId" in event ? event.lastEventId : "",
      ready_state: event.currentTarget && typeof event.currentTarget.readyState === "number"
        ? event.currentTarget.readyState
        : null
    });
  };
  function PatchedEventSource(url, eventSourceInitDict) {
    const source = new NativeEventSource(url, eventSourceInitDict);
    const sourceUrl = String(url);
    source.addEventListener("open", (event) => record(sourceUrl, "open", event));
    source.addEventListener("message", (event) => record(sourceUrl, "message", event));
    source.addEventListener("error", (event) => record(sourceUrl, "error", event));
    const nativeAddEventListener = source.addEventListener.bind(source);
    source.addEventListener = (type, listener, options) => {
      const eventName = String(type);
      if (!["open", "message", "error"].includes(eventName)) {
        nativeAddEventListener(eventName, (event) => record(sourceUrl, eventName, event), options);
      }
      return nativeAddEventListener(type, listener, options);
    };
    return source;
  }
  Object.setPrototypeOf(PatchedEventSource, NativeEventSource);
  PatchedEventSource.prototype = NativeEventSource.prototype;
  window.EventSource = PatchedEventSource;
})();
"""


_WEBRTC_OBSERVER_SCRIPT = r"""
(() => {
  window.__aiAutomateWebRTCEvents = window.__aiAutomateWebRTCEvents || [];
  if (window.__aiAutomateWebRTCPatched) {
    return;
  }
  window.__aiAutomateWebRTCPatched = true;
  const NativePeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!NativePeerConnection) {
    return;
  }
  let nextPeerConnectionId = 1;
  const record = (peerConnection, event, detail = {}) => {
    window.__aiAutomateWebRTCEvents.push({
      type: "webrtc",
      event,
      id: peerConnection.__aiAutomatePeerConnectionId,
      signaling_state: peerConnection.signalingState || null,
      ice_connection_state: peerConnection.iceConnectionState || null,
      connection_state: peerConnection.connectionState || null,
      detail
    });
  };
  const describeDescription = (description) => {
    if (!description) {
      return null;
    }
    const value = {
      type: description.type || null,
      sdp_length: description.sdp ? description.sdp.length : 0
    };
    if (window.__aiAutomateWebRTCIncludeSdp && description.sdp) {
      value.sdp = description.sdp;
    }
    return value;
  };
  const describeCandidate = (candidate) => {
    if (!candidate) {
      return null;
    }
    const value = {
      sdp_mid: candidate.sdpMid || null,
      sdp_m_line_index: candidate.sdpMLineIndex,
      username_fragment: candidate.usernameFragment || null,
      candidate_length: candidate.candidate ? candidate.candidate.length : 0
    };
    if (window.__aiAutomateWebRTCIncludeCandidate && candidate.candidate) {
      value.candidate = candidate.candidate;
    }
    return value;
  };
  class PatchedPeerConnection extends NativePeerConnection {
    constructor(configuration, constraints) {
      super(configuration, constraints);
      this.__aiAutomatePeerConnectionId = nextPeerConnectionId++;
      record(this, "constructor", {
        has_configuration: configuration !== undefined,
        ice_server_count: configuration && Array.isArray(configuration.iceServers)
          ? configuration.iceServers.length
          : 0
      });
      this.addEventListener("icecandidate", (event) => {
        record(this, "icecandidate", { candidate: describeCandidate(event.candidate) });
      });
      this.addEventListener("connectionstatechange", () => record(this, "connectionstatechange"));
      this.addEventListener("iceconnectionstatechange", () => record(this, "iceconnectionstatechange"));
      this.addEventListener("signalingstatechange", () => record(this, "signalingstatechange"));
      this.addEventListener("negotiationneeded", () => record(this, "negotiationneeded"));
      this.addEventListener("track", (event) => {
        record(this, "track", {
          receiver_track_kind: event.track ? event.track.kind : null,
          stream_count: event.streams ? event.streams.length : 0
        });
      });
      this.addEventListener("datachannel", (event) => {
        record(this, "datachannel", { label: event.channel ? event.channel.label : null });
      });
    }
    createDataChannel(label, dataChannelDict) {
      record(this, "createDataChannel", { label: String(label) });
      return super.createDataChannel(label, dataChannelDict);
    }
    async createOffer(options) {
      record(this, "createOffer:start", { has_options: options !== undefined });
      const description = await super.createOffer(options);
      record(this, "createOffer:done", { description: describeDescription(description) });
      return description;
    }
    async createAnswer(options) {
      record(this, "createAnswer:start", { has_options: options !== undefined });
      const description = await super.createAnswer(options);
      record(this, "createAnswer:done", { description: describeDescription(description) });
      return description;
    }
    async setLocalDescription(description) {
      record(this, "setLocalDescription:start", { description: describeDescription(description) });
      const result = await super.setLocalDescription(description);
      record(this, "setLocalDescription:done", { description: describeDescription(this.localDescription) });
      return result;
    }
    async setRemoteDescription(description) {
      record(this, "setRemoteDescription:start", { description: describeDescription(description) });
      const result = await super.setRemoteDescription(description);
      record(this, "setRemoteDescription:done", { description: describeDescription(this.remoteDescription) });
      return result;
    }
    async addIceCandidate(candidate) {
      record(this, "addIceCandidate:start", { candidate: describeCandidate(candidate) });
      const result = await super.addIceCandidate(candidate);
      record(this, "addIceCandidate:done", {});
      return result;
    }
    close() {
      record(this, "close");
      return super.close();
    }
  }
  window.RTCPeerConnection = PatchedPeerConnection;
  if (window.webkitRTCPeerConnection) {
    window.webkitRTCPeerConnection = PatchedPeerConnection;
  }
})();
"""


_SERVICEWORKER_OBSERVER_SCRIPT = r"""
(() => {
  window.__aiAutomateServiceWorkerEvents = window.__aiAutomateServiceWorkerEvents || [];
  if (window.__aiAutomateServiceWorkerPatched) {
    return;
  }
  window.__aiAutomateServiceWorkerPatched = true;
  if (!navigator.serviceWorker) {
    return;
  }
  const record = (event, detail = {}) => {
    window.__aiAutomateServiceWorkerEvents.push({
      type: "serviceworker",
      event,
      url: location.href,
      detail
    });
  };
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    record("controllerchange", {
      controller_url: navigator.serviceWorker.controller ? navigator.serviceWorker.controller.scriptURL : null
    });
  });
  navigator.serviceWorker.addEventListener("message", (event) => {
    record("message", { data: String(event.data) });
  });
  const nativeRegister = navigator.serviceWorker.register.bind(navigator.serviceWorker);
  navigator.serviceWorker.register = async (scriptURL, options) => {
    record("register:start", { script_url: String(scriptURL), scope: options && options.scope ? String(options.scope) : null });
    try {
      const registration = await nativeRegister(scriptURL, options);
      record("register:done", {
        scope: registration.scope || null,
        active_state: registration.active ? registration.active.state : null,
        installing_state: registration.installing ? registration.installing.state : null,
        waiting_state: registration.waiting ? registration.waiting.state : null
      });
      return registration;
    } catch (error) {
      record("register:error", { message: String(error && error.message ? error.message : error) });
      throw error;
    }
  };
  navigator.serviceWorker.ready.then((registration) => {
    record("ready", {
      scope: registration.scope || null,
      active_state: registration.active ? registration.active.state : null
    });
  }).catch((error) => {
    record("ready:error", { message: String(error && error.message ? error.message : error) });
  });
})();
"""
