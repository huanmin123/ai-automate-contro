from __future__ import annotations

import json
from typing import Any

from ai_automate_contro.engine.desktop.locators import ELEMENT_LOCATOR_FIELDS, WINDOW_QUERY_FIELDS


TARGETING_SCHEMA_VERSION = 1
MAX_TARGET_CANDIDATES = 12
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def build_observation_targeting(
    *,
    desktop: str,
    window_query: dict[str, Any] | None,
    element_locator: dict[str, Any] | None,
    selected_window: dict[str, Any] | None,
    elements_payload: dict[str, Any] | None,
    screenshot_payload: dict[str, Any] | None = None,
    capability_matrix: dict[str, Any] | None = None,
    limit: int = MAX_TARGET_CANDIDATES,
) -> dict[str, Any]:
    normalized_window_query = _clean_fields(window_query or {}, WINDOW_QUERY_FIELDS)
    normalized_element_locator = _clean_fields(element_locator or {}, ELEMENT_LOCATOR_FIELDS)
    selected = _compact_window(selected_window or {})
    elements = elements_payload if isinstance(elements_payload, dict) else {}
    capabilities = capability_matrix.get("capabilities") if isinstance(capability_matrix, dict) else {}
    candidates: list[dict[str, Any]] = []

    if selected:
        candidates.append(
            _window_context_candidate(
                desktop=desktop,
                selected_window=selected,
                window_query=normalized_window_query,
            )
        )

    matches = elements.get("matches") if isinstance(elements.get("matches"), list) else []
    for index, element in enumerate(matches[:8]):
        if isinstance(element, dict):
            candidates.append(
                _semantic_element_candidate(
                    desktop=desktop,
                    source="element_match",
                    source_index=index,
                    element=element,
                    selected_window=selected,
                    window_query=normalized_window_query,
                    requested_locator=normalized_element_locator,
                    base_score=90,
                    reason="Element Locator matched this control in the selected window.",
                )
            )

    near_matches = elements.get("near_matches") if isinstance(elements.get("near_matches"), list) else []
    for index, near_match in enumerate(near_matches[:8]):
        if not isinstance(near_match, dict):
            continue
        element = near_match.get("element") if isinstance(near_match.get("element"), dict) else {}
        if not element:
            continue
        candidates.append(
            _semantic_element_candidate(
                desktop=desktop,
                source="element_near_match",
                source_index=index,
                element=element,
                selected_window=selected,
                window_query=normalized_window_query,
                requested_locator=normalized_element_locator,
                base_score=55 + min(25, _int(near_match.get("score"), 0)),
                reason="Requested Element Locator did not fully match; this is the closest semantic control candidate.",
                near_match=near_match,
            )
        )

    if isinstance(screenshot_payload, dict) and screenshot_payload.get("ok"):
        candidates.append(
            _screenshot_evidence_candidate(
                desktop=desktop,
                screenshot_payload=screenshot_payload,
                selected_window=selected,
                window_query=normalized_window_query,
            )
        )

    sorted_candidates = _dedupe_and_sort(candidates, limit=max(1, min(MAX_TARGET_CANDIDATES, int(limit or MAX_TARGET_CANDIDATES))))
    return _targeting_payload(
        query={
            "window_query": normalized_window_query,
            "element_locator": normalized_element_locator,
        },
        candidates=sorted_candidates,
        capabilities=capabilities if isinstance(capabilities, dict) else {},
    )


