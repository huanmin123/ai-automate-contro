from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output
from ai_automate_contro.engine.template import render_value
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


RESERVED_OUTPUT_VARIABLES = {"last"}


def action_run_sub_plan(executor: Any, step: dict[str, Any]) -> None:
    raw_path = str(step["path"])
    sub_plan_path = resolve_sub_plan_path(executor, raw_path)
    sub_plan = load_plan(sub_plan_path)
    if "steps" not in sub_plan:
        raise ValueError(f"子计划必须是带 steps 的 plan 文档：{sub_plan_path}")

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
    _ensure_loop_variable_allowed(str(loop_var))
    _ensure_loop_variable_allowed(str(index_var))
    body = step.get("steps", [])
    total = len(items)
    executor.state.logger.log("info", "foreach start", loop_var=loop_var, total=total)
    for index, item in enumerate(items):
        executor.state.variables[loop_var] = item
        executor.state.variables[index_var] = index
        executor.state.logger.log("info", "foreach item", index=index, loop_var=loop_var, value=item)
        executor.run(body)
    executor.state.logger.log("info", "foreach finished", total=total)


def _ensure_loop_variable_allowed(name: str) -> None:
    if name in RESERVED_OUTPUT_VARIABLES:
        raise ValueError(f"{name} 是保留输出变量，只能由 output 发布器维护。")


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
                    executor._wait_for_timeout(session.require_page(), int(wait_seconds * 1000))
    if last_error is not None:
        raise last_error


def action_trigger(executor: Any, step: dict[str, Any]) -> None:
    definition = _render_trigger_definition(executor, step)
    trigger_type = str(definition.get("type") or "").strip()
    if trigger_type != "interval":
        raise ValueError(f"不支持的 trigger type：{trigger_type}")
    trigger_name = str(definition.get("name") or step.get("name") or "trigger").strip() or "trigger"
    runtime = _new_trigger_runtime(trigger_name, definition)
    executor.state.logger.log(
        "info",
        "trigger started",
        trigger=trigger_name,
        every_seconds=runtime["every_seconds"],
        next_run_at=runtime["next_run_at"],
    )
    executor.state.logger.log("info", "trigger wait start", trigger=trigger_name)
    while runtime.get("status") == "running":
        executor._raise_if_interrupted()
        if _trigger_should_finish(executor, step, definition, runtime):
            _complete_trigger(executor, trigger_name, runtime)
            break
        now = time.monotonic()
        due_at = float(runtime.get("next_due_monotonic", now))
        if now >= due_at:
            _run_trigger_once(executor, step, definition, runtime)
            continue
        _wait_runtime(executor, min(due_at - now, 0.25))
    status = _trigger_status(runtime)
    publish_step_output(executor, step, status, action="trigger")
    executor.state.logger.log(
        "info",
        "trigger wait finished",
        trigger=trigger_name,
        status=runtime.get("status"),
        run_count=runtime.get("run_count"),
    )


def _complete_trigger(executor: Any, trigger_name: str, runtime: dict[str, Any]) -> None:
    runtime["status"] = "completed"
    runtime["finished_at"] = _now_text()
    executor.state.logger.log("info", "trigger completed", trigger=trigger_name, run_count=runtime.get("run_count"))


