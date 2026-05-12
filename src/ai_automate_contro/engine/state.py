from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


class RunStateWriter:
    def __init__(self, output_dir: Path, *, run_name: str, plan_path: str | None) -> None:
        self.output_dir = output_dir
        self.state_path = output_dir / "state.json"
        self._lock = Lock()
        now = _now()
        self._state: dict[str, Any] = {
            "run_name": run_name,
            "plan_path": plan_path,
            "output_dir": str(output_dir),
            "status": "created",
            "current_step": None,
            "waiting": None,
            "started_at": None,
            "updated_at": now,
            "finished_at": None,
            "error": None,
        }
        self.write()

    def mark_started(self) -> None:
        self.update(status="running", started_at=_now())

    def mark_step_started(self, *, step: int, action: str, step_name: str) -> None:
        self.update(
            status="running",
            current_step={
                "step": step,
                "action": action,
                "step_name": step_name,
                "status": "running",
            },
            waiting=None,
        )

    def mark_step_finished(self, *, step: int, action: str, step_name: str) -> None:
        self.update(
            status="running",
            current_step={
                "step": step,
                "action": action,
                "step_name": step_name,
                "status": "finished",
            },
            waiting=None,
        )

    def mark_waiting(self, *, prompt: str, wait_type: str = "manual_confirm") -> None:
        self.update(status="waiting", waiting={"type": wait_type, "prompt": prompt})

    def mark_resumed(self) -> None:
        self.update(status="running", waiting=None)

    def mark_finished(self, *, status: str, error: str | None) -> None:
        self.update(status=status, finished_at=_now(), waiting=None, error=error)

    def update(self, **changes: Any) -> None:
        with self._lock:
            self._state.update(changes)
            self._state["updated_at"] = _now()
            self._write_unlocked()

    def write(self) -> None:
        with self._lock:
            self._write_unlocked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _write_unlocked(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as file:
            json.dump(self._state, file, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
