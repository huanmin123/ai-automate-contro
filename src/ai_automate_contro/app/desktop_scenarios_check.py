from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.scenarios import (
    DEFAULT_SCENARIO_LIMITS,
    DesktopScenario,
    desktop_scenario_event_names,
    record_desktop_scenario_event,
    run_desktop_scenario,
)


def self_check_desktop_scenarios(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    scenarios = [_game_daily_scenario(), _wechat_blessing_scenario(), _qq_schedule_scenario()]
    results = [run_desktop_scenario(scenario) for scenario in scenarios]
    return {
        "ok": all(bool(result.get("ok")) for result in results),
        "check": "desktop_scenarios",
        "project_root": str(root),
        "limits": dict(DEFAULT_SCENARIO_LIMITS),
        "scenario_count": len(results),
        "scenarios": results,
        "checks": [
            {
                "name": result["name"],
                "ok": bool(result.get("ok")),
                "summary": result.get("summary", {}),
            }
            for result in results
        ],
        "commands": {
            "run": "python .\\cplan.py self-check desktop-scenarios",
            "release_matrix": "python .\\cplan.py self-check release-matrix --only desktop_scenarios",
        },
    }


def _game_daily_scenario() -> DesktopScenario:
    return DesktopScenario(
        name="mock_game_daily",
        intent=[
            "open target game window",
            "claim daily reward",
            "run one dungeon",
            "recover from covered window and repeated battle observation",
            "verify reward collection",
        ],
        initial_state={
            "app": "MockGame",
            "app_open": True,
            "window_state": "covered",
            "surface": "home",
            "reward_claimed": False,
            "target_dungeon_runs": 1,
            "dungeon_runs": 0,
            "battle_progress": 0,
            "sent_messages": {},
        },
        decide=_decide_game_daily,
        apply_action=_apply_game_daily,
        goal_reached=lambda state: state.get("surface") == "done",
        assertions=_assert_game_daily,
        recover_repeated_observation=_recover_game_repeated_observation,
    )


def _decide_game_daily(observation: dict[str, Any], state: dict[str, Any], context: dict[str, Any]) -> str:
    surface = str(observation.get("surface") or "")
    if not observation.get("app_open"):
        return "launch_game"
    if surface == "home" and not state.get("reward_claimed"):
        return "claim_daily_reward"
    if surface == "home" and int(state.get("dungeon_runs", 0) or 0) < int(state.get("target_dungeon_runs", 1) or 1):
        return "enter_dungeon"
    if surface == "dungeon_lobby":
        return "start_dungeon"
    if surface == "battle":
        return "press_skill_rotation"
    if surface == "reward":
        return "collect_dungeon_reward"
    return "noop"


def _apply_game_daily(state: dict[str, Any], action: str, context: dict[str, Any]) -> None:
    if action == "launch_game":
        state.update({"app_open": True, "window_state": "active", "surface": "home"})
        record_desktop_scenario_event(context, "game_launched")
        return
    if action == "claim_daily_reward":
        state["reward_claimed"] = True
        state["popup"] = "daily_reward_confirm"
        record_desktop_scenario_event(context, "daily_reward_claimed")
        return
    if action == "enter_dungeon":
        state["surface"] = "dungeon_lobby"
        record_desktop_scenario_event(context, "dungeon_entered")
        return
    if action == "start_dungeon":
        state["surface"] = "battle"
        state["battle_progress"] = 0
        record_desktop_scenario_event(context, "battle_started")
        return
    if action == "press_skill_rotation":
        progress = int(state.get("battle_progress", 0) or 0)
        if progress == 1 and not state.get("game_stuck_recovered"):
            record_desktop_scenario_event(context, "battle_no_progress", {"battle_progress": progress})
            return
        progress += 1
        state["battle_progress"] = progress
        record_desktop_scenario_event(context, "battle_progressed", {"battle_progress": progress})
        if progress >= 3:
            state["surface"] = "reward"
        return
    if action == "collect_dungeon_reward":
        state["dungeon_runs"] = int(state.get("dungeon_runs", 0) or 0) + 1
        state["surface"] = "done"
        record_desktop_scenario_event(context, "dungeon_reward_collected")
        return
    context["errors"].append({"type": "unknown_game_action", "action": action})


def _assert_game_daily(state: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    events = desktop_scenario_event_names(context)
    return [
        {"name": "daily_reward_claimed", "ok": bool(state.get("reward_claimed"))},
        {"name": "dungeon_run_completed", "ok": int(state.get("dungeon_runs", 0) or 0) == 1},
        {"name": "covered_window_recovered", "ok": "window_refocused" in events},
        {"name": "blocking_popup_closed", "ok": "popup_closed" in events},
        {"name": "battle_stuck_recovered", "ok": "repeated_observation_unstuck" in events},
        {"name": "bounded_runtime", "ok": len(context["trace"]) < int(context["limits"]["max_steps"])},
    ]


def _recover_game_repeated_observation(state: dict[str, Any], _context: dict[str, Any]) -> None:
    if state.get("surface") == "battle":
        state["battle_progress"] = max(int(state.get("battle_progress", 0) or 0), 2)
        state["game_stuck_recovered"] = True


def _wechat_blessing_scenario() -> DesktopScenario:
    return DesktopScenario(
        name="mock_wechat_blessing",
        intent=[
            "restore chat app",
            "close transient popup",
            "send prepared text to two contacts",
            "verify recipient before each send",
            "avoid duplicate or wrong-recipient messages",
        ],
        initial_state={
            "app": "MockWeChat",
            "app_open": True,
            "window_state": "minimized",
            "surface": "chat_list",
            "popup": "update_prompt",
            "contacts": ["Alice", "Bob"],
            "message": "daily blessing",
            "active_target": "",
            "draft": "",
            "sent_messages": {},
            "pre_send_checks": 0,
            "wrong_recipient_count": 0,
        },
        decide=_decide_wechat_blessing,
        apply_action=_apply_wechat_blessing,
        goal_reached=lambda state: len(state.get("sent_messages", {}) or {}) == len(state.get("contacts", []) or []),
        assertions=_assert_wechat_blessing,
    )


def _decide_wechat_blessing(observation: dict[str, Any], state: dict[str, Any], context: dict[str, Any]) -> str:
    target = _next_unsent_target(state)
    if not target:
        return "noop"
    if observation.get("active_target") != target:
        return "search_next_contact"
    if not observation.get("draft_ready"):
        return "fill_chat_draft"
    return "verify_recipient_and_send"


def _apply_wechat_blessing(state: dict[str, Any], action: str, context: dict[str, Any]) -> None:
    target = _next_unsent_target(state)
    if action == "search_next_contact":
        state["active_target"] = target
        state["surface"] = "chat"
        state["draft"] = ""
        record_desktop_scenario_event(context, "contact_selected", {"target": target})
        return
    if action == "fill_chat_draft":
        state["draft"] = state.get("message", "")
        record_desktop_scenario_event(context, "chat_draft_filled", {"target": state.get("active_target", "")})
        return
    if action == "verify_recipient_and_send":
        state["pre_send_checks"] = int(state.get("pre_send_checks", 0) or 0) + 1
        if state.get("active_target") != target:
            state["wrong_recipient_count"] = int(state.get("wrong_recipient_count", 0) or 0) + 1
            context["errors"].append(
                {
                    "type": "wrong_recipient",
                    "expected": target,
                    "actual": state.get("active_target", ""),
                }
            )
            return
        state.setdefault("sent_messages", {})[target] = state.get("draft", "")
        state["active_target"] = ""
        state["draft"] = ""
        state["surface"] = "chat_list"
        if target == "Alice":
            state["popup"] = "sync_tip"
        record_desktop_scenario_event(context, "message_sent", {"target": target})
        return
    context["errors"].append({"type": "unknown_wechat_action", "action": action})


def _assert_wechat_blessing(state: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    contacts = list(state.get("contacts", []) or [])
    sent = state.get("sent_messages", {}) or {}
    return [
        {"name": "all_contacts_sent", "ok": sorted(sent) == sorted(contacts)},
        {"name": "message_text_preserved", "ok": all(value == state.get("message", "") for value in sent.values())},
        {"name": "recipient_checked_each_send", "ok": int(state.get("pre_send_checks", 0) or 0) == len(contacts)},
        {"name": "no_wrong_recipient", "ok": int(state.get("wrong_recipient_count", 0) or 0) == 0},
        {"name": "minimized_window_restored", "ok": "window_restored" in desktop_scenario_event_names(context)},
        {"name": "popups_closed", "ok": desktop_scenario_event_names(context).count("popup_closed") >= 2},
    ]


def _qq_schedule_scenario() -> DesktopScenario:
    return DesktopScenario(
        name="mock_qq_schedule",
        intent=[
            "wait for scheduled time",
            "launch chat app",
            "recover missing window after launch",
            "send one group message",
            "verify schedule gate and final delivery",
        ],
        initial_state={
            "app": "MockQQ",
            "app_open": False,
            "window_state": "missing",
            "surface": "",
            "schedule_due": False,
            "group": "FamilyGroup",
            "message": "scheduled greeting",
            "active_target": "",
            "draft": "",
            "sent_messages": {},
        },
        decide=_decide_qq_schedule,
        apply_action=_apply_qq_schedule,
        goal_reached=lambda state: state.get("surface") == "done",
        assertions=_assert_qq_schedule,
    )


def _decide_qq_schedule(observation: dict[str, Any], state: dict[str, Any], context: dict[str, Any]) -> str:
    if not observation.get("schedule_due"):
        return "wait_until_schedule_due"
    if not observation.get("app_open"):
        return "launch_qq"
    if observation.get("active_target") != state.get("group"):
        return "search_group"
    if not observation.get("draft_ready"):
        return "fill_group_message"
    return "verify_group_and_send"


def _apply_qq_schedule(state: dict[str, Any], action: str, context: dict[str, Any]) -> None:
    if action == "wait_until_schedule_due":
        state["schedule_due"] = True
        record_desktop_scenario_event(context, "schedule_gate_passed")
        return
    if action == "launch_qq":
        state["app_open"] = True
        state["window_state"] = "missing"
        state["surface"] = "chat_list"
        record_desktop_scenario_event(context, "qq_launched_waiting_window")
        return
    if action == "search_group":
        state["active_target"] = state.get("group", "")
        state["surface"] = "group_chat"
        record_desktop_scenario_event(context, "group_selected", {"target": state.get("group", "")})
        return
    if action == "fill_group_message":
        state["draft"] = state.get("message", "")
        record_desktop_scenario_event(context, "group_draft_filled")
        return
    if action == "verify_group_and_send":
        target = state.get("group", "")
        if state.get("active_target") != target:
            context["errors"].append(
                {
                    "type": "wrong_group",
                    "expected": target,
                    "actual": state.get("active_target", ""),
                }
            )
            return
        state.setdefault("sent_messages", {})[target] = state.get("draft", "")
        state["draft"] = ""
        state["surface"] = "done"
        record_desktop_scenario_event(context, "message_sent", {"target": target})
        return
    context["errors"].append({"type": "unknown_qq_action", "action": action})


def _assert_qq_schedule(state: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    sent = state.get("sent_messages", {}) or {}
    target = state.get("group", "")
    events = desktop_scenario_event_names(context)
    return [
        {"name": "schedule_gate_checked", "ok": "schedule_gate_passed" in events},
        {"name": "missing_window_recovered", "ok": "window_visible_after_relaunch" in events},
        {"name": "group_message_sent", "ok": sent.get(target) == state.get("message", "")},
        {"name": "single_delivery", "ok": len(sent) == 1},
        {"name": "bounded_runtime", "ok": len(context["trace"]) < int(context["limits"]["max_steps"])},
    ]


def _next_unsent_target(state: dict[str, Any]) -> str:
    sent = state.get("sent_messages", {}) or {}
    for target in state.get("contacts", []) or []:
        if target not in sent:
            return str(target)
    return ""
