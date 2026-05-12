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
        """选择 plan 包入口：use <plan.json-or-package-dir>"""
        raw_path = arg.strip()
        if not raw_path:
            self.perror("用法：use <plan.json-or-package-dir>")
            return
        plan_path = Path(raw_path).resolve()
        if plan_path.is_dir():
            plan_path = plan_path / "plan.json"
        self.current_plan_path = plan_path
        self._refresh_prompt()
        self.poutput(f"当前 plan：{plan_path}")

    def do_current(self, _: str) -> None:
        """查看当前选择的 plan 和本次终端上下文。"""
        if self.current_plan_path is None:
            self.poutput("当前 plan：<无>")
        else:
            self.poutput(f"当前 plan：{self.current_plan_path}")
        self.poutput(f"本次终端变量数：{len(self.variables)}")
        if self.last_plan_result is not None:
            self.poutput(f"最近运行：{self.last_plan_result.status} {self.last_plan_result.output_dir}")

    def do_validate(self, arg: str) -> None:
        """校验当前或指定 plan：validate [plan.json-or-package-dir]"""
        try:
            plan_path = self._resolve_plan_arg(arg)
        except ValueError as error:
            self.perror(error)
            return
        self._print_validation(plan_path)

    def do_create(self, arg: str) -> None:
        """创建 plan 包模板：create <dir> [name]"""
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0]:
            self.perror("用法：create <dir> [name]")
            return
        name = parts[1] if len(parts) > 1 else None
        try:
            package_dir = create_plan_package(parts[0], project_root=self.project_root, name=name)
        except Exception as error:
            self.perror(error)
            return
        self.poutput(f"已创建 plan 包：{package_dir}")

    def do_list(self, arg: str) -> None:
        """列出 plan 包：list [filter]"""
        filter_text = arg.strip().lower()
        plans = discover_plan_packages(self.project_root)
        if filter_text:
            plans = [plan_path for plan_path in plans if plan_matches_filter(plan_path, self.project_root, filter_text)]
        if not plans:
            self.poutput("没有找到 plan 包")
            return

        for index, plan_path in enumerate(plans, start=1):
            summary = summarize_plan(plan_path, self.project_root)
            self.poutput(
                f"{index:02d}. {summary['relative_path']} "
                f"| 名称={summary['name']} | 步骤数={summary['steps']}"
            )

    def do_inspect(self, arg: str) -> None:
        """检查当前或指定 plan 包摘要：inspect [plan.json-or-package-dir]"""
        try:
            plan_path = self._resolve_plan_arg(arg)
            summary = summarize_plan(plan_path, self.project_root)
        except Exception as error:
            self.perror(error)
            return

        self.poutput(f"路径：{summary['path']}")
        self.poutput(f"名称：{summary['name']}")
        self.poutput(f"标签：{', '.join(summary['tags']) if summary['tags'] else '<无>'}")
        self.poutput(f"变量：{', '.join(summary['variables']) if summary['variables'] else '<无>'}")
        self.poutput(f"步骤数：{summary['steps']}")
        self.poutput(f"子计划：{', '.join(summary['sub_plans']) if summary['sub_plans'] else '<无>'}")
        self.poutput(f"最近输出：{summary['latest_output'] or '<无>'}")
        result = validate_plan_file(plan_path, self.project_root)
        self.poutput("校验：通过" if result.ok else f"校验：{len(result.errors)} 个错误")

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
            raise ValueError("当前没有选择 plan；请先执行 use <plan.json-or-package-dir>。")
        return self.current_plan_path

    def _print_validation(self, plan_path: Path) -> bool:
        result = validate_plan_file(plan_path, self.project_root)
        if result.ok:
            self.poutput(f"计划校验通过：{result.plan_path}")
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