def _run_trigger_once(
    executor: Any,
    step: dict[str, Any],
    definition: dict[str, Any],
    runtime: dict[str, Any],
) -> None:
    trigger_name = str(runtime["name"])
    before_due = float(runtime.get("next_due_monotonic", time.monotonic()))
    run_index = int(runtime.get("run_count", 0)) + 1
    runtime["status"] = "running"
    runtime["run_count"] = run_index
    runtime["last_run_at"] = _now_text()
    executor.state.variables.update(
        {
            "trigger_name": trigger_name,
            "trigger_run_index": run_index,
            "trigger_started_at": runtime.get("started_at"),
            "trigger_last_run_at": runtime.get("last_run_at"),
            "trigger_next_run_at": runtime.get("next_run_at"),
        }
    )
    executor.state.logger.log("info", "trigger body start", trigger=trigger_name, run_index=run_index)
    try:
        _run_trigger_body(executor, step)
    except Exception as error:
        runtime["last_error"] = str(error)
        runtime["last_error_type"] = type(error).__name__
        runtime["finished_at"] = _now_text()
        runtime["finish_reason"] = "error"
        on_error = str(definition.get("on_error", "fail_plan"))
        executor.state.logger.log(
            "error",
            "trigger body failed",
            trigger=trigger_name,
            run_index=run_index,
            on_error=on_error,
            error=str(error),
        )
        if on_error == "stop_trigger":
            runtime["status"] = "failed"
            return
        raise
    runtime["last_error"] = ""
    runtime["last_error_type"] = ""
    runtime["last_finished_at"] = _now_text()
    executor.state.logger.log("info", "trigger body finished", trigger=trigger_name, run_index=run_index)
    _schedule_next_trigger_run(executor, runtime, before_due, definition)


def _run_trigger_body(executor: Any, step: dict[str, Any]) -> None:
    steps = step.get("steps")
    path = step.get("path")
    if steps is not None and path:
        raise ValueError("trigger.steps 和 trigger.path 只能提供一种。")
    if steps is not None:
        if not isinstance(steps, list) or not steps:
            raise ValueError("trigger.steps 必须是非空步骤数组。")
        executor.run(steps)
        return
    if path:
        executor.run([{"action": "run_sub_plan", "path": path}])
        return
    raise ValueError("trigger 需要 steps 或 path 作为周期执行体。")


def _schedule_next_trigger_run(
    executor: Any,
    runtime: dict[str, Any],
    before_due: float,
    definition: dict[str, Any],
) -> None:
    every_seconds = float(runtime["every_seconds"])
    overlap = str(definition.get("overlap", "skip"))
    scheduled_next = before_due + every_seconds
    now = time.monotonic()
    if now > scheduled_next:
        if overlap == "fail":
            raise RuntimeError(f"trigger body 执行时间超过间隔：every_seconds={every_seconds}, overlap=fail")
        if overlap == "skip":
            scheduled_next = now + every_seconds
    runtime["next_due_monotonic"] = scheduled_next
    runtime["next_run_at"] = _future_text(max(0.0, scheduled_next - now))
    executor.state.variables["trigger_next_run_at"] = runtime["next_run_at"]


def _trigger_should_finish(
    executor: Any,
    step: dict[str, Any],
    definition: dict[str, Any],
    runtime: dict[str, Any],
) -> bool:
    max_runs = definition.get("max_runs")
    if max_runs not in (None, "") and _as_positive_int(max_runs, "max_runs") <= int(runtime.get("run_count", 0)):
        runtime["finish_reason"] = "max_runs"
        return True
    duration_seconds = definition.get("duration_seconds")
    if duration_seconds not in (None, ""):
        elapsed = time.monotonic() - float(runtime.get("started_monotonic", time.monotonic()))
        if elapsed >= float(duration_seconds):
            runtime["finish_reason"] = "duration_seconds"
            return True
    stop_condition = step.get("stop_condition")
    if stop_condition is not None:
        rendered_condition = render_value(stop_condition, executor.state.variables)
        if executor.conditions.evaluate(rendered_condition):
            runtime["finish_reason"] = "stop_condition"
            return True
    return False


