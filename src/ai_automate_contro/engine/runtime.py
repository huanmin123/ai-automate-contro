from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Dialog, Download, Page, Playwright

from ai_automate_contro.support.logger import RunLogger
from ai_automate_contro.engine.state import RunStateWriter


@dataclass
class BrowserSession:
    name: str
    browser: Browser
    context: BrowserContext
    pages: dict[str, Page] = field(default_factory=dict)
    current_page_name: str = "main"

    def register_page(self, page_name: str, page: Page, switch: bool = True) -> None:
        if page_name in self.pages:
            raise ValueError(f"Page '{page_name}' already exists in browser session '{self.name}'.")
        self.pages[page_name] = page
        if switch:
            self.current_page_name = page_name

    def require_page(self, page_name: str | None = None) -> Page:
        target_name = page_name or self.current_page_name
        if target_name not in self.pages:
            raise KeyError(f"Page '{target_name}' does not exist in browser session '{self.name}'.")
        return self.pages[target_name]

    def switch_page(self, page_name: str) -> None:
        self.require_page(page_name)
        self.current_page_name = page_name

    def close_page(self, page_name: str | None = None) -> str:
        target_name = page_name or self.current_page_name
        page = self.require_page(target_name)
        page.close()
        del self.pages[target_name]
        if self.pages:
            self.current_page_name = next(reversed(self.pages))
        else:
            self.current_page_name = ""
        return target_name


@dataclass
class RuntimeState:
    project_root: Path
    playwright: Playwright
    run_name: str
    output_dir: Path
    logger: RunLogger
    state_writer: RunStateWriter
    plan_path: Path | None = None
    package_dir: Path | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    sessions: dict[str, BrowserSession] = field(default_factory=dict)
    step_counter: int = 0
    failure_screenshots: list[str] = field(default_factory=list)
    failure_htmls: list[str] = field(default_factory=list)
    failure_page_states: list[str] = field(default_factory=list)
    downloads: list[str] = field(default_factory=list)
    last_dialog_message: str | None = None
    pending_dialog: Dialog | None = None
    manual_confirmation_handler: Callable[[str], bool] | None = None
    sub_plan_stack: list[Path] = field(default_factory=list)

    def require_session(self, name: str) -> BrowserSession:
        if name not in self.sessions:
            raise KeyError(f"Browser session '{name}' does not exist.")
        return self.sessions[name]

    @property
    def plan_dir(self) -> Path:
        if self.plan_path is None:
            return self.project_root
        return self.plan_path.parent

    def next_step_number(self) -> int:
        self.step_counter += 1
        return self.step_counter

    def resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        if path.parts and path.parts[0] in {"resources", "output", "docs"} and self.package_dir is not None:
            return (self.package_dir / path).resolve()
        return (self.plan_dir / path).resolve()

    def resolve_output_path(self, raw_path: str, category: str | None = None) -> Path:
        package_output_dir = self.package_output_dir
        path = Path(raw_path)
        if path.is_absolute():
            raise ValueError(f"Runtime output paths must be relative to the current plan output directory: {raw_path}")
        if not path.parts:
            raise ValueError("Runtime output path cannot be empty.")
        if path.parts[0] in {"output", "resources", "docs", "sub-plans"}:
            raise ValueError(
                "Runtime output paths are relative to the plan output directory; "
                f"do not start with '{path.parts[0]}': {raw_path}"
            )

        category_root = (package_output_dir / category).resolve() if category else None
        if category and path.parts[0] != category:
            resolved_path = (category_root / path).resolve()
        else:
            resolved_path = (package_output_dir / path).resolve()

        if not _is_relative_to(resolved_path, package_output_dir):
            raise ValueError(f"Runtime output must stay under the current plan output directory: {raw_path}")
        if category_root is not None and not _is_relative_to(resolved_path, category_root):
            raise ValueError(f"Runtime output for this action must stay under output/{category}/: {raw_path}")
        return resolved_path

    @property
    def package_output_dir(self) -> Path:
        return ((self.package_dir or self.plan_dir) / "output").resolve()

    def close_all(self) -> None:
        try:
            for session in reversed(list(self.sessions.values())):
                for page_name in reversed(list(session.pages.keys())):
                    self._close_runtime_resource(
                        lambda page=session.pages[page_name]: page.close(),
                        browser=session.name,
                        resource="page",
                        name=page_name,
                    )
                self._close_runtime_resource(
                    session.context.close,
                    browser=session.name,
                    resource="context",
                )
                self._close_runtime_resource(
                    session.browser.close,
                    browser=session.name,
                    resource="browser",
                )
        finally:
            self.sessions.clear()

    def _close_runtime_resource(
        self,
        close: Callable[[], Any],
        *,
        browser: str,
        resource: str,
        name: str | None = None,
    ) -> None:
        try:
            close()
        except Exception as error:
            self.logger.log(
                "warning",
                "runtime resource close failed",
                browser=browser,
                resource=resource,
                name=name,
                error=str(error),
                error_type=type(error).__name__,
            )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
