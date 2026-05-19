from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Dialog, Download, Page, Playwright

from ai_automate_contro.support.logger import RunLogger
from ai_automate_contro.engine.state import RunStateWriter
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


@dataclass
class BrowserSession:
    name: str
    browser: Browser
    context: BrowserContext
    headed: bool = False
    pages: dict[str, Page] = field(default_factory=dict)
    current_page_name: str = "main"

    def register_page(self, page_name: str, page: Page, switch: bool = True) -> None:
        if page_name in self.pages:
            raise ValueError(f"浏览器会话 {self.name} 中已存在页面：{page_name}")
        self.pages[page_name] = page
        if switch:
            self.current_page_name = page_name

    def require_page(self, page_name: str | None = None) -> Page:
        target_name = page_name or self.current_page_name
        if target_name not in self.pages:
            raise KeyError(f"浏览器会话 {self.name} 中不存在页面：{target_name}")
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
    browser_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    browser_event_handlers: dict[str, list[tuple[Any, str, Any]]] = field(default_factory=dict)
    browser_event_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    browser_coverage_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_dialog_message: str | None = None
    pending_dialog: Dialog | None = None
    manual_confirmation_handler: Callable[[str], bool] | None = None
    interrupt_checker: Callable[[], bool] | None = None
    sub_plan_stack: list[Path] = field(default_factory=list)

    def interrupt_requested(self) -> bool:
        checker = self.interrupt_checker
        if checker is None:
            return False
        return bool(checker())

    def require_session(self, name: str) -> BrowserSession:
        if name not in self.sessions:
            raise KeyError(f"浏览器会话不存在：{name}")
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
        path = path_from_text(raw_path)
        if is_absolute_path_text(raw_path):
            return path.resolve()
        if path.parts and path.parts[0] in {"resources", "output", "docs"} and self.package_dir is not None:
            return (self.package_dir / path).resolve()
        return (self.plan_dir / path).resolve()

    def resolve_output_path(self, raw_path: str, category: str | None = None) -> Path:
        package_output_dir = self.package_output_dir
        path = path_from_text(raw_path)
        if is_absolute_path_text(raw_path):
            raise ValueError(f"运行输出路径必须相对于当前 plan output 目录：{raw_path}")
        if not path.parts:
            raise ValueError("运行输出路径不能为空。")
        if path.parts[0] in {"output", "resources", "docs", "sub-plans"}:
            raise ValueError(
                "运行输出路径已经相对于 plan output 目录，"
                f"不要以 {path.parts[0]!r} 开头：{raw_path}"
            )

        category_root = (package_output_dir / category).resolve() if category else None
        if category and path.parts[0] != category:
            resolved_path = (category_root / path).resolve()
        else:
            resolved_path = (package_output_dir / path).resolve()

        if not _is_relative_to(resolved_path, package_output_dir):
            raise ValueError(f"运行输出必须位于当前 plan output 目录下：{raw_path}")
        if category_root is not None and not _is_relative_to(resolved_path, category_root):
            raise ValueError(f"当前 action 的运行输出必须位于 output/{category}/ 下：{raw_path}")
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