def _new_trigger_runtime(trigger_name: str, definition: dict[str, Any]) -> dict[str, Any]:
    every_seconds = float(definition.get("every_seconds", 0))
    if every_seconds <= 0:
        raise ValueError("interval trigger.every_seconds 必须大于 0。")
    if not _has_finite_trigger_bound(definition) and not _as_bool(definition.get("allow_infinite", False), "allow_infinite"):
        raise ValueError("无限 trigger 必须显式设置 allow_infinite=true。")
    now = time.monotonic()
    run_immediately = _as_bool(definition.get("run_immediately", False), "run_immediately")
    next_due = now if run_immediately else now + every_seconds
    return {
        "name": trigger_name,
        "status": "running",
        "started_at": _now_text(),
        "started_monotonic": now,
        "every_seconds": every_seconds,
        "run_count": 0,
        "next_due_monotonic": next_due,
        "next_run_at": _future_text(max(0.0, next_due - now)),
        "last_run_at": "",
        "last_finished_at": "",
        "finished_at": "",
        "finish_reason": "",
        "last_error": "",
        "last_error_type": "",
    }


def _trigger_status(runtime: dict[str, Any]) -> dict[str, Any]:
    public_keys = {
        "name",
        "status",
        "started_at",
        "run_count",
        "next_run_at",
        "last_run_at",
        "last_finished_at",
        "finished_at",
        "finish_reason",
        "last_error",
        "last_error_type",
    }
    return {key: value for key, value in runtime.items() if key in public_keys}


def _render_trigger_definition(executor: Any, step: dict[str, Any]) -> dict[str, Any]:
    rendered: dict[str, Any] = {}
    for key, value in step.items():
        if key in {"steps", "stop_condition"}:
            continue
        rendered[key] = render_value(value, executor.state.variables)
    return rendered


def _has_finite_trigger_bound(definition: dict[str, Any]) -> bool:
    return definition.get("max_runs") not in (None, "") or definition.get("duration_seconds") not in (None, "")


def _as_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"trigger.{field} 必须是大于 0 的整数。")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError(f"trigger.{field} 必须是大于 0 的整数。")
    if number <= 0:
        raise ValueError(f"trigger.{field} 必须是大于 0 的整数。")
    return number


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    raise ValueError(f"trigger.{field} 必须是布尔值。")


def _wait_runtime(executor: Any, seconds: float) -> None:
    milliseconds = int(max(0.0, seconds) * 1000)
    sessions = list(executor.state.sessions.values())
    if sessions and sessions[0].pages:
        executor._wait_for_timeout(sessions[0].require_page(), milliseconds)
        return
    remaining = max(0, milliseconds)
    while remaining > 0:
        executor._raise_if_interrupted()
        step_ms = min(remaining, 200)
        time.sleep(step_ms / 1000)
        remaining -= step_ms
    executor._raise_if_interrupted()


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _future_text(after_seconds: float) -> str:
    return datetime.fromtimestamp(time.time() + max(0.0, after_seconds)).isoformat(timespec="seconds")


def resolve_sub_plan_path(executor: Any, raw_path: str) -> Path:
    path = path_from_text(raw_path)
    if is_absolute_path_text(raw_path):
        raise ValueError("run_sub_plan path 必须是相对于当前 plan 包的路径。")
    package_root = executor._package_root().resolve()
    resolved_path = (package_root / path).resolve()
    sub_plans_dir = (package_root / "sub-plans").resolve()
    if not _is_relative_to(resolved_path, package_root):
        raise ValueError(f"子计划必须位于当前 plan 包内：{raw_path}")
    if not path.parts or path.parts[0] != "sub-plans":
        raise ValueError("子计划路径必须放在 sub-plans/ 下。")
    if not _is_relative_to(resolved_path, sub_plans_dir):
        raise ValueError("子计划路径解析后必须仍位于 sub-plans/ 下。")
    if resolved_path.name == "plan.json":
        raise ValueError("run_sub_plan 不能引用另一个名为 plan.json 的入口计划。")
    if not resolved_path.name.endswith("-plan.json"):
        raise ValueError("子计划文件名必须使用 *-plan.json 格式。")
    if not resolved_path.exists():
        raise FileNotFoundError(f"子计划不存在：{resolved_path}")
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
    "trigger": action_trigger,
}
