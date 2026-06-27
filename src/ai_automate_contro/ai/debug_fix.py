from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.run_artifacts import read_json_if_exists
from ai_automate_contro.support.utils import dict_get, first_string
from ai_automate_contro.ai import debug_desktop_fix, debug_selector_fix


def build_debug_fix_proposals(
    analysis: dict[str, Any],
    source_plan_path: Path,
    *,
    user_hint: str,
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    proposals.extend(
        debug_selector_fix.build_debug_fix_proposals(
            analysis,
            source_plan_path,
            user_hint=user_hint,
        )
    )
    proposals.extend(
        debug_desktop_fix.build_desktop_debug_fix_proposals(
            analysis,
            source_plan_path,
            user_hint=user_hint,
        )
    )
    return proposals


def auto_apply_gate(proposals: list[dict[str, Any]], *, user_hint: str) -> dict[str, Any]:
    if not proposals:
        return {"ok": False, "reason": "No debug fix proposal is available."}
    selected = proposals[0]
    proposal_type = str(selected.get("type", ""))
    if proposal_type.startswith("desktop_"):
        return debug_desktop_fix.desktop_auto_apply_gate(proposals, user_hint=user_hint)
    return debug_selector_fix.selector_auto_apply_gate(proposals, user_hint=user_hint)


def selected_patch_operations(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    operations = proposal.get("operations")
    if isinstance(operations, list) and operations:
        return [operation for operation in operations if isinstance(operation, dict)]
    operation = proposal.get("operation")
    if isinstance(operation, dict):
        return [operation]
    return []


def failure_browser_page(analysis: dict[str, Any]) -> tuple[str | None, str | None]:
    failure_page_states = dict_get(analysis, "failure_page_states")
    if isinstance(failure_page_states, list):
        for raw_path in failure_page_states:
            try:
                state = read_json_if_exists(Path(str(raw_path)))
            except OSError:
                state = None
            browser = first_string(dict_get(state, "browser"))
            page = first_string(dict_get(state, "page"))
            if browser:
                return browser, page or None

    failed_plan_step = dict_get(dict_get(analysis, "plan_context"), "failed_step")
    browser = first_string(dict_get(failed_plan_step, "browser"))
    page = first_string(dict_get(failed_plan_step, "page"))
    if browser:
        return browser, page or None
    return None, None


def failure_debug_message(analysis: dict[str, Any]) -> str:
    failed_step = dict_get(analysis, "failed_step")
    step_number = dict_get(failed_step, "step")
    plan_failed_step = dict_get(dict_get(analysis, "plan_context"), "failed_step")
    action = dict_get(failed_step, "action") or dict_get(plan_failed_step, "action") or "step"
    error = first_string(dict_get(analysis, "error")).splitlines()[0:1]
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
        file.write(f"- Source run: `{dict_get(analysis, 'output_dir')}`\n")
        file.write(f"- Failed step: `{step or '<unknown>'}`\n")
        file.write(f"- Injection position: `{position}`\n")
        file.write(f"- Presets: `{', '.join(presets)}`\n")
        file.write(f"- Browser/Page: `{browser or '<none>'}` / `{page or '<default>'}`\n")
        error = first_string(dict_get(analysis, "error")).strip()
        if error:
            file.write("\n### Error\n\n")
            file.write("```text\n")
            file.write(error[:2000])
            file.write("\n```\n")
        dom_summaries = dict_get(analysis, "dom_summaries")
        if isinstance(dom_summaries, list) and dom_summaries:
            elements = dict_get(dom_summaries[0], "elements")
            if isinstance(elements, list) and elements:
                file.write("\n### DOM Selector Hints\n\n")
                for element in elements[:20]:
                    if not isinstance(element, dict):
                        continue
                    tag = dict_get(element, "tag")
                    selector = dict_get(element, "selector_hint")
                    text = dict_get(element, "text")
                    file.write(f"- `{tag}` `{selector}`")
                    if text:
                        file.write(f" - {text}")
                    file.write("\n")


def append_debug_fix_note(workspace_root: Path, proposal: dict[str, Any]) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Fix Candidate\n\n")
        file.write("- Source: `propose_debug_fix`\n")
        file.write(f"- Type: `{proposal.get('type')}`\n")
        file.write(f"- Confidence: `{proposal.get('confidence')}`\n")
        file.write(f"- Step: `{proposal.get('step_number')}`\n")
        file.write(f"- From: `{proposal.get('from')}`\n")
        file.write(f"- To: `{proposal.get('to')}`\n")
        file.write("\n### Operation\n\n")
        file.write("```json\n")
        operations = selected_patch_operations(proposal)
        json.dump(operations[0] if len(operations) == 1 else operations, file, ensure_ascii=False, indent=2)
        file.write("\n```\n")
        file.write("\n### Reason\n\n")
        file.write(str(proposal.get("reason", "")).strip() + "\n")
