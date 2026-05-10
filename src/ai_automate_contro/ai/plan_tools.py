from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import detect_document_type, load_plan
from ai_automate_contro.plans.packages import (
    create_plan_package,
    discover_plan_packages,
    plan_matches_filter,
    summarize_plan,
)
from ai_automate_contro.plans.validator import ValidationIssue, validate_plan_file


def list_plan_packages_tool(project_root: str | Path, *, filter_text: str = "") -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_filter = filter_text.lower().strip()
    plan_paths = discover_plan_packages(root)
    if normalized_filter:
        plan_paths = [
            plan_path
            for plan_path in plan_paths
            if plan_matches_filter(plan_path, root, normalized_filter)
        ]
    return {
        "ok": True,
        "plans": [summarize_plan(plan_path, root) for plan_path in plan_paths],
    }


def read_plan_package_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent
    document = read_json_if_exists(resolved_plan_path)
    local_config = read_json_if_exists(package_dir / "config.json")
    docs = read_package_docs(package_dir)
    sub_plans = read_sub_plans(package_dir)
    resources = list_package_files(package_dir / "resources", package_dir)
    return {
        "ok": True,
        "summary": summarize_plan(resolved_plan_path, root),
        "plan": document,
        "config": local_config,
        "docs": docs,
        "sub_plans": sub_plans,
        "resources": resources,
    }


def create_plan_package_tool(
    project_root: str | Path,
    package_path: str | Path,
    *,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    package_dir = create_plan_package(package_path, project_root=root, name=name, force=force)
    return {
        "ok": True,
        "package_dir": str(package_dir),
        "plan_path": str(package_dir / "plan.json"),
        "summary": summarize_plan(package_dir / "plan.json", root),
    }


def validate_plan_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    result = validate_plan_file(plan_path, project_root)
    return {
        "ok": result.ok,
        "plan_path": str(result.plan_path),
        "errors": [issue_to_dict(error) for error in result.errors],
    }


def run_plan_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
    latest_state_reader: Any | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    document = load_plan(plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("Only plan documents can be executed.")
    try:
        result = execute_plan(
            document,
            root,
            plan_path=plan_path,
            run_name=run_name,
            variable_overrides=variable_overrides or {},
        )
    except Exception as error:
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(error),
        }
        if latest_state_reader is not None:
            payload["latest_state"] = latest_state_reader(plan_path)
        return payload
    return {
        "ok": result.status == "passed",
        "result": result.to_dict(),
    }


def resolve_plan_path(raw_plan_path: str | Path) -> Path:
    plan_path = Path(raw_plan_path).resolve()
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"
    return plan_path


def issue_to_dict(issue: ValidationIssue) -> dict[str, str]:
    return {
        "location": issue.location,
        "message": issue.message,
        "formatted": issue.format(),
    }


def read_package_docs(package_dir: Path) -> list[dict[str, Any]]:
    docs_dir = package_dir / "docs"
    docs: list[dict[str, Any]] = []
    if not docs_dir.exists():
        return docs
    for path in sorted(docs_dir.rglob("*.md"), key=lambda item: str(item).lower()):
        docs.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "content": path.read_text(encoding="utf-8", errors="replace"),
            }
        )
    return docs


def read_sub_plans(package_dir: Path) -> list[dict[str, Any]]:
    sub_plans_dir = package_dir / "sub-plans"
    sub_plans: list[dict[str, Any]] = []
    if not sub_plans_dir.exists():
        return sub_plans
    for path in sorted(sub_plans_dir.glob("*-plan.json"), key=lambda item: str(item).lower()):
        sub_plans.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "document": read_json_if_exists(path),
            }
        )
    return sub_plans


def list_package_files(root: Path, package_dir: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return files


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
