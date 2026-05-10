from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cmd2

from keygen_automation.ai_terminal_tools import call_ai_terminal_tool, list_ai_terminal_tools
from keygen_automation.artifacts import list_output_artifacts
from keygen_automation.debug_workspace import (
    apply_debug_patch,
    create_debug_workspace,
    find_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
    list_debug_workspaces,
)
from keygen_automation.executor import execute_plan
from keygen_automation.interactive import InteractiveRun
from keygen_automation.plan_loader import detect_document_type, load_plan
from keygen_automation.plan_packages import (
    create_plan_package,
    discover_plan_packages,
    find_latest_run_output,
    plan_matches_filter,
    summarize_plan,
)
from keygen_automation.validator import validate_plan_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage and run JSON automation plan packages.",
    )

    subparsers = parser.add_subparsers(dest="command")
    plan_parser = subparsers.add_parser("plan", help="Manage plan packages.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command")

    tool_parser = subparsers.add_parser("tool", help="Call structured AI terminal tools.")
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command")
    tool_subparsers.add_parser("list", help="List available structured tools.")
    tool_call_parser = tool_subparsers.add_parser("call", help="Call one structured tool and print JSON.")
    tool_call_parser.add_argument("name", help="Tool name.")
    tool_call_parser.add_argument("--args-json", default="{}", help="Tool arguments as a JSON object.")
    tool_call_parser.add_argument("--args-file", help="Read tool arguments from a JSON file.")
    tool_call_parser.add_argument("--compact", action="store_true", help="Print compact JSON.")

    ai_parser = subparsers.add_parser("ai", help="Start the persistent AI terminal.")
    ai_parser.add_argument("--service", default="default", help="AI service name from test-plans/config.json.")
    ai_parser.add_argument("--thread", default="default", help="Persistent AI terminal thread id.")

    list_parser = plan_subparsers.add_parser("list", help="List plan packages.")
    list_parser.add_argument("filter", nargs="?", help="Optional text filter.")

    create_parser = plan_subparsers.add_parser("create", help="Create a plan package template.")
    create_parser.add_argument("--path", required=True, help="Plan package directory to create.")
    create_parser.add_argument("--name", help="Plan name written into plan.json.")
    create_parser.add_argument("--force", action="store_true", help="Allow using an existing non-empty package directory.")

    validate_parser = plan_subparsers.add_parser("validate", help="Validate a plan package.")
    validate_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")

    run_parser = plan_subparsers.add_parser("run", help="Run a plan package.")
    run_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    run_parser.add_argument("--run-name", help="Override the run name used for output directory naming.")
    run_parser.add_argument(
        "--output-dir",
        help="Override the run output directory. Must stay inside the plan package output/ directory.",
    )

    debug_parser = plan_subparsers.add_parser("debug-create", help="Create an isolated debug workspace for a plan package.")
    debug_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    debug_parser.add_argument("--name", help="Debug workspace name suffix.")

    prepare_parser = plan_subparsers.add_parser("debug-prepare", help="Create a debug workspace from the latest failed run and inject diagnostics.")
    prepare_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    prepare_parser.add_argument("--output-dir", help="Specific failed run output directory. Defaults to latest run.")
    prepare_parser.add_argument("--name", help="Debug workspace name suffix.")
    prepare_parser.add_argument("--manual-confirm", action="store_true", help="Inject a manual confirmation checkpoint before the failed step.")

    fix_parser = plan_subparsers.add_parser("debug-fix", help="Propose or apply a clean fix candidate inside a debug workspace.")
    fix_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    fix_parser.add_argument("--hint", default="", help="Optional user hint used to rank fix candidates.")
    fix_parser.add_argument("--apply", action="store_true", help="Write the selected fix candidate to injected-plan/.")
    fix_parser.add_argument("--run", action="store_true", help="Run the debug plan after applying the candidate.")
    fix_parser.add_argument("--run-name", help="Override debug run name when --run is used.")

    inject_parser = plan_subparsers.add_parser("debug-inject", help="Inject diagnostic steps into an existing debug workspace.")
    inject_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    inject_parser.add_argument(
        "--preset",
        action="append",
        required=True,
        choices=["print", "variables", "manual_confirm", "screenshot", "html"],
        help="Diagnostic preset to inject. May be repeated.",
    )
    inject_parser.add_argument("--message", help="Message used by print/manual_confirm presets.")
    inject_parser.add_argument("--browser", help="Browser session name for screenshot/html presets.")
    inject_parser.add_argument("--page", help="Page name for screenshot/html presets.")
    inject_parser.add_argument("--position", choices=["start", "end", "before_step", "after_step"], default="end", help="Where to inject steps.")
    inject_parser.add_argument("--step", type=int, help="1-based anchor step for before_step or after_step.")

    patch_parser = plan_subparsers.add_parser("debug-patch", help="Generate patch.diff from a debug workspace.")
    patch_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")

    apply_parser = plan_subparsers.add_parser("debug-apply", help="Apply patch.diff from a debug workspace to the original plan package.")
    apply_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    apply_parser.add_argument("--yes", action="store_true", help="Required confirmation to modify the original plan package.")

    return parser


