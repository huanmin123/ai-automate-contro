from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts.prompt import CompleteStyle
from prompt_toolkit.styles import Style

from ai_automate_contro.app.errors import format_error_for_terminal
from ai_automate_contro.app.management_debug_commands import DebugCommandsMixin
from ai_automate_contro.app.management_output_commands import OutputCommandsMixin
from ai_automate_contro.app.management_plan_commands import PlanCommandsMixin
from ai_automate_contro.app.management_run_commands import RunCommandsMixin
from ai_automate_contro.engine.interactive import InteractiveRun


PLAN_COMMANDS: dict[str, str] = {
    "ai": "进入 AI 模式，或发送一条 AI 消息",
    "artifacts": "列出输出产物",
    "continue": "继续正在等待人工确认的运行",
    "create": "创建 plan 包",
    "current": "查看当前选择的 plan 上下文",
    "debug": "管理 debug workspace",
    "events": "查看最近事件行",
    "exit": "退出终端",
    "help": "查看命令",
    "inspect": "检查 plan 包摘要",
    "list": "列出 plan 包",
    "logs": "查看最近运行日志",
    "output": "查看最近输出目录",
    "quit": "退出终端",
    "report": "查看最近 report.md",
    "run": "运行当前 plan",
    "status": "查看运行或 AI 状态",
    "stop": "停止正在等待的运行",
    "use": "选择 plan 包",
    "validate": "校验当前或指定 plan",
    "var": "管理本次终端变量覆盖",
}
PLAN_INPUT_STYLE = Style.from_dict(
    {
        "bottom-toolbar": "fg:#808080",
        "completion-menu.completion": "fg:#d7d7d7",
        "completion-menu.completion.current": "fg:#0087ff bold underline",
        "completion-menu.meta.completion": "fg:#808080",
        "completion-menu.meta.completion.current": "fg:#0087ff",
        "scrollbar.background": "",
        "scrollbar.button": "fg:#808080",
    }
)


class ManagementTerminal(
    DebugCommandsMixin,
    OutputCommandsMixin,
    RunCommandsMixin,
    PlanCommandsMixin,
):
    intro = "AI 自动化控制终端。输入 help 查看命令，输入 ai 进入 AI 模式。"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.current_plan_path: Path | None = None
        self.variables: dict[str, Any] = {}
        self.last_plan_result: Any | None = None
        self.last_run_error: BaseException | None = None
        self.active_run: InteractiveRun | None = None
        self.prompt = "plan> "
        self.mode = "plan"
        self._ai_terminal: Any | None = None
        self._session: PromptSession[str] | None = None
        self._plan_completer = PlanCommandCompleter()

    def cmdloop(self) -> None:
        self.poutput(self.intro)
        while True:
            try:
                line = self._read_line()
            except (EOFError, KeyboardInterrupt):
                self.poutput("")
                break
            try:
                should_exit = self.onecmd(line)
            except SystemExit:
                raise
            except Exception as error:
                self.perror(error)
                should_exit = False
            if should_exit:
                break
        self.close()

    def onecmd(self, line: str) -> bool:
        text = str(line).strip()
        if not text:
            return False
        if self.mode == "ai":
            return self._dispatch_ai_line(text)
        return self._dispatch_plan_line(text)

    def close(self) -> None:
        if self._ai_terminal is not None:
            self._ai_terminal.close()
            self._ai_terminal = None

    def poutput(self, value: Any) -> None:
        print(str(value))

    def perror(self, msg: object, *args: Any, **kwargs: Any) -> None:
        print(format_error_for_terminal(msg, project_root=self.project_root))

    def do_help(self, _: str = "") -> None:
        lines = ["命令："]
        for name, description in sorted(PLAN_COMMANDS.items()):
            lines.append(f"  {name:<12} {description}")
        lines.extend(
            [
                "",
                "AI 模式：",
                "  ai                 进入 AI 模式；启动时不会提前初始化 AI。",
                "  ai <message>       在 plan 模式下直接发送一条 AI 消息。",
                "  exit/back          从 ai> 返回 plan>。",
                "  quit               退出终端。",
                "",
                "提示：plan 命令也支持斜杠形式，例如 /status 或 /run。",
            ]
        )
        self.poutput("\n".join(lines))

    def _read_line(self) -> str:
        if not sys.stdin.isatty():
            return _repair_piped_stdin_text(input(self.prompt), encoding=sys.stdin.encoding)
        if self.mode == "ai":
            return self._require_ai_terminal()._read_ai_input_with_images(self.prompt)
        if self._session is None:
            self._session = PromptSession(history=InMemoryHistory())
        return self._session.prompt(
            self.prompt,
            completer=self._plan_completer,
            complete_while_typing=True,
            complete_in_thread=True,
            complete_style=CompleteStyle.COLUMN,
            key_bindings=_plan_key_bindings(),
            reserve_space_for_menu=0,
            style=PLAN_INPUT_STYLE,
        )

    def _dispatch_plan_line(self, text: str) -> bool:
        command, arg = _split_command(text)
        slash_command = command.startswith("/") and len(command) > 1
        if slash_command:
            command = command[1:]
        normalized = command.lower().replace("-", "_")
        if normalized in {"exit", "quit"}:
            return True
        if normalized in {"help", "?"}:
            self.do_help(arg)
            return False
        if normalized == "ai":
            self._handle_plan_ai(arg)
            return False
        method = getattr(self, f"do_{normalized}", None)
        if callable(method):
            method(arg)
            return False
        display_command = f"/{command}" if slash_command else command
        self.perror(f"unknown command: {display_command}")
        return False

    def _dispatch_ai_line(self, text: str) -> bool:
        normalized = text.split(None, 1)[0].lower()
        if normalized in {"exit", "back"}:
            self.mode = "plan"
            self._refresh_prompt()
            return False
        if normalized == "quit":
            return True
        self._require_ai_terminal().onecmd(text)
        return False

    def _handle_plan_ai(self, arg: str) -> None:
        ai_terminal = self._require_ai_terminal()
        if arg.strip():
            ai_terminal.onecmd(arg)
            return
        self.mode = "ai"
        self.prompt = "ai> "
        self.poutput("已进入 AI 模式。输入 exit 或 back 返回 plan 模式。")

    def _require_ai_terminal(self) -> Any:
        if self._ai_terminal is None:
            from ai_automate_contro.ai.terminal import AITerminal

            self._ai_terminal = AITerminal(self.project_root)
            self._sync_context_to_ai()
        return self._ai_terminal

    def _sync_context_to_ai(self) -> None:
        if self._ai_terminal is None:
            return
        update: dict[str, str] = {}
        if self.current_plan_path is not None:
            update["current_plan_path"] = str(self.current_plan_path)
        output_dir = self._resolve_latest_output_dir()
        if output_dir is not None:
            update["latest_output_dir"] = str(output_dir)
        if update:
            self._ai_terminal._update_context_state(update)

    def _refresh_prompt(self) -> None:
        if self.mode == "ai":
            self.prompt = "ai> "
            return
        if self.current_plan_path is None:
            self.prompt = "plan> "
            return
        try:
            display_path = self.current_plan_path.parent.relative_to(self.project_root)
        except ValueError:
            display_path = self.current_plan_path.parent
        self.prompt = f"plan:{display_path}> "


