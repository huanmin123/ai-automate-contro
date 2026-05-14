from __future__ import annotations

import json
import shlex
from collections import deque
from pathlib import Path
from typing import Any

from ai_automate_contro.ai.terminal_tool_registry import call_ai_terminal_tool
from ai_automate_contro.app.errors import format_error_for_terminal
from ai_automate_contro.client.events import ClientEvent
from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    create_debug_workspace,
    find_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
    list_debug_workspaces,
)
from ai_automate_contro.engine.interactive import InteractiveRun
from ai_automate_contro.plans.artifacts import list_output_artifacts
from ai_automate_contro.plans.packages import (
    create_plan_package,
    discover_plan_packages,
    find_latest_run_output,
    plan_matches_filter,
    summarize_plan,
)
from ai_automate_contro.plans.validator import validate_plan_file
from ai_automate_contro.support.paths import resolve_path_text


MANAGEMENT_COMMANDS: dict[str, str] = {
    "ai": "发送一条 AI 消息：/ai <message>",
    "artifacts": "列出当前 plan 输出产物",
    "close": "关闭 post-run inspection 等待并结束运行",
    "continue": "继续 manual_confirm 等待的运行",
    "create": "创建 plan 包：/create <dir> [name]",
    "current": "查看当前 plan 和变量覆盖",
    "debug": "管理调试工作区：/debug create|prepare|list|fix|inject|patch|apply",
    "events": "查看最近 events.jsonl 行",
    "exit": "关闭客户端",
    "help": "查看命令",
    "inspect": "查看当前或指定 plan 摘要",
    "list": "列出 plan 包",
    "logs": "查看最近 run.log 行",
    "output": "查看最近输出目录",
    "quit": "关闭客户端",
    "report": "查看最近 report.md",
    "run": "运行当前 plan",
    "status": "查看当前运行或最近运行状态",
    "stop": "停止 manual_confirm 等待的运行",
    "use": "选择 plan 包：/use <plan.json-or-package-dir>",
    "validate": "校验当前或指定 plan",
    "var": "管理本轮变量覆盖",
}
DEBUG_USAGE = (
    "用法：/debug prepare [name] [--manual-confirm] | /debug create [name] | /debug list | "
    "/debug fix [--apply] [--hint <text>] [--run] [--run-name <name>] [workspace] | "
    "/debug inject <preset[,preset...]> [workspace] [--message <text>] [--browser <name>] "
    "[--page <name>] [--position start|end|before_step|after_step] [--step <n>] | "
    "/debug patch [workspace] | /debug apply --yes [workspace]"
)