def build_vision_targeting(
    *,
    desktop: str,
    vision_type: str,
    match_query: dict[str, Any] | None = None,
    template_path: str = "",
    source_target: str = "",
    source_bounds: dict[str, Any] | None = None,
    coordinate_profile: dict[str, Any] | None = None,
    coordinate_diagnostics: dict[str, Any] | None = None,
    target_query: dict[str, Any] | None = None,
    locator: dict[str, Any] | None = None,
    matches: list[dict[str, Any]] | None = None,
    selected_match: dict[str, Any] | None = None,
    limit: int = MAX_TARGET_CANDIDATES,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    selected_key = _candidate_match_key(selected_match or {})
    for index, match in enumerate((matches or [])[:MAX_TARGET_CANDIDATES]):
        if not isinstance(match, dict):
            continue
        candidates.append(
            _vision_candidate(
                desktop=desktop,
                vision_type=vision_type,
                source_index=index,
                match=match,
                selected=_candidate_match_key(match) == selected_key,
                match_query=match_query or {},
                template_path=template_path,
                source_target=source_target,
                source_bounds=source_bounds or {},
                coordinate_profile=coordinate_profile or {},
                coordinate_diagnostics=coordinate_diagnostics or {},
                target_query=target_query or {},
                locator=locator or {},
            )
        )
    sorted_candidates = _dedupe_and_sort(candidates, limit=max(1, min(MAX_TARGET_CANDIDATES, int(limit or MAX_TARGET_CANDIDATES))))
    return _targeting_payload(
        query={
            "vision_type": vision_type,
            "match_query": dict(match_query or {}),
            "template_path": template_path,
            "source_target": source_target,
            "window_query": _clean_fields(target_query or {}, WINDOW_QUERY_FIELDS),
            "element_locator": _clean_fields(locator or {}, ELEMENT_LOCATOR_FIELDS),
        },
        candidates=sorted_candidates,
        capabilities={"vision": {"candidate_source": vision_type}},
    )


def build_failure_targeting(
    *,
    desktop: str,
    target: dict[str, Any] | None,
    window_diagnostics: dict[str, Any] | None,
    element_diagnostics: dict[str, Any] | None,
    capability_matrix: dict[str, Any] | None = None,
    screenshot_path: str = "",
    limit: int = MAX_TARGET_CANDIDATES,
) -> dict[str, Any]:
    target_payload = target if isinstance(target, dict) else {}
    window_payload = window_diagnostics if isinstance(window_diagnostics, dict) else {}
    element_payload = element_diagnostics if isinstance(element_diagnostics, dict) else {}
    window_query = _clean_fields(
        window_payload.get("query") if isinstance(window_payload.get("query"), dict) else target_payload,
        WINDOW_QUERY_FIELDS,
    )
    element_locator = _clean_fields(
        element_payload.get("locator") if isinstance(element_payload.get("locator"), dict) else target_payload,
        ELEMENT_LOCATOR_FIELDS,
    )
    selected_window = window_payload.get("current_window") if isinstance(window_payload.get("current_window"), dict) else {}
    candidates: list[dict[str, Any]] = []
    if selected_window:
        candidates.append(
            _window_context_candidate(
                desktop=desktop,
                selected_window=selected_window,
                window_query=window_query,
                source="failure_current_window",
                base_score=35,
            )
        )
    for index, near_match in enumerate(_as_list(window_payload.get("near_matches"))[:5]):
        window = near_match.get("window") if isinstance(near_match.get("window"), dict) else {}
        if window:
            candidates.append(
                _window_repair_candidate(
                    desktop=desktop,
                    source_index=index,
                    window=window,
                    current_query=window_query,
                    near_match=near_match,
                )
            )
    observation_targeting = build_observation_targeting(
        desktop=desktop,
        window_query=window_query,
        element_locator=element_locator,
        selected_window=selected_window,
        elements_payload=element_payload,
        screenshot_payload={"ok": bool(screenshot_path), "path": screenshot_path} if screenshot_path else {},
        capability_matrix=capability_matrix or {},
        limit=limit,
    )
    candidates.extend(observation_targeting.get("candidates", []))
    sorted_candidates = _dedupe_and_sort(candidates, limit=max(1, min(MAX_TARGET_CANDIDATES, int(limit or MAX_TARGET_CANDIDATES))))
    return _targeting_payload(
        query={
            "window_query": window_query,
            "element_locator": element_locator,
            "target": dict(target_payload),
        },
        candidates=sorted_candidates,
        capabilities=(
            capability_matrix.get("capabilities")
            if isinstance(capability_matrix, dict) and isinstance(capability_matrix.get("capabilities"), dict)
            else {}
        ),
    )


def compact_targeting(payload: Any, *, limit: int = 5) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    return {
        "schema_version": payload.get("schema_version", ""),
        "kind": payload.get("kind", ""),
        "candidate_count": int(payload.get("candidate_count", 0) or 0),
        "best_strategy": payload.get("summary", {}).get("best_strategy", "") if isinstance(payload.get("summary"), dict) else "",
        "best_confidence": payload.get("summary", {}).get("best_confidence", "") if isinstance(payload.get("summary"), dict) else "",
        "candidates": [
            {
                "id": candidate.get("id", ""),
                "candidate_id": candidate.get("candidate_id", candidate.get("id", "")),
                "source": candidate.get("source", ""),
                "strategy": candidate.get("strategy", ""),
                "confidence": candidate.get("confidence", ""),
                "score": candidate.get("score", 0),
                "locator": candidate.get("locator", {}) if isinstance(candidate.get("locator"), dict) else {},
                "bounds": candidate.get("bounds", {}) if isinstance(candidate.get("bounds"), dict) else {},
                "point": candidate.get("point", {}) if isinstance(candidate.get("point"), dict) else {},
                "screen_clickable": candidate.get("screen_clickable", ""),
                "reason": candidate.get("reason", ""),
            }
            for candidate in candidates[: max(1, int(limit or 5))]
            if isinstance(candidate, dict)
        ],
    }


def extract_target_candidates_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if value.get("kind") == "desktop_target_candidates" or isinstance(value.get("candidates"), list):
        return value
    nested = value.get("target_candidates")
    if isinstance(nested, dict):
        return nested
    return {}


def find_target_candidate(value: Any, candidate_id: str = "") -> dict[str, Any]:
    payload = extract_target_candidates_payload(value)
    if not payload:
        return {}
    if candidate_id in {"", "best", "best_candidate"}:
        candidate = payload.get("best_candidate")
        return dict(candidate) if isinstance(candidate, dict) else {}
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("candidate_id") or candidate.get("id") or "") == str(candidate_id):
            return dict(candidate)
    return {}


def confidence_meets(candidate: dict[str, Any], minimum: str) -> bool:
    confidence = str(candidate.get("confidence") or "low")
    minimum_confidence = str(minimum or "medium")
    return CONFIDENCE_RANK.get(confidence, 0) >= CONFIDENCE_RANK.get(minimum_confidence, 2)


def _semantic_element_candidate(
    *,
    desktop: str,
    source: str,
    source_index: int,
    element: dict[str, Any],
    selected_window: dict[str, Any],
    window_query: dict[str, Any],
    requested_locator: dict[str, Any],
    base_score: int,
    reason: str,
    near_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selector_hint = _best_selector_hint(element)
    locator = _clean_fields(
        selector_hint.get("locator") if isinstance(selector_hint.get("locator"), dict) else requested_locator,
        ELEMENT_LOCATOR_FIELDS,
    )
    if not locator:
        locator = _fallback_locator_from_element(element)
    resolved_window_query = _action_window_query(window_query, selected_window)
    bounds = _bounds(element.get("bounds"))
    point = _bounds_center(bounds)
    score = base_score + _selector_hint_score(selector_hint)
    if bool(element.get("visible", False)):
        score += 5
    if bool(element.get("enabled", False)):
        score += 5
    confidence = _semantic_confidence(score=score, selector_hint=selector_hint, source=source, locator=locator)
    candidate_id = f"{source}-{source_index}"
    payload = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "source": source,
        "strategy": "semantic_locator",
        "confidence": confidence,
        "score": score,
        "reason": reason,
        "window_query": resolved_window_query,
        "locator": locator,
        "locator_stability": selector_hint.get("stability", ""),
        "locator_unique": bool(selector_hint.get("unique", False)),
        "locator_match_count": _int(selector_hint.get("match_count"), 0),
        "element": _compact_element(element),
        "window": _compact_window(selected_window),
        "bounds": bounds,
        "point": point,
        "recommended_use": "Use desktop_element with this locator; use desktop_input target=element_center only when a real mouse event is required.",
        "action_templates": _semantic_action_templates(desktop, resolved_window_query, locator, bounds),
    }
    if near_match:
        payload["near_match"] = {
            "score": _int(near_match.get("score"), 0),
            "matched_fields": near_match.get("matched_fields", []) if isinstance(near_match.get("matched_fields"), list) else [],
            "missing_fields": near_match.get("missing_fields", []) if isinstance(near_match.get("missing_fields"), list) else [],
            "reasons": near_match.get("reasons", []) if isinstance(near_match.get("reasons"), list) else [],
        }
    return payload


