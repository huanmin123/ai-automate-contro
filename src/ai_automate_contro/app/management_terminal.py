from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
import sys
import threading
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts.prompt import CompleteStyle

from ai_automate_contro.app.errors import format_error_for_terminal
from ai_automate_contro.app.management_debug_commands import DebugCommandsMixin
from ai_automate_contro.app.management_output_commands import OutputCommandsMixin
from ai_automate_contro.app.management_plan_commands import PlanCommandsMixin
from ai_automate_contro.app.management_run_commands import RunCommandsMixin
from ai_automate_contro.engine.interactive import InteractiveRun
from ai_automate_contro.support.terminal_style import terminal_input_style


PLAN_COMMANDS: dict[str, str] = {
    "ai": "进入 AI 模式，或发送一条 AI 消息",
    "artifacts": "列出输出产物",
    "close": "关闭正在等待检查的浏览器并结束运行",
    "continue": "继续正在等待人工确认的运行",
    "create": "创建 plan 包",
    "current": "查看当前选择的 plan 上下文",
    "debug": "管理调试工作区",
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
PLAN_INPUT_STYLE = terminal_input_style({"bottom-toolbar": "fg:#808080 noreverse"})
SLASH_COMMAND_RE = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.*))?$")


class ManagementTerminal(
    DebugCommandsMixin,
    OutputCommandsMixin,
    RunCommandsMixin,
    PlanCommandsMixin,
):
    intro = "AI 自动化控制终端。输入 /help 查看命令，输入 /ai 进入 AI 模式。"

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
        self._ai_queue: deque[QueuedAIInput] = deque()
        self._ai_queue_condition = threading.Condition()
        self._ai_worker_thread: threading.Thread | None = None
        self._ai_worker_shutdown = False
        self._ai_active_input: QueuedAIInput | None = None
        self._ai_force_next_input = False

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
        raw_text = str(line)
        if not raw_text.strip():
            return False
        text = raw_text.rstrip()
        if self.mode == "ai":
            return self._dispatch_ai_line(text)
        return self._dispatch_plan_line(text)

    def close(self) -> None:
        self._shutdown_ai_worker()
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
            lines.append(f"  /{name:<11} {description}")
        lines.extend(
            [
                "",
                "命令语法：",
                "  命令必须写在输入行最开头，格式是 /command 或 /command <args>。",
                "  / 后面的命令名必须以英文字母开头；命令和参数之间至少一个空格。",
                "  普通文字中间的 /xxx 不会被当作命令，也不会触发命令补全。",
                "",
                "AI 模式：",
                "  /ai                进入 AI 模式；启动时不会提前初始化 AI。",
                "  /ai <message>      在 plan 模式下直接发送一条 AI 消息。",
                "  /exit 或 /back     从 ai> 返回 plan>。",
                "  /quit              退出终端。",
            ]
        )
        self.poutput("\n".join(lines))

    def _read_line(self) -> str:
        if not sys.stdin.isatty():
            return _repair_piped_stdin_text(input(self.prompt), encoding=sys.stdin.encoding)
        if self.mode == "ai":
            return self._require_ai_terminal()._read_ai_input_with_images(
                self.prompt,
                bottom_toolbar=self._ai_input_status,
                on_escape=self._mark_next_ai_input_for_interrupt,
            )
        if self._session is None:
            self._session = PromptSession(history=InMemoryHistory())
        with patch_stdout():
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
        parsed = _parse_slash_command(text)
        if parsed is None:
            self.perror("交互命令必须写在行首并以 / 开头，例如 /help。")
            return False
        command, arg = parsed
        normalized = command.lower().replace("-", "_")
        if normalized in {"exit", "quit"}:
            return True
        if normalized == "help":
            self.do_help(arg)
            return False
        if normalized == "ai":
            self._handle_plan_ai(arg)
            return False
        method = getattr(self, f"do_{normalized}", None)
        if callable(method):
            method(arg)
            return False
        self.perror(f"unknown command: /{command}")
        return False

    def _dispatch_ai_line(self, text: str) -> bool:
        ai_terminal = self._require_ai_terminal()
        if self._ai_has_pending_confirmation(ai_terminal):
            self._ai_force_next_input = False
            ai_terminal.onecmd(text)
            return False
        parsed = _parse_slash_command(text)
        normalized = parsed[0].lower().replace("-", "_") if parsed else ""
        if normalized in {"exit", "back"}:
            self._ai_force_next_input = False
            self.mode = "plan"
            self._refresh_prompt()
            return False
        if normalized == "quit":
            self._ai_force_next_input = False
            return True
        if parsed is not None or text.startswith("/"):
            self._ai_force_next_input = False
            ai_terminal.onecmd(text)
            return False
        self._enqueue_ai_line(text)
        return False

    def _is_ai_processing(self) -> bool:
        ai_terminal = self._ai_terminal
        terminal_busy = bool(ai_terminal is not None and ai_terminal._is_agent_busy())
        return terminal_busy or self._is_ai_worker_busy() or self._queued_ai_count() > 0

    def _ai_has_pending_confirmation(self, ai_terminal: Any) -> bool:
        current = getattr(ai_terminal, "_current_ai_confirmation", None)
        return bool(callable(current) and current() is not None)

    def _enqueue_ai_line(self, text: str) -> None:
        force = self._ai_force_next_input
        self._ai_force_next_input = False
        ai_terminal = self._require_ai_terminal()
        queue_position = 1
        with self._ai_queue_condition:
            queued_input = QueuedAIInput(text=text, force=force)
            if force:
                self._request_ai_interrupt(ai_terminal)
                self._ai_queue.appendleft(queued_input)
                queue_position = 1
            else:
                self._ai_queue.append(queued_input)
                queue_position = len(self._ai_queue)
            self._ensure_ai_worker_locked()
            self._ai_queue_condition.notify()
        if force:
            self.poutput("[AI队列] 已请求介入：消息已排到队首，当前轮到达安全边界后处理。")
        elif queue_position > 1:
            self.poutput(f"[AI队列] 已排队：前方还有 {queue_position - 1} 条消息。按 Esc 后发送可插队。")
        elif self._is_ai_worker_busy():
            self.poutput("[AI队列] 已排队：当前回复结束后处理。按 Esc 后发送可插队。")
        else:
            self.poutput("[AI队列] 已发送，AI 正在处理；你可以继续输入下一条。")

    def _ensure_ai_worker_locked(self) -> None:
        if self._ai_worker_thread is not None and self._ai_worker_thread.is_alive():
            return
        self._ai_worker_shutdown = False
        self._ai_worker_thread = threading.Thread(target=self._ai_worker_loop, name="ai-terminal-queue-worker", daemon=True)
        self._ai_worker_thread.start()

    def _ai_worker_loop(self) -> None:
        while True:
            with self._ai_queue_condition:
                while not self._ai_queue and not self._ai_worker_shutdown:
                    self._ai_queue_condition.wait()
                if self._ai_worker_shutdown:
                    return
                queued_input = self._ai_queue.popleft()
                self._ai_active_input = queued_input
            try:
                self._require_ai_terminal().onecmd(queued_input.text)
            except SystemExit:
                raise
            except BaseException as error:
                self.perror(error)
            finally:
                with self._ai_queue_condition:
                    if self._ai_active_input is queued_input:
                        self._ai_active_input = None
                    remaining = len(self._ai_queue)
            if remaining:
                self.poutput(f"[AI队列] 继续处理下一条，剩余 {remaining} 条。")

    def _shutdown_ai_worker(self) -> None:
        worker = self._ai_worker_thread
        if worker is None:
            return
        with self._ai_queue_condition:
            self._ai_worker_shutdown = True
            self._ai_queue.clear()
            self._ai_queue_condition.notify_all()
        if worker.is_alive():
            worker.join(timeout=1)

    def _is_ai_worker_busy(self) -> bool:
        with self._ai_queue_condition:
            return self._ai_active_input is not None

    def _queued_ai_count(self) -> int:
        with self._ai_queue_condition:
            return len(self._ai_queue)

    def _mark_next_ai_input_for_interrupt(self) -> None:
        ai_terminal = self._ai_terminal
        if ai_terminal is not None and self._ai_has_pending_confirmation(ai_terminal):
            self.poutput("[AI确认] 当前正在等待确认；直接回复你的决定即可。")
            return
        self._ai_force_next_input = True
        self.poutput("[AI队列] 介入已开启：下一条消息会排到队首，并在当前轮安全边界后处理。")

    def _request_ai_interrupt(self, ai_terminal: Any) -> None:
        cancel = getattr(ai_terminal, "_cancel_agent_turn", None)
        if callable(cancel):
            cancel()

    def _ai_input_status(self) -> str:
        ai_terminal = self._ai_terminal
        if ai_terminal is not None and self._ai_has_pending_confirmation(ai_terminal):
            return "AI 等待你的确认回复  直接说明继续或停止"
        busy = self._is_ai_worker_busy() or bool(ai_terminal is not None and ai_terminal._is_agent_busy())
        queued = self._queued_ai_count()
        parts: list[str] = []
        if busy:
            parts.append("AI 正在处理")
        if queued:
            parts.append(f"排队 {queued} 条")
        if self._ai_force_next_input:
            parts.append("强制接入：下一条插队")
        return "  ".join(parts)

    def _handle_plan_ai(self, arg: str) -> None:
        ai_terminal = self._require_ai_terminal()
        if arg.strip():
            ai_terminal.onecmd(arg)
            return
        self.mode = "ai"
        self.prompt = "ai> "
        self.poutput("已进入 AI 模式。输入 /exit 或 /back 返回 plan 模式。")

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
        if not _is_plan_completion_context(document.text, document.cursor_position):
            return
        if " " in text:
            return
        prefix = text[1:].lower()
        for name, description in sorted(PLAN_COMMANDS.items()):
            if not name.startswith(prefix):
                continue
            completion_text = f"/{name}"
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
    return before_cursor.startswith("/") and "\n" not in before_cursor and " " not in before_cursor


def _parse_slash_command(text: str) -> tuple[str, str] | None:
    match = SLASH_COMMAND_RE.fullmatch(str(text).rstrip())
    if match is None:
        return None
    return match.group(1), (match.group(2) or "").strip()


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


@dataclass
class QueuedAIInput:
    text: str
    force: bool = False
