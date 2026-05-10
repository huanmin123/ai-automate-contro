from __future__ import annotations

from typing import Any


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


ACTION_HANDLERS = {
    "capture": capture,
}
