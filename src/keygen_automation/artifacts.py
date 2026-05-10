from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OutputArtifact:
    path: Path
    relative_path: Path
    size: int
    modified_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": str(self.relative_path),
            "size": self.size,
            "modified_at": self.modified_at,
        }


def list_output_artifacts(
    plan_path: str | Path,
    *,
    filter_text: str = "",
    limit: int = 100,
) -> list[OutputArtifact]:
    resolved_plan_path = Path(plan_path).resolve()
    if resolved_plan_path.is_dir():
        resolved_plan_path = resolved_plan_path / "plan.json"
    output_root = resolved_plan_path.parent / "output"
    if not output_root.exists():
        return []

    normalized_filter = filter_text.lower().strip()
    artifacts: list[OutputArtifact] = []
    for path in output_root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(output_root)
        if normalized_filter and normalized_filter not in str(relative_path).lower():
            continue
        stat = path.stat()
        artifacts.append(
            OutputArtifact(
                path=path.resolve(),
                relative_path=relative_path,
                size=stat.st_size,
                modified_at=stat.st_mtime,
            )
        )
    artifacts.sort(key=lambda item: item.modified_at, reverse=True)
    return artifacts[:limit]