def _window_context_candidate(
    *,
    desktop: str,
    selected_window: dict[str, Any],
    window_query: dict[str, Any],
    source: str = "selected_window",
    base_score: int = 50,
) -> dict[str, Any]:
    window = _compact_window(selected_window)
    resolved_query = _action_window_query(window_query, window)
    score = base_score + (15 if window_query else 0) + (5 if window.get("focused") else 0)
    return {
        "id": source,
        "candidate_id": source,
        "source": source,
        "strategy": "window_context",
        "confidence": "medium" if resolved_query else "low",
        "score": score,
        "reason": "Selected window can anchor later desktop_window, desktop_element, screenshot, or vision steps.",
        "window_query": resolved_query,
        "window": window,
        "bounds": _bounds(window.get("bounds")),
        "point": _bounds_center(_bounds(window.get("bounds"))),
        "recommended_use": "Use this window query before enumerating controls or taking a window screenshot.",
        "action_templates": _window_action_templates(desktop, resolved_query),
    }


def _window_repair_candidate(
    *,
    desktop: str,
    source_index: int,
    window: dict[str, Any],
    current_query: dict[str, Any],
    near_match: dict[str, Any],
) -> dict[str, Any]:
    compact_window = _compact_window(window)
    query = _candidate_window_query(compact_window)
    score = 55 + min(30, _int(near_match.get("score"), 0) * 3)
    candidate_id = f"window-near-match-{source_index}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "source": "window_near_match",
        "strategy": "window_query_repair",
        "confidence": "medium" if query else "low",
        "score": score,
        "reason": "Failed Window Query had no exact match; this nearby window can be used to repair the query.",
        "from": current_query,
        "to": query,
        "window_query": query,
        "window": compact_window,
        "bounds": _bounds(compact_window.get("bounds")),
        "point": _bounds_center(_bounds(compact_window.get("bounds"))),
        "near_match": {
            "score": _int(near_match.get("score"), 0),
            "matched_fields": near_match.get("matched_fields", []) if isinstance(near_match.get("matched_fields"), list) else [],
            "missing_fields": near_match.get("missing_fields", []) if isinstance(near_match.get("missing_fields"), list) else [],
        },
        "action_templates": _window_action_templates(desktop, query),
    }


def _screenshot_evidence_candidate(
    *,
    desktop: str,
    screenshot_payload: dict[str, Any],
    selected_window: dict[str, Any],
    window_query: dict[str, Any],
) -> dict[str, Any]:
    resolved_query = _action_window_query(window_query, selected_window)
    path = str(screenshot_payload.get("path") or "")
    return {
        "id": "screenshot-evidence",
        "candidate_id": "screenshot-evidence",
        "source": "screenshot",
        "strategy": "visual_evidence",
        "confidence": "low",
        "score": 20,
        "reason": "Screenshot is available for visual inspection, OCR, template matching, or manual confirmation.",
        "window_query": resolved_query,
        "window": _compact_window(selected_window),
        "screenshot_path": path,
        "recommended_use": "Use desktop_vision or manual_confirm before clicking from screenshot-only evidence.",
        "action_templates": [],
    }


