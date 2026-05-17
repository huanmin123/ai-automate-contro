from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.support.logger import RunLogger
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.results import PlanResult
from ai_automate_contro.support.paths import path_from_text


class InteractiveRun:
    def __init__(
        self,
        *,
        plan_path: str | Path,
        project_root: str | Path,
        run_name: str | None = None,
        variable_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.plan_path = path_from_text(plan_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.run_name = run_name
        self.variable_overrides = variable_overrides or {}
        self.result: PlanResult | None = None
        self.error: BaseException | None = None
        self.output_dir: Path | None = None
        self.logger: RunLogger | None = None
        self.waiting_prompt: str | None = None
        self.waiting_type: str | None = None
        self.status = "created"
        self._events: deque[dict[str, Any]] = deque()
        self._condition = threading.Condition()
        self._continue_requested = False
        self._stop_requested = False
        self._interrupt_requested = False
        self._thread = threading.Thread(target=self._run, name="interactive-plan-run", daemon=True)

    def start(self) -> None:
        self.status = "running"
        self._thread.start()

    def continue_run(self, *, expected_waiting_type: str | None = None, command: str = "continue") -> None:
        with self._condition:
            if self.status != "waiting":
                raise RuntimeError(f"Run is not waiting. Current status: {self.status}")
            if expected_waiting_type is not None and self.waiting_type != expected_waiting_type:
                raise RuntimeError(f"Run is waiting for {self.waiting_type}; expected {expected_waiting_type}.")
            self._continue_requested = True
            self.waiting_prompt = None
            self.waiting_type = None
            self.status = "running"
            self._record_command(command, status="accepted")
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            if self.status != "waiting":
                raise RuntimeError(f"Only a waiting run can be stopped. Current status: {self.status}")
            self._stop_requested = True
            self.status = "stopping"
            self._record_command("stop", status="accepted")
            self._condition.notify_all()

    def request_interrupt(self) -> None:
        with self._condition:
            self._interrupt_requested = True
            self._stop_requested = True
            if self.status in {"created", "running", "waiting"}:
                self.status = "stopping"
            self._record_command("interrupt", status="accepted")
            self._condition.notify_all()
        self._close_browser_sessions()

    def is_interrupted(self) -> bool:
        with self._condition:
            return self._interrupt_requested

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def drain_events(self) -> list[dict[str, Any]]:
        with self._condition:
            events = list(self._events)
            self._events.clear()
            return events

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
                inspection_confirmation_handler=self._handle_post_run_inspection,
                run_context_handler=self._capture_run_context,
                interrupt_checker=self.is_interrupted,
                run_event_handler=self._capture_run_event,
                log_echo=False,
            )
            self.status = self.result.status
        except BaseException as error:
            self.error = error
            self.status = "failed"

    def _handle_manual_confirmation(self, prompt: str) -> bool:
        return self._handle_wait(prompt, wait_type="manual_confirm")

    def _handle_post_run_inspection(self, prompt: str) -> bool:
        return self._handle_wait(prompt, wait_type="post_run_inspection")

    def _handle_wait(self, prompt: str, *, wait_type: str) -> bool:
        with self._condition:
            self.waiting_prompt = prompt
            self.waiting_type = wait_type
            self.status = "waiting"
            while not self._continue_requested and not self._stop_requested:
                self._condition.wait(timeout=0.25)
            if self._stop_requested:
                self.waiting_type = None
                if self._interrupt_requested:
                    raise KeyboardInterrupt("用户中断。")
                return False
            self._continue_requested = False
            return True

    def _capture_run_context(self, output_dir: Path, logger: RunLogger) -> None:
        with self._condition:
            self.output_dir = output_dir
            self.logger = logger
            self._write_command_unlocked("run_context", status="created", details={"output_dir": str(output_dir)})

    def _capture_run_event(self, event: dict[str, Any]) -> None:
        with self._condition:
            self._events.append(dict(event))
            self._condition.notify_all()

    def _close_browser_sessions(self) -> None:
        logger = self.logger
        if logger is not None:
            logger.log("warning", "interrupt requested")
        # Browser objects are not guaranteed to be thread-safe. The cooperative
        # interrupt check will stop the run at the next action boundary; closing
        # is left to the executor finally block.

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
