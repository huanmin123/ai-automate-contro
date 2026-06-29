from __future__ import annotations

import json
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
        evidence = (
            _desktop_example_evidence(plan_path.parent.name, root=root, output_dir=plan_path.parent / "output")
            if run_ok
            else {}
        )
        evidence_ok = bool(evidence.get("ok")) if evidence else run_ok
    except Exception as error:
        run_ok = False
        evidence = {}
        evidence_ok = False
        run_error = str(error)
    return {
        "name": plan_path.parent.name,
        "ok": run_ok and evidence_ok,
        "plan_path": str(plan_path),
        "relative_path": relative,
        "validation_ok": True,
        "run_ok": run_ok,
        "evidence_ok": evidence_ok,
        "evidence": evidence,
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


def _desktop_example_evidence(name: str, *, root: Path, output_dir: str) -> dict[str, Any]:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = root / output_path
    if name == "readonly-observe":
        return _readonly_observe_evidence(output_path)
    if name == "offline-vision":
        return _offline_vision_evidence(output_path)
    return {"ok": True, "checked": False, "reason": "No evidence contract for this desktop example."}


def _readonly_observe_evidence(output_dir: Path) -> dict[str, Any]:
    observe_path = output_dir / "desktop-state" / "observe.json"
    observe_screenshot_path = output_dir / "desktop-state" / "observe.png"
    capability_path = output_dir / "json" / "capability-matrix.json"
    target_candidates_path = output_dir / "json" / "target-candidates.json"
    windows_path = output_dir / "desktop-windows" / "windows.json"
    observe = _read_json(observe_path)
    capability = _read_json(capability_path)
    target_candidates = _read_json(target_candidates_path)
    windows = _read_json(windows_path)
    checks = {
        "observe_json": observe.get("kind") == "desktop_observation" and observe.get("ok") is True,
        "observe_screenshot": _file_nonempty(observe_screenshot_path),
        "capability_matrix": isinstance(capability.get("capabilities"), dict),
        "coordinate_profile": isinstance(observe.get("coordinate_profile"), dict)
        and observe["coordinate_profile"].get("kind") == "desktop_coordinate_profile",
        "target_candidates": target_candidates.get("kind") == "desktop_target_candidates",
        "windows": windows.get("ok") is True and isinstance(windows.get("windows"), list),
    }
    return {
        "ok": all(checks.values()),
        "checked": True,
        "type": "readonly_observe",
        "checks": checks,
        "paths": {
            "observe": str(observe_path),
            "observe_screenshot": str(observe_screenshot_path),
            "capability_matrix": str(capability_path),
            "target_candidates": str(target_candidates_path),
            "windows": str(windows_path),
        },
        "summary": {
            "window_count": observe.get("window_count", 0),
            "target_candidate_count": target_candidates.get("candidate_count", 0),
        },
    }


def _offline_vision_evidence(output_dir: Path) -> dict[str, Any]:
    vision_path = output_dir / "desktop-vision" / "offline-vision-match.json"
    source_path = output_dir / "desktop-vision" / "offline-vision-match-source.png"
    crop_path = output_dir / "desktop-vision" / "offline-vision-match-crop.png"
    annotated_path = output_dir / "desktop-vision" / "offline-vision-match-annotated.png"
    summary_path = output_dir / "json" / "offline-vision-summary.json"
    vision = _read_json(vision_path)
    summary = _read_json(summary_path)
    target_candidates = vision.get("target_candidates") if isinstance(vision.get("target_candidates"), dict) else {}
    best_candidate = (
        target_candidates.get("best_candidate") if isinstance(target_candidates.get("best_candidate"), dict) else {}
    )
    checks = {
        "vision_json": vision.get("ok") is True and vision.get("type") == "locate_image",
        "summary_json": summary.get("ok") is True and isinstance(summary.get("target_candidates"), dict),
        "source_image": _file_nonempty(source_path),
        "crop_image": _file_nonempty(crop_path),
        "annotated_image": _file_nonempty(annotated_path),
        "target_candidates": target_candidates.get("kind") == "desktop_target_candidates"
        and int(target_candidates.get("candidate_count", 0) or 0) >= 1,
        "offline_candidate_not_clickable": best_candidate.get("screen_clickable") is False,
    }
    return {
        "ok": all(checks.values()),
        "checked": True,
        "type": "offline_vision",
        "checks": checks,
        "paths": {
            "vision": str(vision_path),
            "source": str(source_path),
            "crop": str(crop_path),
            "annotated": str(annotated_path),
            "summary": str(summary_path),
        },
        "summary": {
            "match_score": vision.get("match", {}).get("score", "") if isinstance(vision.get("match"), dict) else "",
            "target_candidate_count": target_candidates.get("candidate_count", 0),
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _file_nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False
