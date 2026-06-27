from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.run_artifacts import read_json_if_exists
from ai_automate_contro.support.utils import dict_get, first_string, safe_int


WINDOW_QUERY_FIELDS = {
    "title",
    "title_contains",
    "title_regex",
    "app",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "match_index",
}
ELEMENT_LOCATOR_FIELDS = {
    "element_id",
    "automation_id",
    "name",
    "name_contains",
    "name_regex",
    "text",
    "text_contains",
    "text_regex",
    "control_type",
    "role",
    "element_class_name",
    "element_match_index",
}


def build_desktop_debug_fix_proposals(
    analysis: dict[str, Any],
    source_plan_path: Path,
    *,
    user_hint: str,
) -> list[dict[str, Any]]:
    plan_context = dict_get(analysis, "plan_context")
    step_number = safe_int(dict_get(plan_context, "step_number"))
    if step_number is None:
        step_number = safe_int(dict_get(dict_get(analysis, "failed_step"), "step"))
    if step_number is None:
        return []
    zero_based_index = step_number - 1
    source_document = read_json_if_exists(source_plan_path)
    steps = dict_get(source_document, "steps")
    if not isinstance(steps, list) or zero_based_index >= len(steps):
        return []
    failed_step = steps[zero_based_index]
    if not isinstance(failed_step, dict):
        return []

    diagnostics = _diagnostics_for_step(analysis, step_number=step_number, action=str(failed_step.get("action", "")))
    proposals: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        proposals.extend(
            _element_locator_proposals(
                failed_step,
                step_number=step_number,
                zero_based_index=zero_based_index,
                diagnostic=diagnostic,
                user_hint=user_hint,
            )
        )
        proposals.extend(
            _window_query_proposals(
                failed_step,
                step_number=step_number,
                zero_based_index=zero_based_index,
                diagnostic=diagnostic,
                user_hint=user_hint,
            )
        )
    return _dedupe_and_sort(proposals)


def desktop_auto_apply_gate(proposals: list[dict[str, Any]], *, user_hint: str) -> dict[str, Any]:
    if not proposals:
        return {"ok": False, "reason": "No desktop proposal is available."}
    selected = proposals[0]
    proposal_type = str(selected.get("type", ""))
    if proposal_type == "desktop_element_locator_replace":
        if selected.get("auto_apply_allowed") is True:
            return {"ok": True, "reason": "Desktop element locator proposal is backed by a unique high-stability selector hint."}
        return {
            "ok": False,
            "reason": (
                "Desktop element locator proposal is not safe to auto-apply. "
                "Review selector_hints or provide a clearer user_hint before applying."
            ),
        }
    if proposal_type == "desktop_window_query_replace":
        if user_hint.strip() and str(selected.get("confidence")) == "high":
            return {"ok": True, "reason": "Desktop window query proposal has a clear user hint and high confidence."}
        return {
            "ok": False,
            "reason": (
                "Desktop window query replacement can change the target app/window. "
                "Review the near match or provide a user_hint before auto-applying."
            ),
        }
    return {"ok": False, "reason": f"Unsupported desktop proposal type for auto-apply: {proposal_type or '<unknown>'}."}


def _diagnostics_for_step(analysis: dict[str, Any], *, step_number: int, action: str) -> list[dict[str, Any]]:
    diagnostics = dict_get(analysis, "desktop_diagnostics")
    if not isinstance(diagnostics, list):
        return []
    exact: list[dict[str, Any]] = []
    related: list[dict[str, Any]] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        diagnostic_step = safe_int(item.get("step"))
        diagnostic_action = str(item.get("action", ""))
        if diagnostic_step == step_number:
            exact.append(item)
        elif action and diagnostic_action and action in diagnostic_action:
            related.append(item)
    return exact or related or [item for item in diagnostics if isinstance(item, dict)]


def _element_locator_proposals(
    failed_step: dict[str, Any],
    *,
    step_number: int,
    zero_based_index: int,
    diagnostic: dict[str, Any],
    user_hint: str,
) -> list[dict[str, Any]]:
    action = str(failed_step.get("action", ""))
    if action not in {"desktop_element", "desktop_assert", "desktop_input"}:
        return []
    if action == "desktop_assert" and str(failed_step.get("type", "")) != "element":
        return []
    if action == "desktop_input" and str(failed_step.get("target", "")) != "element_center":
        return []
    element = dict_get(diagnostic, "element")
    if not isinstance(element, dict):
        return []
    current_locator = dict_get(element, "locator")
    near_matches = dict_get(element, "near_matches")
    if not isinstance(current_locator, dict) or not current_locator:
        return []
    if not isinstance(near_matches, list) or not near_matches:
        return []

    proposals: list[dict[str, Any]] = []
    for match in near_matches[:5]:
        if not isinstance(match, dict):
            continue
        candidate_element = dict_get(match, "element")
        if not isinstance(candidate_element, dict):
            continue
        for candidate in _candidate_locators_from_element(candidate_element):
            locator = candidate["locator"]
            if locator == current_locator:
                continue
            operations = _field_patch_operations(
                failed_step,
                step_index=zero_based_index,
                remove_fields=ELEMENT_LOCATOR_FIELDS,
                add_fields=locator,
            )
            if not operations:
                continue
            score = _desktop_locator_score(match, candidate, user_hint=user_hint)
            confidence = _desktop_locator_confidence(score, candidate)
            proposals.append(
                {
                    "type": "desktop_element_locator_replace",
                    "confidence": confidence,
                    "score": score,
                    "step_number": step_number,
                    "from": current_locator,
                    "to": locator,
                    "operation": operations[0],
                    "operations": operations,
                    "reason": _locator_fix_reason(current_locator, locator, match, candidate, user_hint=user_hint),
                    "evidence": {
                        "near_match": match,
                        "selector_hint": candidate,
                    },
                    "auto_apply_allowed": _locator_auto_apply_allowed(confidence, candidate),
                }
            )
    return proposals


