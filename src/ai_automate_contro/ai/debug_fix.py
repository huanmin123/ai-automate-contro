from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai import run_inspection


def failure_browser_page(analysis: dict[str, Any]) -> tuple[str | None, str | None]:
    failure_page_states = run_inspection.dict_get(analysis, "failure_page_states")
    if isinstance(failure_page_states, list):
        for raw_path in failure_page_states:
            try:
                state = run_inspection.read_json_if_exists(Path(str(raw_path)))
            except OSError:
                state = None
            browser = run_inspection.first_string(run_inspection.dict_get(state, "browser"))
            page = run_inspection.first_string(run_inspection.dict_get(state, "page"))
            if browser:
                return browser, page or None

    failed_plan_step = run_inspection.dict_get(run_inspection.dict_get(analysis, "plan_context"), "failed_step")
    browser = run_inspection.first_string(run_inspection.dict_get(failed_plan_step, "browser"))
    page = run_inspection.first_string(run_inspection.dict_get(failed_plan_step, "page"))
    if browser:
        return browser, page or None
    return None, None


def failure_debug_message(analysis: dict[str, Any]) -> str:
    failed_step = run_inspection.dict_get(analysis, "failed_step")
    step_number = run_inspection.dict_get(failed_step, "step")
    plan_failed_step = run_inspection.dict_get(run_inspection.dict_get(analysis, "plan_context"), "failed_step")
    action = run_inspection.dict_get(failed_step, "action") or run_inspection.dict_get(plan_failed_step, "action") or "step"
    error = run_inspection.first_string(run_inspection.dict_get(analysis, "error")).splitlines()[0:1]
    error_text = error[0] if error else "unknown failure"
    if step_number:
        return f"[debug] before failed step {step_number}: {action}; {error_text}"
    return f"[debug] failure diagnostic checkpoint: {error_text}"


def append_failure_debug_note(
    workspace_root: Path,
    *,
    analysis: dict[str, Any],
    presets: list[str],
    position: str,
    step: int | None,
    browser: str | None,
    page: str | None,
) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Failure Debug Preparation\n\n")
        file.write(f"- Source run: `{run_inspection.dict_get(analysis, 'output_dir')}`\n")
        file.write(f"- Failed step: `{step or '<unknown>'}`\n")
        file.write(f"- Injection position: `{position}`\n")
        file.write(f"- Presets: `{', '.join(presets)}`\n")
        file.write(f"- Browser/Page: `{browser or '<none>'}` / `{page or '<default>'}`\n")
        error = run_inspection.first_string(run_inspection.dict_get(analysis, "error")).strip()
        if error:
            file.write("\n### Error\n\n")
            file.write("```text\n")
            file.write(error[:2000])
            file.write("\n```\n")
        dom_summaries = run_inspection.dict_get(analysis, "dom_summaries")
        if isinstance(dom_summaries, list) and dom_summaries:
            elements = run_inspection.dict_get(dom_summaries[0], "elements")
            if isinstance(elements, list) and elements:
                file.write("\n### DOM Selector Hints\n\n")
                for element in elements[:20]:
                    if not isinstance(element, dict):
                        continue
                    tag = run_inspection.dict_get(element, "tag")
                    selector = run_inspection.dict_get(element, "selector_hint")
                    text = run_inspection.dict_get(element, "text")
                    file.write(f"- `{tag}` `{selector}`")
                    if text:
                        file.write(f" - {text}")
                    file.write("\n")


def build_debug_fix_proposals(
    analysis: dict[str, Any],
    source_plan_path: Path,
    *,
    user_hint: str,
) -> list[dict[str, Any]]:
    plan_context = run_inspection.dict_get(analysis, "plan_context")
    step_index = run_inspection.safe_int(run_inspection.dict_get(plan_context, "step_number"))
    if step_index is None:
        return []
    zero_based_index = step_index - 1
    source_document = run_inspection.read_json_if_exists(source_plan_path)
    steps = run_inspection.dict_get(source_document, "steps")
    if not isinstance(steps, list) or zero_based_index >= len(steps):
        return []
    failed_step = steps[zero_based_index]
    if not isinstance(failed_step, dict):
        return []
    if failed_step.get("action") != "wait" or failed_step.get("type") != "selector":
        return []
    current_selector = run_inspection.first_string(failed_step.get("selector"))
    if not current_selector:
        return []

    candidates = _rank_selector_candidates(
        run_inspection.dict_get(analysis, "dom_summaries"),
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
    score = run_inspection.safe_int(selected.get("score")) or 0
    if confidence != "high" or score < 85:
        return {
            "ok": False,
            "reason": (
                f"Selected selector confidence is {confidence or '<unknown>'} with score {score}; "
                "auto-apply requires high confidence from a clear hint."
            ),
        }
    if len(proposals) > 1:
        second_score = run_inspection.safe_int(proposals[1].get("score")) or 0
        if score - second_score < 10:
            return {
                "ok": False,
                "reason": (
                    "Top selector candidates are too close in score. "
                    f"Selected score is {score}, second score is {second_score}; review manually."
                ),
            }
    return {"ok": True, "reason": "Selector candidate is high-confidence and sufficiently distinct."}


def append_debug_fix_note(workspace_root: Path, proposal: dict[str, Any]) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Fix Candidate\n\n")
        file.write("- Source: `propose_debug_fix`\n")
        file.write(f"- Type: `{proposal.get('type')}`\n")
        file.write(f"- Confidence: `{proposal.get('confidence')}`\n")
        file.write(f"- Step: `{proposal.get('step_number')}`\n")
        file.write(f"- Selector: `{proposal.get('from')}` -> `{proposal.get('to')}`\n")
        file.write("\n### Operation\n\n")
        file.write("```json\n")
        json.dump(proposal.get("operation"), file, ensure_ascii=False, indent=2)
        file.write("\n```\n")
        file.write("\n### Reason\n\n")
        file.write(str(proposal.get("reason", "")).strip() + "\n")


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
        selector = run_inspection.first_string(run_inspection.dict_get(element, "selector_hint")).strip()
        tag = run_inspection.first_string(run_inspection.dict_get(element, "tag")).strip().lower()
        attrs = run_inspection.dict_get(element, "attrs")
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
        summary_elements = run_inspection.dict_get(summary, "elements")
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
    attrs = run_inspection.dict_get(element, "attrs")
    attrs_text = json.dumps(attrs if isinstance(attrs, dict) else {}, ensure_ascii=False)
    text = run_inspection.first_string(run_inspection.dict_get(element, "text"))
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
