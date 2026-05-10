from __future__ import annotations

from typing import Any


def keyboard(executor: Any, step: dict[str, Any]) -> None:
    keyboard_type = step["type"]
    target_keyboard = executor._page(step).keyboard
    if keyboard_type == "press":
        target_keyboard.press(step["key"])
        return
    if keyboard_type == "type":
        target_keyboard.type(str(step["value"]), delay=int(step.get("delay_ms", 50)))
        return
    if keyboard_type == "down":
        target_keyboard.down(step["key"])
        return
    if keyboard_type == "up":
        target_keyboard.up(step["key"])
        return
    raise ValueError(f"Unsupported keyboard type: {keyboard_type}")


def scroll(executor: Any, step: dict[str, Any]) -> None:
    scroll_type = step.get("type", "by")
    if scroll_type == "into_view":
        executor._locator(step).scroll_into_view_if_needed()
        return
    if scroll_type == "by":
        target_page = executor._page(step)
        delta_x = int(step.get("delta_x", 0))
        delta_y = int(step.get("delta_y", 0))
        target_page.evaluate(
            "(args) => window.scrollBy(args.deltaX, args.deltaY)",
            {"deltaX": delta_x, "deltaY": delta_y},
        )
        return
    raise ValueError(f"Unsupported scroll type: {scroll_type}")


def mouse(executor: Any, step: dict[str, Any]) -> None:
    mouse_type = step["type"]
    target_mouse = executor._page(step).mouse
    if mouse_type == "move":
        target_mouse.move(float(step["x"]), float(step["y"]))
        return
    if mouse_type == "click":
        target_mouse.click(
            float(step["x"]),
            float(step["y"]),
            button=step.get("button", "left"),
            click_count=int(step.get("click_count", 1)),
        )
        return
    if mouse_type == "down":
        target_mouse.down(button=step.get("button", "left"))
        return
    if mouse_type == "up":
        target_mouse.up(button=step.get("button", "left"))
        return
    if mouse_type == "wheel":
        target_mouse.wheel(float(step.get("delta_x", 0)), float(step.get("delta_y", 0)))
        return
    raise ValueError(f"Unsupported mouse type: {mouse_type}")


def capture(executor: Any, step: dict[str, Any]) -> None:
    capture_type = step["type"]
    if capture_type == "screenshot":
        output_path = executor._resolve_output_path(step["path"], category="screenshots")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        executor._page(step).screenshot(
            path=str(output_path),
            full_page=bool(step.get("full_page", False)),
        )
        executor.state.logger.log("info", "screenshot saved", path=str(output_path))
        return
    if capture_type == "html":
        output_path = executor._resolve_output_path(step["path"], category="html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html = executor._page(step).content()
        with output_path.open("w", encoding="utf-8") as file:
            file.write(html)
        executor.state.logger.log("info", "page html saved", path=str(output_path))
        return
    if capture_type == "storage_state":
        session = executor.state.require_session(step["browser"])
        output_path = executor._resolve_output_path(step["path"], category="storage-states")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        session.context.storage_state(path=str(output_path))
        executor.state.logger.log("info", "storage state saved", browser=step["browser"], path=str(output_path))
        return
    raise ValueError(f"Unsupported capture type: {capture_type}")


def dialog(executor: Any, step: dict[str, Any]) -> None:
    dialog_type = step["type"]
    if dialog_type == "accept":
        _handle_dialog_action(executor, step, accept=True)
        return
    if dialog_type == "dismiss":
        _handle_dialog_action(executor, step, accept=False)
        return
    raise ValueError(f"Unsupported dialog type: {dialog_type}")


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


ACTION_HANDLERS = {
    "capture": capture,
    "dialog": dialog,
    "keyboard": keyboard,
    "mouse": mouse,
    "scroll": scroll,
    "wait_for_download": wait_for_download,
    "wait_for_network": wait_for_network,
    "wait_for_popup": wait_for_popup,
}


def _handle_dialog_action(executor: Any, step: dict[str, Any], *, accept: bool) -> None:
    trigger = step.get("trigger")
    if trigger:
        target_page = executor._page(step)
        prompt_text = step.get("prompt_text")

        def handler(dialog_object: Any) -> None:
            executor.state.last_dialog_message = dialog_object.message
            executor.state.logger.log(
                "info",
                "dialog auto-accepted" if accept else "dialog auto-dismissed",
                dialog_type=dialog_object.type,
                dialog_message=dialog_object.message,
            )
            if accept:
                dialog_object.accept(prompt_text)
            else:
                dialog_object.dismiss()

        target_page.once("dialog", handler)
        executor.run([trigger])
        executor.state.pending_dialog = None
        return

    if executor.state.pending_dialog is None:
        raise RuntimeError("No pending dialog to handle.")
    if accept:
        prompt_text = step.get("prompt_text")
        executor.state.pending_dialog.accept(prompt_text)
        executor.state.logger.log("info", "dialog accepted", message=executor.state.last_dialog_message)
    else:
        executor.state.pending_dialog.dismiss()
        executor.state.logger.log("info", "dialog dismissed", message=executor.state.last_dialog_message)
    executor.state.pending_dialog = None


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