def _window_query_proposals(
    failed_step: dict[str, Any],
    *,
    step_number: int,
    zero_based_index: int,
    diagnostic: dict[str, Any],
    user_hint: str,
) -> list[dict[str, Any]]:
    action = str(failed_step.get("action", ""))
    if action not in {"desktop_window", "desktop_wait", "desktop_capture", "desktop_assert", "desktop_element", "desktop_input"}:
        return []
    window = dict_get(diagnostic, "window")
    if not isinstance(window, dict):
        return []
    current_query = dict_get(window, "query")
    near_matches = dict_get(window, "near_matches")
    if not isinstance(current_query, dict) or not current_query:
        return []
    if safe_int(window.get("match_count")):
        return []
    if not isinstance(near_matches, list) or not near_matches:
        return []
    proposals: list[dict[str, Any]] = []
    for match in near_matches[:3]:
        if not isinstance(match, dict):
            continue
        candidate_window = dict_get(match, "window")
        if not isinstance(candidate_window, dict):
            continue
        query = _candidate_window_query(candidate_window)
        if not query or query == current_query:
            continue
        operations = _field_patch_operations(
            failed_step,
            step_index=zero_based_index,
            remove_fields=WINDOW_QUERY_FIELDS,
            add_fields=query,
        )
        if not operations:
            continue
        score = _desktop_window_score(match, candidate_window, user_hint=user_hint)
        confidence = "high" if user_hint.strip() and score >= 70 else ("medium" if score >= 35 else "low")
        proposals.append(
            {
                "type": "desktop_window_query_replace",
                "confidence": confidence,
                "score": score,
                "step_number": step_number,
                "from": current_query,
                "to": query,
                "operation": operations[0],
                "operations": operations,
                "reason": _window_fix_reason(current_query, query, match, user_hint=user_hint),
                "evidence": {"near_match": match},
                "auto_apply_allowed": False,
            }
        )
    return proposals


