from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


@dataclass(frozen=True)
class BrowserConfig:
    headed: bool = False
    slow_mo_ms: int = 0
    timeout_ms: int = 15_000


@contextmanager
def open_page(config: BrowserConfig) -> Iterator[tuple[Playwright, Browser, BrowserContext, Page]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not config.headed,
            slow_mo=config.slow_mo_ms,
        )
        context = browser.new_context()
        context.set_default_timeout(config.timeout_ms)
        page = context.new_page()

        try:
            yield playwright, browser, context, page
        finally:
            context.close()
            browser.close()
