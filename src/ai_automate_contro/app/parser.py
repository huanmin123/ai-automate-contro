from __future__ import annotations

import argparse

from ai_automate_contro.app.errors import UserFacingError


class ChineseHelpFormatter(argparse.HelpFormatter):
    def start_section(self, heading: str | None) -> None:
        heading_map = {
            "positional arguments": "位置参数",
            "options": "选项",
            "optional arguments": "选项",
            "subcommands": "子命令",
        }
        super().start_section(heading_map.get(str(heading), heading))

    def add_usage(self, usage: str | None, actions: object, groups: object, prefix: str | None = None) -> None:
        if prefix is None or prefix == "usage: ":
            prefix = "用法："
        super().add_usage(usage, actions, groups, prefix=prefix)


class UserFacingArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("formatter_class", ChineseHelpFormatter)
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help="显示这段帮助信息并退出。")

    def error(self, message: str) -> None:
        raise UserFacingError(
            "命令参数不正确。",
            details=[_friendly_argparse_message(message)],
            fix=_friendly_usage(self.format_usage()),
        )

    def add_subparsers(self, *args: object, **kwargs: object) -> argparse._SubParsersAction:
        kwargs.setdefault("parser_class", type(self))
        return super().add_subparsers(*args, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = UserFacingArgumentParser(
        description="启动 AI-first Textual 客户端，或运行 AI 相关诊断。",
    )

    subparsers = parser.add_subparsers(dest="command")

    tool_parser = subparsers.add_parser("tool", help="调用结构化 AI 工具。")
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command")
    tool_subparsers.add_parser("list", help="列出可用的结构化工具。")
    tool_subparsers.add_parser("check", help="检查结构化工具注册表。")
    tool_schema_parser = tool_subparsers.add_parser("schema", help="输出某个结构化工具的 JSON schema。")
    tool_schema_parser.add_argument("name", help="工具名称。")
    tool_call_parser = tool_subparsers.add_parser("call", help="调用一个结构化工具并输出 JSON。")
    tool_call_parser.add_argument("name", help="工具名称。")
    tool_call_parser.add_argument("--args-json", default="{}", help="JSON 对象格式的工具参数。")
    tool_call_parser.add_argument("--args-file", help="从 JSON 文件读取工具参数。")
    tool_call_parser.add_argument("--compact", action="store_true", help="输出紧凑 JSON。")

    ai_parser = subparsers.add_parser(
        "ai",
        help="启动 Textual AI 客户端。",
        usage="%(prog)s [--service SERVICE] [--thread THREAD] [check|ask] ...",
        description="不带子命令时启动 Textual AI 客户端；带 check/ask 时执行一次性 AI 诊断或脚本化请求。",
    )
    ai_parser.add_argument("--service", default="default", help="配置中的 AI 服务名称。")
    ai_parser.add_argument("--thread", default="default", help="持久化 AI 会话线程 id。")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_command")
    ai_check_parser = ai_subparsers.add_parser("check", help="发送真实模型请求，诊断 AI 服务连通性。")
    ai_check_parser.add_argument("--message", default="只回复 ok", help="用于诊断的测试消息。")
    ai_check_parser.add_argument("--json", action="store_true", help="以 JSON 输出诊断结果。")
    ai_check_parser.add_argument("--compact", action="store_true", help="配合 --json 输出紧凑 JSON。")
    ai_ask_parser = ai_subparsers.add_parser("ask", help="发送一条 AI 消息并等待结果。")
    ai_ask_parser.add_argument("--message", required=True, help="要发送给 AI 的用户消息。")
    ai_ask_parser.add_argument("--json", action="store_true", help="以 JSON 输出完整结果。")
    ai_ask_parser.add_argument(
        "--events",
        action="store_true",
        help="以 JSONL 实时输出结构化事件，适合真实网站、工具调用和人工确认回归。",
    )
    ai_ask_parser.add_argument("--compact", action="store_true", help="配合 --json 输出紧凑 JSON。")

    self_check_parser = subparsers.add_parser("self-check", help="运行本地确定性自检。")
    self_check_subparsers = self_check_parser.add_subparsers(dest="self_check_command")
    self_check_subparsers.add_parser("env", help="检查本地客户端环境依赖。")
    self_check_subparsers.add_parser("textual-client", help="检查 Textual AI 客户端渲染、队列和工具进度。")
    self_check_subparsers.add_parser("ai-stream", help="检查本地 chat completions 流式解析。")
    self_check_subparsers.add_parser("ai-terminal", help="检查 AI 会话、压缩和图片状态。")
    self_check_subparsers.add_parser("ai-tools", help="检查 LangChain StructuredTool 接线。")
    self_check_subparsers.add_parser("ai-plan-generation", help="模拟服务端 AI 的执行线识别和 plan 生成工具调用。")
    self_check_subparsers.add_parser("ai-desktop-loop", help="运行 AI 工具链到桌面 runtime 的真实闭环自检。")
    ai_real_desktop_loop_parser = self_check_subparsers.add_parser(
        "ai-real-desktop-loop",
        help="使用真实模型驱动 AI 终端生成并运行 desktop smoke plan。",
    )
    ai_real_desktop_loop_parser.add_argument("--service", default="default", help="配置中的 AI 服务名称。")
    ai_real_desktop_loop_parser.add_argument("--thread", default="", help="可选 AI 终端 thread id；默认自动生成。")
    ai_real_desktop_loop_parser.add_argument("--api-key-file", default="", help="可选本机密钥文件；支持从文件中解析 URL 和 sk-* key。")
    ai_real_desktop_loop_parser.add_argument("--api-key-env", default="AIC_TEST_API_KEY", help="未提供密钥文件时读取的环境变量。")
    ai_real_desktop_loop_parser.add_argument("--base-url", default="", help="覆盖 OpenAI-compatible base_url。")
    ai_real_desktop_loop_parser.add_argument("--model", default="gpt-5.5", help="真实模型名，默认 gpt-5.5。")
    ai_real_desktop_loop_parser.add_argument("--timeout-seconds", type=int, default=180, help="单次模型请求超时秒数。")
    ai_real_desktop_loop_parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        help="真实模型调用遇到连接或超时类瞬态错误时的最大尝试次数。",
    )
    ai_real_desktop_loop_parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=3.0,
        help="真实模型闭环外层重试的基础等待秒数；实际等待按尝试次数线性退避。",
    )
    ai_real_execution_line_parser = self_check_subparsers.add_parser(
        "ai-real-execution-line",
        help="使用真实模型回归 AI 终端执行线确认，不创建 plan。",
    )
    ai_real_execution_line_parser.add_argument("--service", default="default", help="配置中的 AI 服务名称。")
    ai_real_execution_line_parser.add_argument("--thread", default="", help="可选 AI 终端 thread id；默认自动生成。")
    ai_real_execution_line_parser.add_argument("--api-key-file", default="", help="可选本机密钥文件；支持从文件中解析 URL 和 sk-* key。")
    ai_real_execution_line_parser.add_argument("--api-key-env", default="AIC_TEST_API_KEY", help="未提供密钥文件时读取的环境变量。")
    ai_real_execution_line_parser.add_argument("--base-url", default="", help="覆盖 OpenAI-compatible base_url。")
    ai_real_execution_line_parser.add_argument("--model", default="gpt-5.5", help="真实模型名，默认 gpt-5.5。")
    ai_real_execution_line_parser.add_argument("--timeout-seconds", type=int, default=180, help="单次模型请求超时秒数。")
    ai_real_execution_line_parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        help="真实模型调用遇到连接或超时类瞬态错误时的最大尝试次数。",
    )
    ai_real_execution_line_parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=3.0,
        help="真实模型执行线回归外层重试的基础等待秒数；实际等待按尝试次数线性退避。",
    )

    return parser


