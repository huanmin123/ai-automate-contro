from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.plans.validation_models import ValidationIssue
from ai_automate_contro.plans.validation_rules import FORBIDDEN_OUTPUT_ROOTS


def validate_output_path(
    raw_path: Any,
    category: str,
    location: str,
    package_root: Path,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(raw_path, str) or not raw_path:
        issues.append(ValidationIssue(location, "output path must be a non-empty string"))
        return

    path = Path(raw_path)
    if path.is_absolute():
        issues.append(ValidationIssue(location, f"output path must be relative to output/{category}/"))
        return
    if not path.parts:
        issues.append(ValidationIssue(location, "output path cannot be empty"))
        return
    if path.parts[0] in FORBIDDEN_OUTPUT_ROOTS:
        issues.append(
            ValidationIssue(
                location,
                f"output path is already relative to output/{category}/; do not start with {path.parts[0]}/",
            )
        )
        return
    if "{{" in raw_path or "}}" in raw_path:
        return

    output_root = (package_root / "output").resolve()
    category_root = (output_root / category).resolve()
    resolved_path = (category_root / path).resolve() if path.parts[0] != category else (output_root / path).resolve()
    if not is_relative_to(resolved_path, output_root):
        issues.append(ValidationIssue(location, "output path must stay inside the current plan output directory"))
    if not is_relative_to(resolved_path, category_root):
        issues.append(ValidationIssue(location, f"output path for this action must stay inside output/{category}/"))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
