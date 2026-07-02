from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.desktop.backends.native_elements import _limit_text, _regex_matches


def _matching_windows(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    return [window for window in windows if _window_matches(window, query)]


def _window_diagnostics(
    windows: list[dict[str, Any]],
    query: dict[str, Any],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query": dict(query),
        "total_windows": len(windows),
        "match_count": len(matches),
        "matches": [_compact_window_candidate(window) for window in matches[:5]],
        "near_matches": _near_window_matches(windows, query),
    }


def _near_window_matches(windows: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for window in windows:
        score, matched_fields, missing_fields = _window_match_score(window, query)
        scored.append(
            {
                "score": score,
                "matched_fields": matched_fields,
                "missing_fields": missing_fields,
                "window": _compact_window_candidate(window),
            }
        )
    scored.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            len(item.get("missing_fields", [])),
            not bool(item.get("window", {}).get("focused")),
        )
    )
    return scored[:5]


def _window_match_score(window: dict[str, Any], query: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    checks: list[tuple[str, bool]] = []
    if "window_id" in query:
        checks.append(("window_id", str(window.get("id")) == str(query.get("window_id"))))
    if "title" in query:
        checks.append(("title", str(window.get("title", "")) == str(query.get("title"))))
    if "title_contains" in query:
        checks.append(("title_contains", str(query.get("title_contains")) in str(window.get("title", ""))))
    if "title_regex" in query:
        checks.append(("title_regex", _regex_matches(str(query.get("title_regex")), str(window.get("title", "")))))
    for query_field, window_field in (
        ("app", "app"),
        ("process", "process_name"),
        ("process_name", "process_name"),
        ("class_name", "class_name"),
    ):
        if query_field in query:
            checks.append(
                (
                    query_field,
                    str(query.get(query_field)).lower() in str(window.get(window_field, "")).lower(),
                )
            )
    matched_fields = [field for field, ok in checks if ok]
    missing_fields = [field for field, ok in checks if not ok]
    score = len(matched_fields) * 10 - len(missing_fields) * 2
    if bool(window.get("focused")):
        score += 1
    return score, matched_fields, missing_fields


def _compact_window_candidate(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": window.get("id", ""),
        "title": _limit_text(str(window.get("title", "")), 120),
        "app": window.get("app", ""),
        "process_name": window.get("process_name", ""),
        "class_name": window.get("class_name", ""),
        "focused": bool(window.get("focused")),
        "visible": bool(window.get("visible", True)),
        "bounds": window.get("bounds", {}),
    }


def _window_matches(window: dict[str, Any], query: dict[str, Any]) -> bool:
    if "window_id" in query and str(window.get("id")) != str(query.get("window_id")):
        return False
    if "title" in query and str(window.get("title", "")) != str(query.get("title")):
        return False
    if "title_contains" in query and str(query.get("title_contains")) not in str(window.get("title", "")):
        return False
    if "title_regex" in query and not re.search(str(query.get("title_regex")), str(window.get("title", ""))):
        return False
    for query_field, window_field in (
        ("app", "app"),
        ("process", "process_name"),
        ("process_name", "process_name"),
        ("class_name", "class_name"),
    ):
        if query_field in query and str(query.get(query_field)).lower() not in str(window.get(window_field, "")).lower():
            return False
    return True
