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
    target_page = executor._page(step)
    target_mouse = target_page.mouse
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
        target_page.touchscreen.tap(float(step["x"]), float(step["y"]))
        return
    if mouse_type == "swipe":
        _swipe(executor, step)
        return
    raise ValueError(f"Unsupported mouse type: {mouse_type}")


def _swipe(executor: Any, step: dict[str, Any]) -> None:
    target_page = executor._page(step)
    start_x = float(step["start_x"])
    start_y = float(step["start_y"])
    end_x = float(step["end_x"])
    end_y = float(step["end_y"])
    steps = max(1, int(step.get("steps", 10)))
    duration_ms = max(0, int(step.get("duration_ms", 300)))

    if bool(step.get("touch", True)):
        try:
            _touch_swipe(target_page, start_x, start_y, end_x, end_y, steps, duration_ms)
            if bool(step.get("dom_touch_fallback", True)):
                _dom_touch_swipe(target_page, start_x, start_y, end_x, end_y, steps, duration_ms)
            return
        except Exception as error:
            if not bool(step.get("fallback_to_mouse", True)):
                raise RuntimeError("touch swipe 需要 Chromium/CDP 支持。") from error
            executor.state.logger.log(
                "warning",
                "touch swipe fallback to mouse",
                error=str(error),
                error_type=type(error).__name__,
            )

    target_page.mouse.move(start_x, start_y)
    target_page.mouse.down()
    for index in range(1, steps + 1):
        progress = index / steps
        target_page.mouse.move(
            start_x + (end_x - start_x) * progress,
            start_y + (end_y - start_y) * progress,
        )
        if duration_ms:
            target_page.wait_for_timeout(duration_ms / steps)
    target_page.mouse.up()


def _touch_swipe(
    page: Any,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    steps: int,
    duration_ms: int,
) -> None:
    session = page.context.new_cdp_session(page)
    try:
        touch_point = {"x": start_x, "y": start_y, "id": 1}
        session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [touch_point]})
        for index in range(1, steps + 1):
            progress = index / steps
            touch_point = {
                "x": start_x + (end_x - start_x) * progress,
                "y": start_y + (end_y - start_y) * progress,
                "id": 1,
            }
            session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [touch_point]})
            if duration_ms:
                page.wait_for_timeout(duration_ms / steps)
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        detach = getattr(session, "detach", None)
        if detach is not None:
            detach()


def _dom_touch_swipe(
    page: Any,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    steps: int,
    duration_ms: int,
) -> None:
    delay_ms = duration_ms / steps if duration_ms else 0
    page.evaluate(
        """
        async (args) => {
          const hasTouchIntent = (element) => {
            if (!element || element === document.documentElement) {
              return false;
            }
            const touchAction = window.getComputedStyle(element).touchAction || "";
            return touchAction && touchAction !== "auto";
          };
          const containsPoint = (element, x, y) => {
            const rect = element.getBoundingClientRect();
            return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
          };
          const startHit = document.elementFromPoint(args.startX, args.startY);
          const touchCandidates = Array.from(document.querySelectorAll("*")).filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && hasTouchIntent(element);
          });
          let target = hasTouchIntent(startHit) ? startHit : null;
          if (!target) {
            target = touchCandidates.find((element) => containsPoint(element, args.startX, args.startY));
          }
          if (!target) {
            target = touchCandidates[0] || startHit || document.body;
          }
          const deltaX = args.endX - args.startX;
          const deltaY = args.endY - args.startY;
          let startX = args.startX;
          let startY = args.startY;
          let endX = args.endX;
          let endY = args.endY;
          if (!containsPoint(target, startX, startY)) {
            const rect = target.getBoundingClientRect();
            startX = rect.left + rect.width / 2;
            startY = rect.top + rect.height / 2;
            endX = startX + deltaX;
            endY = startY + deltaY;
          }
          const makeTouch = (x, y) => new Touch({
            identifier: 1,
            target,
            clientX: x,
            clientY: y,
            screenX: x,
            screenY: y,
            pageX: x + window.scrollX,
            pageY: y + window.scrollY,
            radiusX: 1,
            radiusY: 1,
            rotationAngle: 0,
            force: 1,
          });
          const dispatch = (type, x, y) => {
            const touch = makeTouch(x, y);
            const event = new TouchEvent(type, {
              bubbles: true,
              cancelable: true,
              composed: true,
              touches: type === "touchend" ? [] : [touch],
              targetTouches: type === "touchend" ? [] : [touch],
              changedTouches: [touch],
            });
            target.dispatchEvent(event);
          };
          dispatch("touchstart", startX, startY);
          for (let index = 1; index <= args.steps; index += 1) {
            const progress = index / args.steps;
            const x = startX + (endX - startX) * progress;
            const y = startY + (endY - startY) * progress;
            dispatch("touchmove", x, y);
            if (args.delayMs) {
              await new Promise((resolve) => setTimeout(resolve, args.delayMs));
            }
          }
          dispatch("touchend", endX, endY);
        }
        """,
        {
            "startX": start_x,
            "startY": start_y,
            "endX": end_x,
            "endY": end_y,
            "steps": steps,
            "delayMs": delay_ms,
        },
    )


ACTION_HANDLERS = {
    "keyboard": keyboard,
    "mouse": mouse,
    "scroll": scroll,
}
