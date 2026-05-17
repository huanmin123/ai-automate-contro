from __future__ import annotations

import os
import platform
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class UserFacingError(Exception):
    message: str
    fix: str = ""
    details: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    exit_code: int = 1

    def __str__(self) -> str:
        return self.message


def print_cli_error(error: BaseException, *, project_root: Path | None = None) -> int:
    if isinstance(error, KeyboardInterrupt):
        print("已取消。", file=sys.stderr)
        return 130

    if isinstance(error, UserFacingError):
        _print_user_facing_error(error)
        return error.exit_code

    message = _exception_message(error)
    print(f"错误：{message}", file=sys.stderr)

    if _is_external_ai_service_error(error):
        return 1

    fix = _generic_fix_for(error, project_root=project_root)
    if fix:
        print("处理办法：", file=sys.stderr)
        for line in _as_lines(fix):
            print(f"  {line}", file=sys.stderr)

    if _debug_traceback_enabled():
        traceback.print_exception(type(error), error, error.__traceback__)
    elif not _is_common_user_error(error):
        print(f"需要开发堆栈时，设置环境变量后重试：{_debug_env_hint()}", file=sys.stderr)
    return 1


def format_error_for_terminal(error: BaseException | object, *, project_root: Path | None = None) -> str:
    if isinstance(error, KeyboardInterrupt):
        return "已取消。"
    if isinstance(error, UserFacingError):
        return "\n".join(_user_facing_error_lines(error))
    if isinstance(error, BaseException):
        message = _exception_message(error)
        if _is_external_ai_service_error(error):
            return f"错误：{message}"
        friendly = _friendly_text_error(message)
        if friendly:
            lines = friendly
        else:
            lines = [f"错误：{message}"]
        fix = _generic_fix_for(error, project_root=project_root)
        if fix and not any(line.startswith("处理办法：") for line in lines):
            lines.append("处理办法：")
            lines.extend(f"  {line}" for line in _as_lines(fix))
        if _debug_traceback_enabled():
            lines.append("开发堆栈：")
            lines.extend(traceback.format_exception(type(error), error, error.__traceback__))
        return "\n".join(line.rstrip("\n") for line in lines)

    text = str(error).strip()
    if not text:
        return "错误：未知错误"
    if text.startswith(("错误：", "详情：", "处理办法：", "验证命令：")):
        return text
    friendly = _friendly_text_error(text)
    if friendly:
        return "\n".join(friendly)
    return f"错误：{text}"


def is_external_ai_service_error(error: BaseException) -> bool:
    return _is_external_ai_service_error(error)


def _print_user_facing_error(error: UserFacingError) -> None:
    for line in _user_facing_error_lines(error):
        print(line, file=sys.stderr)


def _user_facing_error_lines(error: UserFacingError) -> list[str]:
    lines = [f"错误：{error.message}"]
    if error.details:
        lines.append("详情：")
        for detail in error.details:
            lines.append(f"  {detail}")
    if error.fix:
        lines.append("处理办法：")
        for line in _as_lines(error.fix):
            lines.append(f"  {line}")
    if error.verify:
        lines.append("验证命令：")
        for command in error.verify:
            lines.append(f"  {command}")
    return lines


def _generic_fix_for(error: BaseException, *, project_root: Path | None) -> str:
    if isinstance(error, FileNotFoundError):
        location_command = "Set-Location" if platform.system() == "Windows" else "cd"
        return f"检查命令里的文件路径是否存在；相对路径请确认当前 {location_command} 所在目录。"
    if isinstance(error, PermissionError):
        return "检查文件是否被占用、是否有读写权限，或换到有权限的工作目录后重试。"
    if isinstance(error, (ValueError, KeyError)):
        return "检查命令参数、plan.json、config.json 或 plan.config。可以先运行 self-check runtime 和 self-check env。"
    return ""


def _exception_message(error: BaseException) -> str:
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error).strip() or error.__class__.__name__


