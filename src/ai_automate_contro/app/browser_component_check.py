from __future__ import annotations

import json
import platform
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file


@dataclass(frozen=True)
class BrowserRegressionCase:
    name: str
    plan_path: str
    evidence_check: Callable[[Path, float], list[dict[str, Any]]]


BROWSER_REGRESSION_CASES = (
    BrowserRegressionCase(
        "browser-advanced",
        "test-plans/basic/browser-advanced/plan.json",
        lambda root, started_at: _browser_advanced_evidence(root, started_at),
    ),
    BrowserRegressionCase(
        "browser-parameter-coverage",
        "test-plans/basic/browser-parameter-coverage/plan.json",
        lambda root, started_at: _browser_parameter_coverage_evidence(root, started_at),
    ),
    BrowserRegressionCase(
        "browser-backlog",
        "test-plans/basic/browser-backlog/plan.json",
        lambda root, started_at: _browser_backlog_evidence(root, started_at),
    ),
    BrowserRegressionCase(
        "browser-observability",
        "test-plans/basic/browser-observability/plan.json",
        lambda root, started_at: _browser_observability_evidence(root, started_at),
    ),
)

NEGATIVE_CASES_PATHS = (
    Path("test-plans/regression/browser-validation-negative/resources/negative-cases.json"),
    Path("test-plans/regression/http-command-validation-negative/resources/negative-cases.json"),
)


def self_check_browser_components(project_root: Path) -> dict[str, Any]:
    resolved_root = Path(project_root).resolve()
    positive_cases = [_run_browser_regression_case(resolved_root, regression_case) for regression_case in BROWSER_REGRESSION_CASES]
    negative_cases = _run_negative_validation_cases(resolved_root)
    positive_ok = all(case["ok"] for case in positive_cases)
    negative_ok = all(case["ok"] for case in negative_cases)
    return {
        "ok": positive_ok and negative_ok,
        "checks": [
            {
                "name": "browser_plan_regression_matrix",
                "ok": positive_ok,
                "cases": positive_cases,
            },
            {
                "name": "browser_parameter_negative_validation",
                "ok": negative_ok,
                "cases": negative_cases,
            },
        ],
        "commands": {
            "run": f"python {_cplan_script_path()} self-check browser-components",
            "playwright": "python -m playwright install chromium",
        },
    }


def _run_browser_regression_case(project_root: Path, regression_case: BrowserRegressionCase) -> dict[str, Any]:
    plan_path = project_root / regression_case.plan_path
    validation = validate_plan_file(plan_path, project_root)
    if not validation.ok:
        return {
            "name": regression_case.name,
            "ok": False,
            "plan_path": str(plan_path),
            "validation_ok": False,
            "errors": [error.format() for error in validation.errors],
        }

    try:
        plan = load_plan(plan_path)
        run_started_at = time.time()
        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name=f"browser-components-{regression_case.name}",
            run_context_handler=_disable_run_log_echo,
        )
    except Exception as error:
        return {
            "name": regression_case.name,
            "ok": False,
            "plan_path": str(plan_path),
            "validation_ok": True,
            "run_ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
        }

    try:
        evidence = regression_case.evidence_check(project_root, run_started_at)
    except Exception as error:
        return {
            "name": regression_case.name,
            "ok": False,
            "plan_path": str(plan_path),
            "validation_ok": True,
            "run_ok": result.status == "passed",
            "output_dir": result.output_dir,
            "evidence": [
                {
                    "name": "evidence_read",
                    "ok": False,
                    "error": str(error),
                    "error_type": type(error).__name__,
                }
            ],
        }
    evidence_ok = all(item["ok"] for item in evidence)
    return {
        "name": regression_case.name,
        "ok": result.status == "passed" and evidence_ok,
        "plan_path": str(plan_path),
        "validation_ok": True,
        "run_ok": result.status == "passed",
        "output_dir": result.output_dir,
        "evidence": evidence,
    }


def _disable_run_log_echo(_output_dir: Path, logger: Any) -> None:
    logger.echo = False


def _run_negative_validation_cases(project_root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="browser-validation-negative-") as raw_temp_dir:
        temp_dir = Path(raw_temp_dir)
        for manifest_relative_path in NEGATIVE_CASES_PATHS:
            manifest_path = project_root / manifest_relative_path
            try:
                manifest = _read_json(manifest_path)
                raw_cases = manifest["cases"]
                if not isinstance(raw_cases, list):
                    raise ValueError("negative-cases.json 字段 cases 必须是数组。")
            except Exception as error:
                results.append(
                    {
                        "name": f"negative-case-manifest-{manifest_relative_path.parent.parent.name}",
                        "ok": False,
                        "manifest_path": str(manifest_path),
                        "error": str(error),
                        "error_type": type(error).__name__,
                    }
                )
                continue
            for raw_case in raw_cases:
                results.append(_run_negative_validation_case(project_root, temp_dir, raw_case))
    return results


def _run_negative_validation_case(project_root: Path, temp_dir: Path, raw_case: Any) -> dict[str, Any]:
    if not isinstance(raw_case, dict):
        return {"name": "<invalid>", "ok": False, "error": "case 必须是 JSON 对象。"}
    name = str(raw_case.get("name") or "unnamed")
    expected_message = str(raw_case.get("expected_message") or "")
    plan = raw_case.get("plan")
    if not expected_message or not isinstance(plan, dict):
        return {
            "name": name,
            "ok": False,
            "error": "case 必须包含 expected_message 和 plan 对象。",
        }

    package_dir = temp_dir / name
    package_dir.mkdir(parents=True, exist_ok=True)
    plan_path = package_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = validate_plan_file(plan_path, project_root)
    errors = [error.format() for error in validation.errors]
    matched = any(expected_message in error for error in errors)
    return {
        "name": name,
        "ok": (not validation.ok) and matched,
        "expected_message": expected_message,
        "validation_ok": validation.ok,
        "matched": matched,
        "errors": errors,
    }


def _browser_advanced_evidence(project_root: Path, started_at: float) -> list[dict[str, Any]]:
    summary_path = project_root / "test-plans/basic/browser-advanced/output/json/browser-advanced-summary.json"
    summary = _read_json(summary_path)
    mock_response = summary.get("mock_response", {})
    mock_body = mock_response.get("body", {}) if isinstance(mock_response, dict) else {}
    return [
        _expect("summary_fresh", _file_nonempty_after(summary_path, started_at)),
        _expect("context_text", str(summary.get("context_text", "")).startswith("zh-CN 900x700")),
        _expect("init_script", summary.get("init_script_value") == "ready"),
        _expect("local_storage", summary.get("local_storage_value") == "token-123"),
        _expect("session_storage", summary.get("session_storage_value") == "flag-yes"),
        _expect("mock_response", isinstance(mock_body, dict) and mock_body.get("ok") is True),
        _expect(
            "trace_zip",
            _file_nonempty_after(
                project_root / "test-plans/basic/browser-advanced/output/traces/browser-advanced.zip",
                started_at,
            ),
        ),
        _expect(
            "har_file",
            _file_nonempty_after(
                project_root / "test-plans/basic/browser-advanced/output/har/browser-advanced.har",
                started_at,
            ),
        ),
    ]


def _browser_parameter_coverage_evidence(project_root: Path, started_at: float) -> list[dict[str, Any]]:
    summary_path = project_root / "test-plans/basic/browser-parameter-coverage/output/json/coverage-summary.json"
    summary = _read_json(summary_path)
    cookies = summary.get("cookies", [])
    events = summary.get("events", [])
    first_event = events[0] if isinstance(events, list) and events and isinstance(events[0], dict) else {}
    download_path = str(summary.get("download_path", ""))
    download_file = project_root / "test-plans/basic/browser-parameter-coverage/output/downloads/coverage-download.txt"
    download_text = download_file.read_text(encoding="utf-8") if _file_nonempty(download_file) else ""
    return [
        _expect("summary_fresh", _file_nonempty_after(summary_path, started_at)),
        _expect(
            "cookie_roundtrip",
            isinstance(cookies, list)
            and any(cookie.get("name") == "coverage" for cookie in cookies if isinstance(cookie, dict)),
        ),
        _expect("event_clear_then_console", isinstance(events, list) and len(events) == 1 and first_event.get("type") == "console"),
        _expect(
            "har_file",
            _file_nonempty_after(
                project_root / "test-plans/basic/browser-parameter-coverage/output/har/coverage.har",
                started_at,
            ),
        ),
        _expect(
            "wait_for_download_saved",
            download_path.endswith("coverage-download.txt") and _file_nonempty_after(download_file, started_at),
        ),
        _expect("download_content", download_text == "coverage download ok\n"),
    ]


def _browser_backlog_evidence(project_root: Path, started_at: float) -> list[dict[str, Any]]:
    summary_path = project_root / "test-plans/basic/browser-backlog/output/json/browser-backlog-summary.json"
    summary = _read_json(summary_path)
    coverage_summary = summary.get("coverage_summary", {})
    events = summary.get("events", [])
    event_types = {event.get("type") for event in events if isinstance(event, dict)}
    websocket_frames = [event for event in events if isinstance(event, dict) and event.get("type") == "websocket_frame"]
    eventsource_events = [event for event in events if isinstance(event, dict) and event.get("type") == "eventsource"]
    return [
        _expect("summary_fresh", _file_nonempty_after(summary_path, started_at)),
        _expect("coverage_js", isinstance(coverage_summary, dict) and "js" in coverage_summary),
        _expect("coverage_css", isinstance(coverage_summary, dict) and "css" in coverage_summary),
        _expect("websocket_frame_events", "websocket_frame" in event_types and len(websocket_frames) >= 2),
        _expect("eventsource_events", "eventsource" in event_types and len(eventsource_events) >= 1),
        _expect("aria_snapshot", "Browser Backlog Demo" in str(summary.get("aria_snapshot", ""))),
    ]


def _browser_observability_evidence(project_root: Path, started_at: float) -> list[dict[str, Any]]:
    summary_path = project_root / "test-plans/basic/browser-observability/output/json/browser-observability-summary.json"
    summary = _read_json(summary_path)
    frames = summary.get("frames", [])
    events = summary.get("events", [])
    webrtc_events = [event.get("event") for event in events if isinstance(event, dict) and event.get("type") == "webrtc"]
    serviceworker_events = [
        event.get("event") for event in events if isinstance(event, dict) and event.get("type") == "serviceworker"
    ]
    return [
        _expect("summary_fresh", _file_nonempty_after(summary_path, started_at)),
        _expect("frame_list", isinstance(frames, list) and any(frame.get("name") == "details-frame" for frame in frames if isinstance(frame, dict))),
        _expect("webrtc_offer", "createOffer:done" in webrtc_events),
        _expect("webrtc_close", "close" in webrtc_events),
        _expect("serviceworker_created", "created" in serviceworker_events),
        _expect("serviceworker_registered", "register:done" in serviceworker_events),
    ]


def _read_project_json(project_root: Path, relative_path: str) -> Any:
    return _read_json(project_root / relative_path)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _file_nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _file_nonempty_after(path: Path, started_at: float) -> bool:
    return _file_nonempty(path) and path.stat().st_mtime >= started_at - 1.0


def _expect(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok)}


def _cplan_script_path() -> str:
    return ".\\cplan.py" if platform.system() == "Windows" else "./cplan.py"