class ClientManagementController:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.current_plan_path: Path | None = None
        self.variables: dict[str, Any] = {}
        self.last_plan_result: Any | None = None
        self.last_run_error: BaseException | None = None
        self.active_run: InteractiveRun | None = None
        self.current_debug_workspace: Path | None = None

    def is_management_input(self, message: str) -> bool:
        stripped = message.strip()
        if not stripped.startswith("/"):
            return False
        command, _ = _parse_command(stripped)
        return command in MANAGEMENT_COMMANDS

    def handle(self, message: str) -> list[ClientEvent]:
        command, arg = _parse_command(message.strip())
        try:
            if command in {"exit", "quit"}:
                return [ClientEvent("exit_requested", text="正在关闭")]
            method = getattr(self, f"_command_{command}", None)
            if not callable(method):
                return [self._error(f"未知管理命令：/{command}")]
            return list(method(arg))
        except Exception as error:
            return [self._error(error)]

    def can_handle_during_turn(self, message: str) -> bool:
        command, _ = _parse_command(message.strip())
        return command in {"status", "continue", "close", "stop"}

    def _command_help(self, _: str) -> list[ClientEvent]:
        lines = ["管理命令："]
        for name, description in sorted(MANAGEMENT_COMMANDS.items()):
            lines.append(f"  /{name:<10} {description}")
        lines.extend(
            [
                "",
                "自然语言会直接发给 AI。",
                "需要把斜杠开头的文字发给 AI 时，用 /ai <message>。",
            ]
        )
        return [self._output("\n".join(lines))]

    def _command_ai(self, _: str) -> list[ClientEvent]:
        return [self._error("用法：/ai <message>")]

    def _command_list(self, arg: str) -> list[ClientEvent]:
        filter_text = arg.strip().lower()
        plans = discover_plan_packages(self.project_root)
        if filter_text:
            plans = [plan for plan in plans if plan_matches_filter(plan, self.project_root, filter_text)]
        if not plans:
            return [self._output("没有找到 plan 包")]
        lines = []
        for index, plan_path in enumerate(plans, start=1):
            summary = summarize_plan(plan_path, self.project_root)
            lines.append(
                f"{index:02d}. {summary['relative_path']} | 名称={summary['name']} | 步骤数={summary['steps']}"
            )
        return [self._output("\n".join(lines))]

    def _command_use(self, arg: str) -> list[ClientEvent]:
        raw_path = arg.strip()
        if not raw_path:
            return [self._error("用法：/use <plan.json-or-package-dir>")]
        plan_path = self._resolve_plan_path(raw_path)
        if not plan_path.exists():
            raise FileNotFoundError(f"plan 不存在：{plan_path}")
        self.current_plan_path = plan_path
        self.current_debug_workspace = None
        return [self._output(f"当前 plan：{plan_path}")]

    def _command_current(self, _: str) -> list[ClientEvent]:
        lines = [f"当前 plan：{self.current_plan_path or '<无>'}"]
        lines.append(f"本轮变量数：{len(self.variables)}")
        lines.append(f"当前 debug workspace：{self.current_debug_workspace or '<无>'}")
        if self.last_plan_result is not None:
            lines.append(f"最近运行：{self.last_plan_result.status} {self.last_plan_result.output_dir}")
        return [self._output("\n".join(lines))]

    def _command_validate(self, arg: str) -> list[ClientEvent]:
        plan_path = self._resolve_plan_arg(arg)
        result = validate_plan_file(plan_path, self.project_root)
        if result.ok:
            return [self._output(f"计划校验通过：{result.plan_path}")]
        return [self._error("\n".join(error.format() for error in result.errors))]

    def _command_inspect(self, arg: str) -> list[ClientEvent]:
        plan_path = self._resolve_plan_arg(arg)
        summary = summarize_plan(plan_path, self.project_root)
        result = validate_plan_file(plan_path, self.project_root)
        lines = [
            f"路径：{summary['path']}",
            f"名称：{summary['name']}",
            f"标签：{', '.join(summary['tags']) if summary['tags'] else '<无>'}",
            f"变量：{', '.join(summary['variables']) if summary['variables'] else '<无>'}",
            f"步骤数：{summary['steps']}",
            f"子计划：{', '.join(summary['sub_plans']) if summary['sub_plans'] else '<无>'}",
            f"最近输出：{summary['latest_output'] or '<无>'}",
            "校验：通过" if result.ok else f"校验：{len(result.errors)} 个错误",
        ]
        return [self._output("\n".join(lines))]

    def _command_create(self, arg: str) -> list[ClientEvent]:
        parts = _split_args(arg)
        if not parts:
            return [self._error("用法：/create <dir> [name]")]
        package_path = resolve_path_text(parts[0], base=self.project_root)
        package_dir = create_plan_package(
            package_path,
            project_root=self.project_root,
            name=" ".join(parts[1:]) if len(parts) > 1 else None,
        )
        return [self._output(f"已创建 plan 包：{package_dir}")]

    def _command_run(self, arg: str) -> list[ClientEvent]:
        self._sync_active_run()
        if self.active_run is not None and self.active_run.status in {"running", "waiting", "stopping"}:
            return [self._error(f"已有 plan 正在运行或等待：{self.active_run.status}")]
        plan_path = self._require_current_plan()
        validation = validate_plan_file(plan_path, self.project_root)
        if not validation.ok:
            return [self._error("\n".join(error.format() for error in validation.errors))]
        run_name = arg.strip() or None
        self.active_run = InteractiveRun(
            plan_path=plan_path,
            project_root=self.project_root,
            run_name=run_name,
            variable_overrides=dict(self.variables),
        )
        self.last_run_error = None
        self.active_run.start()
        events = [self._output(f"计划校验通过：{validation.plan_path}"), ClientEvent("status", text="plan 正在运行")]
        events.extend(self._wait_for_interactive_checkpoint())
        events.extend(self._active_run_events())
        return events

    def _command_continue(self, _: str) -> list[ClientEvent]:
        return self._continue_active_run(expected_waiting_type="manual_confirm", command="continue")

    def _command_close(self, _: str) -> list[ClientEvent]:
        return self._continue_active_run(expected_waiting_type="post_run_inspection", command="close")

    def _command_stop(self, _: str) -> list[ClientEvent]:
        self._sync_active_run()
        if self.active_run is None:
            return [self._error("当前没有正在运行或等待的 plan。")]
        if getattr(self.active_run, "waiting_type", None) == "post_run_inspection":
            return [self._error("当前运行正在等待浏览器检查结束；请用 /close 关闭浏览器并结束。")]
        self.active_run.stop()
        while self.active_run is not None and self.active_run.is_alive():
            self.active_run.join(timeout=0.1)
        self._sync_active_run()
        return self._active_run_events()

    def _command_var(self, arg: str) -> list[ClientEvent]:
        parts = _split_args(arg)
        if not parts or parts[0] == "list":
            return [self._output(json.dumps(self.variables, ensure_ascii=False, indent=2))]
        command = parts[0]
        if command == "set" and len(parts) >= 3:
            name = parts[1]
            raw_value = " ".join(parts[2:])
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            self.variables[name] = value
            return [self._output(f"已设置 {name} = {value!r}")]
        if command == "unset" and len(parts) == 2:
            removed = self.variables.pop(parts[1], None)
            return [self._output(f"已移除 {parts[1]}" if removed is not None else f"{parts[1]} 未设置")]
        if command == "clear" and len(parts) == 1:
            self.variables.clear()
            return [self._output("已清空本轮变量")]
        return [self._error("用法：/var list | /var set <name> <json-or-text> | /var unset <name> | /var clear")]

    def _command_status(self, arg: str) -> list[ClientEvent]:
        self._sync_active_run()
        mode = arg.strip()
        if mode and mode not in {"--short", "--json"}:
            return [self._error("用法：/status [--short|--json]")]
        latest_state = self._read_latest_state()
        if latest_state is not None:
            if mode == "--short":
                return [self._output(_short_state(latest_state))]
            return [self._output(json.dumps(latest_state, ensure_ascii=False, indent=2))]
        if self.active_run is not None:
            return self._active_run_events()
        if self.last_plan_result is not None:
            if mode == "--short":
                return [self._output(f"{self.last_plan_result.status} {self.last_plan_result.output_dir}")]
            return [self._output(json.dumps(self.last_plan_result.to_dict(), ensure_ascii=False, indent=2))]
        if self.last_run_error is not None:
            return [self._error(self.last_run_error)]
        return [self._output("最近运行：<无>")]

    def _command_output(self, _: str) -> list[ClientEvent]:
        output_dir = self._resolve_latest_output_dir()
        return [self._output(f"输出目录：{output_dir or '<无>'}")]

    def _command_report(self, _: str) -> list[ClientEvent]:
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            return [self._output("报告：<无>")]
        report_path = output_dir / "report.md"
        if not report_path.exists():
            return [self._output(f"未找到报告：{report_path}")]
        return [self._output(report_path.read_text(encoding="utf-8", errors="replace"))]

    def _command_logs(self, arg: str) -> list[ClientEvent]:
        return self._tail_output_file(arg, filename="run.log", label="日志", default_lines=80)

    def _command_events(self, arg: str) -> list[ClientEvent]:
        return self._tail_output_file(arg, filename="events.jsonl", label="事件", default_lines=40)

    def _command_artifacts(self, arg: str) -> list[ClientEvent]:
        parts = _split_args(arg)
        filter_text = ""
        limit = 80
        if len(parts) == 1:
            if parts[0].isdigit():
                limit = int(parts[0])
            else:
                filter_text = parts[0]
        elif len(parts) == 2:
            filter_text = parts[0]
            limit = int(parts[1])
        elif len(parts) > 2:
            return [self._error("用法：/artifacts [filter] [limit]")]
        if limit <= 0:
            return [self._error("数量必须大于 0。")]
        plan_path = self._require_current_plan()
        artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
        if not artifacts:
            return [self._output("输出产物：<无>")]
        return [self._output("\n".join(f"{item.relative_path} | {item.size} 字节" for item in artifacts))]

    def _command_debug(self, arg: str) -> list[ClientEvent]:
        parts = _split_args(arg)
        if not parts:
            return [self._error(DEBUG_USAGE)]
        command = parts[0].lower().replace("-", "_")
        plan_path = self._require_current_plan()
        if command == "prepare":
            return self._debug_prepare(plan_path, parts[1:])
        if command == "create":
            return self._debug_create(plan_path, parts[1:])
        if command == "list":
            return self._debug_list(plan_path, parts[1:])
        if command == "fix":
            return self._debug_fix(plan_path, parts[1:])
        if command == "inject":
            return self._debug_inject(plan_path, parts[1:])
        if command == "patch":
            return self._debug_patch(plan_path, parts[1:])
        if command == "apply":
            return self._debug_apply(plan_path, parts[1:])
        return [self._error(DEBUG_USAGE)]

    def _debug_prepare(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        include_manual_confirm = False
        names: list[str] = []
        for part in parts:
            if part == "--manual-confirm":
                include_manual_confirm = True
            else:
                names.append(part)
        if len(names) > 1:
            return [self._error("用法：/debug prepare [name] [--manual-confirm]")]
        result = call_ai_terminal_tool(
            "prepare_failure_debug_workspace",
            self.project_root,
            {
                "plan_path": str(plan_path),
                "name": names[0] if names else None,
                "include_manual_confirm": include_manual_confirm,
            },
        )
        self._capture_debug_workspace_from_result(result)
        summary = {
            "ok": result.get("ok"),
            "workspace": result.get("workspace"),
            "injection": result.get("injection"),
            "validation": result.get("validation"),
            "recommended_next_actions": result.get("recommended_next_actions"),
        }
        return [self._output(_json(summary))]

    def _debug_create(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        if len(parts) > 1:
            return [self._error("用法：/debug create [name]")]
        workspace = create_debug_workspace(plan_path, self.project_root, name=parts[0] if parts else None)
        self.current_debug_workspace = workspace.root
        return [self._output(_json(workspace.to_dict()))]

    def _debug_list(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        if parts:
            return [self._error("用法：/debug list")]
        workspaces = list_debug_workspaces(plan_path)
        if not workspaces:
            return [self._output("调试工作区：<无>")]
        lines = []
        for workspace in workspaces:
            lines.append(f"{workspace.get('name')} | {workspace.get('root')}")
        return [self._output("\n".join(lines))]

    def _debug_fix(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        positionals, options = _parse_debug_options(
            parts,
            value_options={"--hint", "--run-name"},
            boolean_options={"--apply", "--run"},
        )
        if len(positionals) > 1:
            return [self._error("用法：/debug fix [--apply] [--hint <text>] [--run] [--run-name <name>] [workspace]")]
        workspace = find_debug_workspace(plan_path, positionals[0] if positionals else None)
        self._capture_debug_workspace(workspace)
        result = call_ai_terminal_tool(
            "propose_debug_fix",
            self.project_root,
            {
                "workspace": workspace["root"],
                "user_hint": options.get("--hint", ""),
                "apply": bool(options.get("--apply")),
                "run_after_apply": bool(options.get("--run")),
                "run_name": options.get("--run-name"),
            },
        )
        self._capture_debug_workspace_from_result(result)
        return [self._output(_json(result))]

    def _debug_inject(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        positionals, options = _parse_debug_options(
            parts,
            value_options={"--message", "--browser", "--page", "--position", "--step"},
            boolean_options=set(),
        )
        if not positionals or len(positionals) > 2:
            return [self._error("用法：/debug inject <preset[,preset...]> [workspace]")]
        presets = [preset.strip() for preset in positionals[0].split(",") if preset.strip()]
        if not presets:
            return [self._error("至少需要一个 debug 注入预设。")]
        workspace = find_debug_workspace(plan_path, positionals[1] if len(positionals) == 2 else None)
        self._capture_debug_workspace(workspace)
        step = None
        if options.get("--step") not in {None, ""}:
            step = int(str(options["--step"]))
        result = inject_debug_steps(
            workspace["root"],
            presets=presets,
            message=_option_text(options, "--message"),
            browser=_option_text(options, "--browser"),
            page=_option_text(options, "--page"),
            position=str(options.get("--position") or "end"),
            step=step,
        )
        return [self._output(_json(result.to_dict()))]

    def _debug_patch(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        if len(parts) > 1:
            return [self._error("用法：/debug patch [workspace]")]
        workspace = find_debug_workspace(plan_path, parts[0] if parts else None)
        self._capture_debug_workspace(workspace)
        result = generate_debug_patch(workspace["root"])
        output = [_json(result.to_dict())]
        patch_text = Path(result.patch_path).read_text(encoding="utf-8")
        if patch_text.strip():
            output.append(patch_text)
        return [self._output("\n".join(output))]

    def _debug_apply(self, plan_path: Path, parts: list[str]) -> list[ClientEvent]:
        positionals, options = _parse_debug_options(
            parts,
            value_options=set(),
            boolean_options={"--yes"},
        )
        if not options.get("--yes") or len(positionals) > 1:
            return [self._error("用法：/debug apply --yes [workspace]")]
        workspace = find_debug_workspace(plan_path, positionals[0] if positionals else None)
        self._capture_debug_workspace(workspace)
        result = apply_debug_patch(workspace["root"], yes=True)
        return [self._output(_json(result.to_dict()))]

    def context_update(self) -> dict[str, str]:
        update: dict[str, str] = {}
        if self.current_plan_path is not None:
            update["current_plan_path"] = str(self.current_plan_path)
        if self.current_debug_workspace is not None:
            update["current_debug_workspace"] = str(self.current_debug_workspace)
        output_dir = self._resolve_latest_output_dir()
        if output_dir is not None:
            update["latest_output_dir"] = str(output_dir)
        return update

    def _capture_debug_workspace_from_result(self, result: dict[str, Any]) -> None:
        workspace = result.get("workspace") if isinstance(result, dict) else None
        if isinstance(workspace, dict):
            self._capture_debug_workspace(workspace)
        elif isinstance(workspace, str) and workspace:
            self.current_debug_workspace = Path(workspace).resolve()

    def _capture_debug_workspace(self, workspace: dict[str, Any]) -> None:
        root = workspace.get("root")
        if isinstance(root, str) and root:
            self.current_debug_workspace = Path(root).resolve()

    def _tail_output_file(self, arg: str, *, filename: str, label: str, default_lines: int) -> list[ClientEvent]:
        try:
            line_count = int(arg.strip()) if arg.strip() else default_lines
        except ValueError:
            return [self._error(f"用法：/{'logs' if filename == 'run.log' else 'events'} [lines]")]
        if line_count <= 0:
            return [self._error("行数必须大于 0。")]
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            return [self._output(f"{label}：<无>")]
        path = output_dir / filename
        if not path.exists():
            return [self._output(f"未找到{label}文件：{path}")]
        return [self._output("\n".join(_tail_text_lines(path, line_count)))]

    def _continue_active_run(self, *, expected_waiting_type: str, command: str) -> list[ClientEvent]:
        self._sync_active_run()
        if self.active_run is None:
            return [self._error("当前没有正在运行或等待的 plan。")]
        self.active_run.continue_run(expected_waiting_type=expected_waiting_type, command=command)
        events = [ClientEvent("status", text="plan 正在继续")]
        events.extend(self._wait_for_interactive_checkpoint())
        events.extend(self._active_run_events())
        return events

    def _active_run_events(self) -> list[ClientEvent]:
        if self.active_run is None:
            if self.last_plan_result is not None:
                return [self._output(f"计划运行结果 {self.last_plan_result.status}：{self.last_plan_result.output_dir}")]
            if self.last_run_error is not None:
                return [self._error(self.last_run_error)]
            return [self._output("运行状态：<无>")]
        if self.active_run.status == "waiting":
            suffix = "输入 /close 关闭浏览器并结束。" if self.active_run.waiting_type == "post_run_inspection" else "输入 /continue 继续，或 /stop 停止。"
            return [
                ClientEvent(
                    "approval_requested",
                    text=f"{self.active_run.waiting_prompt}\n{suffix}",
                )
            ]
        if self.active_run.error is not None:
            self.last_run_error = self.active_run.error
            if not self.active_run.is_alive():
                self.active_run = None
            return [self._error(self.last_run_error)]
        if self.active_run.result is not None:
            self.last_plan_result = self.active_run.result
            self.active_run = None
            return [self._output(f"计划运行结果 {self.last_plan_result.status}：{self.last_plan_result.output_dir}")]
        return [self._output(f"运行状态：{self.active_run.status}")]

    def _wait_for_interactive_checkpoint(self) -> list[ClientEvent]:
        events: list[ClientEvent] = []
        if self.active_run is None:
            return events
        while self.active_run.is_alive() and self.active_run.status == "running":
            self.active_run.join(timeout=0.1)
            if self.active_run.is_alive() and self.active_run.status == "running":
                events.append(ClientEvent("status", text="plan 正在运行"))
        self._sync_active_run()
        return events

    def _sync_active_run(self) -> None:
        if self.active_run is None or self.active_run.is_alive():
            return
        if self.active_run.result is not None:
            self.last_plan_result = self.active_run.result
            self.last_run_error = None
        if self.active_run.error is not None:
            self.last_run_error = self.active_run.error
        if self.active_run.status in {"passed", "failed"} and self.active_run.result is not None:
            self.active_run = None

    def _read_latest_state(self) -> dict[str, Any] | None:
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            return None
        state_path = output_dir / "state.json"
        if not state_path.exists():
            return None
        with state_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _resolve_latest_output_dir(self) -> Path | None:
        self._sync_active_run()
        if self.active_run is not None and self.active_run.result is not None:
            return Path(self.active_run.result.output_dir)
        if self.last_plan_result is not None:
            return Path(self.last_plan_result.output_dir)
        if self.current_plan_path is None:
            return None
        return find_latest_run_output(self.current_plan_path.parent)

    def _resolve_plan_arg(self, arg: str) -> Path:
        raw_path = arg.strip()
        if raw_path:
            return self._resolve_plan_path(raw_path)
        return self._require_current_plan()

    def _resolve_plan_path(self, raw_path: str) -> Path:
        plan_path = resolve_path_text(raw_path, base=self.project_root)
        if plan_path.is_dir():
            plan_path = plan_path / "plan.json"
        return plan_path

    def _require_current_plan(self) -> Path:
        if self.current_plan_path is None:
            raise ValueError("当前没有选择 plan；请先输入 /use <plan.json-or-package-dir>。")
        return self.current_plan_path

    def _output(self, text: str) -> ClientEvent:
        return ClientEvent("terminal_output", text=text)

    def _error(self, error: object) -> ClientEvent:
        return ClientEvent("error", text=format_error_for_terminal(error, project_root=self.project_root))


def _parse_command(message: str) -> tuple[str, str]:
    stripped = message.strip()
    without_slash = stripped[1:] if stripped.startswith("/") else stripped
    command, _, arg = without_slash.partition(" ")
    return command.lower().replace("-", "_"), arg.strip()


def _split_args(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _parse_debug_options(
    parts: list[str],
    *,
    value_options: set[str],
    boolean_options: set[str],
) -> tuple[list[str], dict[str, Any]]:
    positionals: list[str] = []
    options: dict[str, Any] = {}
    index = 0
    while index < len(parts):
        part = parts[index]
        if part in boolean_options:
            options[part] = True
            index += 1
            continue
        if part in value_options:
            if index + 1 >= len(parts):
                raise ValueError(f"{part} 需要一个值。")
            options[part] = parts[index + 1]
            index += 2
            continue
        if part.startswith("--"):
            supported = ", ".join(sorted(value_options | boolean_options))
            raise ValueError(f"不支持的 debug 参数：{part}。支持参数：{supported}")
        positionals.append(part)
        index += 1
    return positionals, options


def _option_text(options: dict[str, Any], key: str) -> str | None:
    value = options.get(key)
    if value is None:
        return None
    return str(value)


def _tail_text_lines(path: Path, line_count: int) -> list[str]:
    lines: deque[str] = deque(maxlen=line_count)
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for raw_line in file:
            lines.append(raw_line.rstrip("\r\n"))
    return list(lines)


def _short_state(state: dict[str, Any]) -> str:
    status = state.get("status", "<unknown>")
    current_step = state.get("current_step") or {}
    output_dir = state.get("output_dir", "")
    waiting = state.get("waiting")
    parts = [str(status)]
    if isinstance(current_step, dict) and current_step:
        parts.append(f"step={current_step.get('step')}:{current_step.get('action')}:{current_step.get('status')}")
    if isinstance(waiting, dict):
        parts.append(f"waiting={waiting.get('type')}")
    if output_dir:
        parts.append(str(output_dir))
    return " | ".join(parts)
