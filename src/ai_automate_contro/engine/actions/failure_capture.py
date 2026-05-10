from __future__ import annotations

import json
from typing import Any

from ai_automate_contro.engine.runtime import RuntimeState


def capture_failure_state(state: RuntimeState, *, step_number: int, action: str, step_name: str) -> None:
    screenshot_dir = state.output_dir / "failure-screenshots"
    html_dir = state.output_dir / "failure-html"
    page_state_dir = state.output_dir / "failure-page-state"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    page_state_dir.mkdir(parents=True, exist_ok=True)
    for browser_name, session in state.sessions.items():
        for page_name, page in session.pages.items():
            file_stem = f"step-{step_number:03d}-{browser_name}-{page_name}-{action}"
            screenshot_path = screenshot_dir / f"{file_stem}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                state.failure_screenshots.append(str(screenshot_path))
                state.logger.log(
                    "warning",
                    "failure screenshot captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(screenshot_path),
                )
            except Exception as screenshot_error:
                state.logger.log(
                    "warning",
                    "failure screenshot capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(screenshot_error),
                )
            html_path = html_dir / f"{file_stem}.html"
            try:
                html_path.write_text(page.content(), encoding="utf-8")
                state.failure_htmls.append(str(html_path))
                state.logger.log(
                    "warning",
                    "failure html captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(html_path),
                )
            except Exception as html_error:
                state.logger.log(
                    "warning",
                    "failure html capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(html_error),
                )
            page_state_path = page_state_dir / f"{file_stem}.json"
            try:
                page_state = _page_state_payload(
                    step_number=step_number,
                    action=action,
                    step_name=step_name,
                    browser_name=browser_name,
                    page_name=page_name,
                    page=page,
                    screenshot=str(screenshot_path) if screenshot_path.exists() else "",
                    html=str(html_path) if html_path.exists() else "",
                )
                with page_state_path.open("w", encoding="utf-8") as file:
                    json.dump(page_state, file, ensure_ascii=False, indent=2)
                state.failure_page_states.append(str(page_state_path))
                state.logger.log(
                    "warning",
                    "failure page state captured",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    path=str(page_state_path),
                )
            except Exception as page_state_error:
                state.logger.log(
                    "warning",
                    "failure page state capture failed",
                    step=step_number,
                    step_name=step_name,
                    browser=browser_name,
                    page=page_name,
                    error=str(page_state_error),
                )


def _page_state_payload(
    *,
    step_number: int,
    action: str,
    step_name: str,
    browser_name: str,
    page_name: str,
    page: Any,
    screenshot: str,
    html: str,
) -> dict[str, Any]:
    return {
        "step": step_number,
        "action": action,
        "step_name": step_name,
        "browser": browser_name,
        "page": page_name,
        "url": page.url,
        "title": page.title(),
        "screenshot": screenshot,
        "html": html,
    }