def _friendly_text_error(text: str) -> list[str] | None:
    lowered = text.lower()
    if lowered.startswith("usage: "):
        return [
            "错误：命令用法不正确。",
            "处理办法：",
            f"  命令格式：{text[len('usage:'):]}",
        ]
    if lowered.startswith("用法："):
        return [
            "错误：命令用法不正确。",
            "处理办法：",
            f"  命令格式：{text.split('：', 1)[1].strip()}",
        ]
    if lowered == "no active run":
        return [
            "错误：当前没有正在运行或等待的 plan。",
            "处理办法：",
            "  先用 use <plan.json-or-package-dir> 选择 plan，再执行 run。",
        ]
    if lowered == "no pending approval":
        return [
            "错误：当前没有等待审批的操作。",
            "处理办法：",
            "  只有 AI 请求应用受保护补丁时，才需要 /approve 或 /reject。",
        ]
    if lowered == "limit must be greater than 0":
        return ["错误：数量必须大于 0。"]
    if lowered == "lines must be greater than 0":
        return ["错误：行数必须大于 0。"]
    if lowered.startswith("unknown ai terminal command:"):
        return [
            f"错误：未知 AI 会话命令：{text.split(':', 1)[1].strip()}",
            "处理办法：",
            "  输入 /help 查看支持的命令。",
        ]
    if lowered.startswith("unknown command:"):
        return [
            f"错误：未知命令：{text.split(':', 1)[1].strip()}",
            "处理办法：",
            "  输入 help 查看支持的命令。",
        ]
    if lowered.startswith("ai terminal is busy"):
        return [
            "错误：AI 正在处理上一轮请求。",
            "处理办法：",
            "  等待当前回复完成后再输入下一句。",
            "  如果当前等待不想继续，按 Ctrl+C 中断。",
        ]
    if lowered.startswith("run is waiting for browser inspection"):
        return [
            "错误：当前运行正在等待浏览器检查结束。",
            "处理办法：",
            "  在 Textual 客户端输入 /close 关闭浏览器并结束运行。",
        ]
    if lowered.startswith("pending approval"):
        return [
            "错误：当前有补丁审批等待处理。",
            "处理办法：",
            "  输入 /approve 应用补丁，或输入 /reject <reason> 拒绝。",
        ]
    if lowered.startswith("debug workspace does not exist:"):
        return [
            f"错误：调试工作区不存在：{text.split(':', 1)[1].strip()}",
            "处理办法：",
            "  检查路径是否存在；必要时先运行 debug prepare 或 debug create。",
        ]
    if lowered.startswith("run output does not exist:"):
        return [
            f"错误：运行输出目录不存在：{text.split(':', 1)[1].strip()}",
            "处理办法：",
            "  检查 output 路径，或先运行 plan 生成新的 output。",
        ]
    if lowered.startswith("a run is already active:"):
        return [
            f"错误：已有 plan 正在运行或等待：{text.split(':', 1)[1].strip()}",
            "处理办法：",
            "  先等待当前 run 结束；如果正在等待人工确认，可在 Textual 客户端输入 /continue 或 /stop。",
        ]
    if lowered.startswith("unsupported ai sdk response object:"):
        object_type = text.split(":", 1)[1].strip() or "unknown"
        return [
            f"错误：AI 服务返回了当前协议不支持的响应对象：{object_type}",
            "处理办法：",
            "  检查 ai_services.* 的 base_url、api 和 response_format 是否真的兼容 OpenAI-compatible 接口。",
            "  如果服务实际直接返回纯文本或 JSON 字符串，请升级到当前版本后重试；仍失败时查看 output/ai/ 下的原始响应产物。",
        ]
    if lowered.startswith("no current plan selected"):
        return [
            "错误：当前没有选择 plan。",
            "处理办法：",
            "  先执行 use <plan.json-or-package-dir>。",
        ]
    return None


def _as_lines(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        return [line for line in value.splitlines() if line.strip()]
    return [str(line) for line in value if str(line).strip()]


def _debug_traceback_enabled() -> bool:
    return os.environ.get("AI_AUTOMATE_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _debug_env_hint() -> str:
    if platform.system() == "Windows":
        return "$env:AI_AUTOMATE_DEBUG='1'"
    return "AI_AUTOMATE_DEBUG=1"


def _is_common_user_error(error: BaseException) -> bool:
    return isinstance(error, (FileNotFoundError, PermissionError, ValueError, KeyError, RuntimeError, AssertionError))


def _is_external_ai_service_error(error: BaseException) -> bool:
    module = error.__class__.__module__.lower()
    if module.startswith(
        (
            "openai",
            "httpx",
            "httpcore",
            "langchain",
            "langchain_core",
            "langchain_openai",
        )
    ):
        return True
    text = _exception_message(error).lower()
    return "model_dump" in text or "error code:" in text or "status code:" in text
