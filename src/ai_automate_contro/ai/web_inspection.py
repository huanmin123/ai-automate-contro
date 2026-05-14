from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from ai_automate_contro.support.paths import path_from_text


MAX_WEB_INSPECTION_ELEMENTS = 120
MAX_WEB_INSPECTION_TEXT_CHARS = 12_000
DEFAULT_VIEWPORT = {"width": 1365, "height": 900}
SUPPORTED_WAIT_UNTIL = {"commit", "domcontentloaded", "load", "networkidle"}


def inspect_web_page_tool(
    project_root: str | Path,
    *,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 15_000,
    wait_ms: int = 1_000,
    max_elements: int = 80,
    text_limit: int = 6_000,
    headed: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    target_url = _resolve_inspection_url(root, url)
    resolved_wait_until = _normalize_wait_until(wait_until)
    resolved_timeout_ms = _clamp_int(timeout_ms, minimum=1_000, maximum=60_000)
    resolved_wait_ms = _clamp_int(wait_ms, minimum=0, maximum=10_000)
    resolved_max_elements = _clamp_int(max_elements, minimum=1, maximum=MAX_WEB_INSPECTION_ELEMENTS)
    resolved_text_limit = _clamp_int(text_limit, minimum=200, maximum=MAX_WEB_INSPECTION_TEXT_CHARS)

    navigation_error = ""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        try:
            context = browser.new_context(viewport=DEFAULT_VIEWPORT)
            try:
                page = context.new_page()
                response = None
                try:
                    response = page.goto(
                        target_url,
                        wait_until=resolved_wait_until,
                        timeout=resolved_timeout_ms,
                    )
                except PlaywrightTimeoutError as error:
                    navigation_error = str(error)
                if resolved_wait_ms:
                    page.wait_for_timeout(resolved_wait_ms)

                data = page.evaluate(
                    PAGE_INSPECTION_SCRIPT,
                    {
                        "maxElements": resolved_max_elements,
                        "textLimit": resolved_text_limit,
                    },
                )
                data["status"] = response.status if response is not None else None
                data["navigation_error"] = navigation_error
            finally:
                context.close()
        finally:
            browser.close()

    auth = data.get("auth") if isinstance(data.get("auth"), dict) else {}
    next_actions = [
        "Use the returned selectors and labels as evidence before writing browser steps.",
        "If evidence is incomplete, ask the user for the missing page state instead of inventing selectors.",
    ]
    if auth.get("challenge_detected"):
        next_actions.insert(
            0,
            "A challenge or verification signal was detected. Ask the user to complete it, then continue with manual_confirm or saved storage_state.",
        )
    elif auth.get("login_fields_detected"):
        next_actions.insert(
            0,
            "Login fields were detected. Use user-provided variables/resources or ask the user for a manual login handoff; do not hardcode credentials.",
        )

    return {
        "ok": True,
        "tool": "inspect_web_page",
        "requested_url": url,
        "resolved_url": target_url,
        "wait_until": resolved_wait_until,
        "timeout_ms": resolved_timeout_ms,
        "wait_ms": resolved_wait_ms,
        "max_elements": resolved_max_elements,
        "text_limit": resolved_text_limit,
        "page": data,
        "next_actions": next_actions,
    }


def _resolve_inspection_url(project_root: Path, raw_url: str) -> str:
    text = str(raw_url).strip()
    if not text:
        raise ValueError("inspect_web_page 需要非空 url。")

    local_candidate = path_from_text(text)
    if local_candidate.is_absolute() or "://" not in text:
        if "://" in text and not local_candidate.is_absolute():
            return text
        resolved = local_candidate.resolve() if local_candidate.is_absolute() else (project_root / local_candidate).resolve()
        if not _is_relative_to(resolved, project_root):
            raise ValueError("本地检查路径必须位于项目根目录内。")
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"本地检查文件不存在：{resolved}")
        return resolved.as_uri()

    scheme = text.split("://", 1)[0].lower()
    if scheme not in {"http", "https", "file"}:
        raise ValueError("inspect_web_page 支持 http、https、file URL 或本地项目文件。")
    if scheme == "file":
        parsed = urlparse(text)
        local_path = Path(url2pathname(parsed.path)).resolve()
        if not _is_relative_to(local_path, project_root):
            raise ValueError("本地检查 file URL 必须位于项目根目录内。")
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"本地检查文件不存在：{local_path}")
    return text


