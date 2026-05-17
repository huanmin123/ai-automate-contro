from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class RunLogger:
    output_dir: Path
    echo: bool = True
    event_callback: Callable[[dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output_dir / "run.log"
        self.events_path = self.output_dir / "events.jsonl"
        self._lock = Lock()

    def log(self, level: str, message: str, **fields: Any) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        event = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message,
            "fields": fields,
        }
        line = f"[{timestamp}][{level.upper()}] {message}"
        if fields:
            line = f"{line} | {json.dumps(fields, ensure_ascii=False)}"

        with self._lock:
            if self.echo:
                print(line)

            with self.log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{line}\n")

            with self.events_path.open("a", encoding="utf-8") as events_file:
                events_file.write(json.dumps(event, ensure_ascii=False) + "\n")

        callback = self.event_callback
        if callback is not None:
            try:
                callback(dict(event))
            except Exception:
                return
