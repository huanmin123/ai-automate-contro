from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import plan_roots_for_project
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.support.paths import path_from_text


def create_plan_package(
    raw_path: str | Path,
    *,
    project_root: Path,
    automation_type: str,
    name: str | None = None,
    force: bool = False,
) -> Path:
    if automation_type not in {"browser", "desktop"}:
        raise ValueError("automation_type 必须是 browser 或 desktop。")
    package_dir = path_from_text(raw_path).resolve()
    if package_dir.exists():
        existing_items = list(package_dir.iterdir())
        if existing_items and not force:
            raise FileExistsError(f"plan 包目录非空：{package_dir}")
    package_dir.mkdir(parents=True, exist_ok=True)

    plan_name = name or package_dir.name
    _write_json_if_missing(
        package_dir / "plan.json",
        {
            "name": plan_name,
            "automation_type": automation_type,
            "variables": {},
            "steps": [
                {
                    "action": "print",
                    "message": f"plan {plan_name} ready",
                }
            ],
        },
    )
    _write_json_if_missing(
        package_dir / "config.json",
        {
            "description": f"Local config for {plan_name}.",
        },
    )
    (package_dir / "sub-plans").mkdir(exist_ok=True)
    (package_dir / "resources").mkdir(exist_ok=True)
    (package_dir / "output").mkdir(exist_ok=True)
    docs_dir = package_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    readme_path = docs_dir / "README.md"
    if not readme_path.exists():
        plan_path_for_command = _display_path(package_dir / "plan.json", project_root)
        readme_path.write_text(
            f"# {plan_name}\n\n## 目标\n\n## 前置条件\n\n## 运行方式\n\n```powershell\npython .\\cplan.py run --file {plan_path_for_command}\n```\n",
            encoding="utf-8",
        )
    return package_dir


def default_plan_package_dir(project_root: Path, *, name: str) -> Path:
    slug = slugify_plan_name(name)
    roots = plan_roots_for_project(project_root)
    if not roots:
        raise ValueError("plan.config 必须至少定义一个 plan root。")
    return roots[0] / slug


def slugify_plan_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    return normalized or "new-plan"


def discover_plan_packages(project_root: Path) -> list[Path]:
    plan_paths: list[Path] = []
    for root in plan_roots_for_project(project_root):
        if not root.exists():
            continue
        for plan_path in root.rglob("plan.json"):
            if "output" in plan_path.parts or "sub-plans" in plan_path.parts:
                continue
            plan_paths.append(plan_path.resolve())
    return sorted(plan_paths, key=lambda item: str(item).lower())


def summarize_plan(plan_path: str | Path, project_root: Path) -> dict[str, Any]:
    resolved_plan_path = path_from_text(plan_path).resolve()
    if resolved_plan_path.is_dir():
        resolved_plan_path = resolved_plan_path / "plan.json"
    document = load_plan(resolved_plan_path)
    steps = document.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    variables = document.get("variables", {})
    if not isinstance(variables, dict):
        variables = {}
    tags = document.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    sub_plans = _collect_static_sub_plans(steps)
    latest_output = find_latest_run_output(resolved_plan_path.parent)
    try:
        relative_path = resolved_plan_path.relative_to(project_root.resolve())
    except ValueError:
        relative_path = resolved_plan_path
    return {
        "path": str(resolved_plan_path),
        "relative_path": str(relative_path),
        "package_dir": str(resolved_plan_path.parent),
        "name": document.get("name") or resolved_plan_path.parent.name,
        "automation_type": document.get("automation_type") or "",
        "tags": [str(tag) for tag in tags],
        "variables": sorted(str(key) for key in variables.keys()),
        "steps": len(steps),
        "sub_plans": sub_plans,
        "latest_output": str(latest_output) if latest_output is not None else "",
    }


def find_latest_run_output(plan_dir: Path) -> Path | None:
    output_dir = plan_dir / "output"
    if not output_dir.exists():
        return None
    candidates = [
        child
        for child in output_dir.iterdir()
        if child.is_dir() and ((child / "run.log").exists() or (child / "result.json").exists())
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime).resolve()


def plan_matches_filter(plan_path: Path, project_root: Path, filter_text: str) -> bool:
    if not filter_text:
        return True
    summary = summarize_plan(plan_path, project_root)
    relative_path = str(summary["relative_path"]).lower()
    tokens = {
        str(summary["name"]).lower(),
        *(str(tag).lower() for tag in summary["tags"]),
        *(part.lower() for part in Path(str(summary["relative_path"])).parts),
    }
    if filter_text in tokens:
        return True
    if len(filter_text) <= 2:
        return False
    searchable = " ".join([relative_path, str(summary["name"]).lower(), " ".join(summary["tags"]).lower()])
    return filter_text in searchable


def resolve_plan_path(raw_plan_path: str | Path) -> Path:
    plan_path = path_from_text(raw_plan_path).resolve()
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"
    return plan_path


def _collect_static_sub_plans(steps: list[Any]) -> list[str]:
    sub_plans: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if action == "run_sub_plan" and isinstance(step.get("path"), str):
            sub_plans.append(step["path"])
        if action == "if":
            for branch in ("then", "else"):
                branch_steps = step.get(branch, [])
                if isinstance(branch_steps, list):
                    sub_plans.extend(_collect_static_sub_plans(branch_steps))
        if action in {"foreach", "retry", "trigger"}:
            child_steps = step.get("steps", [])
            if isinstance(child_steps, list):
                sub_plans.extend(_collect_static_sub_plans(child_steps))
        if action == "trigger" and isinstance(step.get("path"), str):
            sub_plans.append(step["path"])
        trigger = step.get("trigger")
        if isinstance(trigger, dict):
            sub_plans.extend(_collect_static_sub_plans([trigger]))
    return sorted(dict.fromkeys(sub_plans))


def _write_json_if_missing(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        return
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _display_path(path: Path, project_root: Path) -> str:
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
        return f".\\{relative_path}".replace("/", "\\")
    except ValueError:
        return str(path)