def _candidate_locators_from_element(element: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    selector_hints = element.get("selector_hints")
    if isinstance(selector_hints, list):
        for hint in selector_hints:
            if not isinstance(hint, dict):
                continue
            locator = _clean_locator(dict_get(hint, "locator"))
            if locator:
                candidates.append(
                    {
                        "locator": locator,
                        "stability": str(hint.get("stability") or ""),
                        "unique": bool(hint.get("unique")),
                        "match_count": safe_int(hint.get("match_count")) or 0,
                        "source": "selector_hints",
                    }
                )

    fallback_locators = _fallback_locators_from_element(element)
    for locator, stability in fallback_locators:
        candidates.append(
            {
                "locator": locator,
                "stability": stability,
                "unique": False,
                "match_count": 0,
                "source": "near_match",
            }
        )

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        locator = candidate["locator"]
        if set(locator) <= {"element_id"} and any(set(item["locator"]) - {"element_id"} for item in candidates):
            continue
        key = json.dumps(locator, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    unique.sort(key=lambda item: (-_stability_rank(str(item.get("stability", ""))), not bool(item.get("unique")), item.get("match_count") or 999))
    return unique[:5]


def _fallback_locators_from_element(element: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    automation_id = first_string(element.get("automation_id"))
    name = first_string(element.get("name"))
    text = first_string(element.get("text"), element.get("value"))
    control_type = first_string(element.get("control_type"))
    role = first_string(element.get("role"))
    class_name = first_string(element.get("class_name"))
    locators: list[tuple[dict[str, Any], str]] = []
    if automation_id:
        locator = {"automation_id": automation_id}
        if control_type:
            locator["control_type"] = control_type
        locators.append((locator, "high"))
    if name:
        locator = {"name": name}
        if control_type:
            locator["control_type"] = control_type
        locators.append((locator, "medium"))
    if text and text != name:
        locator = {"text": text}
        if control_type:
            locator["control_type"] = control_type
        locators.append((locator, "medium"))
    if role:
        locator = {"role": role}
        if name:
            locator["name"] = name
        locators.append((locator, "medium"))
    if class_name:
        locator = {"element_class_name": class_name}
        if control_type:
            locator["control_type"] = control_type
        locators.append((locator, "low"))
    return [(locator, stability) for locator, stability in locators if _clean_locator(locator)]


def _clean_locator(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {field: value[field] for field in ELEMENT_LOCATOR_FIELDS if field in value and value[field] not in (None, "")}


def _candidate_window_query(window: dict[str, Any]) -> dict[str, Any]:
    title = first_string(window.get("title")).strip()
    app = first_string(window.get("app"), window.get("process_name")).strip()
    process_name = first_string(window.get("process_name")).strip()
    class_name = first_string(window.get("class_name")).strip()
    if title:
        query: dict[str, Any] = {"title_contains": title}
        if process_name:
            query["process_name"] = process_name
        return query
    if process_name:
        return {"process_name": process_name}
    if app:
        return {"app": app}
    if class_name:
        return {"class_name": class_name}
    return {}


def _field_patch_operations(
    failed_step: dict[str, Any],
    *,
    step_index: int,
    remove_fields: set[str],
    add_fields: dict[str, Any],
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for field in sorted(remove_fields):
        if field in add_fields:
            continue
        if field in failed_step:
            operations.append({"op": "remove", "path": ["steps", step_index, field]})
    for field, value in add_fields.items():
        if field in failed_step:
            if failed_step.get(field) != value:
                operations.append({"op": "replace", "path": ["steps", step_index, field], "value": value})
        else:
            operations.append({"op": "add", "path": ["steps", step_index, field], "value": value})
    return operations


def _desktop_locator_score(match: dict[str, Any], candidate: dict[str, Any], *, user_hint: str) -> int:
    score = safe_int(match.get("score")) or 0
    stability = str(candidate.get("stability") or "")
    score += _stability_rank(stability) * 20
    if candidate.get("unique") is True or candidate.get("match_count") == 1:
        score += 25
    if candidate.get("source") == "selector_hints":
        score += 10
    if _hint_overlaps_locator(user_hint, candidate.get("locator")):
        score += 30
    return score


def _desktop_locator_confidence(score: int, candidate: dict[str, Any]) -> str:
    if str(candidate.get("stability")) == "high" and (candidate.get("unique") is True or candidate.get("match_count") == 1):
        return "high"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _locator_auto_apply_allowed(confidence: str, candidate: dict[str, Any]) -> bool:
    return (
        confidence == "high"
        and str(candidate.get("stability")) == "high"
        and (candidate.get("unique") is True or candidate.get("match_count") == 1)
        and isinstance(candidate.get("locator"), dict)
        and "element_id" not in candidate["locator"]
    )


def _desktop_window_score(match: dict[str, Any], window: dict[str, Any], *, user_hint: str) -> int:
    score = (safe_int(match.get("score")) or 0) * 3
    if first_string(window.get("title")):
        score += 20
    if first_string(window.get("process_name"), window.get("app")):
        score += 10
    if bool(window.get("focused")):
        score += 5
    if _hint_overlaps_locator(user_hint, window):
        score += 35
    return score


def _locator_fix_reason(
    current_locator: dict[str, Any],
    locator: dict[str, Any],
    match: dict[str, Any],
    candidate: dict[str, Any],
    *,
    user_hint: str,
) -> str:
    reason = (
        f"Desktop Element Locator {current_locator!r} did not match. "
        f"The closest control suggests locator {locator!r} from {candidate.get('source')} "
        f"with stability={candidate.get('stability')!r}, unique={candidate.get('unique')!r}, score={match.get('score')!r}."
    )
    if user_hint.strip():
        reason += f" User hint used for ranking: {user_hint.strip()!r}."
    return reason


def _window_fix_reason(current_query: dict[str, Any], query: dict[str, Any], match: dict[str, Any], *, user_hint: str) -> str:
    reason = (
        f"Desktop Window Query {current_query!r} did not match. "
        f"The closest window suggests query {query!r}; near_match score={match.get('score')!r}."
    )
    if user_hint.strip():
        reason += f" User hint used for ranking: {user_hint.strip()!r}."
    else:
        reason += " Review before applying because window targeting can affect a different app."
    return reason


def _hint_overlaps_locator(user_hint: str, value: Any) -> bool:
    hint_tokens = _tokenize(user_hint)
    if not hint_tokens:
        return False
    value_tokens = _tokenize(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return bool(hint_tokens & value_tokens)


def _tokenize(value: str) -> set[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return {token for token in normalized.split() if len(token) >= 2}


def _stability_rank(stability: str) -> int:
    return {
        "high": 3,
        "medium": 2,
        "low": 1,
        "session": 0,
    }.get(stability, 0)


def _dedupe_and_sort(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in proposals:
        operation = proposal.get("operation")
        key = json.dumps(operation, ensure_ascii=False, sort_keys=True) if isinstance(operation, dict) else ""
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(proposal)
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    unique.sort(key=lambda item: (-confidence_rank.get(str(item.get("confidence")), 0), -(safe_int(item.get("score")) or 0)))
    return unique[:5]
