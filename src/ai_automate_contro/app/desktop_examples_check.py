from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file


def self_check_desktop_examples(
    project_root: str | Path,
    *,
    require_vision: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    examples_root = root / "test-plans" / "desktop"
    plan_paths = _desktop_example_plan_paths(examples_root)
    results = [
        _run_desktop_example(root, plan_path, require_vision=require_vision)
        for plan_path in plan_paths
    ]
    return {
        "ok": bool(plan_paths) and all(bool(result.get("ok")) for result in results),
        "check": "desktop_examples",
        "project_root": str(root),
        "examples_root": str(examples_root),
        "platform": platform.system(),
        "require_vision": bool(require_vision),
        "plan_count": len(plan_paths),
        "results": results,
        "commands": {
            "run": "python .\\cplan.py self-check desktop-examples",
            "run_require_vision": "python .\\cplan.py self-check desktop-examples --require-vision",
        },
    }


def _desktop_example_plan_paths(examples_root: Path) -> list[Path]:
    if not examples_root.exists():
        return []
    return sorted(
        path
        for path in examples_root.glob("*/plan.json")
        if path.is_file() and path.parent.name != "output"
    )


def _run_desktop_example(root: Path, plan_path: Path, *, require_vision: bool) -> dict[str, Any]:
    relative = plan_path.relative_to(root).as_posix()
    validation = validate_plan_file(plan_path, root)
    validation_errors = [error.format() for error in validation.errors]
    if not validation.ok:
        return {
            "name": plan_path.parent.name,
            "ok": False,
            "plan_path": str(plan_path),
            "relative_path": relative,
            "validation_ok": False,
            "errors": validation_errors,
        }
    skip_reason = _desktop_example_skip_reason(plan_path, require_vision=require_vision)
    if skip_reason:
        return {
            "name": plan_path.parent.name,
            "ok": True,
            "skipped": True,
            "reason": skip_reason,
            "plan_path": str(plan_path),
            "relative_path": relative,
            "validation_ok": True,
        }
    run_error = ""
    output_dir = ""
    try:
        plan = load_plan(plan_path)
        result = execute_plan(
            plan,
            root,
            plan_path=plan_path,
            run_name=f"desktop-example-{plan_path.parent.name}",
            log_echo=False,
        )
        run_ok = result.status == "passed"
        output_dir = result.output_dir
    except Exception as error:
        run_ok = False
        run_error = str(error)
    return {
        "name": plan_path.parent.name,
        "ok": run_ok,
        "plan_path": str(plan_path),
        "relative_path": relative,
        "validation_ok": True,
        "run_ok": run_ok,
        "output_dir": output_dir,
        "run_error": run_error,
    }


def _desktop_example_skip_reason(plan_path: Path, *, require_vision: bool) -> str:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return f"desktop examples only run on Windows/macOS, current={system}"
    if plan_path.parent.name == "offline-vision" and not (_module_available("cv2") and _module_available("PIL")):
        reason = "offline vision example requires opencv-python and Pillow"
        if require_vision:
            return ""
        return reason
    return ""


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except Exception:
        return False
    return True
