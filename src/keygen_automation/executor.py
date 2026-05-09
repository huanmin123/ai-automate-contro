from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime

from playwright.sync_api import sync_playwright

from keygen_automation.actions import ActionExecutor
from keygen_automation.ai_registry import AiRegistry
from keygen_automation.config import load_plan_config
from keygen_automation.logger import RunLogger
from keygen_automation.results import PlanResult, write_result_json
from keygen_automation.runtime import RuntimeState
from keygen_automation.utils import ensure_directory, make_timestamp, sanitize_name


def execute_plan(
    plan: dict[str, Any],
    project_root: str | Path,
    plan_path: str | Path | None = None,
    run_name: str | None = None,
    output_dir: str | Path | None = None,
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
    logger = RunLogger(resolved_output_dir)
    plan_config = load_plan_config(root_path, plan_dir)
    variables = _build_builtin_variables(
        project_root=root_path,
        plan_dir=plan_dir,
        output_dir=resolved_output_dir,
        plan_config=plan_config,
        plan_variables=dict(plan.get("variables", {})),
    )

    started_at = datetime.now().isoformat(timespec="seconds")
    error_message: str | None = None
    status = "passed"

    result: PlanResult | None = None

    with sync_playwright() as playwright:
        state = RuntimeState(
            project_root=root_path,
            playwright=playwright,
            run_name=resolved_run_name,
            output_dir=resolved_output_dir,
            logger=logger,
            plan_path=resolved_plan_path,
            package_dir=plan_dir,
            variables=variables,
            ai_registry=AiRegistry(plan_config),
        )
        state.logger.log("info", "plan started", run_name=resolved_run_name, plan_path=str(resolved_plan_path) if resolved_plan_path else None)
        executor = ActionExecutor(state)
        try:
            executor.run(plan.get("steps", []))
        except Exception as error:
            status = "failed"
            error_message = str(error)
            raise
        finally:
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
                tags=list(plan.get("tags", [])),
                metadata={
                    "downloads": list(state.downloads),
                    "last_dialog_message": state.last_dialog_message,
                },
            )
            write_result_json(result, resolved_output_dir)

    if result is None:
        raise RuntimeError("Plan result was not created.")
    return result


def _build_builtin_variables(
    project_root: Path,
    plan_dir: Path,
    output_dir: Path,
    plan_config: dict[str, Any],
    plan_variables: dict[str, Any],
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
    return variables


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()
