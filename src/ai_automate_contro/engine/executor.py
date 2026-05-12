from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from datetime import datetime

from playwright.sync_api import sync_playwright

from ai_automate_contro.engine.actions import ActionExecutor
from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.support.logger import RunLogger
from ai_automate_contro.plans.results import PlanResult, write_report_markdown, write_result_json
from ai_automate_contro.engine.runtime import RuntimeState
from ai_automate_contro.engine.state import RunStateWriter
from ai_automate_contro.support.utils import ensure_directory, make_timestamp, sanitize_name


def execute_plan(
    plan: dict[str, Any],
    project_root: str | Path,
    plan_path: str | Path | None = None,
    run_name: str | None = None,
    output_dir: str | Path | None = None,
    variable_overrides: dict[str, Any] | None = None,
    manual_confirmation_handler: Callable[[str], bool] | None = None,
    inspection_confirmation_handler: Callable[[str], bool] | None = None,
    run_context_handler: Callable[[Path, RunLogger], None] | None = None,
) -> PlanResult:
    root_path = Path(project_root).resolve()
    resolved_plan_path = Path(plan_path).resolve() if plan_path else None
    if resolved_plan_path is not None and resolved_plan_path.name != "plan.json":
        raise ValueError(
            "Only a package entry plan named 'plan.json' can be executed directly. "
            "Use run_sub_plan inside the package entry plan for child 'sub-plans/*-plan.json' files."
        )
    plan_dir = resolved_plan_path.parent if resolved_plan_path else root_path
    resolved_run_name = run_name or plan.get("name") or (resolved_plan_path.stem if resolved_plan_path else "plan-run")
    resolved_output_dir = (
        Path(output_dir).resolve()
        if output_dir
        else ensure_directory(plan_dir / "output" / f"{make_timestamp()}-{sanitize_name(resolved_run_name)}")
    )
    package_output_dir = (plan_dir / "output").resolve()
    if not _is_relative_to(resolved_output_dir, package_output_dir):
        raise ValueError(f"Run output directory must stay inside the current plan package output directory: {package_output_dir}")
    ensure_directory(resolved_output_dir)
    logger = RunLogger(resolved_output_dir)
    if run_context_handler is not None:
        run_context_handler(resolved_output_dir, logger)
    state_writer = RunStateWriter(
        resolved_output_dir,
        run_name=resolved_run_name,
        plan_path=str(resolved_plan_path) if resolved_plan_path else None,
    )
    plan_config = load_plan_config(root_path, plan_dir)
    variables = _build_builtin_variables(
        project_root=root_path,
        plan_dir=plan_dir,
        output_dir=resolved_output_dir,
        plan_config=plan_config,
        plan_variables=dict(plan.get("variables", {})),
        variable_overrides=variable_overrides or {},
    )

    started_at = datetime.now().isoformat(timespec="seconds")
    error_message: str | None = None
    status = "passed"

    result: PlanResult | None = None
    caught_error: Exception | None = None

    with sync_playwright() as playwright:
        state = RuntimeState(
            project_root=root_path,
            playwright=playwright,
            run_name=resolved_run_name,
            output_dir=resolved_output_dir,
            logger=logger,
            state_writer=state_writer,
            plan_path=resolved_plan_path,
            package_dir=plan_dir,
            variables=variables,
            manual_confirmation_handler=manual_confirmation_handler,
        )
        state.state_writer.mark_started()
        state.logger.log("info", "plan started", run_name=resolved_run_name, plan_path=str(resolved_plan_path) if resolved_plan_path else None)
        executor = ActionExecutor(state)
        try:
            executor.run(plan.get("steps", []))
        except Exception as error:
            status = "failed"
            error_message = str(error)
            caught_error = error
        finally:
            if status == "passed" and _should_wait_for_inspection(plan_config):
                if inspection_confirmation_handler is not None:
                    prompt = _inspection_prompt(plan_config)
                    state.logger.log("info", "waiting for post-run inspection confirmation", prompt=prompt)
                    state.state_writer.mark_waiting(prompt=prompt, wait_type="post_run_inspection")
                    accepted = inspection_confirmation_handler(prompt)
                    state.state_writer.mark_resumed()
                    if not accepted:
                        status = "failed"
                        error_message = "Post-run inspection was not accepted."
                        caught_error = RuntimeError(error_message)
                else:
                    state.logger.log(
                        "warning",
                        "post-run inspection wait requested but no confirmation handler is available",
                    )
            state.close_all()
            state.logger.log("info", "plan finished", run_name=resolved_run_name)
            finished_at = datetime.now().isoformat(timespec="seconds")
            result = PlanResult(
                run_name=resolved_run_name,
                status=status,
                plan_path=str(resolved_plan_path) if resolved_plan_path else None,
                output_dir=str(resolved_output_dir),
                started_at=started_at,
                finished_at=finished_at,
                error=error_message,
                failure_screenshots=list(state.failure_screenshots),
                failure_htmls=list(state.failure_htmls),
                failure_page_states=list(state.failure_page_states),
                tags=list(plan.get("tags", [])),
                metadata={
                    "downloads": list(state.downloads),
                    "last_dialog_message": state.last_dialog_message,
                },
            )
            write_result_json(result, resolved_output_dir)
            write_report_markdown(result, resolved_output_dir)
            state.state_writer.mark_finished(status=status, error=error_message)

        if caught_error is not None:
            raise caught_error

    if result is None:
        raise RuntimeError("Plan result was not created.")
    return result


def _build_builtin_variables(
    project_root: Path,
    plan_dir: Path,
    output_dir: Path,
    plan_config: dict[str, Any],
    plan_variables: dict[str, Any],
    variable_overrides: dict[str, Any],
) -> dict[str, Any]:
    variables = {
        "project_root": str(project_root),
        "plan_dir": str(plan_dir),
        "plan_dir_file_url": _file_url(plan_dir),
        "resources_dir": str(plan_dir / "resources"),
        "resources_file_url": _file_url(plan_dir / "resources"),
        "output_dir": str(plan_dir / "output"),
        "output_dir_file_url": _file_url(plan_dir / "output"),
        "run_output_dir": str(output_dir),
        "run_output_dir_file_url": _file_url(output_dir),
        "config": plan_config,
    }
    config_variables = plan_config.get("variables", {})
    if config_variables:
        if not isinstance(config_variables, dict):
            raise ValueError("Plan config field 'variables' must be a JSON object.")
        variables.update(config_variables)
    variables.update(plan_variables)
    variables.update(variable_overrides)
    return variables


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _should_wait_for_inspection(plan_config: dict[str, Any]) -> bool:
    runtime_config = plan_config.get("runtime", {})
    if not isinstance(runtime_config, dict):
        return False
    return bool(runtime_config.get("wait_for_inspection_on_success", False))


def _inspection_prompt(plan_config: dict[str, Any]) -> str:
    runtime_config = plan_config.get("runtime", {})
    default_prompt = "Plan steps passed. Inspect the browser, then confirm to close browsers and finish: "
    if not isinstance(runtime_config, dict):
        return default_prompt
    prompt = runtime_config.get("inspection_prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt
    return default_prompt