def _vision_candidate(
    *,
    desktop: str,
    vision_type: str,
    source_index: int,
    match: dict[str, Any],
    selected: bool,
    match_query: dict[str, Any],
    template_path: str,
    source_target: str,
    source_bounds: dict[str, Any],
    coordinate_profile: dict[str, Any],
    coordinate_diagnostics: dict[str, Any],
    target_query: dict[str, Any],
    locator: dict[str, Any],
) -> dict[str, Any]:
    bounds = _bounds(match.get("bounds"))
    point = _point(match.get("point")) or _bounds_center(bounds)
    numeric_score = _numeric_match_score(match)
    score = int(numeric_score * 100) + (10 if selected else 0)
    confidence = "high" if numeric_score >= 0.85 else ("medium" if numeric_score >= 0.6 else "low")
    if vision_type == "locate_text" and _int(match.get("confidence"), 0) >= 80:
        confidence = "high"
    screen_clickable = _screen_clickable(coordinate_profile)
    reason = (
        "Visual/OCR match produced screen-global bounds. Use as a coordinate fallback when semantic locators are unavailable."
        if screen_clickable
        else "Visual/OCR match came from an offline/source image. Use it as evidence only; it is not a direct screen click target."
    )
    candidate_id = f"vision-match-{source_index}"
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "source": "vision_match",
        "strategy": "visual_bounds",
        "confidence": confidence,
        "score": score,
        "reason": reason,
        "selected": selected,
        "vision_type": vision_type,
        "match_query": dict(match_query),
        "template_path": template_path,
        "source_target": source_target,
        "source_bounds": _bounds(source_bounds),
        "coordinate_profile": dict(coordinate_profile),
        "screen_clickable": screen_clickable,
        "local_bounds": _bounds(match.get("local_bounds")),
        "local_point": _point(match.get("local_point")) or {},
        "coordinate_diagnostics": dict(coordinate_diagnostics),
        "window_query": _clean_fields(target_query, WINDOW_QUERY_FIELDS),
        "locator": _clean_fields(locator, ELEMENT_LOCATOR_FIELDS),
        "text": str(match.get("text") or ""),
        "bounds": bounds,
        "point": point,
        "recommended_use": (
            "Prefer desktop_element if a semantic locator exists; otherwise click with desktop_input target=bounds_center after confidence review."
            if screen_clickable
            else "This visual match came from an offline/source image; use it as evidence only, not as a direct screen click target."
        ),
        "action_templates": _visual_action_templates(desktop, bounds) if screen_clickable else [],
    }


