from __future__ import annotations

from pathlib import Path

from ai_automate_contro.plans.validation_io import load_json_document, validate_config
from ai_automate_contro.plans.validation_models import ValidationIssue, ValidationResult
from ai_automate_contro.plans.validation_walker import validate_plan_document
from ai_automate_contro.support.paths import format_missing_path_message, path_from_text


def validate_plan_file(plan_path: str | Path, project_root: str | Path) -> ValidationResult:
    resolved_plan_path = path_from_text(plan_path).resolve()
    resolved_project_root = Path(project_root).resolve()
    issues: list[ValidationIssue] = []

    if not resolved_plan_path.exists():
        return ValidationResult(
            plan_path=resolved_plan_path,
            errors=(
                ValidationIssue(
                    str(resolved_plan_path),
                    format_missing_path_message(plan_path, resolved_plan_path, label="plan 文件"),
                ),
            ),
        )
    if resolved_plan_path.name != "plan.json":
        issues.append(
            ValidationIssue(
                str(resolved_plan_path),
                "directly executable plan files must be named plan.json",
            )
        )

    document = load_json_document(resolved_plan_path, issues)
    if document is None:
        return ValidationResult(resolved_plan_path, tuple(issues))

    plan_dir = resolved_plan_path.parent
    validate_config(resolved_project_root, plan_dir, issues)
    validate_plan_document(
        document,
        document_path=resolved_plan_path,
        package_root=plan_dir,
        issues=issues,
        stack=[],
    )
    return ValidationResult(resolved_plan_path, tuple(issues))
