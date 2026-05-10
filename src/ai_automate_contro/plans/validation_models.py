from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationIssue:
    location: str
    message: str

    def format(self) -> str:
        return f"{self.location}: {self.message}"


@dataclass(frozen=True)
class ValidationResult:
    plan_path: Path
    errors: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors
