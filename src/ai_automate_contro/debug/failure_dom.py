from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.workspace_io import is_relative_to
from ai_automate_contro.support.paths import path_from_text


MAX_FAILURE_HTML_SUMMARY_BYTES = 256_000
DOM_SUMMARY_TAGS = {"a", "button", "form", "input", "label", "option", "select", "textarea"}
DOM_TEXT_IGNORED_TAGS = {"head", "script", "style", "template"}


def summarize_failure_html(run_output_dir: Path, raw_html_path: str) -> dict[str, Any]:
    html_path = path_from_text(raw_html_path).resolve()
    if not is_relative_to(html_path, run_output_dir.resolve()):
        return {}
    if not html_path.exists() or not html_path.is_file():
        return {}
    raw_text, truncated = read_failure_html_preview(html_path)
    parser = FailureDomSummaryParser()
    parser.feed(raw_text)
    return {
        "path": str(html_path),
        "relative_path": str(html_path.relative_to(run_output_dir.resolve())),
        "truncated": truncated,
        "elements": parser.elements[:80],
        "text_snippets": parser.text_snippets[:40],
    }


def read_failure_html_preview(path: Path) -> tuple[str, bool]:
    with path.open("rb") as file:
        data = file.read(MAX_FAILURE_HTML_SUMMARY_BYTES + 1)
    truncated = len(data) > MAX_FAILURE_HTML_SUMMARY_BYTES
    if truncated:
        data = data[:MAX_FAILURE_HTML_SUMMARY_BYTES]
    return data.decode("utf-8", errors="replace"), truncated


class FailureDomSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, Any]] = []
        self.text_snippets: list[str] = []
        self._capture_stack: list[dict[str, Any]] = []
        self._ignored_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in DOM_TEXT_IGNORED_TAGS:
            self._ignored_stack.append(normalized_tag)
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if normalized_tag in DOM_SUMMARY_TAGS:
            element = {
                "tag": normalized_tag,
                "selector_hint": selector_hint(normalized_tag, attrs_dict),
                "attrs": interesting_attrs(attrs_dict),
                "text": "",
            }
            self.elements.append(element)
            if normalized_tag in {"a", "button", "label", "option", "textarea"}:
                self._capture_stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._ignored_stack and self._ignored_stack[-1] == normalized_tag:
            self._ignored_stack.pop()
        if normalized_tag not in {"a", "button", "label", "option", "textarea"}:
            return
        if self._capture_stack:
            self._capture_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored_stack:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_stack:
            element = self._capture_stack[-1]
            current = str(element.get("text", ""))
            element["text"] = (current + " " + text).strip()[:200]
        if len(text) >= 2 and len(self.text_snippets) < 80:
            self.text_snippets.append(text[:200])


def interesting_attrs(attrs: dict[str, str]) -> dict[str, str]:
    keys = [
        "id",
        "name",
        "type",
        "class",
        "placeholder",
        "autocomplete",
        "aria-label",
        "role",
        "href",
        "for",
        "value",
    ]
    result: dict[str, str] = {}
    for key in keys:
        value = attrs.get(key)
        if not value:
            continue
        result[key] = value
    return result


def selector_hint(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get("id"):
        return f"#{attrs['id']}"
    if attrs.get("name"):
        return f"{tag}[name='{attrs['name']}']"
    if attrs.get("autocomplete"):
        return f"{tag}[autocomplete='{attrs['autocomplete']}']"
    if attrs.get("placeholder"):
        return f"{tag}[placeholder='{attrs['placeholder']}']"
    if attrs.get("aria-label"):
        return f"{tag}[aria-label='{attrs['aria-label']}']"
    return tag