class PlanCommandCompleter(Completer):
    def get_completions(self, document: Any, complete_event: Any) -> Any:
        text = document.text_before_cursor
        if " " in text:
            return
        uses_slash = text.startswith("/")
        prefix = text[1:].lower() if uses_slash else text.lower()
        for name, description in sorted(PLAN_COMMANDS.items()):
            if not name.startswith(prefix):
                continue
            completion_text = f"/{name}" if uses_slash else name
            yield Completion(completion_text, start_position=-len(text), display=completion_text, display_meta=description)


def _plan_key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("/")
    def _(event: Any) -> None:
        buffer = event.current_buffer
        buffer.insert_text("/")
        if _is_plan_completion_context(buffer.text, buffer.cursor_position):
            buffer.start_completion(select_first=False)

    @bindings.add("up", filter=has_completions)
    def _(event: Any) -> None:
        _select_plan_completion_candidate(event.current_buffer, previous=True)

    @bindings.add("down", filter=has_completions)
    def _(event: Any) -> None:
        _select_plan_completion_candidate(event.current_buffer, previous=False)

    return bindings


def _select_plan_completion_candidate(buffer: Any, *, previous: bool) -> None:
    state = getattr(buffer, "complete_state", None)
    completions = list(getattr(state, "completions", []) or [])
    if not completions:
        return
    if getattr(state, "complete_index", None) is None:
        buffer.go_to_completion(len(completions) - 1 if previous else 0)
    elif previous:
        buffer.complete_previous()
    else:
        buffer.complete_next()


def _is_plan_completion_context(text: str, cursor: int) -> bool:
    before_cursor = text[:cursor]
    line_start = before_cursor.rfind("\n") + 1
    current_line = before_cursor[line_start:]
    return current_line.startswith("/") and " " not in current_line


def _split_command(text: str) -> tuple[str, str]:
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split(maxsplit=1)
    if not parts:
        return "", ""
    command = parts[0]
    raw_arg = text[len(command) :].strip()
    return command, raw_arg


def _repair_piped_stdin_text(text: str, *, encoding: str | None = None) -> str:
    if not any("\udc80" <= char <= "\udcff" for char in text):
        return text
    stdin_encoding = encoding or "utf-8"
    try:
        raw = text.encode(stdin_encoding, errors="surrogateescape")
    except Exception:
        return text.encode("utf-8", errors="replace").decode("utf-8")
    for candidate in ("utf-8", "gb18030"):
        try:
            decoded = raw.decode(candidate)
        except UnicodeDecodeError:
            continue
        if not any("\udc80" <= char <= "\udcff" for char in decoded):
            return decoded
    return text.encode("utf-8", errors="replace").decode("utf-8")
