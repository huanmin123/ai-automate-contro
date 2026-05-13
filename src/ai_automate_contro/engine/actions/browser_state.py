from __future__ import annotations

from typing import Any


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
    raise ValueError(f"不支持的 network type：{network_type}")


def script(executor: Any, step: dict[str, Any]) -> None:
    script_type = step["type"]
    if script_type == "evaluate":
        page = executor._page(step)
        result = page.evaluate(step["js"], step["arg"]) if "arg" in step else page.evaluate(step["js"])
        if "save_as" in step:
            executor.state.variables[step["save_as"]] = result
        executor.state.logger.log("info", "page script evaluated", save_as=step.get("save_as"))
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
        executor.state.variables[step["save_as"]] = cookies
        executor.state.logger.log("info", "cookies read", browser=step["browser"], save_as=step["save_as"])
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
        executor.state.variables[step["save_as"]] = value
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
        executor.state.variables[step["save_as"]] = value
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
        page = executor._page(step)
        key = _event_key(step)
        _remove_event_handlers(executor, key)
        executor.state.browser_events[key] = []
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
                lambda websocket, event_key=key: _record_websocket(executor, event_key, websocket),
            )
        executor.state.logger.log("info", "browser event capture started", browser=step["browser"], key=key)
        return
    if event_type == "stop":
        key = _event_key(step)
        output_path = executor._resolve_output_path(step["path"], category="json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(executor.state.browser_events.get(key, []), file, ensure_ascii=False, indent=2)
        if "save_as" in step:
            executor.state.variables[step["save_as"]] = executor.state.browser_events.get(key, [])
        _remove_event_handlers(executor, key)
        executor.state.logger.log("info", "browser event capture saved", browser=step["browser"], path=str(output_path))
        return
    if event_type == "clear":
        executor.state.browser_events[_event_key(step)] = []
        executor.state.logger.log("info", "browser event capture cleared", browser=step["browser"])
        return
    raise ValueError(f"不支持的 event type：{event_type}")


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


ACTION_HANDLERS = {
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


def _record_websocket(executor: Any, key: str, websocket: Any) -> None:
    _append_event(
        executor,
        key,
        {
            "type": "websocket",
            "url": websocket.url,
        },
    )
