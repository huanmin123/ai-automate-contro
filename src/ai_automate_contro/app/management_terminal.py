from __future__ import annotations

from pathlib import Path
from typing import Any

import cmd2

from ai_automate_contro.app.management_debug_commands import DebugCommandsMixin
from ai_automate_contro.app.management_output_commands import OutputCommandsMixin
from ai_automate_contro.app.management_plan_commands import PlanCommandsMixin
from ai_automate_contro.app.management_run_commands import RunCommandsMixin
from ai_automate_contro.engine.interactive import InteractiveRun


class ManagementTerminal(
    DebugCommandsMixin,
    OutputCommandsMixin,
    RunCommandsMixin,
    PlanCommandsMixin,
    cmd2.Cmd,
):
    intro = "Keygen Automation Management Terminal. Type help or ? to list commands."

    def __init__(self, project_root: Path) -> None:
        super().__init__(allow_cli_args=False)
        self.project_root = project_root.resolve()
        self.current_plan_path: Path | None = None
        self.variables: dict[str, Any] = {}
        self.last_plan_result: Any | None = None
        self.last_run_error: BaseException | None = None
        self.active_run: InteractiveRun | None = None
        self.prompt = "plan> "
