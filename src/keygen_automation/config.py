from __future__ import annotations

from pathlib import Path


def ensure_config_directory(project_root: Path) -> Path:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir
