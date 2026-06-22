from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_rules import FORBIDDEN_OUTPUT_ROOTS
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


def validate_output_path(
    raw_path: Any,
    category: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "output path 必须是非空字符串"))
        return

    path = path_from_text(raw_path)
    if "\\" in raw_path and not is_absolute_path_text(raw_path):
        issues.append(ValidationIssue(location, "plan JSON 内部路径必须使用 /，不要使用 Windows 反斜杠。"))
    if is_absolute_path_text(raw_path):
        issues.append(ValidationIssue(location, f"output path 必须相对于 output/{category}/"))
        return
    if not path.parts:
        issues.append(ValidationIssue(location, "output path 不能为空"))
        return
    if path.parts[0] in FORBIDDEN_OUTPUT_ROOTS:
        issues.append(
            ValidationIssue(
                location,
                f"output path 已经相对于 output/{category}/；不要以 {path.parts[0]}/ 开头",
            )
        )
        return
    if "{{" in raw_path or "}}" in raw_path:
        return

    output_root = (package_root / "output").resolve()
    category_root = (output_root / category).resolve()
    resolved_path = (category_root / path).resolve() if path.parts[0] != category else (output_root / path).resolve()
    if not is_relative_to(resolved_path, output_root):
        issues.append(ValidationIssue(location, "output path 必须位于当前 plan output 目录内"))
    if not is_relative_to(resolved_path, category_root):
        issues.append(ValidationIssue(location, f"当前 action 的 output path 必须位于 output/{category}/ 内"))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
