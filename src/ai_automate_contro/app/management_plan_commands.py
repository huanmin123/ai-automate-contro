from __future__ import annotations

from pathlib import Path

from ai_automate_contro.plans.packages import (
    create_plan_package,
    discover_plan_packages,
    plan_matches_filter,
    summarize_plan,
)
from ai_automate_contro.plans.validator import validate_plan_file


class PlanCommandsMixin:
    def do_use(self, arg: str) -> None:
        """Select a plan package entry: use <plan.json-or-package-dir>"""
        raw_path = arg.strip()
        if not raw_path:
            self.perror("usage: use <plan.json-or-package-dir>")
            return
        plan_path = Path(raw_path).resolve()
        if plan_path.is_dir():
            plan_path = plan_path / "plan.json"
        self.current_plan_path = plan_path
        self._refresh_prompt()
        self.poutput(f"current plan: {plan_path}")

    def do_current(self, _: str) -> None:
        """Show selected plan and session context."""
        if self.current_plan_path is None:
            self.poutput("current plan: <none>")
        else:
            self.poutput(f"current plan: {self.current_plan_path}")
        self.poutput(f"session variables: {len(self.variables)}")
        if self.last_plan_result is not None:
            self.poutput(f"last run: {self.last_plan_result.status} {self.last_plan_result.output_dir}")

    def do_validate(self, arg: str) -> None:
        """Validate selected or given plan: validate [plan.json-or-package-dir]"""
        try:
            plan_path = self._resolve_plan_arg(arg)
        except ValueError as error:
            self.perror(str(error))
            return
        self._print_validation(plan_path)

    def do_create(self, arg: str) -> None:
        """Create a plan package template: create <dir> [name]"""
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0]:
            self.perror("usage: create <dir> [name]")
            return
        name = parts[1] if len(parts) > 1 else None
        try:
            package_dir = create_plan_package(parts[0], project_root=self.project_root, name=name)
        except Exception as error:
            self.perror(str(error))
            return
        self.poutput(f"created plan package: {package_dir}")

    def do_list(self, arg: str) -> None:
        """List plan packages: list [filter]"""
        filter_text = arg.strip().lower()
        plans = discover_plan_packages(self.project_root)
        if filter_text:
            plans = [plan_path for plan_path in plans if plan_matches_filter(plan_path, self.project_root, filter_text)]
        if not plans:
            self.poutput("no plan packages found")
            return

        for index, plan_path in enumerate(plans, start=1):
            summary = summarize_plan(plan_path, self.project_root)
            self.poutput(
                f"{index:02d}. {summary['relative_path']} "
                f"| name={summary['name']} | steps={summary['steps']}"
            )

    def do_inspect(self, arg: str) -> None:
        """Inspect selected or given plan package: inspect [plan.json-or-package-dir]"""
        try:
            plan_path = self._resolve_plan_arg(arg)
            summary = summarize_plan(plan_path, self.project_root)
        except Exception as error:
            self.perror(str(error))
            return

        self.poutput(f"path: {summary['path']}")
        self.poutput(f"name: {summary['name']}")
        self.poutput(f"tags: {', '.join(summary['tags']) if summary['tags'] else '<none>'}")
        self.poutput(f"variables: {', '.join(summary['variables']) if summary['variables'] else '<none>'}")
        self.poutput(f"steps: {summary['steps']}")
        self.poutput(f"sub-plans: {', '.join(summary['sub_plans']) if summary['sub_plans'] else '<none>'}")
        self.poutput(f"latest output: {summary['latest_output'] or '<none>'}")
        result = validate_plan_file(plan_path, self.project_root)
        self.poutput("validation: passed" if result.ok else f"validation: {len(result.errors)} error(s)")

    def _resolve_plan_arg(self, arg: str) -> Path:
        raw_path = arg.strip()
        if not raw_path:
            return self._require_current_plan()
        plan_path = Path(raw_path).resolve()
        if plan_path.is_dir():
            plan_path = plan_path / "plan.json"
        return plan_path

    def _require_current_plan(self) -> Path:
        if self.current_plan_path is None:
            raise ValueError("no current plan selected; use <plan.json-or-package-dir> first")
        return self.current_plan_path

    def _print_validation(self, plan_path: Path) -> bool:
        result = validate_plan_file(plan_path, self.project_root)
        if result.ok:
            self.poutput(f"plan valid: {result.plan_path}")
            return True
        for error in result.errors:
            self.perror(error.format())
        return False

    def _refresh_prompt(self) -> None:
        if self.current_plan_path is None:
            self.prompt = "plan> "
            return
        try:
            display_path = self.current_plan_path.parent.relative_to(self.project_root)
        except ValueError:
            display_path = self.current_plan_path.parent
        self.prompt = f"plan:{display_path}> "
