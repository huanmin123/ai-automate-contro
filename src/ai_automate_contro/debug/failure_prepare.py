from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.debug.workspace import create_debug_workspace, inject_debug_steps
from ai_automate_contro.support.utils import dict_get, first_string, safe_int


CPLAN_DEBUG_NEXT_ACTIONS = [
    "先读取调试工作区 notes.md 和 injected-plan/plan.json。",
    "使用 cplan validate --file <workspace>/injected-plan/plan.json 校验调试副本。",
    "使用 cplan run --file <workspace>/injected-plan/plan.json 运行调试副本。",
    "确认修复后使用 cplan debug-patch 生成补丁，再用 cplan debug-apply 应用。",
]


def prepare_failure_debug_workspace(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    analyze_latest_run_failure: Any,
    validate_plan: Any,
    output_dir: str | Path | None = None,
    name: str | None = None,
    include_manual_confirm: bool = False,
    recommended_next_actions: list[str] | None = None,
) -> dict[str, Any]:
    analysis = analyze_latest_run_failure(
        plan_path,
        output_dir=output_dir,
        log_lines=40,
        event_lines=80,
    )
    status = first_string(dict_get(analysis, "status"))
    if status != "failed":
        raise ValueError(
            f"prepare_failure_debug_workspace requires a failed run; latest status is '{status}'. "
            "Run the plan first or pass a failed output_dir."
        )
    failed_step_number = safe_int(dict_get(dict_get(analysis, "failed_step"), "step"))
    browser, page = failure_browser_page(analysis)
    presets = ["print", "variables"]
    if browser:
        presets.extend(["screenshot", "html"])
    if include_manual_confirm:
        presets.append("manual_confirm")

    workspace = create_debug_workspace(
        plan_path,
        project_root,
        name=name or "failure-debug",
    )
    position = "before_step" if failed_step_number else "end"
    message = failure_debug_message(analysis)
    injection = inject_debug_steps(
        workspace.root,
        presets=presets,
        message=message,
        browser=browser,
        page=page,
        position=position,
        step=failed_step_number,
    )
    append_failure_debug_note(
        workspace.root,
        analysis=analysis,
        presets=presets,
        position=position,
        step=failed_step_number,
        browser=browser,
        page=page,
    )
    validation = validate_plan(project_root, workspace.injected_plan_dir / "plan.json")
    return {
        "ok": validation["ok"],
        "workspace": workspace.to_dict(),
        "analysis": analysis,
        "injection": injection.to_dict(),
        "validation": validation,
        "recommended_next_actions": recommended_next_actions or CPLAN_DEBUG_NEXT_ACTIONS,
    }


def failure_browser_page(analysis: dict[str, Any]) -> tuple[str | None, str | None]:
    failure_page_states = dict_get(analysis, "failure_page_states")
    if isinstance(failure_page_states, list):
        for raw_path in failure_page_states:
            try:
                state = _read_json_if_exists(Path(str(raw_path)))
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


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    import json

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
