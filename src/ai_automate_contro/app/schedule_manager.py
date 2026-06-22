from __future__ import annotations

import json
import time
from datetime import UTC, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ai_automate_contro.app.command_helpers import run_plan
from ai_automate_contro.plans.validator import validate_plan_file
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


SCHEDULES_FILE_NAME = "schedules.json"
SCHEDULE_STATE_PATH = Path(".keygen") / "schedules-state.json"
SUPPORTED_TRIGGER_TYPES = {"daily", "interval"}
SUPPORTED_CONCURRENCY = {"skip"}


def list_schedules(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    config = load_schedule_config(root)
    state = load_schedule_state(root)
    schedules = [
        _schedule_public_summary(root, schedule, state.get(str(schedule.get("id")), {}))
        for schedule in config["schedules"]
    ]
    return {
        "ok": True,
        "path": str(schedule_config_path(root)),
        "state_path": str(schedule_state_path(root)),
        "schedules": schedules,
    }


def add_schedule(
    project_root: str | Path,
    *,
    schedule_id: str,
    plan_file: str | Path,
    trigger: dict[str, Any],
    schedule_project_root: str | Path | None = None,
    timezone_name: str = "Asia/Shanghai",
    enabled: bool = True,
    concurrency: str = "skip",
    timeout_seconds: int | None = None,
    run_name: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_id = _normalize_schedule_id(schedule_id)
    schedule_root = _resolve_schedule_project_root(root, schedule_project_root)
    resolved_plan_file = _resolve_plan_file(schedule_root, plan_file)
    normalized_trigger = _normalize_trigger(trigger)
    _load_timezone(timezone_name)
    if concurrency not in SUPPORTED_CONCURRENCY:
        raise ValueError(f"concurrency 只支持：{', '.join(sorted(SUPPORTED_CONCURRENCY))}")
    validation = validate_plan_file(resolved_plan_file, schedule_root)
    if not validation.ok:
        first_error = validation.errors[0].format() if validation.errors else str(resolved_plan_file)
        raise ValueError(f"schedule plan 校验失败：{first_error}")

    config = load_schedule_config(root)
    existing_index = _find_schedule_index(config, normalized_id)
    if existing_index is not None and not replace:
        raise ValueError(f"schedule 已存在：{normalized_id}。需要覆盖时使用 --replace。")
    now = _utc_now_text()
    schedule = {
        "id": normalized_id,
        "enabled": enabled,
        "plan_file": str(resolved_plan_file),
        "project_root": str(schedule_root),
        "timezone": timezone_name,
        "trigger": normalized_trigger,
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
        "run_name": run_name or "",
        "created_at": now,
        "updated_at": now,
    }
    if existing_index is None:
        config["schedules"].append(schedule)
    else:
        previous_created_at = config["schedules"][existing_index].get("created_at") or now
        schedule["created_at"] = previous_created_at
        config["schedules"][existing_index] = schedule
    save_schedule_config(root, config)
    return {
        "ok": True,
        "schedule": _schedule_public_summary(root, schedule, load_schedule_state(root).get(normalized_id, {})),
    }


def remove_schedule(project_root: str | Path, schedule_id: str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_id = _normalize_schedule_id(schedule_id)
    config = load_schedule_config(root)
    original_count = len(config["schedules"])
    config["schedules"] = [schedule for schedule in config["schedules"] if schedule.get("id") != normalized_id]
    if len(config["schedules"]) == original_count:
        raise ValueError(f"schedule 不存在：{normalized_id}")
    config_removed = False
    if config["schedules"]:
        save_schedule_config(root, config)
    else:
        config_removed = _remove_file_if_exists(schedule_config_path(root))
    state = load_schedule_state(root)
    remaining_ids = {str(schedule.get("id") or "") for schedule in config["schedules"]}
    state = {state_id: value for state_id, value in state.items() if state_id in remaining_ids}
    state_removed = False
    if state:
        save_schedule_state(root, state)
    else:
        state_removed = _remove_file_if_exists(schedule_state_path(root))
    return {
        "ok": True,
        "id": normalized_id,
        "removed": True,
        "config_removed": config_removed,
        "state_removed": state_removed,
    }


def set_schedule_enabled(project_root: str | Path, schedule_id: str, enabled: bool) -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_id = _normalize_schedule_id(schedule_id)
    config = load_schedule_config(root)
    schedule = _require_schedule(config, normalized_id)
    schedule["enabled"] = enabled
    schedule["updated_at"] = _utc_now_text()
    save_schedule_config(root, config)
    return {
        "ok": True,
        "schedule": _schedule_public_summary(root, schedule, load_schedule_state(root).get(normalized_id, {})),
    }


def run_schedule_now(project_root: str | Path, schedule_id: str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_id = _normalize_schedule_id(schedule_id)
    config = load_schedule_config(root)
    schedule = _require_schedule(config, normalized_id)
    state = load_schedule_state(root)
    result = _run_schedule_entry(root, schedule, state, reason="run-now")
    save_schedule_state(root, state)
    return result


def run_due_schedules(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    config = load_schedule_config(root)
    state = load_schedule_state(root)
    results: list[dict[str, Any]] = []
    for schedule in config["schedules"]:
        schedule_id = str(schedule.get("id") or "")
        schedule_state = state.get(schedule_id, {})
        if not schedule.get("enabled", True):
            results.append({"id": schedule_id, "due": False, "skipped": True, "reason": "disabled"})
            continue
        due_at = compute_next_run_at(schedule, schedule_state)
        now = _now_in_timezone(str(schedule.get("timezone") or "Asia/Shanghai"))
        if due_at is None or due_at > now:
            results.append(
                {
                    "id": schedule_id,
                    "due": False,
                    "next_run_at": due_at.isoformat(timespec="seconds") if due_at else "",
                }
            )
            continue
        results.append(_run_schedule_entry(root, schedule, state, reason="due"))
    save_schedule_state(root, state)
    return {"ok": True, "ran": [result for result in results if result.get("ran")], "results": results}


def run_schedule_daemon(project_root: str | Path, *, poll_seconds: float = 60.0, once: bool = False) -> dict[str, Any]:
    if poll_seconds <= 0:
        raise ValueError("poll_seconds 必须大于 0。")
    iterations = 0
    last_result: dict[str, Any] = {"ok": True, "results": []}
    while True:
        iterations += 1
        last_result = run_due_schedules(project_root)
        if once:
            return {"ok": True, "iterations": iterations, "last_result": last_result}
        time.sleep(poll_seconds)


def compute_next_run_at(schedule: dict[str, Any], state: dict[str, Any]) -> datetime | None:
    timezone_name = str(schedule.get("timezone") or "Asia/Shanghai")
    tz = _load_timezone(timezone_name)
    trigger = schedule.get("trigger", {})
    if not isinstance(trigger, dict):
        return None
    trigger_type = trigger.get("type")
    if trigger_type == "interval":
        every_seconds = float(trigger.get("every_seconds", 0))
        if every_seconds <= 0:
            return None
        last_started = _parse_utc_datetime(state.get("last_started_at"))
        if last_started is None:
            created = _parse_utc_datetime(schedule.get("created_at")) or datetime.now(UTC)
            if bool(trigger.get("run_immediately", False)):
                return created.astimezone(tz)
            return (created + timedelta(seconds=every_seconds)).astimezone(tz)
        return (last_started + timedelta(seconds=every_seconds)).astimezone(tz)
    if trigger_type == "daily":
        at_text = str(trigger.get("at") or "")
        hour, minute = _parse_daily_at(at_text)
        now = _now_in_timezone(timezone_name)
        scheduled_today = datetime.combine(now.date(), datetime_time(hour=hour, minute=minute), tzinfo=tz)
        last_started_local = (_parse_utc_datetime(state.get("last_started_at")) or datetime.min.replace(tzinfo=UTC)).astimezone(tz)
        if now <= scheduled_today and last_started_local < scheduled_today:
            return scheduled_today
        if last_started_local < scheduled_today <= now:
            return scheduled_today
        return scheduled_today + timedelta(days=1)
    return None


def load_schedule_config(project_root: str | Path) -> dict[str, Any]:
    path = schedule_config_path(project_root)
    if not path.exists():
        return {"version": 1, "schedules": []}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"{SCHEDULES_FILE_NAME} 必须是 JSON 对象。")
    schedules = payload.get("schedules", [])
    if not isinstance(schedules, list):
        raise ValueError("schedules.json 的 schedules 必须是数组。")
    return {"version": int(payload.get("version", 1)), "schedules": schedules}


def save_schedule_config(project_root: str | Path, config: dict[str, Any]) -> None:
    path = schedule_config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        "version": int(config.get("version", 1)),
        "schedules": sorted(config.get("schedules", []), key=lambda item: str(item.get("id", ""))),
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_schedule_state(project_root: str | Path) -> dict[str, Any]:
    path = schedule_state_path(project_root)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(".keygen/schedules-state.json 必须是 JSON 对象。")
    return payload


def save_schedule_state(project_root: str | Path, state: dict[str, Any]) -> None:
    path = schedule_state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")


def schedule_config_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / SCHEDULES_FILE_NAME


def schedule_state_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / SCHEDULE_STATE_PATH


def _remove_file_if_exists(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _run_schedule_entry(
    default_project_root: Path,
    schedule: dict[str, Any],
    state: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    schedule_id = str(schedule.get("id") or "")
    schedule_state = dict(state.get(schedule_id, {}))
    schedule_root = _resolve_schedule_project_root(default_project_root, schedule.get("project_root"))
    plan_file = _resolve_plan_file(schedule_root, schedule.get("plan_file", ""))
    timeout_seconds = schedule.get("timeout_seconds")
    deadline = time.monotonic() + float(timeout_seconds) if timeout_seconds not in (None, "") else None

    validation = validate_plan_file(plan_file, schedule_root)
    started_at = _utc_now_text()
    schedule_state.update(
        {
            "last_started_at": started_at,
            "last_status": "running",
            "last_reason": reason,
            "last_error": "",
            "last_output_dir": "",
        }
    )
    state[schedule_id] = schedule_state
    save_schedule_state(default_project_root, state)

    if not validation.ok:
        error = validation.errors[0].format() if validation.errors else "plan 校验失败"
        schedule_state.update(
            {
                "last_finished_at": _utc_now_text(),
                "last_status": "failed",
                "last_error": error,
                "next_run_at": _next_run_text(schedule, schedule_state),
            }
        )
        state[schedule_id] = schedule_state
        return {"ok": False, "ran": False, "id": schedule_id, "error": error}

    def interrupt_checker() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    try:
        result = run_plan(
            plan_file,
            schedule_root,
            run_name=str(schedule.get("run_name") or schedule_id),
            variable_overrides={},
            interrupt_checker=interrupt_checker if deadline is not None else None,
        )
    except Exception as error:
        schedule_state.update(
            {
                "last_finished_at": _utc_now_text(),
                "last_status": "failed",
                "last_error": str(error),
                "next_run_at": _next_run_text(schedule, schedule_state),
            }
        )
        state[schedule_id] = schedule_state
        return {"ok": False, "ran": True, "id": schedule_id, "error": str(error)}

    schedule_state.update(
        {
            "last_finished_at": _utc_now_text(),
            "last_status": result.status,
            "last_error": result.error or "",
            "last_output_dir": result.output_dir,
            "next_run_at": _next_run_text(schedule, schedule_state),
        }
    )
    state[schedule_id] = schedule_state
    return {
        "ok": result.status == "passed",
        "ran": True,
        "id": schedule_id,
        "status": result.status,
        "output_dir": result.output_dir,
        "error": result.error,
    }


def _schedule_public_summary(root: Path, schedule: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    next_run_at = compute_next_run_at(schedule, state)
    return {
        "id": schedule.get("id"),
        "enabled": bool(schedule.get("enabled", True)),
        "plan_file": schedule.get("plan_file"),
        "project_root": schedule.get("project_root") or str(root),
        "timezone": schedule.get("timezone") or "Asia/Shanghai",
        "trigger": schedule.get("trigger", {}),
        "concurrency": schedule.get("concurrency", "skip"),
        "timeout_seconds": schedule.get("timeout_seconds"),
        "run_name": schedule.get("run_name") or "",
        "next_run_at": next_run_at.isoformat(timespec="seconds") if next_run_at else "",
        "state": state,
    }


def _next_run_text(schedule: dict[str, Any], state: dict[str, Any]) -> str:
    next_run = compute_next_run_at(schedule, state)
    return next_run.isoformat(timespec="seconds") if next_run else ""


def _find_schedule_index(config: dict[str, Any], schedule_id: str) -> int | None:
    for index, schedule in enumerate(config["schedules"]):
        if schedule.get("id") == schedule_id:
            return index
    return None


def _require_schedule(config: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    index = _find_schedule_index(config, schedule_id)
    if index is None:
        raise ValueError(f"schedule 不存在：{schedule_id}")
    return config["schedules"][index]


def _normalize_schedule_id(schedule_id: str) -> str:
    normalized = str(schedule_id or "").strip()
    if not normalized:
        raise ValueError("schedule id 不能为空。")
    if any(char.isspace() for char in normalized):
        raise ValueError("schedule id 不能包含空白字符。")
    return normalized


def _normalize_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(trigger, dict):
        raise ValueError("trigger 必须是对象。")
    trigger_type = trigger.get("type")
    if trigger_type not in SUPPORTED_TRIGGER_TYPES:
        raise ValueError(f"schedule trigger.type 只支持：{', '.join(sorted(SUPPORTED_TRIGGER_TYPES))}")
    if trigger_type == "daily":
        at_text = str(trigger.get("at") or "")
        _parse_daily_at(at_text)
        return {"type": "daily", "at": at_text}
    every_seconds = float(trigger.get("every_seconds", 0))
    if every_seconds <= 0:
        raise ValueError("interval schedule.every_seconds 必须大于 0。")
    return {
        "type": "interval",
        "every_seconds": every_seconds,
        "run_immediately": bool(trigger.get("run_immediately", False)),
    }


def _resolve_schedule_project_root(default_root: Path, raw_root: str | Path | None) -> Path:
    if raw_root in (None, ""):
        return default_root.resolve()
    raw_path = path_from_text(raw_root)
    if is_absolute_path_text(raw_root):
        return raw_path.resolve()
    return (default_root / raw_path).resolve()


def _resolve_plan_file(project_root: Path, raw_plan_file: str | Path) -> Path:
    raw_path = path_from_text(raw_plan_file)
    if is_absolute_path_text(raw_plan_file):
        path = raw_path.resolve()
    else:
        path = (project_root / raw_path).resolve()
    if path.is_dir():
        path = path / "plan.json"
    return path


def _load_timezone(timezone_name: str) -> Any:
    if timezone_name in {"UTC", "Etc/UTC"}:
        return UTC
    if timezone_name in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "Asia/Urumqi"}:
        return timezone(timedelta(hours=8), timezone_name)
    try:
        return ZoneInfo(timezone_name)
    except Exception as error:
        raise ValueError(f"不支持的 timezone：{timezone_name}") from error


def _now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(_load_timezone(timezone_name))


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_daily_at(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("daily trigger.at 必须是 HH:MM。")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as error:
        raise ValueError("daily trigger.at 必须是 HH:MM。") from error
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("daily trigger.at 必须是 00:00 到 23:59。")
    return hour, minute
