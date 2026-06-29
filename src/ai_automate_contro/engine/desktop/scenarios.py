from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_SCENARIO_LIMITS = {
    "max_steps": 40,
    "max_repeated_observations": 2,
    "max_no_progress_actions": 2,
    "max_recoveries": 8,
    "max_same_action_attempts": 8,
}


@dataclass(frozen=True)
class DesktopScenario:
    name: str
    intent: list[str]
    initial_state: dict[str, Any]
    decide: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], str]
    apply_action: Callable[[dict[str, Any], str, dict[str, Any]], None]
    goal_reached: Callable[[dict[str, Any]], bool]
    assertions: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]]
    recover_repeated_observation: Callable[[dict[str, Any], dict[str, Any]], None] | None = None


def run_desktop_scenario(
    scenario: DesktopScenario,
    *,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = copy.deepcopy(scenario.initial_state)
    context = build_desktop_scenario_context(limits=limits)
    reached = False
    max_steps = int(context["limits"]["max_steps"])
    for step_index in range(1, max_steps + 1):
        observation = desktop_observation_from_state(state)
        repeat_count = record_desktop_scenario_observation(context, observation)
        if repeat_count > int(context["limits"]["max_repeated_observations"]) + 1:
            context["errors"].append(
                {
                    "type": "repeated_observation_limit_exceeded",
                    "repeat_count": repeat_count,
                    "observation": observation,
                }
            )
            break
        if scenario.goal_reached(state):
            reached = True
            context["trace"].append(
                {
                    "step": step_index,
                    "observation": observation,
                    "repeat_count": repeat_count,
                    "action": "complete",
                    "source": "scenario_goal",
                    "state_after": desktop_scenario_state_summary(state),
                }
            )
            break

        guard_action = desktop_scenario_guard_action(state, observation, repeat_count, context)
        action_source = "runtime_guard" if guard_action else "scenario_plan"
        action = guard_action or scenario.decide(observation, state, context)
        if not action or action == "noop":
            context["errors"].append({"type": "no_progress_action", "observation": observation})
            break

        action_count = record_desktop_scenario_action(context, action)
        if action_count > int(context["limits"]["max_same_action_attempts"]):
            context["errors"].append({"type": "same_action_limit_exceeded", "action": action, "count": action_count})
            break

        if action_source == "runtime_guard":
            apply_desktop_scenario_guard_action(state, action, context, scenario=scenario)
        else:
            scenario.apply_action(state, action, context)
        after_observation = desktop_observation_from_state(state)
        no_progress_streak = record_desktop_scenario_progress(context, observation, action, after_observation)

        context["trace"].append(
            {
                "step": step_index,
                "observation": observation,
                "repeat_count": repeat_count,
                "action": action,
                "source": action_source,
                "after_observation": after_observation,
                "no_progress_streak": no_progress_streak,
                "state_after": desktop_scenario_state_summary(state),
            }
        )
        if no_progress_streak > int(context["limits"]["max_no_progress_actions"]):
            context["errors"].append(
                {
                    "type": "no_progress_limit_exceeded",
                    "action": action,
                    "streak": no_progress_streak,
                    "observation": observation,
                    "after_observation": after_observation,
                }
            )
            break
        if total_desktop_scenario_recoveries(context) > int(context["limits"]["max_recoveries"]):
            context["errors"].append(
                {
                    "type": "recovery_limit_exceeded",
                    "guard_counts": dict(context["guard_counts"]),
                }
            )
            break
    else:
        context["errors"].append({"type": "max_steps_exceeded"})

    if not reached and scenario.goal_reached(state):
        reached = True
    assertions = scenario.assertions(state, context)
    assertion_ok = all(bool(item.get("ok")) for item in assertions)
    return {
        "name": scenario.name,
        "ok": reached and assertion_ok and not context["errors"],
        "intent": scenario.intent,
        "goal_reached": reached,
        "assertions": assertions,
        "errors": context["errors"],
        "summary": {
            "steps": len(context["trace"]),
            "events": len(context["events"]),
            "recoveries": total_desktop_scenario_recoveries(context),
            "guard_counts": dict(context["guard_counts"]),
            "max_repeated_observation_seen": context["max_repeated_observation_seen"],
            "max_no_progress_streak": context["max_no_progress_streak"],
            "final_surface": state.get("surface", ""),
        },
        "events": context["events"],
        "final_state": desktop_scenario_state_summary(state),
        "trace": context["trace"],
    }


def build_desktop_scenario_context(*, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    merged_limits = dict(DEFAULT_SCENARIO_LIMITS)
    if limits:
        merged_limits.update(limits)
    return {
        "limits": merged_limits,
        "events": [],
        "trace": [],
        "guard_counts": {},
        "observation_counts": {},
        "action_counts": {},
        "errors": [],
        "max_repeated_observation_seen": 0,
        "no_progress_streak": 0,
        "max_no_progress_streak": 0,
    }


def desktop_observation_from_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "app": state.get("app", ""),
        "app_open": bool(state.get("app_open")),
        "window_state": state.get("window_state", "missing"),
        "surface": state.get("surface", ""),
        "popup": state.get("popup", ""),
        "schedule_due": bool(state.get("schedule_due", True)),
        "active_target": state.get("active_target", ""),
        "draft_ready": bool(state.get("draft", "")),
        "sent_count": len(state.get("sent_messages", {}) or {}),
        "reward_claimed": bool(state.get("reward_claimed", False)),
        "dungeon_runs": int(state.get("dungeon_runs", 0) or 0),
        "battle_progress": int(state.get("battle_progress", 0) or 0),
    }


def record_desktop_scenario_observation(context: dict[str, Any], observation: dict[str, Any]) -> int:
    key = json.dumps(observation, sort_keys=True, ensure_ascii=True)
    counts = context["observation_counts"]
    counts[key] = int(counts.get(key, 0)) + 1
    context["max_repeated_observation_seen"] = max(int(context["max_repeated_observation_seen"]), counts[key])
    return counts[key]


def record_desktop_scenario_action(context: dict[str, Any], action: str) -> int:
    counts = context["action_counts"]
    counts[action] = int(counts.get(action, 0)) + 1
    return counts[action]


def record_desktop_scenario_progress(
    context: dict[str, Any],
    before: dict[str, Any],
    action: str,
    after: dict[str, Any],
) -> int:
    if json.dumps(before, sort_keys=True, ensure_ascii=True) == json.dumps(after, sort_keys=True, ensure_ascii=True):
        context["no_progress_streak"] = int(context.get("no_progress_streak", 0) or 0) + 1
        record_desktop_scenario_event(
            context,
            "no_progress_detected",
            {"action": action, "streak": int(context["no_progress_streak"])},
        )
    else:
        context["no_progress_streak"] = 0
    context["max_no_progress_streak"] = max(
        int(context.get("max_no_progress_streak", 0) or 0),
        int(context["no_progress_streak"]),
    )
    return int(context["no_progress_streak"])


def desktop_scenario_guard_action(
    state: dict[str, Any],
    observation: dict[str, Any],
    repeat_count: int,
    context: dict[str, Any],
) -> str:
    window_state = str(observation.get("window_state") or "missing")
    if state.get("app_open") and window_state == "missing":
        return "runtime_wait_or_relaunch_window"
    if window_state == "minimized":
        return "runtime_restore_target_window"
    if window_state in {"covered", "background"}:
        return "runtime_focus_target_window"
    if observation.get("popup"):
        return "runtime_close_blocking_popup"
    if int(context.get("no_progress_streak", 0) or 0) >= int(context["limits"]["max_no_progress_actions"]):
        return "runtime_unstick_no_progress"
    if repeat_count > int(context["limits"]["max_repeated_observations"]):
        return "runtime_unstick_repeated_observation"
    return ""


def apply_desktop_scenario_guard_action(
    state: dict[str, Any],
    action: str,
    context: dict[str, Any],
    *,
    scenario: DesktopScenario,
) -> None:
    count_desktop_scenario_guard(context, action)
    if action == "runtime_wait_or_relaunch_window":
        state["app_open"] = True
        state["window_state"] = "active"
        record_desktop_scenario_event(context, "window_visible_after_relaunch", {"app": state.get("app", "")})
        return
    if action == "runtime_restore_target_window":
        state["window_state"] = "active"
        record_desktop_scenario_event(context, "window_restored", {"app": state.get("app", "")})
        return
    if action == "runtime_focus_target_window":
        state["window_state"] = "active"
        record_desktop_scenario_event(context, "window_refocused", {"app": state.get("app", "")})
        return
    if action == "runtime_close_blocking_popup":
        popup = state.get("popup", "")
        state["popup"] = ""
        record_desktop_scenario_event(context, "popup_closed", {"popup": popup})
        return
    if action == "runtime_unstick_repeated_observation":
        state["unstick_count"] = int(state.get("unstick_count", 0) or 0) + 1
        if scenario.recover_repeated_observation is not None:
            scenario.recover_repeated_observation(state, context)
        state["window_state"] = "active"
        record_desktop_scenario_event(context, "repeated_observation_unstuck", {"surface": state.get("surface", "")})
        return
    if action == "runtime_unstick_no_progress":
        state["unstick_count"] = int(state.get("unstick_count", 0) or 0) + 1
        if scenario.recover_repeated_observation is not None:
            scenario.recover_repeated_observation(state, context)
        state["window_state"] = "active"
        context["no_progress_streak"] = 0
        record_desktop_scenario_event(context, "no_progress_unstuck", {"surface": state.get("surface", "")})
        return
    context["errors"].append({"type": "unknown_guard_action", "action": action})


def count_desktop_scenario_guard(context: dict[str, Any], action: str) -> None:
    counts = context["guard_counts"]
    counts[action] = int(counts.get(action, 0)) + 1


def total_desktop_scenario_recoveries(context: dict[str, Any]) -> int:
    return sum(int(value) for value in context["guard_counts"].values())


def record_desktop_scenario_event(context: dict[str, Any], name: str, details: dict[str, Any] | None = None) -> None:
    context["events"].append({"name": name, "details": details or {}})


def desktop_scenario_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = [
        "app",
        "app_open",
        "window_state",
        "surface",
        "popup",
        "schedule_due",
        "active_target",
        "draft",
        "sent_messages",
        "reward_claimed",
        "dungeon_runs",
        "battle_progress",
        "unstick_count",
    ]
    return {key: copy.deepcopy(state.get(key)) for key in allowed_keys if key in state}


def desktop_scenario_event_names(context: dict[str, Any]) -> list[str]:
    return [str(item.get("name", "")) for item in context.get("events", []) if isinstance(item, dict)]
