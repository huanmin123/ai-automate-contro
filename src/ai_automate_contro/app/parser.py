from __future__ import annotations

import argparse

from ai_automate_contro.app.errors import UserFacingError


class UserFacingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UserFacingError(
            "命令参数不正确。",
            details=[_friendly_argparse_message(message)],
            fix=_friendly_usage(self.format_usage()),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = UserFacingArgumentParser(
        description="管理并运行 JSON 自动化 plan 包。",
    )

    subparsers = parser.add_subparsers(dest="command")
    plan_parser = subparsers.add_parser("plan", help="管理 plan 包。")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command")

    tool_parser = subparsers.add_parser("tool", help="调用结构化 AI 终端工具。")
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

    ai_parser = subparsers.add_parser("ai", help="启动持久化 AI 终端。")
    ai_parser.add_argument("--service", default="default", help="配置中的 AI 服务名称。")
    ai_parser.add_argument("--thread", default="default", help="持久化 AI 终端线程 id。")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_command")
    ai_ask_parser = ai_subparsers.add_parser("ask", help="发送一条 AI 终端消息并等待结果。")
    ai_ask_parser.add_argument("--message", required=True, help="要发送给 AI 终端的用户消息。")
    ai_ask_parser.add_argument("--json", action="store_true", help="以 JSON 输出完整结果。")
    ai_ask_parser.add_argument("--compact", action="store_true", help="配合 --json 输出紧凑 JSON。")

    self_check_parser = subparsers.add_parser("self-check", help="运行本地确定性自检。")
    self_check_subparsers = self_check_parser.add_subparsers(dest="self_check_command")
    self_check_subparsers.add_parser("env", help="检查本地客户端环境依赖。")
    self_check_subparsers.add_parser("runtime", help="检查 plan.config、handbook 和 plan 根目录。")
    self_check_subparsers.add_parser("ai-stream", help="检查本地 chat completions 流式解析。")
    self_check_subparsers.add_parser("ai-terminal", help="检查 AI 终端会话、压缩和图片状态。")
    self_check_subparsers.add_parser("ai-tools", help="检查 LangChain StructuredTool 接线。")

    list_parser = plan_subparsers.add_parser("list", help="列出 plan 包。")
    list_parser.add_argument("filter", nargs="?", help="可选文本过滤条件。")

    create_parser = plan_subparsers.add_parser("create", help="创建 plan 包模板。")
    create_parser.add_argument("--path", required=True, help="要创建的 plan 包目录。")
    create_parser.add_argument("--name", help="写入 plan.json 的 plan 名称。")
    create_parser.add_argument("--force", action="store_true", help="允许使用已有的非空包目录。")

    validate_parser = plan_subparsers.add_parser("validate", help="校验 plan 包。")
    validate_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")

    run_parser = plan_subparsers.add_parser("run", help="运行 plan 包。")
    run_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    run_parser.add_argument("--run-name", help="覆盖用于输出目录命名的运行名称。")
    run_parser.add_argument(
        "--output-dir",
        help="覆盖运行输出目录；必须位于当前 plan 包的 output/ 目录内。",
    )

    debug_parser = plan_subparsers.add_parser("debug-create", help="为 plan 包创建隔离 debug workspace。")
    debug_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    debug_parser.add_argument("--name", help="debug workspace 名称后缀。")

    prepare_parser = plan_subparsers.add_parser("debug-prepare", help="从最近失败运行创建 debug workspace 并注入诊断。")
    prepare_parser.add_argument("--file", required=True, help="入口 plan.json 路径。")
    prepare_parser.add_argument("--output-dir", help="指定失败运行输出目录；默认使用最近一次运行。")
    prepare_parser.add_argument("--name", help="debug workspace 名称后缀。")
    prepare_parser.add_argument("--manual-confirm", action="store_true", help="在失败步骤前注入人工确认点。")

    fix_parser = plan_subparsers.add_parser("debug-fix", help="在 debug workspace 中生成或应用干净修复候选。")
    fix_parser.add_argument("--workspace", required=True, help="output/debug/<run> workspace 路径。")
    fix_parser.add_argument("--hint", default="", help="可选用户提示，用于排序修复候选。")
    fix_parser.add_argument("--apply", action="store_true", help="把选中的修复候选写入 injected-plan/。")
    fix_parser.add_argument("--run", action="store_true", help="应用候选后运行 debug plan。")
    fix_parser.add_argument("--run-name", help="配合 --run 使用时覆盖 debug 运行名称。")

    inject_parser = plan_subparsers.add_parser("debug-inject", help="向已有 debug workspace 注入诊断步骤。")
    inject_parser.add_argument("--workspace", required=True, help="output/debug/<run> workspace 路径。")
    inject_parser.add_argument(
        "--preset",
        action="append",
        required=True,
        choices=["print", "variables", "manual_confirm", "screenshot", "html"],
        help="要注入的诊断预设；可重复传入。",
    )
    inject_parser.add_argument("--message", help="print/manual_confirm 预设使用的消息。")
    inject_parser.add_argument("--browser", help="screenshot/html 预设使用的浏览器会话名。")
    inject_parser.add_argument("--page", help="screenshot/html 预设使用的页面名。")
    inject_parser.add_argument("--position", choices=["start", "end", "before_step", "after_step"], default="end", help="步骤注入位置。")
    inject_parser.add_argument("--step", type=int, help="before_step 或 after_step 使用的 1-based 锚点步骤。")

    patch_parser = plan_subparsers.add_parser("debug-patch", help="从 debug workspace 生成 patch.diff。")
    patch_parser.add_argument("--workspace", required=True, help="output/debug/<run> workspace 路径。")

    apply_parser = plan_subparsers.add_parser("debug-apply", help="把 debug workspace 的 patch.diff 应用回原始 plan 包。")
    apply_parser.add_argument("--workspace", required=True, help="output/debug/<run> workspace 路径。")
    apply_parser.add_argument("--yes", action="store_true", help="必填确认参数，用于允许修改原始 plan 包。")

    return parser


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
