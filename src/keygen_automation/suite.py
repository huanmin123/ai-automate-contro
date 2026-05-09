from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from keygen_automation.executor import execute_plan
from keygen_automation.filters import matches_tags
from keygen_automation.logger import RunLogger
from keygen_automation.plan_loader import load_plan
from keygen_automation.results import PlanResult
from keygen_automation.utils import ensure_directory, make_timestamp, sanitize_name


@dataclass
class SuiteItemResult:
    name: str
    path: str
    status: str
    tags: list[str]
    result: dict[str, Any] | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def execute_suite(suite: dict[str, Any], project_root: str | Path, suite_path: str | Path) -> None:
    root_path = Path(project_root).resolve()
    suite_file = Path(suite_path).resolve()
    suite_name = suite.get("name", suite_file.stem)
    run_root = ensure_directory(root_path / "output" / "suite-runs" / f"{make_timestamp()}-{sanitize_name(suite_name)}")
    logger = RunLogger(run_root)
    mode = suite.get("mode", "sequential")
    plans = suite.get("plans", [])
    include_tags = list(suite.get("include_tags", []))
    exclude_tags = list(suite.get("exclude_tags", []))
    tag_mode = suite.get("tag_mode", "any")

    logger.log(
        "info",
        "suite started",
        suite=suite_name,
        mode=mode,
        count=len(plans),
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        tag_mode=tag_mode,
    )

    selected_entries, skipped_results = _filter_entries(plans, include_tags, exclude_tags, tag_mode, logger)

    if mode == "sequential":
        executed_results = _run_sequential(selected_entries, root_path, suite_file.parent, run_root, logger)
    elif mode == "parallel":
        executed_results = _run_parallel(
            selected_entries,
            root_path,
            suite_file.parent,
            run_root,
            logger,
            int(suite.get("max_workers", len(selected_entries) or 1)),
        )
    else:
        raise ValueError(f"Unsupported suite mode: {mode}")

    all_results = skipped_results + executed_results
    _write_suite_report(run_root, suite_name, mode, all_results)
    logger.log("info", "suite finished", suite=suite_name, mode=mode, count=len(all_results))


def _filter_entries(
    plan_entries: list[dict[str, Any]],
    include_tags: list[str],
    exclude_tags: list[str],
    tag_mode: str,
    logger: RunLogger,
) -> tuple[list[dict[str, Any]], list[SuiteItemResult]]:
    selected: list[dict[str, Any]] = []
    skipped: list[SuiteItemResult] = []

    for entry in plan_entries:
        tags = list(entry.get("tags", []))
        if matches_tags(tags, include_tags=include_tags, exclude_tags=exclude_tags, tag_mode=tag_mode):
            selected.append(entry)
            continue

        logger.log("info", "suite item skipped", name=entry.get("name"), tags=tags)
        skipped.append(
            SuiteItemResult(
                name=entry.get("name", Path(entry["path"]).stem),
                path=entry["path"],
                status="skipped",
                tags=tags,
                skip_reason="tag filtered",
            )
        )

    return selected, skipped


def _run_sequential(
    plan_entries: list[dict[str, Any]],
    project_root: Path,
    suite_dir: Path,
    run_root: Path,
    logger: RunLogger,
) -> list[SuiteItemResult]:
    results: list[SuiteItemResult] = []
    for index, entry in enumerate(plan_entries, start=1):
        logger.log("info", "suite item start", index=index, name=entry.get("name"))
        results.append(_run_plan_entry(entry, project_root, suite_dir, run_root, logger))
        logger.log("info", "suite item finished", index=index, name=entry.get("name"))
    return results


def _run_parallel(
    plan_entries: list[dict[str, Any]],
    project_root: Path,
    suite_dir: Path,
    run_root: Path,
    logger: RunLogger,
    max_workers: int,
) -> list[SuiteItemResult]:
    futures = {}
    results: list[SuiteItemResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for entry in plan_entries:
            future = executor.submit(_run_plan_entry, entry, project_root, suite_dir, run_root, logger)
            futures[future] = entry

        for future in as_completed(futures):
            entry = futures[future]
            result = future.result()
            results.append(result)
            logger.log("info", "suite parallel item finished", name=entry.get("name"), status=result.status)

    return results


def _run_plan_entry(
    entry: dict[str, Any],
    project_root: Path,
    suite_dir: Path,
    run_root: Path,
    logger: RunLogger,
) -> SuiteItemResult:
    plan_path = (suite_dir / entry["path"]).resolve()
    plan = load_plan(plan_path)
    overrides = dict(entry.get("variables", {}))
    if overrides:
        plan.setdefault("variables", {}).update(overrides)

    plan_tags = list(dict.fromkeys(list(plan.get("tags", [])) + list(entry.get("tags", []))))
    if plan_tags:
        plan["tags"] = plan_tags

    plan_name = entry.get("name", plan_path.stem)
    plan_output_dir = run_root / sanitize_name(plan_name)
    logger.log("info", "plan dispatch", name=plan_name, path=str(plan_path), tags=plan_tags)

    try:
        plan_result = execute_plan(
            plan,
            project_root=project_root,
            plan_path=plan_path,
            run_name=plan_name,
            output_dir=plan_output_dir,
        )
        return SuiteItemResult(
            name=plan_name,
            path=entry["path"],
            status=plan_result.status,
            tags=plan_tags,
            result=plan_result.to_dict(),
        )
    except Exception as error:
        result_path = plan_output_dir / "result.json"
        result_payload = None
        if result_path.exists():
            with result_path.open("r", encoding="utf-8") as file:
                result_payload = json.load(file)
        logger.log("error", "plan execution failed", name=plan_name, error=str(error))
        return SuiteItemResult(
            name=plan_name,
            path=entry["path"],
            status="failed",
            tags=plan_tags,
            result=result_payload,
        )


def _write_suite_report(run_root: Path, suite_name: str, mode: str, results: list[SuiteItemResult]) -> None:
    summary = {
        "suite": suite_name,
        "mode": mode,
        "total": len(results),
        "passed": sum(1 for item in results if item.status == "passed"),
        "failed": sum(1 for item in results if item.status == "failed"),
        "skipped": sum(1 for item in results if item.status == "skipped"),
        "items": [item.to_dict() for item in results],
    }

    with (run_root / "suite-summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    markdown_lines = [
        f"# Suite Report: {suite_name}",
        "",
        f"- mode: `{mode}`",
        f"- total: `{summary['total']}`",
        f"- passed: `{summary['passed']}`",
        f"- failed: `{summary['failed']}`",
        f"- skipped: `{summary['skipped']}`",
        "",
        "## Items",
        "",
        "| Name | Status | Tags | Path |",
        "| --- | --- | --- | --- |",
    ]
    for item in results:
        markdown_lines.append(
            f"| {item.name} | {item.status} | {', '.join(item.tags)} | {item.path} |"
        )

    with (run_root / "suite-summary.md").open("w", encoding="utf-8") as file:
        file.write("\n".join(markdown_lines) + "\n")
