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
    if mouse_type == "tap":
        executor._page(step).touchscreen.tap(float(step["x"]), float(step["y"]))
        return
    raise ValueError(f"Unsupported mouse type: {mouse_type}")


ACTION_HANDLERS = {
    "keyboard": keyboard,
    "mouse": mouse,
    "scroll": scroll,
}
