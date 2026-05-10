from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.run_artifacts import read_json_if_exists
from ai_automate_contro.support.utils import dict_get, first_string, safe_int


def build_debug_fix_proposals(
    analysis: dict[str, Any],
    source_plan_path: Path,
    *,
    user_hint: str,
) -> list[dict[str, Any]]:
    plan_context = dict_get(analysis, "plan_context")
    step_index = safe_int(dict_get(plan_context, "step_number"))
    if step_index is None:
        return []
    zero_based_index = step_index - 1
    source_document = read_json_if_exists(source_plan_path)
    steps = dict_get(source_document, "steps")
    if not isinstance(steps, list) or zero_based_index >= len(steps):
        return []
    failed_step = steps[zero_based_index]
    if not isinstance(failed_step, dict):
        return []
    if failed_step.get("action") != "wait" or failed_step.get("type") != "selector":
        return []
    current_selector = first_string(failed_step.get("selector"))
    if not current_selector:
        return []

    candidates = _rank_selector_candidates(
        dict_get(analysis, "dom_summaries"),
        current_selector=current_selector,
        user_hint=user_hint,
    )
    proposals: list[dict[str, Any]] = []
    for candidate in candidates[:5]:
        selector = candidate["selector"]
        proposal = {
            "type": "selector_replace",
            "confidence": candidate["confidence"],
            "score": candidate["score"],
            "step_number": step_index,
            "from": current_selector,
            "to": selector,
            "operation": {
                "op": "replace",
                "path": ["steps", zero_based_index, "selector"],
                "value": selector,
            },
            "reason": _selector_fix_reason(current_selector, candidate, user_hint=user_hint),
            "evidence": candidate["element"],
        }
        proposals.append(proposal)
    return proposals


def selector_auto_apply_gate(proposals: list[dict[str, Any]], *, user_hint: str) -> dict[str, Any]:
    if not proposals:
        return {"ok": False, "reason": "No selector proposal is available."}
    selected = proposals[0]
    if selected.get("type") != "selector_replace":
        return {"ok": True, "reason": "Non-selector proposals do not use the selector ambiguity gate."}
    hint_tokens = _tokenize_selector_text(user_hint)
    if not hint_tokens:
        return {
            "ok": False,
            "reason": (
                "Selector replacement is ambiguous without a user_hint. "
                "The tool can list candidates, but will not auto-apply one only because it exists in the DOM."
            ),
        }
    confidence = str(selected.get("confidence", ""))
    score = safe_int(selected.get("score")) or 0
    if confidence != "high" or score < 85:
        return {
            "ok": False,
            "reason": (
                f"Selected selector confidence is {confidence or '<unknown>'} with score {score}; "
                "auto-apply requires high confidence from a clear hint."
            ),
        }
    if len(proposals) > 1:
        second_score = safe_int(proposals[1].get("score")) or 0
        if score - second_score < 10:
            return {
                "ok": False,
                "reason": (
                    "Top selector candidates are too close in score. "
                    f"Selected score is {score}, second score is {second_score}; review manually."
                ),
            }
    return {"ok": True, "reason": "Selector candidate is high-confidence and sufficiently distinct."}


def _rank_selector_candidates(
    dom_summaries: Any,
    *,
    current_selector: str,
    user_hint: str,
) -> list[dict[str, Any]]:
    elements = _dom_summary_elements(dom_summaries)
    user_hint_tokens = _tokenize_selector_text(user_hint)
    current_tokens = _tokenize_selector_text(current_selector)
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        selector = first_string(dict_get(element, "selector_hint")).strip()
        tag = first_string(dict_get(element, "tag")).strip().lower()
        attrs = dict_get(element, "attrs")
        if not selector or selector == current_selector:
            continue
        if selector in seen:
            continue
        if _is_weak_selector_hint(selector, tag):
            continue
        if isinstance(attrs, dict) and str(attrs.get("type", "")).lower() == "hidden":
            continue
        score = _score_selector_candidate(
            selector=selector,
            tag=tag,
            element=element,
            user_hint_tokens=user_hint_tokens,
            current_tokens=current_tokens,
        )
        seen.add(selector)
        candidates.append(
            {
                "selector": selector,
                "score": score,
                "confidence": _selector_confidence(score, user_hint_tokens=user_hint_tokens),
                "element": element,
            }
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def _dom_summary_elements(dom_summaries: Any) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    if not isinstance(dom_summaries, list):
        return elements
    for summary in dom_summaries:
        summary_elements = dict_get(summary, "elements")
        if not isinstance(summary_elements, list):
            continue
        elements.extend(element for element in summary_elements if isinstance(element, dict))
    return elements


def _is_weak_selector_hint(selector: str, tag: str) -> bool:
    if selector.startswith("#") or "[" in selector:
        return False
    return tag in {"form", "label"} or selector == tag


def _score_selector_candidate(
    *,
    selector: str,
    tag: str,
    element: dict[str, Any],
    user_hint_tokens: set[str],
    current_tokens: set[str],
) -> int:
    attrs = dict_get(element, "attrs")
    attrs_text = json.dumps(attrs if isinstance(attrs, dict) else {}, ensure_ascii=False)
    text = first_string(dict_get(element, "text"))
    searchable = " ".join([selector, tag, attrs_text, text]).lower()
    searchable_tokens = _tokenize_selector_text(searchable)

    score = 0
    if selector.startswith("#"):
        score += 40
    elif "[" in selector:
        score += 32
    else:
        score += 8
    if tag in {"input", "button", "select", "textarea"}:
        score += 24
    elif tag == "a":
        score += 16
    if isinstance(attrs, dict):
        if attrs.get("autocomplete"):
            score += 8
        if attrs.get("placeholder"):
            score += 8
        if attrs.get("name"):
            score += 8
        if attrs.get("aria-label"):
            score += 8
    if text:
        score += 6
    if user_hint_tokens:
        overlap = user_hint_tokens & searchable_tokens
        score += min(50, len(overlap) * 25)
        compact_hint = _compact_search_text(user_hint_tokens)
        if compact_hint and compact_hint in _compact_search_text(searchable_tokens):
            score += 50
    if current_tokens:
        overlap = current_tokens & searchable_tokens
        score += min(20, len(overlap) * 10)
    return score


def _selector_confidence(score: int, *, user_hint_tokens: set[str]) -> str:
    if user_hint_tokens and score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _selector_fix_reason(current_selector: str, candidate: dict[str, Any], *, user_hint: str) -> str:
    selector = candidate["selector"]
    confidence = candidate["confidence"]
    reason = (
        f"Failed selector `{current_selector}` was not found, while `{selector}` appears in the captured failure DOM. "
        f"Confidence is {confidence} based on selector stability and DOM attributes."
    )
    if user_hint.strip():
        reason += f" User hint used for ranking: {user_hint.strip()!r}."
    else:
        reason += " No user hint was supplied, so review the selector before applying it to the original plan."
    return reason


def _tokenize_selector_text(value: str) -> set[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return {token for token in normalized.split() if len(token) >= 2}


def _compact_search_text(tokens: set[str]) -> str:
    return "".join(sorted(tokens))
