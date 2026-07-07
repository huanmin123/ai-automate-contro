from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output


BROWSER_TRIGGER_EVENT_TYPES = {"download", "file_chooser", "popup", "request", "response"}


def browser_trigger_event(executor: Any, step: dict[str, Any]) -> None:
    event_type = str(step["type"])
    if event_type == "download":
        _capture_download(executor, step, event_label="event.download")
        return
    if event_type == "file_chooser":
        _capture_file_chooser(executor, step, event_label="event.file_chooser")
        return
    if event_type == "popup":
        _capture_popup(executor, step, event_label="event.popup")
        return
    if event_type == "request":
        _capture_request(executor, step, event_label="event.request")
        return
    if event_type == "response":
        _capture_response(executor, step, event_label="event.response")
        return
    raise ValueError(f"不支持的 event type：{event_type}")


def _capture_download(executor: Any, step: dict[str, Any], *, event_label: str) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError(f"{event_label} 需要 trigger 步骤。")
    with target_page.expect_download() as download_info:
        executor.run([trigger])
    download = download_info.value
    output_path = executor._resolve_output_path(step["path"], category="downloads")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(output_path))
    executor.state.downloads.append(str(output_path))
    publish_step_output(executor, step, str(output_path), action="event")
    executor.state.logger.log("info", "download saved", path=str(output_path))


def _capture_file_chooser(executor: Any, step: dict[str, Any], *, event_label: str) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError(f"{event_label} 需要 trigger 步骤。")
    with target_page.expect_file_chooser() as chooser_info:
        executor.run([trigger])
    files = step["files"]
    if isinstance(files, str):
        files = [files]
    resolved_files = [str(executor._resolve_path(file_path)) for file_path in files]
    chooser_info.value.set_files(resolved_files)
    publish_step_output(executor, step, resolved_files, action="event")
    executor.state.logger.log("info", "file chooser handled", files=resolved_files)


def _capture_popup(executor: Any, step: dict[str, Any], *, event_label: str) -> None:
    target_page = executor._page(step)
    session = executor.state.require_session(step["browser"])
    trigger = step.get("trigger")
    popup_name = step["popup_page"]
    if not trigger:
        raise ValueError(f"{event_label} 需要 trigger 步骤。")
    with target_page.expect_popup() as popup_info:
        executor.run([trigger])
    popup_page = popup_info.value
    session.register_page(popup_name, popup_page, switch=bool(step.get("switch", True)))
    publish_step_output(executor, step, popup_name, action="event")
    executor.state.logger.log(
        "info",
        "popup captured",
        browser=step["browser"],
        page=popup_name,
        url=popup_page.url,
    )


def _capture_request(executor: Any, step: dict[str, Any], *, event_label: str) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError(f"{event_label} 需要 trigger 步骤。")
    with target_page.expect_request(step["url"]) as request_info:
        executor.run([trigger])
    request = request_info.value
    payload = {
        "url": request.url,
        "method": request.method,
        "resource_type": request.resource_type,
        "headers": request.headers if bool(step.get("include_headers", False)) else {},
    }
    if bool(step.get("include_post_data", False)):
        payload["post_data"] = request.post_data
    publish_step_output(executor, step, payload, action="event")
    executor.state.logger.log(
        "info",
        "request captured",
        url=request.url,
        method=request.method,
        resource_type=request.resource_type,
    )


def _capture_response(executor: Any, step: dict[str, Any], *, event_label: str) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError(f"{event_label} 需要 trigger 步骤。")
    with target_page.expect_response(step["url"]) as response_info:
        executor.run([trigger])
    response = response_info.value
    payload = {
        "url": response.url,
        "status": response.status,
        "ok": response.ok,
        "headers": response.headers if bool(step.get("include_headers", False)) else {},
    }
    if bool(step.get("include_body", False)):
        body_type = step.get("body_type", "text")
        if body_type == "json":
            payload["body"] = response.json()
        elif body_type == "body":
            payload["body"] = list(response.body())
        else:
            payload["body"] = response.text()
    publish_step_output(executor, step, payload, action="event")
    executor.state.logger.log(
        "info",
        "response captured",
        url=response.url,
        status=response.status,
        ok=response.ok,
    )


ACTION_HANDLERS = {
}