def _targeting_payload(
    *,
    query: dict[str, Any],
    candidates: list[dict[str, Any]],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    best = candidates[0] if candidates else {}
    return {
        "schema_version": TARGETING_SCHEMA_VERSION,
        "kind": "desktop_target_candidates",
        "query": query,
        "strategy_order": [
            "semantic_locator",
            "window_context",
            "window_query_repair",
            "visual_bounds",
            "visual_evidence",
            "manual_confirm",
        ],
        "candidate_count": len(candidates),
        "best_candidate": best,
        "candidates": candidates,
        "summary": {
            "best_strategy": best.get("strategy", "") if isinstance(best, dict) else "",
            "best_confidence": best.get("confidence", "") if isinstance(best, dict) else "",
            "has_semantic_candidate": any(item.get("strategy") == "semantic_locator" for item in candidates),
            "has_visual_candidate": any(item.get("strategy") == "visual_bounds" for item in candidates),
            "has_window_candidate": any(item.get("strategy") in {"window_context", "window_query_repair"} for item in candidates),
            "manual_confirm_recommended": not candidates or (
                bool(candidates) and str(best.get("confidence", "")) == "low"
            ),
        },
        "capabilities_used": _compact_capabilities(capabilities),
    }


def _semantic_action_templates(
    desktop: str,
    window_query: dict[str, Any],
    locator: dict[str, Any],
    bounds: dict[str, Any],
) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    if window_query and locator:
        templates.append(_with_desktop({"action": "desktop_element", "type": "find", **window_query, **locator}, desktop))
        templates.append(
            _with_desktop({"action": "desktop_input", "type": "click", "target": "element_center", **window_query, **locator}, desktop)
        )
    if bounds:
        templates.append(_with_desktop({"action": "desktop_input", "type": "click", "target": "bounds_center", "bounds": bounds}, desktop))
    return templates


def _window_action_templates(desktop: str, window_query: dict[str, Any]) -> list[dict[str, Any]]:
    if not window_query:
        return []
    return [
        _with_desktop({"action": "desktop_window", "type": "focus", **window_query}, desktop),
        _with_desktop({"action": "desktop_capture", "type": "screenshot", "target": "window", "path": "window.png", **window_query}, desktop),
    ]


def _visual_action_templates(desktop: str, bounds: dict[str, Any]) -> list[dict[str, Any]]:
    if not bounds:
        return []
    return [_with_desktop({"action": "desktop_input", "type": "click", "target": "bounds_center", "bounds": bounds}, desktop)]


def _screen_clickable(coordinate_profile: dict[str, Any]) -> bool:
    source = coordinate_profile.get("source") if isinstance(coordinate_profile, dict) else {}
    if isinstance(source, dict) and "screen_clickable" in source:
        return bool(source.get("screen_clickable"))
    source_kind = str(source.get("kind") or "") if isinstance(source, dict) else ""
    return source_kind not in {"source_path", "image", "offline_image"}


def _with_desktop(template: dict[str, Any], desktop: str) -> dict[str, Any]:
    if desktop:
        return {"desktop": desktop, **template}
    return template


def _action_window_query(window_query: dict[str, Any], selected_window: dict[str, Any]) -> dict[str, Any]:
    query = _clean_fields(window_query, WINDOW_QUERY_FIELDS)
    if query:
        return query
    window_id = str(selected_window.get("id") or "")
    if window_id:
        return {"window_id": window_id}
    title = str(selected_window.get("title") or "")
    process_name = str(selected_window.get("process_name") or selected_window.get("app") or "")
    if title:
        query = {"title_contains": title}
        if process_name:
            query["process_name"] = process_name
        return query
    if process_name:
        return {"process_name": process_name}
    return {}


def _candidate_window_query(window: dict[str, Any]) -> dict[str, Any]:
    title = str(window.get("title") or "")
    process_name = str(window.get("process_name") or window.get("app") or "")
    class_name = str(window.get("class_name") or "")
    if title:
        query = {"title_contains": title}
        if process_name:
            query["process_name"] = process_name
        return query
    if process_name:
        return {"process_name": process_name}
    if class_name:
        return {"class_name": class_name}
    return {}


def _best_selector_hint(element: dict[str, Any]) -> dict[str, Any]:
    hints = element.get("selector_hints") if isinstance(element.get("selector_hints"), list) else []
    candidates = [hint for hint in hints if isinstance(hint, dict) and isinstance(hint.get("locator"), dict)]
    if not candidates:
        return {}
    candidates.sort(
        key=lambda hint: (
            -_stability_rank(str(hint.get("stability") or "")),
            0 if bool(hint.get("unique")) else 1,
            _int(hint.get("match_count"), 999),
        )
    )
    return dict(candidates[0])


def _fallback_locator_from_element(element: dict[str, Any]) -> dict[str, Any]:
    automation_id = str(element.get("automation_id") or "")
    control_type = str(element.get("control_type") or "")
    name = str(element.get("name") or "")
    text = str(element.get("text") or "")
    role = str(element.get("role") or "")
    class_name = str(element.get("class_name") or "")
    if automation_id:
        locator = {"automation_id": automation_id}
        if control_type:
            locator["control_type"] = control_type
        return locator
    if name:
        locator = {"name": name}
        if control_type:
            locator["control_type"] = control_type
        return locator
    if text:
        locator = {"text": text}
        if control_type:
            locator["control_type"] = control_type
        return locator
    if role:
        return {"role": role}
    if class_name:
        return {"element_class_name": class_name}
    return {}


def _semantic_confidence(*, score: int, selector_hint: dict[str, Any], source: str, locator: dict[str, Any]) -> str:
    stable = str(selector_hint.get("stability") or "")
    unique = bool(selector_hint.get("unique"))
    if source == "element_match" and stable == "high" and unique:
        return "high"
    if source == "element_match" and locator and "element_id" not in locator and score >= 85:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def _selector_hint_score(selector_hint: dict[str, Any]) -> int:
    if not selector_hint:
        return 0
    score = _stability_rank(str(selector_hint.get("stability") or "")) * 5
    if bool(selector_hint.get("unique")):
        score += 10
    if _int(selector_hint.get("match_count"), 0) == 1:
        score += 5
    return score


def _numeric_match_score(match: dict[str, Any]) -> float:
    for field in ("score", "confidence"):
        value = match.get(field)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 1:
            return max(0.0, min(1.0, number / 100))
        return max(0.0, min(1.0, number))
    return 0.0


def _compact_window(window: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(window, dict) or not window:
        return {}
    return {
        "id": window.get("id", ""),
        "title": _limit_text(str(window.get("title") or ""), 160),
        "app": window.get("app", ""),
        "process_name": window.get("process_name", ""),
        "class_name": window.get("class_name", ""),
        "pid": window.get("pid", ""),
        "focused": bool(window.get("focused")),
        "visible": bool(window.get("visible", True)),
        "bounds": _bounds(window.get("bounds")),
    }


def _compact_element(element: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": element.get("index", ""),
        "id": element.get("id", ""),
        "name": _limit_text(str(element.get("name") or ""), 160),
        "text": _limit_text(str(element.get("text") or ""), 160),
        "value": _limit_text(str(element.get("value") or ""), 160),
        "automation_id": element.get("automation_id", ""),
        "control_type": element.get("control_type", ""),
        "role": element.get("role", ""),
        "class_name": element.get("class_name", ""),
        "enabled": bool(element.get("enabled", False)),
        "visible": bool(element.get("visible", False)),
        "focused": bool(element.get("focused", False)),
        "bounds": _bounds(element.get("bounds")),
        "depth": element.get("depth", 0),
        "parent_id": element.get("parent_id", ""),
    }


def _clean_fields(value: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {field: value[field] for field in fields if field in value and value[field] not in (None, "")}


def _bounds(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    bounds = {
        "x": _int(value.get("x"), 0),
        "y": _int(value.get("y"), 0),
        "width": _int(value.get("width"), 0),
        "height": _int(value.get("height"), 0),
    }
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        return {}
    return bounds


def _bounds_center(bounds: dict[str, Any]) -> dict[str, int]:
    normalized = _bounds(bounds)
    if not normalized:
        return {}
    return {
        "x": normalized["x"] + normalized["width"] // 2,
        "y": normalized["y"] + normalized["height"] // 2,
    }


def _point(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    if "x" not in value or "y" not in value:
        return {}
    return {"x": _int(value.get("x"), 0), "y": _int(value.get("y"), 0)}


def _compact_capabilities(capabilities: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(capabilities, dict):
        return {}
    result: dict[str, Any] = {}
    for group in ("semantic", "input", "screenshot", "vision"):
        value = capabilities.get(group)
        if isinstance(value, dict):
            result[group] = {key: bool(item) for key, item in value.items()}
    return result


def _dedupe_and_sort(candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = json.dumps(
            {
                "strategy": candidate.get("strategy", ""),
                "source": candidate.get("source", ""),
                "locator": candidate.get("locator", {}),
                "window_query": candidate.get("window_query", {}),
                "bounds": candidate.get("bounds", {}),
                "text": candidate.get("text", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    strategy_rank = {
        "semantic_locator": 5,
        "window_query_repair": 4,
        "window_context": 3,
        "visual_bounds": 2,
        "visual_evidence": 1,
    }
    unique.sort(
        key=lambda item: (
            0 if bool(item.get("selected", False)) else 1,
            -confidence_rank.get(str(item.get("confidence", "")), 0),
            -strategy_rank.get(str(item.get("strategy", "")), 0),
            -_int(item.get("score"), 0),
        )
    )
    return unique[:limit]


def _candidate_match_key(match: dict[str, Any]) -> str:
    return json.dumps(
        {
            "bounds": _bounds(match.get("bounds")),
            "point": _point(match.get("point")),
            "text": match.get("text", ""),
            "index": match.get("index", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _as_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stability_rank(stability: str) -> int:
    return {
        "high": 3,
        "medium": 2,
        "low": 1,
        "session": 0,
    }.get(stability, 0)


def _limit_text(value: str, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
