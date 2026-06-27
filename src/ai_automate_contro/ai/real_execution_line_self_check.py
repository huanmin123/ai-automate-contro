from __future__ import annotations

import tempfile
import time
import uuid
import re
from pathlib import Path
from typing import Any, Literal

from ai_automate_contro.ai.real_desktop_loop_self_check import (
    DEFAULT_REAL_DESKTOP_LOOP_API_KEY_ENV,
    DEFAULT_REAL_DESKTOP_LOOP_BASE_URL,
    DEFAULT_REAL_DESKTOP_LOOP_MAX_ATTEMPTS,
    DEFAULT_REAL_DESKTOP_LOOP_MODEL,
    DEFAULT_REAL_DESKTOP_LOOP_RETRY_DELAY_SECONDS,
    _compact_event,
    _resolve_secret,
    _retry_delay_seconds,
    _should_retry_real_loop,
    _temporary_env,
    _tool_sequence,
    _write_loop_project_config,
)
from ai_automate_contro.ai.terminal import AITerminal


ExecutionLineDecision = Literal["browser", "desktop", "ambiguous"]

_PLAN_MUTATION_TOOLS = {
    "create_plan_package",
    "write_plan_package_file",
    "validate_plan",
    "review_plan_quality",
    "run_plan",
}

_CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "clear_browser",
        "expected_decision": "browser",
        "requires_confirmation": False,
        "message": "用户要在浏览器里打开 https://example.com，截一张网页截图并保存。",
    },
    {
        "name": "clear_desktop",
        "expected_decision": "desktop",
        "requires_confirmation": False,
        "message": "用户要控制本机桌面 Notepad 窗口，输入文字，截图并保存状态。",
    },
    {
        "name": "mixed_ambiguous",
        "expected_decision": "ambiguous",
        "requires_confirmation": True,
        "message": "用户说：帮我自动化客户端后台登录，也可能是在网页后台里操作表格，现在开始写 plan。",
    },
    {
        "name": "platform_word_browser",
        "expected_decision": "browser",
        "requires_confirmation": False,
        "message": "用户要在 Windows 上用 Chrome 浏览器打开 https://example.com 并截图。",
    },
    {
        "name": "file_dialog",
        "expected_decision": "desktop",
        "requires_confirmation": False,
        "message": "用户要控制当前系统 App 的 Open/Save 文件对话框，输入完整文件路径并按 Enter。",
    },
)


