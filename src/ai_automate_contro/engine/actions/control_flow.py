from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.engine.template import render_value
from ai_automate_contro.plans.loader import load_plan


def action_run_sub_plan(executor: Any, step: dict[str, Any]) -> None:
    raw_path = str(step["path"])
    sub_plan_path = resolve_sub_plan_path(executor, raw_path)
    sub_plan = load_plan(sub_plan_path)
    if "steps" not in sub_plan:
        raise ValueError(f"Sub plan must be a plan document with steps: {sub_plan_path}")

    previous_plan_path = executor.state.plan_path
    executor.state.plan_path = sub_plan_path
    executor.state.sub_plan_stack.append(sub_plan_path)
    executor.state.logger.log("info", "sub plan started", path=str(sub_plan_path))
    try:
        executor.run(sub_plan.get("steps", []))
    finally:
        executor.state.logger.log("info", "sub plan finished", path=str(sub_plan_path))
        executor.state.sub_plan_stack.pop()
        executor.state.plan_path = previous_plan_path


def action_if(executor: Any, step: dict[str, Any]) -> None:
    rendered_condition = render_value(step.get("condition"), executor.state.variables)
    matched = executor.conditions.evaluate(rendered_condition)
    raw_branch = step.get("then", []) if matched else step.get("else", [])
    executor.state.logger.log("info", "if evaluated", matched=matched)
    executor.run(raw_branch)


def action_foreach(executor: Any, step: dict[str, Any]) -> None:
    items = render_value(step["items"], executor.state.variables)
    loop_var = step.get("item_var", "item")
    index_var = step.get("index_var", "index")
    body = step.get("steps", [])
    total = len(items)
    executor.state.logger.log("info", "foreach start", loop_var=loop_var, total=total)
    for index, item in enumerate(items):
        executor.state.variables[loop_var] = item
        executor.state.variables[index_var] = index
        executor.state.logger.log("info", "foreach item", index=index, loop_var=loop_var, value=item)
        executor.run(body)
    executor.state.logger.log("info", "foreach finished", total=total)


def action_retry(executor: Any, step: dict[str, Any]) -> None:
    attempts = int(step.get("attempts", 3))
    wait_seconds = float(step.get("wait_seconds", 1))
    body = step.get("steps", [])
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            executor.state.logger.log("info", "retry attempt", attempt=attempt, attempts=attempts)
            executor.run(body)
            return
        except Exception as error:
            last_error = error
            executor.state.logger.log("warning", "retry failed", attempt=attempt, error=str(error))
            if attempt < attempts:
                for session in executor.state.sessions.values():
                    session.require_page().wait_for_timeout(int(wait_seconds * 1000))
    if last_error is not None:
        raise last_error


def resolve_sub_plan_path(executor: Any, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError("run_sub_plan path must be relative to the current plan package.")
    package_root = executor._package_root().resolve()
    resolved_path = (package_root / path).resolve()
    sub_plans_dir = (package_root / "sub-plans").resolve()
    if not _is_relative_to(resolved_path, package_root):
        raise ValueError(f"Sub plan must stay inside the current plan package: {raw_path}")
    if not path.parts or path.parts[0] != "sub-plans":
        raise ValueError("Sub plan paths must be placed under 'sub-plans/'.")
    if not _is_relative_to(resolved_path, sub_plans_dir):
        raise ValueError("Sub plan paths must resolve under 'sub-plans/'.")
    if resolved_path.name == "plan.json":
        raise ValueError("run_sub_plan cannot reference another entry plan named 'plan.json'.")
    if not resolved_path.name.endswith("-plan.json"):
        raise ValueError("Sub plan filenames must use the '*-plan.json' pattern.")
    if not resolved_path.exists():
        raise FileNotFoundError(f"Sub plan not found: {resolved_path}")
    return resolved_path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


ACTION_HANDLERS = {
    "foreach": action_foreach,
    "if": action_if,
    "retry": action_retry,
    "run_sub_plan": action_run_sub_plan,
}
