from __future__ import annotations

import json
import os
import platform
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ai_automate_contro.ai.terminal import AITerminal


DEFAULT_REAL_DESKTOP_LOOP_MODEL = "gpt-5.5"
DEFAULT_REAL_DESKTOP_LOOP_BASE_URL = "https://vsllm.com/v1"
DEFAULT_REAL_DESKTOP_LOOP_API_KEY_ENV = "AIC_TEST_API_KEY"
DEFAULT_REAL_DESKTOP_LOOP_MAX_ATTEMPTS = 5
DEFAULT_REAL_DESKTOP_LOOP_RETRY_DELAY_SECONDS = 3.0
DEFAULT_REAL_DESKTOP_LOOP_REQUEST_MAX_RETRIES = 2
_SECRET_FILE_API_KEY_ENV = "AIC_REAL_DESKTOP_LOOP_API_KEY"
_URL_RE = re.compile(r"https?://[^\s\"']+")
_API_KEY_RE = re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]+")
_TRANSIENT_ERROR_MARKERS = (
    "connection",
    "connecterror",
    "connectionerror",
    "apiconnectionerror",
    "timeout",
    "timed out",
    "readtimeout",
    "server disconnected",
    "temporarily unavailable",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "502",
    "503",
    "504",
)


def self_check_real_ai_desktop_loop(
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
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        return {
            "ok": True,
            "check": "real_ai_desktop_loop",
            "skipped": True,
            "reason": f"real desktop loop only runs on Windows/macOS, current={system}",
            "project_root": str(resolved_project_root),
        }

    secret = _resolve_secret(api_key_file=api_key_file, api_key_env=api_key_env, base_url=base_url)
    if not secret.get("ok"):
        return {
            "ok": bool(secret.get("skipped")),
            "check": "real_ai_desktop_loop",
            "skipped": bool(secret.get("skipped")),
            "reason": secret.get("reason", ""),
            "error": secret.get("error", ""),
            "project_root": str(resolved_project_root),
        }

    resolved_thread_id = thread_id.strip() or f"ai-real-desktop-loop-{uuid.uuid4().hex[:12]}"
    resolved_model = str(model or DEFAULT_REAL_DESKTOP_LOOP_MODEL).strip()
    resolved_base_url = str(secret.get("base_url") or base_url or DEFAULT_REAL_DESKTOP_LOOP_BASE_URL).strip()
    resolved_api_key_env = str(secret["api_key_env"])
    timeout = max(30, int(timeout_seconds or 180))
    attempts_limit = max(1, int(max_attempts or 1))
    retry_delay = max(0.0, float(retry_delay_seconds or 0.0))
    attempts: list[dict[str, Any]] = []

    with _temporary_env(resolved_api_key_env, str(secret["api_key"])):
        for attempt_index in range(1, attempts_limit + 1):
            attempt_thread_id = (
                resolved_thread_id if attempts_limit == 1 else f"{resolved_thread_id}-attempt-{attempt_index}"
            )
            with tempfile.TemporaryDirectory(prefix="real-ai-desktop-loop-") as raw_temp_dir:
                loop_root = Path(raw_temp_dir).resolve()
                _write_loop_project_config(
                    loop_root,
                    service=service,
                    model=resolved_model,
                    base_url=resolved_base_url,
                    api_key_env=resolved_api_key_env,
                    timeout_seconds=timeout,
                )
                result = _run_real_loop(
                    loop_root,
                    original_project_root=resolved_project_root,
                    service=service,
                    thread_id=attempt_thread_id,
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
        "check": "real_ai_desktop_loop",
        "project_root": str(resolved_project_root),
        "service": service,
        "model": resolved_model,
        "base_url": resolved_base_url,
        "thread_id": resolved_thread_id,
        "attempt_count": attempts_limit,
        "max_attempts": attempts_limit,
        "retry_delay_seconds": retry_delay,
        "attempts": attempts,
        "error": "real desktop loop ended without a result",
    }


def _compact_attempt_result(result: dict[str, Any], *, attempt_index: int) -> dict[str, Any]:
    compacted: dict[str, Any] = {
        "attempt": attempt_index,
        "ok": bool(result.get("ok")),
        "thread_id": result.get("thread_id"),
        "event_count": result.get("event_count"),
        "tool_sequence": result.get("tool_sequence") if isinstance(result.get("tool_sequence"), list) else [],
        "plan_path": result.get("plan_path"),
        "output_dir": result.get("output_dir"),
        "error_type": result.get("error_type"),
        "error": str(result.get("error") or "")[:500],
    }
    checks = result.get("checks")
    if isinstance(checks, list):
        compacted["failed_checks"] = [
            str(check.get("name") or "")
            for check in checks
            if isinstance(check, dict) and check.get("passed") is False and check.get("name")
        ]
    return {key: value for key, value in compacted.items() if value not in (None, "", [])}


def _should_retry_real_loop(result: dict[str, Any]) -> bool:
    if result.get("ok"):
        return False
    error_text = " ".join(
        str(result.get(key) or "")
        for key in ("error_type", "error", "formatted_error")
        if result.get(key)
    ).lower()
    if not error_text:
        return False
    return any(marker in error_text for marker in _TRANSIENT_ERROR_MARKERS)


def _retry_delay_seconds(base_delay_seconds: float, attempt_index: int) -> float:
    if base_delay_seconds <= 0:
        return 0.0
    return min(float(base_delay_seconds) * max(1, attempt_index), 30.0)


def _run_real_loop(
    project_root: Path,
    *,
    original_project_root: Path,
    service: str,
    thread_id: str,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    terminal: AITerminal | None = None
    try:
        terminal = AITerminal(project_root, service=service, thread_id=thread_id)
        result = terminal.ask_once(_real_loop_prompt(), event_sink=lambda event: events.append(_compact_event(event)))
        tool_sequence = _tool_sequence(events)
        tool_results = _latest_tool_results(events)
        run_result = tool_results.get("run_plan", {})
        context_state = result.get("context_state") if isinstance(result.get("context_state"), dict) else {}
        plan_path = _context_or_tool_plan_path(context_state, tool_results)
        output_dir = _context_or_tool_output_dir(context_state, run_result)
        evidence = _local_evidence(plan_path, output_dir)
        checks = [
            _check("model_response_ok", bool(result.get("ok")), {"messages": result.get("messages")}),
            _check(
                "required_tool_sequence",
                _ordered_subset(
                    tool_sequence,
                    [
                        "inspect_desktop",
                        "create_plan_package",
                        "write_plan_package_file",
                        "validate_plan",
                        "review_plan_quality",
                        "run_plan",
                    ],
                ),
                {"tool_sequence": tool_sequence},
            ),
            _check(
                "artifact_tools_used",
                any(name in tool_sequence for name in {"list_output_artifacts", "read_output_artifact", "read_latest_run_state"}),
                {"tool_sequence": tool_sequence},
            ),
            _check("run_plan_passed", _run_plan_passed(run_result), {"run_result": _compact_tool_result(run_result)}),
            _check("desktop_plan_written", evidence.get("automation_type") == "desktop", evidence),
            _check("desktop_artifacts_exist", bool(evidence.get("artifacts_ok")), evidence),
        ]
        return {
            "ok": all(check["passed"] for check in checks),
            "check": "real_ai_desktop_loop",
            "project_root": str(original_project_root),
            "runtime_root": "temporary",
            "service": service,
            "model": model,
            "base_url": base_url,
            "thread_id": thread_id,
            "tool_sequence": tool_sequence,
            "event_count": len(events),
            "plan_path": plan_path,
            "output_dir": output_dir,
            "assistant_message": str(result.get("assistant_message") or "")[:2000],
            "checks": checks,
            "commands": {
                "run": "python .\\main.py self-check ai-real-desktop-loop --api-key-file D:\\模型密钥.txt",
                "deterministic": "python .\\main.py self-check ai-desktop-loop",
            },
        }
    except Exception as error:
        formatted = terminal.format_error_message(error) if terminal is not None else str(error)
        return {
            "ok": False,
            "check": "real_ai_desktop_loop",
            "project_root": str(original_project_root),
            "service": service,
            "model": model,
            "base_url": base_url,
            "thread_id": thread_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "formatted_error": formatted,
            "tool_sequence": _tool_sequence(events),
            "event_count": len(events),
        }
    finally:
        if terminal is not None:
            terminal.close()


def _real_loop_prompt() -> str:
    plan = {
        "name": "real ai desktop loop smoke",
        "automation_type": "desktop",
        "variables": {},
        "steps": [
            {
                "action": "open_desktop",
                "name": "desktop",
                "backend": "auto",
                "request_permissions": False,
                "save_as": "desktop_probe",
            },
            {
                "action": "desktop_window",
                "desktop": "desktop",
                "type": "list",
                "path": "windows.json",
                "save_as": "desktop_windows",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "screen.png",
                "save_as": "desktop_screenshot",
            },
            {
                "action": "desktop_assert",
                "desktop": "desktop",
                "type": "screenshot",
                "path": "screen.png",
                "min_bytes": 1,
                "save_as": "desktop_screenshot_assertion",
            },
            {
                "action": "desktop_capture",
                "desktop": "desktop",
                "type": "snapshot",
                "path": "snapshot.json",
                "save_as": "desktop_snapshot",
            },
            {"action": "close_desktop", "desktop": "desktop"},
        ],
    }
    return (
        "这是 ai-automate-contro 的真实模型桌面闭环回归。不要请求人工确认，不要访问网页，不要修改仓库源码。"
        "必须使用工具完成，并按下面顺序执行：\n"
        "1. 调用 update_work_plan，列出 inspect、创建 plan、校验复查、运行、读取产物、总结这几步。\n"
        "2. 调用 inspect_desktop，include_windows=true，include_screenshot=false，request_permissions=false。\n"
        "3. 调用 create_plan_package，package_path='plans/real-ai-desktop-loop-smoke'，automation_type='desktop'。\n"
        "4. 调用 write_plan_package_file 写入 plan.json，JSON 必须完全使用下面这个 desktop plan：\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n"
        "5. 调用 validate_plan；如果失败就修正后重试。\n"
        "6. 调用 review_plan_quality，user_request='只读探测本机桌面窗口并保存截图和 snapshot 证据'，"
        "evidence_summary 必须引用 inspect_desktop 的平台、backend、capability_matrix 和窗口数量。\n"
        "7. 质量复查通过后调用 run_plan，run_name='real-ai-desktop-loop'。\n"
        "8. 调用 read_latest_run_state 或 list_output_artifacts，并读取至少一个 JSON 产物来确认结果。\n"
        "9. 最终只用简短中文总结：是否通过、plan_path、output_dir、关键产物。"
    )


def _write_loop_project_config(
    project_root: Path,
    *,
    service: str,
    model: str,
    base_url: str,
    api_key_env: str,
    timeout_seconds: int,
) -> None:
    (project_root / "plans").mkdir(parents=True, exist_ok=True)
    (project_root / "test-plans").mkdir(parents=True, exist_ok=True)
    (project_root / "handbook").mkdir(parents=True, exist_ok=True)
    (project_root / "plan.config").write_text(
        json.dumps(
            {
                "handbook_path": "handbook",
                "plan_roots": ["plans", "test-plans"],
                "default_ai_config_dir": "plans",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "plans" / "config.json").write_text(
        json.dumps(
            {
                "ai_services": {
                    service: {
                        "provider": "openai-compatible",
                        "api": "chat_completions",
                        "base_url": base_url,
                        "model": model,
                        "timeout_seconds": timeout_seconds,
                        "temperature": 0.2,
                        "max_retries": DEFAULT_REAL_DESKTOP_LOOP_REQUEST_MAX_RETRIES,
                        "api_key_env": api_key_env,
                        "graph_recursion_limit": 96,
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _resolve_secret(*, api_key_file: str, api_key_env: str, base_url: str) -> dict[str, Any]:
    if api_key_file:
        path = Path(api_key_file).expanduser().resolve()
        if not path.exists():
            return {"ok": False, "error": f"api key file not found: {path}"}
        parsed = _parse_secret_file(path)
        if not parsed.get("api_key"):
            return {"ok": False, "error": f"api key file does not contain a usable sk-* key: {path}"}
        return {
            "ok": True,
            "api_key": str(parsed["api_key"]),
            "api_key_env": _SECRET_FILE_API_KEY_ENV,
            "base_url": str(base_url or parsed.get("base_url") or DEFAULT_REAL_DESKTOP_LOOP_BASE_URL),
        }
    env_name = str(api_key_env or DEFAULT_REAL_DESKTOP_LOOP_API_KEY_ENV)
    api_key = os.environ.get(env_name, "")
    if not api_key:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"missing AI api key env: {env_name}",
        }
    return {
        "ok": True,
        "api_key": api_key,
        "api_key_env": env_name,
        "base_url": str(base_url or os.environ.get("AIC_TEST_BASE_URL") or DEFAULT_REAL_DESKTOP_LOOP_BASE_URL),
    }


def _parse_secret_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    parsed: dict[str, str] = {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        for key_name in ("key", "api_key", "OPENAI_API_KEY", "token"):
            raw_key = value.get(key_name)
            if isinstance(raw_key, str) and raw_key.strip():
                parsed["api_key"] = raw_key.strip()
                break
        for url_name in ("url", "base_url", "OPENAI_BASE_URL"):
            raw_url = value.get(url_name)
            if isinstance(raw_url, str) and raw_url.strip():
                parsed["base_url"] = raw_url.strip()
                break
    if "api_key" not in parsed:
        match = _API_KEY_RE.search(text)
        if match:
            parsed["api_key"] = match.group(0)
    if "base_url" not in parsed:
        match = _URL_RE.search(text)
        if match:
            parsed["base_url"] = match.group(0).rstrip(",;")
    return parsed


@contextmanager
def _temporary_env(name: str, value: str) -> Iterator[None]:
    old_present = name in os.environ
    old_value = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old_present and old_value is not None:
            os.environ[name] = old_value
        else:
            os.environ.pop(name, None)


def _compact_event(event: Any) -> dict[str, Any]:
    data = getattr(event, "data", {})
    kind = str(getattr(event, "kind", "") or "")
    result: dict[str, Any] = {
        "kind": kind,
        "title": str(getattr(event, "title", "") or ""),
    }
    if isinstance(data, dict):
        result["tool_name"] = str(data.get("tool_name") or "")
        if kind == "tool_finished":
            result["ok"] = bool(data.get("ok"))
            tool_result = data.get("result") if isinstance(data.get("result"), dict) else {}
            result["result"] = _compact_tool_result(tool_result)
        elif kind == "tool_started":
            result["arguments"] = _compact_arguments(data.get("arguments"))
    return result


def _compact_tool_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    compacted: dict[str, Any] = {
        "ok": result.get("ok"),
        "error": str(result.get("error") or "")[:500],
        "plan_path": result.get("plan_path"),
        "output_dir": result.get("output_dir"),
    }
    for key in ("summary", "result", "latest_state"):
        value = result.get(key)
        if isinstance(value, dict):
            compacted[key] = {
                "status": value.get("status"),
                "output_dir": value.get("output_dir"),
                "plan_path": value.get("plan_path"),
                "metadata": value.get("metadata") if isinstance(value.get("metadata"), dict) else None,
            }
    return {key: value for key, value in compacted.items() if value not in (None, "", {})}


def _compact_arguments(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    return {
        key: ("<json>" if key == "json_value" else value)
        for key, value in arguments.items()
        if not str(key).startswith("_") and key not in {"api_key", "key", "token"}
    }


def _tool_sequence(events: list[dict[str, Any]]) -> list[str]:
    return [
        str(event.get("tool_name") or "")
        for event in events
        if event.get("kind") == "tool_started" and event.get("tool_name")
    ]


def _latest_tool_results(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("kind") != "tool_finished":
            continue
        name = str(event.get("tool_name") or "")
        result = event.get("result")
        if name and isinstance(result, dict):
            results[name] = result
    return results


def _context_or_tool_plan_path(context_state: dict[str, Any], tool_results: dict[str, dict[str, Any]]) -> str:
    raw = context_state.get("current_plan_path")
    if isinstance(raw, str) and raw:
        return raw
    for tool_name in ("run_plan", "review_plan_quality", "validate_plan", "write_plan_package_file", "create_plan_package"):
        raw = tool_results.get(tool_name, {}).get("plan_path")
        if isinstance(raw, str) and raw:
            return raw
        summary = tool_results.get(tool_name, {}).get("summary")
        if isinstance(summary, dict) and isinstance(summary.get("plan_path"), str):
            return str(summary["plan_path"])
    return ""


def _context_or_tool_output_dir(context_state: dict[str, Any], run_result: dict[str, Any]) -> str:
    raw = context_state.get("latest_output_dir")
    if isinstance(raw, str) and raw:
        return raw
    for key in ("output_dir", "result", "latest_state"):
        value = run_result.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict) and isinstance(value.get("output_dir"), str):
            return str(value["output_dir"])
    return ""


def _local_evidence(plan_path: str, output_dir: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {"plan_path": plan_path, "output_dir": output_dir}
    if plan_path:
        path = Path(plan_path)
        if path.exists():
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                plan = {}
            evidence["automation_type"] = plan.get("automation_type") if isinstance(plan, dict) else ""
            package_dir = path.parent
            expected_artifacts = [
                package_dir / "output" / "desktop-windows" / "windows.json",
                package_dir / "output" / "desktop-screenshots" / "screen.png",
                package_dir / "output" / "desktop-state" / "snapshot.json",
            ]
            evidence["artifacts"] = [
                {"path": str(item), "exists": item.exists(), "size": item.stat().st_size if item.exists() else 0}
                for item in expected_artifacts
            ]
            evidence["artifacts_ok"] = all(item.exists() and item.stat().st_size > 0 for item in expected_artifacts)
    if output_dir:
        result_path = Path(output_dir) / "result.json"
        evidence["result_json_exists"] = result_path.exists()
        if result_path.exists():
            try:
                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                result_payload = {}
            evidence["result_status"] = result_payload.get("status") if isinstance(result_payload, dict) else ""
    return evidence


def _run_plan_passed(run_result: dict[str, Any]) -> bool:
    if run_result.get("ok") is False:
        return False
    for key in ("result", "latest_state"):
        value = run_result.get(key)
        if isinstance(value, dict) and value.get("status") == "passed":
            return True
    return bool(run_result.get("ok"))


def _ordered_subset(sequence: list[str], expected: list[str]) -> bool:
    cursor = 0
    for item in sequence:
        if cursor < len(expected) and item == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def _check(name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed}
    if detail is not None:
        result["detail"] = detail
    return result