def build_cplan_parser() -> argparse.ArgumentParser:
    parser = UserFacingArgumentParser(
        prog="cplan",
        description="无 AI 环境下控制 JSON 自动化 plan：创建、校验、运行和调试。",
    )
    subparsers = parser.add_subparsers(dest="cplan_command")
    _add_cplan_subcommands(subparsers)
    return parser


def _add_cplan_subcommands(subparsers: argparse._SubParsersAction) -> None:
    list_parser = subparsers.add_parser("list", help="列出 plan 包。")
    list_parser.add_argument("filter", nargs="?", help="可选文本过滤条件。")

    create_parser = subparsers.add_parser("create", help="创建 plan 包模板。")
    create_parser.add_argument("--path", required=True, help="要创建的 plan 包目录。")
    create_parser.add_argument(
        "--automation-type",
        required=True,
        choices=["browser", "desktop"],
        help="plan 执行线：browser 或 desktop。",
    )
    create_parser.add_argument("--name", help="写入 plan.json 的 plan 名称。")
    create_parser.add_argument("--force", action="store_true", help="允许使用已有的非空包目录。")

    validate_parser = subparsers.add_parser("validate", help="校验 plan 包。")
    validate_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")

    run_parser = subparsers.add_parser("run", help="运行 plan 包。")
    run_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    run_parser.add_argument("--run-name", help="覆盖用于输出目录命名的运行名称。")
    run_parser.add_argument(
        "--output-dir",
        help="覆盖运行输出目录；必须位于当前 plan 包的 output/ 目录内。",
    )

    schedule_parser = subparsers.add_parser("schedule", help="管理长期定时启动 plan 的 schedule。")
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command")
    schedule_list_parser = schedule_subparsers.add_parser("list", help="列出 schedules.json 中的定时计划。")
    schedule_list_parser.add_argument("--json", action="store_true", help="以 JSON 输出。")
    schedule_add_parser = schedule_subparsers.add_parser("add", help="新增或覆盖一个定时计划。")
    schedule_add_parser.add_argument("--id", required=True, help="schedule id。")
    schedule_add_parser.add_argument("--file", required=True, help="要运行的 plan.json 或 plan 包目录。")
    trigger_group = schedule_add_parser.add_mutually_exclusive_group(required=True)
    trigger_group.add_argument("--daily-at", help="每天执行时间，格式 HH:MM。")
    trigger_group.add_argument("--every-seconds", type=float, help="按固定秒数间隔执行。")
    schedule_add_parser.add_argument("--run-immediately", action="store_true", help="interval 首次 daemon 扫描时立即运行。")
    schedule_add_parser.add_argument("--project-root", help="该 schedule 运行 plan 时使用的 project root；默认当前运行根。")
    schedule_add_parser.add_argument("--timezone", default="Asia/Shanghai", help="时区，默认 Asia/Shanghai。")
    schedule_add_parser.add_argument("--run-name", help="覆盖运行名称；默认使用 schedule id。")
    schedule_add_parser.add_argument("--timeout-seconds", type=int, help="单次运行超时秒数。")
    schedule_add_parser.add_argument("--disabled", action="store_true", help="创建后保持禁用。")
    schedule_add_parser.add_argument("--replace", action="store_true", help="允许覆盖同 id schedule。")
    schedule_remove_parser = schedule_subparsers.add_parser("remove", help="删除一个 schedule。")
    schedule_remove_parser.add_argument("id", help="schedule id。")
    schedule_enable_parser = schedule_subparsers.add_parser("enable", help="启用一个 schedule。")
    schedule_enable_parser.add_argument("id", help="schedule id。")
    schedule_disable_parser = schedule_subparsers.add_parser("disable", help="禁用一个 schedule。")
    schedule_disable_parser.add_argument("id", help="schedule id。")
    schedule_run_now_parser = schedule_subparsers.add_parser("run-now", help="立即运行一个 schedule。")
    schedule_run_now_parser.add_argument("id", help="schedule id。")
    schedule_run_now_parser.add_argument("--json", action="store_true", help="以 JSON 输出。")
    schedule_daemon_parser = schedule_subparsers.add_parser("daemon", help="启动 schedule daemon。")
    schedule_daemon_parser.add_argument("--poll-seconds", type=float, default=60.0, help="扫描间隔秒数。")
    schedule_daemon_parser.add_argument("--once", action="store_true", help="只扫描一次后退出，适合测试和系统任务计划程序。")
    schedule_daemon_parser.add_argument("--json", action="store_true", help="以 JSON 输出本次扫描结果。")

    debug_parser = subparsers.add_parser("debug-create", help="为 plan 包创建隔离调试工作区。")
    debug_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    debug_parser.add_argument("--name", help="调试工作区名称后缀。")

    prepare_parser = subparsers.add_parser("debug-prepare", help="从最近失败运行创建调试工作区并注入诊断。")
    prepare_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    prepare_parser.add_argument("--output-dir", help="指定失败运行输出目录；默认使用最近一次运行。")
    prepare_parser.add_argument("--name", help="调试工作区名称后缀。")
    prepare_parser.add_argument("--manual-confirm", action="store_true", help="在失败步骤前注入人工确认点。")

    inject_parser = subparsers.add_parser("debug-inject", help="向已有调试工作区注入诊断步骤。")
    inject_parser.add_argument("--workspace", required=True, help="output/debug/<run> 调试工作区路径。")
    inject_parser.add_argument(
        "--preset",
        action="append",
        required=True,
        choices=["print", "variables", "manual_confirm", "screenshot", "html", "desktop_screenshot", "desktop_snapshot", "desktop_windows"],
        help="要注入的诊断预设；可重复传入。",
    )
    inject_parser.add_argument("--message", help="print/manual_confirm 预设使用的消息。")
    inject_parser.add_argument("--browser", help="screenshot/html 预设使用的浏览器会话名。")
    inject_parser.add_argument("--page", help="screenshot/html 预设使用的页面名。")
    inject_parser.add_argument("--desktop", help="desktop_* 预设使用的桌面会话名；默认 desktop。")
    inject_parser.add_argument("--position", choices=["start", "end", "before_step", "after_step"], default="end", help="步骤注入位置。")
    inject_parser.add_argument("--step", type=int, help="before_step 或 after_step 使用的 1-based 锚点步骤。")

    patch_parser = subparsers.add_parser("debug-patch", help="从调试工作区生成 patch.diff。")
    patch_parser.add_argument("--workspace", required=True, help="output/debug/<run> 调试工作区路径。")

    apply_parser = subparsers.add_parser("debug-apply", help="把调试工作区的 patch.diff 应用回原始 plan 包。")
    apply_parser.add_argument("--workspace", required=True, help="output/debug/<run> 调试工作区路径。")
    apply_parser.add_argument("--yes", action="store_true", help="必填确认参数，用于允许修改原始 plan 包。")

    self_check_parser = subparsers.add_parser("self-check", help="运行 plan 相关确定性自检。")
    self_check_subparsers = self_check_parser.add_subparsers(dest="self_check_command")
    self_check_subparsers.add_parser("cli", help="检查 aic/main.py 与 cplan 的命令边界。")
    self_check_subparsers.add_parser("runtime", help="检查 plan.config、handbook 和 plan 根目录。")
    self_check_subparsers.add_parser("browser-components", help="运行浏览器组件回归矩阵和参数负向校验。")
    self_check_subparsers.add_parser("desktop-components", help="运行桌面控制组件 schema、执行线隔离和轻量运行自检。")
    self_check_subparsers.add_parser("desktop-real-app", help="运行真实桌面 App 回归；Windows 使用 Notepad，macOS 使用 TextEdit。")


def _friendly_argparse_message(message: str) -> str:
    if message.startswith("the following arguments are required:"):
        required = message.split(":", 1)[1].strip()
        return f"缺少必填参数：{required}"
    if message.startswith("unrecognized arguments:"):
        arguments = message.split(":", 1)[1].strip()
        return f"不支持的参数：{arguments}"
    if "invalid choice:" in message:
        invalid_part = message.split("invalid choice:", 1)[1].strip()
        if "(choose from" in invalid_part:
            raw_value, raw_choices = invalid_part.split("(choose from", 1)
            choices = raw_choices.rstrip(")").strip()
            return f"参数值不支持：{raw_value.strip()}；可选值：{choices}"
        return f"参数值不支持：{invalid_part}"
    if "invalid int value:" in message:
        return f"整数参数格式不正确：{message}"
    return message


def _friendly_usage(usage: str) -> str:
    text = usage.strip()
    if text.startswith("usage:"):
        return "命令格式：" + text[len("usage:") :]
    return text
