from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PlanResult:
    run_name: str
    status: str
    plan_path: str | None
    output_dir: str
    started_at: str
    finished_at: str
    error: str | None = None
    failure_screenshots: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_result_json(result: PlanResult, output_dir: Path) -> Path:
    result_path = output_dir / "result.json"
    import json

    with result_path.open("w", encoding="utf-8") as file:
        json.dump(result.to_dict(), file, ensure_ascii=False, indent=2)
    return result_path
