from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Dialog, Download, Page, Playwright

from keygen_automation.ai_registry import AiRegistry
from keygen_automation.logger import RunLogger


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
    plan_path: Path | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    sessions: dict[str, BrowserSession] = field(default_factory=dict)
    step_counter: int = 0
    failure_screenshots: list[str] = field(default_factory=list)
    downloads: list[str] = field(default_factory=list)
    last_dialog_message: str | None = None
    pending_dialog: Dialog | None = None
    ai_registry: AiRegistry | None = None

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
        return (self.plan_dir / path).resolve()

    def close_all(self) -> None:
        for session in reversed(list(self.sessions.values())):
            for page_name in reversed(list(session.pages.keys())):
                try:
                    session.pages[page_name].close()
                except Exception:
                    pass
            session.context.close()
            session.browser.close()
        self.sessions.clear()
