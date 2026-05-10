from __future__ import annotations

from typing import Any


def wait_for_download(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError("wait_for_download requires a trigger step.")
    with target_page.expect_download() as download_info:
        executor.run([trigger])
    download = download_info.value
    output_path = executor._resolve_output_path(step["path"], category="downloads")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(output_path))
    executor.state.downloads.append(str(output_path))
    if "save_as" in step:
        executor.state.variables[step["save_as"]] = str(output_path)
    executor.state.logger.log("info", "download saved", path=str(output_path))


def wait_for_popup(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    session = executor.state.require_session(step["browser"])
    trigger = step.get("trigger")
    popup_name = step["popup_page"]
    if not trigger:
        raise ValueError("wait_for_popup requires a trigger step.")
    with target_page.expect_popup() as popup_info:
        executor.run([trigger])
    popup_page = popup_info.value
    session.register_page(popup_name, popup_page, switch=bool(step.get("switch", True)))
    if "save_as" in step:
        executor.state.variables[step["save_as"]] = popup_name
    executor.state.logger.log(
        "info",
        "popup captured",
        browser=step["browser"],
        page=popup_name,
        url=popup_page.url,
    )


def wait_for_network(executor: Any, step: dict[str, Any]) -> None:
    network_type = step["type"]
    if network_type == "request":
        _wait_for_request(executor, step)
        return
    if network_type == "response":
        _wait_for_response(executor, step)
        return
    raise ValueError(f"Unsupported wait_for_network type: {network_type}")


def _wait_for_request(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError("wait_for_network type 'request' requires a trigger step.")
    with target_page.expect_request(step["url"]) as request_info:
        executor.run([trigger])
    request = request_info.value
    payload = {
        "url": request.url,
        "method": request.method,
        "resource_type": request.resource_type,
    }
    if "save_as" in step:
        executor.state.variables[step["save_as"]] = payload
    executor.state.logger.log(
        "info",
        "request captured",
        url=request.url,
        method=request.method,
        resource_type=request.resource_type,
    )


def _wait_for_response(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    trigger = step.get("trigger")
    if not trigger:
        raise ValueError("wait_for_network type 'response' requires a trigger step.")
    with target_page.expect_response(step["url"]) as response_info:
        executor.run([trigger])
    response = response_info.value
    payload = {
        "url": response.url,
        "status": response.status,
        "ok": response.ok,
    }
    if "save_as" in step:
        executor.state.variables[step["save_as"]] = payload
    executor.state.logger.log(
        "info",
        "response captured",
        url=response.url,
        status=response.status,
        ok=response.ok,
    )


ACTION_HANDLERS = {
    "wait_for_download": wait_for_download,
    "wait_for_network": wait_for_network,
    "wait_for_popup": wait_for_popup,
}