def _normalize_wait_until(value: str) -> str:
    normalized = str(value or "domcontentloaded").strip().lower()
    if normalized not in SUPPORTED_WAIT_UNTIL:
        supported = ", ".join(sorted(SUPPORTED_WAIT_UNTIL))
        raise ValueError(f"不支持的 wait_until：{value}。支持值：{supported}。")
    return normalized


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = minimum
    return max(minimum, min(maximum, numeric))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


PAGE_INSPECTION_SCRIPT = r"""
(args) => {
  const maxElements = Math.max(1, Math.min(Number(args.maxElements) || 80, 120));
  const textLimit = Math.max(200, Math.min(Number(args.textLimit) || 6000, 12000));

  function clip(value, limit = 300) {
    const text = String(value ?? '').replace(/\s+/g, ' ').trim();
    return text.length > limit ? text.slice(0, limit) + '...' : text;
  }

  function attr(el, name) {
    const value = el.getAttribute(name);
    return value == null ? '' : String(value);
  }

  function selectorValue(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, (ch) => '\\' + ch.charCodeAt(0).toString(16) + ' ');
  }

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && Number(style.opacity || 1) !== 0
      && rect.width > 0
      && rect.height > 0;
  }

  function uniqueSelector(selector) {
    try {
      return document.querySelectorAll(selector).length === 1;
    } catch {
      return false;
    }
  }

  function cssPath(el) {
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
      const tag = current.tagName.toLowerCase();
      if (current.id) {
        parts.unshift('#' + cssEscape(current.id));
        break;
      }
      let nth = 1;
      let sibling = current;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName === current.tagName) nth += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + nth + ')');
      current = current.parentElement;
    }
    return parts.join(' > ');
  }

  function stableSelector(el) {
    const tag = el.tagName.toLowerCase();
    if (el.id) {
      const selector = '#' + cssEscape(el.id);
      if (uniqueSelector(selector)) return selector;
    }
    for (const name of ['data-testid', 'data-test', 'data-cy', 'name', 'aria-label', 'placeholder']) {
      const value = attr(el, name);
      if (!value) continue;
      const selector = tag + '[' + name + '="' + selectorValue(value) + '"]';
      if (uniqueSelector(selector)) return selector;
    }
    if (tag === 'a' && attr(el, 'href')) {
      const selector = 'a[href="' + selectorValue(attr(el, 'href')) + '"]';
      if (uniqueSelector(selector)) return selector;
    }
    return cssPath(el);
  }

  function labelFor(el) {
    if (el.id) {
      const label = document.querySelector('label[for="' + selectorValue(el.id) + '"]');
      if (label) return clip(label.innerText || label.textContent, 160);
    }
    const wrapper = el.closest('label');
    if (wrapper) return clip(wrapper.innerText || wrapper.textContent, 160);
    return '';
  }

  function elementSummary(el, extra = {}) {
    return {
      tag: el.tagName.toLowerCase(),
      selector: stableSelector(el),
      text: clip(el.innerText || el.textContent || '', 220),
      id: attr(el, 'id'),
      name: attr(el, 'name'),
      type: attr(el, 'type'),
      role: attr(el, 'role'),
      aria_label: attr(el, 'aria-label'),
      placeholder: attr(el, 'placeholder'),
      label: labelFor(el),
      visible: isVisible(el),
      ...extra,
    };
  }

  const headings = Array.from(document.querySelectorAll('h1,h2,h3'))
    .filter(isVisible)
    .slice(0, maxElements)
    .map((el) => elementSummary(el, { level: el.tagName.toLowerCase() }));

  const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
    .filter(isVisible)
    .slice(0, maxElements)
    .map((el) => {
      const summary = elementSummary(el, {
        required: Boolean(el.required),
        autocomplete: attr(el, 'autocomplete'),
      });
      if (el.tagName.toLowerCase() === 'select') {
        summary.options = Array.from(el.options || []).slice(0, 12).map((option) => clip(option.textContent, 80));
      }
      return summary;
    });

  const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]'))
    .filter(isVisible)
    .slice(0, maxElements)
    .map((el) => elementSummary(el, { value_text: clip(attr(el, 'value'), 160) }));

  const links = Array.from(document.querySelectorAll('a[href]'))
    .filter(isVisible)
    .slice(0, maxElements)
    .map((el) => elementSummary(el, { href: attr(el, 'href') }));

  const forms = Array.from(document.querySelectorAll('form'))
    .slice(0, Math.min(maxElements, 20))
    .map((form) => ({
      selector: stableSelector(form),
      id: attr(form, 'id'),
      name: attr(form, 'name'),
      method: attr(form, 'method') || 'get',
      action: form.action || attr(form, 'action'),
      visible: isVisible(form),
      controls: Array.from(form.querySelectorAll('input, textarea, select, button'))
        .filter(isVisible)
        .slice(0, 24)
        .map((el) => elementSummary(el)),
    }));

  const tables = Array.from(document.querySelectorAll('table'))
    .filter(isVisible)
    .slice(0, Math.min(maxElements, 20))
    .map((table) => ({
      selector: stableSelector(table),
      headers: Array.from(table.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
        .slice(0, 20)
        .map((el) => clip(el.innerText || el.textContent, 120)),
      row_count: table.querySelectorAll('tr').length,
      visible: isVisible(table),
    }));

  const bodyText = clip(document.body ? document.body.innerText : '', textLimit);
  const lowerBody = bodyText.toLowerCase();
  const challengeKeywords = [
    'captcha', 'recaptcha', 'hcaptcha', 'turnstile', 'cloudflare',
    'verify you are human', 'human verification', 'security check',
    '验证码', '人机验证', '安全验证', '二次验证', '两步验证',
  ];
  const loginKeywords = ['login', 'log in', 'sign in', '登录', '登陆'];
  const keywordHits = challengeKeywords.filter((item) => lowerBody.includes(item.toLowerCase()));
  const loginKeywordHits = loginKeywords.filter((item) => lowerBody.includes(item.toLowerCase()));
  const challengeSelectors = [
    'iframe[src*="captcha" i]',
    'iframe[src*="challenge" i]',
    '[id*="captcha" i]',
    '[class*="captcha" i]',
    '[name*="captcha" i]',
    '[id*="challenge" i]',
    '[class*="challenge" i]',
    '[data-sitekey]',
  ];
  const challengeElementCount = challengeSelectors.reduce((total, selector) => {
    try {
      return total + document.querySelectorAll(selector).length;
    } catch {
      return total;
    }
  }, 0);
  const passwordFieldCount = inputs.filter((item) => String(item.type).toLowerCase() === 'password').length;

  return {
    title: document.title || '',
    final_url: window.location.href,
    body_text_preview: bodyText,
    counts: {
      headings: headings.length,
      inputs: inputs.length,
      buttons: buttons.length,
      links: links.length,
      forms: forms.length,
      tables: tables.length,
    },
    headings,
    forms,
    inputs,
    buttons,
    links,
    tables,
    auth: {
      login_fields_detected: passwordFieldCount > 0,
      login_keyword_hits: loginKeywordHits,
      password_field_count: passwordFieldCount,
      challenge_detected: keywordHits.length > 0 || challengeElementCount > 0,
      challenge_keyword_hits: keywordHits,
      challenge_element_count: challengeElementCount,
      requires_user_action: keywordHits.length > 0 || challengeElementCount > 0,
    },
  };
}
"""
