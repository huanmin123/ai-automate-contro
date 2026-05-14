from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.models import DebugInjectionResult
from ai_automate_contro.debug.workspace_paths import load_workspace_manifest
from ai_automate_contro.support.paths import path_from_text
from ai_automate_contro.support.utils import ensure_directory, make_timestamp


def inject_debug_steps(
    workspace: str | Path,
    *,
    presets: list[str],
    message: str | None = None,
    browser: str | None = None,
    page: str | None = None,
    position: str = "end",
    step: int | None = None,
) -> DebugInjectionResult:
    workspace_root = path_from_text(workspace).resolve()
    manifest = load_workspace_manifest(workspace_root)
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    plan_path = injected_plan_dir / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"注入后的 plan 不存在：{plan_path}")

    document = _load_plan_document(plan_path)
    steps = document.setdefault("steps", [])
    if not isinstance(steps, list):
        raise ValueError(f"注入后的 plan steps 必须是数组：{plan_path}")

    normalized_presets = [_normalize_preset(preset) for preset in presets]
    injected_steps = [
        _build_debug_step(preset, message=message, browser=browser, page=page)
        for preset in normalized_presets
    ]
    backup_path = _backup_plan(plan_path)
    if position == "start":
        steps[0:0] = injected_steps
    elif position == "end":
        steps.extend(injected_steps)
    elif position in {"before_step", "after_step"}:
        if step is None or step < 1:
            raise ValueError("position 为 before_step 或 after_step 时，step 必须是从 1 开始的正整数。")
        if step > len(steps):
            raise ValueError(f"step {step} 超出注入后 plan 的步骤范围 1..{len(steps)}。")
        insertion_index = step - 1 if position == "before_step" else step
        steps[insertion_index:insertion_index] = injected_steps
    else:
        raise ValueError("position 必须是 start、end、before_step 或 after_step。")
    _write_plan_document(plan_path, document)
    _append_injection_note(workspace_root, injected_steps, position=position, step=step)
    return DebugInjectionResult(
        workspace_root=workspace_root,
        plan_path=plan_path,
        injected_steps=injected_steps,
        backup_path=backup_path,
    )


def _load_plan_document(plan_path: Path) -> dict[str, Any]:
    with plan_path.open("r", encoding="utf-8") as file:
        document = json.load(file)
    if not isinstance(document, dict):
        raise ValueError(f"plan 文档必须是 JSON 对象：{plan_path}")
    return document


def _write_plan_document(plan_path: Path, document: dict[str, Any]) -> None:
    with plan_path.open("w", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _backup_plan(plan_path: Path) -> Path:
    backup_dir = ensure_directory(plan_path.parent / ".debug-backups")
    backup_path = backup_dir / f"{make_timestamp()}-plan.json"
    shutil.copy2(plan_path, backup_path)
    return backup_path


def _normalize_preset(preset: str) -> str:
    value = preset.strip().lower()
    supported = {"print", "variables", "manual_confirm", "screenshot", "html"}
    if value not in supported:
        raise ValueError(f"Unsupported debug injection preset: {preset}")
    return value


def _build_debug_step(
    preset: str,
    *,
    message: str | None,
    browser: str | None,
    page: str | None,
) -> dict[str, Any]:
    if preset == "print":
        return {
            "action": "print",
            "message": message or "[debug] checkpoint reached",
        }
    if preset == "variables":
        return {
            "action": "write",
            "type": "variables",
            "path": f"debug/variables-{make_timestamp()}.json",
        }
    if preset == "manual_confirm":
        return {
            "action": "manual_confirm",
            "prompt": message or "Debug checkpoint reached. Finish manual checks, then continue.",
        }
    if preset == "screenshot":
        _require_browser_for_preset(preset, browser)
        step: dict[str, Any] = {
            "action": "capture",
            "type": "screenshot",
            "browser": browser,
            "path": f"debug/screenshots/screenshot-{make_timestamp()}.png",
            "full_page": True,
        }
        if page:
            step["page"] = page
        return step
    if preset == "html":
        _require_browser_for_preset(preset, browser)
        step = {
            "action": "capture",
            "type": "html",
            "browser": browser,
            "path": f"debug/html/page-{make_timestamp()}.html",
        }
        if page:
            step["page"] = page
        return step
    raise ValueError(f"Unsupported debug injection preset: {preset}")


def _require_browser_for_preset(preset: str, browser: str | None) -> None:
    if not browser:
        raise ValueError(f"Debug preset '{preset}' requires --browser <name>.")


def _append_injection_note(
    workspace_root: Path,
    injected_steps: list[dict[str, Any]],
    *,
    position: str,
    step: int | None,
) -> None:
    notes_path = workspace_root / "notes.md"
    with notes_path.open("a", encoding="utf-8") as file:
        file.write("\n## Injection\n\n")
        file.write(f"- Time: {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"- Position: {position}\n")
        if step is not None:
            file.write(f"- Anchor step: {step}\n")
        file.write("- Steps:\n\n")
        file.write("```json\n")
        json.dump(injected_steps, file, ensure_ascii=False, indent=2)
        file.write("\n```\n")