def run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        app = ManagementTerminal(project_root)
        app.cmdloop()
        return 0

    if args.command == "ai":
        from keygen_automation.ai_terminal import AITerminal

        app = AITerminal(project_root, service=args.service, thread_id=args.thread)
        app.cmdloop()
        return 0

    if args.command == "plan":
        if args.plan_command == "list":
            _print_plan_list(project_root, args.filter or "")
            return 0
        if args.plan_command == "create":
            package_dir = create_plan_package(
                args.path,
                project_root=project_root,
                name=args.name,
                force=args.force,
            )
            print(f"created plan package: {package_dir}")
            return 0
        if args.plan_command == "validate":
            return _print_validation_result(args.file, project_root)
        if args.plan_command == "run":
            result_code = _print_validation_result(args.file, project_root)
            if result_code != 0:
                return result_code
            plan_result = _run_plan(
                args.file,
                project_root,
                run_name=args.run_name,
                output_dir=args.output_dir,
                variable_overrides={},
            )
            print(f"plan {plan_result.status}: {plan_result.output_dir}")
            return 0
        if args.plan_command == "debug-create":
            workspace = create_debug_workspace(args.file, project_root, name=args.name)
            print(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-prepare":
            result = call_ai_terminal_tool(
                "prepare_failure_debug_workspace",
                project_root,
                {
                    "plan_path": args.file,
                    "output_dir": args.output_dir,
                    "name": args.name,
                    "include_manual_confirm": args.manual_confirm,
                },
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-fix":
            result = call_ai_terminal_tool(
                "propose_debug_fix",
                project_root,
                {
                    "workspace": args.workspace,
                    "user_hint": args.hint,
                    "apply": args.apply,
                    "run_after_apply": args.run,
                    "run_name": args.run_name,
                },
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-inject":
            result = inject_debug_steps(
                args.workspace,
                presets=args.preset,
                message=args.message,
                browser=args.browser,
                page=args.page,
                position=args.position,
                step=args.step,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-patch":
            result = generate_debug_patch(args.workspace)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            if result.patch_path.exists():
                print(result.patch_path.read_text(encoding="utf-8"))
            return 0
        if args.plan_command == "debug-apply":
            try:
                result = apply_debug_patch(args.workspace, yes=args.yes)
            except Exception as error:
                print(f"ERROR {error}")
                return 1
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0

    if args.command == "tool":
        if args.tool_command == "list":
            _print_json(list_ai_terminal_tools())
            return 0
        if args.tool_command == "call":
            try:
                tool_arguments = _load_tool_arguments(args.args_json, args.args_file)
                result = call_ai_terminal_tool(args.name, project_root, tool_arguments)
            except Exception as error:
                _print_json({"ok": False, "error": str(error)}, compact=args.compact)
                return 1
            _print_json(result, compact=args.compact)
            return 0

    parser.print_help()
    return 1


class ManagementTerminal(cmd2.Cmd):
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

    def do_run(self, arg: str) -> None:
        """Validate and run selected plan: run [run-name]"""
        self._sync_active_run()
        if self.active_run is not None and self.active_run.status in {"running", "waiting", "stopping"}:
            self.perror(f"a run is already active: {self.active_run.status}")
            return
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(str(error))
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
        """Continue a run waiting at manual_confirm."""
        self._sync_active_run()
        if self.active_run is None:
            self.perror("no active run")
            return
        try:
            self.active_run.continue_run()
        except Exception as error:
            self.perror(str(error))
            return
        self._wait_for_interactive_checkpoint()
        self._print_active_run_state()

    def do_stop(self, _: str) -> None:
        """Stop a run waiting at manual_confirm."""
        self._sync_active_run()
        if self.active_run is None:
            self.perror("no active run")
            return
        try:
            self.active_run.stop()
        except Exception as error:
            self.perror(str(error))
            return
        while self.active_run is not None and self.active_run.is_alive():
            self.active_run.join(timeout=0.1)
        self._sync_active_run()
        self._print_active_run_state()

    def do_var(self, arg: str) -> None:
        """Manage session variable overrides: var list | var set <name> <json-or-text> | var unset <name> | var clear"""
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
            self.poutput(f"set {name} = {value!r}")
            return
        if command == "unset":
            if len(parts) != 2:
                self.perror("usage: var unset <name>")
                return
            name = parts[1]
            if name in self.variables:
                del self.variables[name]
                self.poutput(f"unset {name}")
            else:
                self.poutput(f"{name} was not set")
            return
        if command == "clear":
            self.variables.clear()
            self.poutput("session variables cleared")
            return
        self.perror("usage: var list | var set <name> <json-or-text> | var unset <name> | var clear")

    def do_status(self, arg: str) -> None:
        """Show the last run result: status [--short|--json]"""
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
                self.poutput(f"last run failed: {self.last_run_error}")
                return
            self.poutput("last run: <none>")
            return
        if mode == "--short":
            self.poutput(f"{self.last_plan_result.status} {self.last_plan_result.output_dir}")
            return
        self.poutput(json.dumps(self.last_plan_result.to_dict(), ensure_ascii=False, indent=2))

    def do_output(self, _: str) -> None:
        """Show the last run output directory."""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("output: <none>")
            return
        self.poutput(str(output_dir))

    def do_report(self, _: str) -> None:
        """Show the latest run report.md."""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("report: <none>")
            return
        report_path = output_dir / "report.md"
        if not report_path.exists():
            self.poutput(f"report not found: {report_path}")
            return
        self.poutput(report_path.read_text(encoding="utf-8", errors="replace"))

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

    def do_logs(self, arg: str) -> None:
        """Show recent run log lines: logs [lines]"""
        try:
            line_count = int(arg.strip()) if arg.strip() else 80
        except ValueError:
            self.perror("usage: logs [lines]")
            return
        if line_count <= 0:
            self.perror("lines must be greater than 0")
            return

        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("log: <none>")
            return
        log_path = output_dir / "run.log"
        if not log_path.exists():
            self.poutput(f"log not found: {log_path}")
            return
        lines = log_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_events(self, arg: str) -> None:
        """Show recent structured event lines: events [lines]"""
        try:
            line_count = int(arg.strip()) if arg.strip() else 40
        except ValueError:
            self.perror("usage: events [lines]")
            return
        if line_count <= 0:
            self.perror("lines must be greater than 0")
            return

        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("events: <none>")
            return
        events_path = output_dir / "events.jsonl"
        if not events_path.exists():
            self.poutput(f"events not found: {events_path}")
            return
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_artifacts(self, arg: str) -> None:
        """List output artifacts: artifacts [filter] [limit]"""
        parts = arg.split()
        filter_text = ""
        limit = 80
        if len(parts) == 1:
            if parts[0].isdigit():
                limit = int(parts[0])
            else:
                filter_text = parts[0]
        elif len(parts) == 2:
            filter_text = parts[0]
            try:
                limit = int(parts[1])
            except ValueError:
                self.perror("usage: artifacts [filter] [limit]")
                return
        elif len(parts) > 2:
            self.perror("usage: artifacts [filter] [limit]")
            return
        if limit <= 0:
            self.perror("limit must be greater than 0")
            return
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(str(error))
            return
        artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
        if not artifacts:
            self.poutput("artifacts: <none>")
            return
        for artifact in artifacts:
            self.poutput(f"{artifact.relative_path} | {artifact.size} bytes")

    def do_debug(self, arg: str) -> None:
        """Manage debug workspaces: debug prepare [name] | debug create [name] | debug list | debug fix [--apply] [workspace] | debug inject <preset[,preset...]> [workspace] | debug patch [workspace] | debug apply --yes [workspace]"""
        parts = arg.split(maxsplit=2)
        if not parts:
            self.perror("usage: debug prepare [name] | debug create [name] | debug list | debug fix [--apply] [workspace] | debug inject <preset[,preset...]> [workspace] | debug patch [workspace] | debug apply --yes [workspace]")
            return
        command = parts[0]
        name = parts[1].strip() if len(parts) > 1 else None
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(str(error))
            return
        if command == "prepare":
            try:
                result = call_ai_terminal_tool(
                    "prepare_failure_debug_workspace",
                    self.project_root,
                    {
                        "plan_path": str(plan_path),
                        "name": name,
                    },
                )
            except Exception as error:
                self.perror(str(error))
                return
            summary = {
                "ok": result.get("ok"),
                "workspace": result.get("workspace"),
                "injection": result.get("injection"),
                "validation": result.get("validation"),
                "recommended_next_actions": result.get("recommended_next_actions"),
            }
            self.poutput(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        if command == "fix":
            apply_candidate = name == "--apply"
            workspace_name = parts[2].strip() if apply_candidate and len(parts) > 2 else name
            try:
                workspace = find_debug_workspace(plan_path, workspace_name)
                result = call_ai_terminal_tool(
                    "propose_debug_fix",
                    self.project_root,
                    {
                        "workspace": workspace["root"],
                        "apply": apply_candidate,
                    },
                )
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if command == "create":
            try:
                workspace = create_debug_workspace(plan_path, self.project_root, name=name)
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))
            return
        if command == "list":
            workspaces = list_debug_workspaces(plan_path)
            if not workspaces:
                self.poutput("debug workspaces: <none>")
                return
            for workspace in workspaces:
                self.poutput(f"{workspace.get('name')} | {workspace.get('root')}")
            return
        if command == "inject":
            if not name:
                self.perror("usage: debug inject <preset[,preset...]> [workspace]")
                return
            workspace_name = parts[2].strip() if len(parts) > 2 else None
            try:
                workspace = find_debug_workspace(plan_path, workspace_name)
                result = inject_debug_steps(
                    workspace["root"],
                    presets=[preset.strip() for preset in name.split(",") if preset.strip()],
                )
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        if command == "patch":
            workspace_name = name
            try:
                workspace = find_debug_workspace(plan_path, workspace_name)
                result = generate_debug_patch(workspace["root"])
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            patch_text = Path(result.patch_path).read_text(encoding="utf-8")
            if patch_text:
                self.poutput(patch_text)
            return
        if command == "apply":
            if name != "--yes":
                self.perror("usage: debug apply --yes [workspace]")
                return
            workspace_name = parts[2].strip() if len(parts) > 2 else None
            try:
                workspace = find_debug_workspace(plan_path, workspace_name)
                result = apply_debug_patch(workspace["root"], yes=True)
            except Exception as error:
                self.perror(str(error))
                return
            self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        self.perror("usage: debug prepare [name] | debug create [name] | debug list | debug fix [--apply] [workspace] | debug inject <preset[,preset...]> [workspace] | debug patch [workspace] | debug apply --yes [workspace]")

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
                self.poutput(f"plan {self.last_plan_result.status}: {self.last_plan_result.output_dir}")
            return
        if self.active_run.status == "waiting":
            self.poutput(f"[WAIT_USER] {self.active_run.waiting_prompt}")
            self.poutput("Use 'continue' to resume or 'stop' to abort.")
            return
        if self.active_run.error is not None:
            self.last_run_error = self.active_run.error
            self.perror(str(self.active_run.error))
            if not self.active_run.is_alive():
                self.active_run = None
            return
        if self.active_run.result is not None:
            self.last_plan_result = self.active_run.result
            self.poutput(f"plan {self.active_run.result.status}: {self.active_run.result.output_dir}")
            self.active_run = None
            return
        self.poutput(f"run status: {self.active_run.status}")


def _print_validation_result(raw_plan_path: str | Path, project_root: Path) -> int:
    result = validate_plan_file(raw_plan_path, project_root)
    if result.ok:
        print(f"plan valid: {result.plan_path}")
        return 0
    for error in result.errors:
        print(f"ERROR {error.format()}")
    return 1


def _print_plan_list(project_root: Path, filter_text: str) -> None:
    normalized_filter = filter_text.lower()
    plans = discover_plan_packages(project_root)
    if normalized_filter:
        plans = [plan_path for plan_path in plans if plan_matches_filter(plan_path, project_root, normalized_filter)]
    for index, plan_path in enumerate(plans, start=1):
        summary = summarize_plan(plan_path, project_root)
        print(
            f"{index:02d}. {summary['relative_path']} "
            f"| name={summary['name']} | steps={summary['steps']}"
        )


def _run_plan(
    raw_plan_path: str | Path,
    project_root: Path,
    *,
    run_name: str | None = None,
    output_dir: str | Path | None = None,
    variable_overrides: dict[str, Any] | None = None,
    manual_confirmation_handler: Any | None = None,
) -> Any:
    document = load_plan(raw_plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("Only plan documents can be executed.")
    return execute_plan(
        document,
        project_root,
        plan_path=raw_plan_path,
        run_name=run_name,
        output_dir=output_dir,
        variable_overrides=variable_overrides,
        manual_confirmation_handler=manual_confirmation_handler,
    )


def _load_tool_arguments(args_json: str, args_file: str | None) -> dict[str, Any]:
    if args_file:
        raw_value = Path(args_file).read_text(encoding="utf-8")
    else:
        raw_value = args_json
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Tool arguments must be a JSON object: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return value


def _print_json(value: Any, *, compact: bool = False) -> None:
    if compact:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))
