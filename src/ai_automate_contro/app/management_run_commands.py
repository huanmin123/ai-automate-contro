from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.interactive import InteractiveRun
from ai_automate_contro.plans.packages import find_latest_run_output


class RunCommandsMixin:
    def do_run(self, arg: str) -> None:
        """校验并运行当前 plan：run [run-name]"""
        self._sync_active_run()
        if self.active_run is not None and self.active_run.status in {"running", "waiting", "stopping"}:
            self.perror(f"a run is already active: {self.active_run.status}")
            return
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(error)
            return
        run_name = arg.strip() or None

        if not self._print_validation(plan_path):
            return
        self.active_run = InteractiveRun(
            plan_path=plan_path,
            project_root=self.project_root,
            run_name=run_name,
            variable_overrides=dict(self.variables),
        )
        self.last_run_error = None
        self.active_run.start()
        self._wait_for_interactive_checkpoint()
        self._print_active_run_state()

    def do_continue(self, _: str) -> None:
        """继续正在 manual_confirm 等待的运行。"""
        self._sync_active_run()
        if self.active_run is None:
            self.perror("no active run")
            return
        try:
            self.active_run.continue_run()
        except Exception as error:
            self.perror(error)
            return
        self._wait_for_interactive_checkpoint()
        self._print_active_run_state()

    def do_stop(self, _: str) -> None:
        """停止正在 manual_confirm 等待的运行。"""
        self._sync_active_run()
        if self.active_run is None:
            self.perror("no active run")
            return
        try:
            self.active_run.stop()
        except Exception as error:
            self.perror(error)
            return
        while self.active_run is not None and self.active_run.is_alive():
            self.active_run.join(timeout=0.1)
        self._sync_active_run()
        self._print_active_run_state()

    def do_var(self, arg: str) -> None:
        """管理本次终端变量覆盖：var list | var set <name> <json-or-text> | var unset <name> | var clear"""
        parts = arg.split(maxsplit=2)
        if not parts:
            self._print_variables()
            return
        command = parts[0]
        if command == "list":
            self._print_variables()
            return
        if command == "set":
            if len(parts) != 3:
                self.perror("usage: var set <name> <json-or-text>")
                return
            name, raw_value = parts[1], parts[2]
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            self.variables[name] = value
            self.poutput(f"已设置 {name} = {value!r}")
            return
        if command == "unset":
            if len(parts) != 2:
                self.perror("usage: var unset <name>")
                return
            name = parts[1]
            if name in self.variables:
                del self.variables[name]
                self.poutput(f"已移除 {name}")
            else:
                self.poutput(f"{name} 未设置")
            return
        if command == "clear":
            self.variables.clear()
            self.poutput("已清空本次终端变量")
            return
        self.perror("usage: var list | var set <name> <json-or-text> | var unset <name> | var clear")

    def do_status(self, arg: str) -> None:
        """查看最近运行结果：status [--short|--json]"""
        self._sync_active_run()
        mode = arg.strip()
        if mode and mode not in {"--short", "--json"}:
            self.perror("usage: status [--short|--json]")
            return
        latest_state = self._read_latest_state()
        if latest_state is not None:
            if mode == "--short":
                self._print_short_state(latest_state)
                return
            self.poutput(json.dumps(latest_state, ensure_ascii=False, indent=2))
            return
        if self.active_run is not None and self.active_run.status in {"running", "waiting", "stopping", "failed"}:
            self._print_active_run_state()
            return
        if self.last_plan_result is None:
            if self.last_run_error is not None:
                self.poutput(f"最近运行失败：{self.last_run_error}")
                return
            self.poutput("最近运行：<无>")
            return
        if mode == "--short":
            self.poutput(f"{self.last_plan_result.status} {self.last_plan_result.output_dir}")
            return
        self.poutput(json.dumps(self.last_plan_result.to_dict(), ensure_ascii=False, indent=2))

    def _print_variables(self) -> None:
        self.poutput(json.dumps(self.variables, ensure_ascii=False, indent=2))

    def _print_short_state(self, state: dict[str, Any]) -> None:
        status = state.get("status", "<unknown>")
        current_step = state.get("current_step") or {}
        output_dir = state.get("output_dir", "")
        waiting = state.get("waiting")
        parts = [str(status)]
        if isinstance(current_step, dict) and current_step:
            parts.append(
                f"step={current_step.get('step')}:{current_step.get('action')}:{current_step.get('status')}"
            )
        if isinstance(waiting, dict):
            parts.append(f"waiting={waiting.get('type')}")
        if output_dir:
            parts.append(str(output_dir))
        self.poutput(" | ".join(parts))

    def _resolve_latest_output_dir(self) -> Path | None:
        self._sync_active_run()
        if self.active_run is not None and self.active_run.result is not None:
            return Path(self.active_run.result.output_dir)
        if self.last_plan_result is not None:
            return Path(self.last_plan_result.output_dir)
        try:
            plan_path = self._require_current_plan()
        except ValueError:
            return None
        return find_latest_run_output(plan_path.parent)

    def _read_latest_state(self) -> dict[str, Any] | None:
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            return None
        state_path = output_dir / "state.json"
        if not state_path.exists():
            return None
        with state_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _wait_for_interactive_checkpoint(self) -> None:
        if self.active_run is None:
            return
        while self.active_run.is_alive() and self.active_run.status == "running":
            self.active_run.join(timeout=0.1)
        self._sync_active_run()

    def _sync_active_run(self) -> None:
        if self.active_run is None:
            return
        if self.active_run.is_alive():
            return
        if self.active_run.result is not None:
            self.last_plan_result = self.active_run.result
            self.last_run_error = None
        if self.active_run.error is not None:
            self.last_run_error = self.active_run.error
        if self.active_run.status in {"passed", "failed"} and self.active_run.result is not None:
            self.active_run = None

    def _print_active_run_state(self) -> None:
        if self.active_run is None:
            if self.last_plan_result is not None:
                self.poutput(f"plan 运行结果 {self.last_plan_result.status}：{self.last_plan_result.output_dir}")
            return
        if self.active_run.status == "waiting":
            self.poutput(f"[等待用户] {self.active_run.waiting_prompt}")
            self.poutput("输入 continue 继续，或输入 stop 停止。")
            return
        if self.active_run.error is not None:
            self.last_run_error = self.active_run.error
            self.perror(self.active_run.error)
            if not self.active_run.is_alive():
                self.active_run = None
            return
        if self.active_run.result is not None:
            self.last_plan_result = self.active_run.result
            self.poutput(f"plan 运行结果 {self.active_run.result.status}：{self.active_run.result.output_dir}")
            self.active_run = None
            return
        self.poutput(f"运行状态：{self.active_run.status}")