def self_check_real_ai_execution_line(
    project_root: str | Path,
    *,
    service: str = "default",
    thread_id: str = "",
    api_key_file: str = "",
    api_key_env: str = DEFAULT_REAL_DESKTOP_LOOP_API_KEY_ENV,
    base_url: str = "",
    model: str = DEFAULT_REAL_DESKTOP_LOOP_MODEL,
    timeout_seconds: int = 180,
    max_attempts: int = DEFAULT_REAL_DESKTOP_LOOP_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_REAL_DESKTOP_LOOP_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    resolved_project_root = Path(project_root).resolve()
    secret = _resolve_secret(api_key_file=api_key_file, api_key_env=api_key_env, base_url=base_url)
    if not secret.get("ok"):
        return {
            "ok": bool(secret.get("skipped")),
            "check": "real_ai_execution_line",
            "skipped": bool(secret.get("skipped")),
            "reason": secret.get("reason", ""),
            "error": secret.get("error", ""),
            "project_root": str(resolved_project_root),
        }

    resolved_thread_id = thread_id.strip() or f"ai-real-execution-line-{uuid.uuid4().hex[:12]}"
    resolved_model = str(model or DEFAULT_REAL_DESKTOP_LOOP_MODEL).strip()
    resolved_base_url = str(secret.get("base_url") or base_url or DEFAULT_REAL_DESKTOP_LOOP_BASE_URL).strip()
    resolved_api_key_env = str(secret["api_key_env"])
    timeout = max(30, int(timeout_seconds or 180))
    attempts_limit = max(1, int(max_attempts or 1))
    retry_delay = max(0.0, float(retry_delay_seconds or 0.0))
    attempts: list[dict[str, Any]] = []

    with _temporary_env(resolved_api_key_env, str(secret["api_key"])):
        for attempt_index in range(1, attempts_limit + 1):
            with tempfile.TemporaryDirectory(prefix="real-ai-execution-line-") as raw_temp_dir:
                runtime_root = Path(raw_temp_dir).resolve()
                _write_loop_project_config(
                    runtime_root,
                    service=service,
                    model=resolved_model,
                    base_url=resolved_base_url,
                    api_key_env=resolved_api_key_env,
                    timeout_seconds=timeout,
                )
                result = _run_real_execution_line_suite(
                    runtime_root,
                    original_project_root=resolved_project_root,
                    service=service,
                    thread_id=(
                        resolved_thread_id
                        if attempts_limit == 1
                        else f"{resolved_thread_id}-attempt-{attempt_index}"
                    ),
                    model=resolved_model,
                    base_url=resolved_base_url,
                )
            attempt_summary = _compact_attempt_result(result, attempt_index=attempt_index)
            attempts.append(attempt_summary)
            if result.get("ok"):
                result["attempt_count"] = attempt_index
                result["max_attempts"] = attempts_limit
                result["retry_delay_seconds"] = retry_delay
                result["attempts"] = attempts
                return result
            if attempt_index >= attempts_limit or not _should_retry_real_loop(result):
                result["attempt_count"] = attempt_index
                result["max_attempts"] = attempts_limit
                result["retry_delay_seconds"] = retry_delay
                result["attempts"] = attempts
                return result
            delay = _retry_delay_seconds(retry_delay, attempt_index)
            attempt_summary["retry_after_seconds"] = delay
            if delay > 0:
                time.sleep(delay)

    return {
        "ok": False,
        "check": "real_ai_execution_line",
        "project_root": str(resolved_project_root),
        "service": service,
        "model": resolved_model,
        "base_url": resolved_base_url,
        "thread_id": resolved_thread_id,
        "attempt_count": attempts_limit,
        "max_attempts": attempts_limit,
        "retry_delay_seconds": retry_delay,
        "attempts": attempts,
        "error": "real execution line check ended without a result",
    }


def _run_real_execution_line_suite(
    project_root: Path,
    *,
    original_project_root: Path,
    service: str,
    thread_id: str,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    try:
        for case in _CASES:
            case_results.append(
                _run_case(
                    project_root,
                    service=service,
                    thread_id=f"{thread_id}-{case['name']}",
                    case=case,
                )
            )
        return {
            "ok": all(case_result.get("passed") for case_result in case_results),
            "check": "real_ai_execution_line",
            "project_root": str(original_project_root),
            "runtime_root": "temporary",
            "service": service,
            "model": model,
            "base_url": base_url,
            "thread_id": thread_id,
            "case_count": len(case_results),
            "cases": case_results,
            "error_type": _first_case_error(case_results, "error_type"),
            "error": _first_case_error(case_results, "error"),
            "commands": {
                "run": "python .\\main.py self-check ai-real-execution-line --api-key-file D:\\模型密钥.txt",
                "deterministic": "python .\\main.py self-check ai-plan-generation",
            },
        }
    except Exception as error:
        return {
            "ok": False,
            "check": "real_ai_execution_line",
            "project_root": str(original_project_root),
            "service": service,
            "model": model,
            "base_url": base_url,
            "thread_id": thread_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "cases": case_results,
        }


def _run_case(
    project_root: Path,
    *,
    service: str,
    thread_id: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    terminal: AITerminal | None = None
    try:
        terminal = AITerminal(project_root, service=service, thread_id=thread_id)
        result = terminal.ask_once(_case_prompt(str(case["message"])), event_sink=lambda event: events.append(_compact_event(event)))
        assistant_message = str(result.get("assistant_message") or "")
        decision = _extract_decision(assistant_message)
        tool_sequence = _tool_sequence(events)
        forbidden_tools = [tool_name for tool_name in tool_sequence if tool_name in _PLAN_MUTATION_TOOLS]
        confirmation_found = _looks_like_confirmation_question(assistant_message)
        expected_decision = str(case["expected_decision"])
        expected_confirmation = bool(case["requires_confirmation"])
        passed = (
            result.get("ok") is True
            and decision == expected_decision
            and confirmation_found == expected_confirmation
            and not forbidden_tools
        )
        return {
            "name": str(case["name"]),
            "passed": passed,
            "expected_decision": expected_decision,
            "decision": decision,
            "expected_confirmation": expected_confirmation,
            "confirmation_found": confirmation_found,
            "forbidden_tools": forbidden_tools,
            "tool_sequence": tool_sequence,
            "event_count": len(events),
            "assistant_message": assistant_message[:1000],
        }
    except Exception as error:
        formatted = terminal.format_error_message(error) if terminal is not None else str(error)
        return {
            "name": str(case["name"]),
            "passed": False,
            "expected_decision": str(case["expected_decision"]),
            "error_type": type(error).__name__,
            "error": str(error),
            "formatted_error": formatted,
            "tool_sequence": _tool_sequence(events),
            "event_count": len(events),
        }
    finally:
        if terminal is not None:
            terminal.close()


def _case_prompt(user_message: str) -> str:
    return (
        "这是 ai-automate-contro 的真实模型执行线确认回归。请按真实 AI 终端规则判断下面用户原始需求。"
        "如果执行线明确，只用 `执行线=browser` 或 `执行线=desktop` 开头，并用一句中文说明原因。"
        "如果执行线不明确，只用 `执行线=ambiguous` 开头，然后问用户一个确认问题。"
        "本轮只判断执行线，不要创建 plan、不要写文件、不要运行工具。\n\n"
        f"用户原始需求：{user_message}"
    )


def _extract_decision(text: str) -> ExecutionLineDecision | str:
    lowered = text.lower()
    match = re.search(r"执行线\s*[:=：]\s*(browser|desktop|ambiguous)", lowered)
    if match:
        return match.group(1)
    for decision in ("browser", "desktop", "ambiguous"):
        if f"执行线={decision}" in lowered or f"执行线: {decision}" in lowered or f"执行线：{decision}" in lowered:
            return decision
    if "ambiguous" in lowered or "需要确认" in text or "请确认" in text:
        return "ambiguous"
    browser_hit = any(token in lowered for token in ("browser", "浏览器", "网页", "url", "website", "web"))
    desktop_hit = any(token in lowered for token in ("desktop", "桌面", "本机", "窗口", "app", "文件对话框"))
    if browser_hit and not desktop_hit:
        return "browser"
    if desktop_hit and not browser_hit:
        return "desktop"
    return "unknown"


def _looks_like_confirmation_question(text: str) -> bool:
    if _extract_decision(text) != "ambiguous":
        return False
    return any(marker in text for marker in ("?", "？", "确认", "网页", "浏览器", "桌面", "本机", "客户端"))


def _compact_attempt_result(result: dict[str, Any], *, attempt_index: int) -> dict[str, Any]:
    cases = result.get("cases") if isinstance(result.get("cases"), list) else []
    return {
        "attempt": attempt_index,
        "ok": bool(result.get("ok")),
        "case_count": result.get("case_count"),
        "failed_cases": [
            str(case.get("name"))
            for case in cases
            if isinstance(case, dict) and case.get("passed") is False
        ],
        "error_type": result.get("error_type"),
        "error": str(result.get("error") or "")[:500],
    }


def _first_case_error(case_results: list[dict[str, Any]], key: str) -> str:
    for case_result in case_results:
        if not isinstance(case_result, dict):
            continue
        value = case_result.get(key)
        if value:
            return str(value)
    return ""
