from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.support.logger import RunLogger
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.results import PlanResult


class InteractiveRun:
    def __init__(
        self,
        *,
        plan_path: str | Path,
        project_root: str | Path,
        run_name: str | None = None,
        variable_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.plan_path = Path(plan_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.run_name = run_name
        self.variable_overrides = variable_overrides or {}
        self.result: PlanResult | None = None
        self.error: BaseException | None = None
        self.output_dir: Path | None = None
        self.logger: RunLogger | None = None
        self.waiting_prompt: str | None = None
        self.status = "created"
        self._condition = threading.Condition()
        self._continue_requested = False
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run, name="interactive-plan-run", daemon=True)

    def start(self) -> None:
        self.status = "running"
        self._thread.start()

    def continue_run(self) -> None:
        with self._condition:
            if self.status != "waiting":
                raise RuntimeError(f"Run is not waiting. Current status: {self.status}")
            self._continue_requested = True
            self.waiting_prompt = None
            self.status = "running"
            self._record_command("continue", status="accepted")
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            if self.status != "waiting":
                raise RuntimeError(f"Only a waiting run can be stopped. Current status: {self.status}")
            self._stop_requested = True
            self.status = "stopping"
            self._record_command("stop", status="accepted")
            self._condition.notify_all()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        try:
            plan = load_plan(self.plan_path)
            self.result = execute_plan(
                plan,
                self.project_root,
                plan_path=self.plan_path,
                run_name=self.run_name,
                variable_overrides=self.variable_overrides,
                manual_confirmation_handler=self._handle_manual_confirmation,
                run_context_handler=self._capture_run_context,
            )
            self.status = self.result.status
        except BaseException as error:
            self.error = error
            self.status = "failed"

    def _handle_manual_confirmation(self, prompt: str) -> bool:
        with self._condition:
            self.waiting_prompt = prompt
            self.status = "waiting"
            while not self._continue_requested and not self._stop_requested:
                self._condition.wait(timeout=0.25)
            if self._stop_requested:
                return False
            self._continue_requested = False
            return True

    def _capture_run_context(self, output_dir: Path, logger: RunLogger) -> None:
        with self._condition:
            self.output_dir = output_dir
            self.logger = logger
            self._write_command_unlocked("run_context", status="created", details={"output_dir": str(output_dir)})

    def _record_command(self, command: str, *, status: str, details: dict[str, Any] | None = None) -> None:
        self._write_command_unlocked(command, status=status, details=details or {})

    def _write_command_unlocked(self, command: str, *, status: str, details: dict[str, Any]) -> None:
        if self.output_dir is None:
            return
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "command": command,
            "status": status,
            "details": details,
        }
        commands_path = self.output_dir / "commands.jsonl"
        with commands_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.logger is not None and command != "run_context":
            self.logger.log("info", "run command received", command=command, status=status, **details)
