from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

from ai_automate_contro.app.errors import UserFacingError
from ai_automate_contro.app.parser import build_cplan_parser, build_parser
from ai_automate_contro.client.commands import all_client_commands


def self_check_cli_boundaries() -> dict[str, Any]:
    main_commands = _subcommands(build_parser())
    main_self_check_commands = _subcommands_for(build_parser(), "self-check")
    cplan_commands = _subcommands(build_cplan_parser())
    cplan_self_check_commands = _subcommands_for(build_cplan_parser(), "self-check")
    textual_commands = {command.name for command in all_client_commands()}
    manual_confirm_check = _check_cplan_manual_confirm_closed_loop()
    manual_confirm_headed_check = _check_manual_confirm_requires_visible_browser()
    debug_patch_delete_check = _check_debug_patch_deletion_backup()
    debug_patch_forbidden_check = _check_debug_patch_rejects_forbidden_paths()
    output_dir_check = _check_cplan_output_dir_package_scope()
    trigger_parent_action_check = _check_cplan_trigger_parent_action()
    schedule_management_check = _check_cplan_schedule_management()
    cplan_debug_prepare_boundary_check = _check_cplan_debug_prepare_uses_neutral_debug_core()
    cplan_error_boundary_check = _check_cplan_error_fix_does_not_reference_ai_side()

    main_forbidden = {
        "cplan",
        "plan",
        "list",
        "create",
        "validate",
        "run",
        "debug-create",
        "debug-prepare",
        "debug-inject",
        "debug-patch",
        "debug-apply",
        "schedule",
    }
    cplan_required = {
        "list",
        "create",
        "validate",
        "run",
        "debug-create",
        "debug-prepare",
        "debug-inject",
        "debug-patch",
        "debug-apply",
        "schedule",
        "self-check",
    }
    cplan_forbidden = {"ai", "tool"}
    textual_forbidden = {"list", "use", "run", "continue", "close", "stop", "validate", "debug"}

    checks = [
        {
            "name": "main_cli_has_only_ai_commands",
            "passed": main_commands == {"tool", "ai", "self-check"},
            "detail": {"commands": sorted(main_commands)},
        },
        {
            "name": "main_cli_rejects_plan_control_commands",
            "passed": main_forbidden.isdisjoint(main_commands)
            and _parse_rejected(build_parser(), ["plan", "validate"])
            and _parse_rejected(build_parser(), ["cplan", "validate"]),
            "detail": {"forbidden": sorted(main_forbidden & main_commands)},
        },
        {
            "name": "cplan_cli_has_plan_control_commands",
            "passed": cplan_required.issubset(cplan_commands),
            "detail": {"missing": sorted(cplan_required - cplan_commands), "commands": sorted(cplan_commands)},
        },
        {
            "name": "cplan_cli_rejects_ai_commands",
            "passed": cplan_forbidden.isdisjoint(cplan_commands)
            and _parse_rejected(build_cplan_parser(), ["ai"])
            and _parse_rejected(build_cplan_parser(), ["tool", "check"]),
            "detail": {"forbidden": sorted(cplan_forbidden & cplan_commands)},
        },
        {
            "name": "textual_client_has_no_plan_control_commands",
            "passed": textual_forbidden.isdisjoint(textual_commands),
            "detail": {"forbidden": sorted(textual_forbidden & textual_commands), "commands": sorted(textual_commands)},
        },
        {
            "name": "cplan_validate_parses_without_main_cli",
            "passed": _parse_accepted(build_cplan_parser(), ["validate", "--file", "plans/demo/plan.json"]),
            "detail": {},
        },
        {
            "name": "cplan_self_check_has_component_and_real_app_entries",
            "passed": {
                "handbook",
                "workspace-clean",
                "release-matrix",
                "browser-components",
                "data-components",
                "database-components",
                "desktop-env",
                "desktop-components",
                "desktop-examples",
                "desktop-scenarios",
                "desktop-scenario-apps",
                "desktop-real-app",
            }.issubset(
                cplan_self_check_commands
            )
            and _parse_accepted(
                build_cplan_parser(),
                [
                    "self-check",
                    "release-matrix",
                    "--only",
                    "compileall",
                    "--repeat",
                    "2",
                    "--fail-fast",
                    "--strict-desktop",
                ],
            ),
            "detail": {"commands": sorted(cplan_self_check_commands)},
        },
        {
            "name": "main_self_check_has_ai_plan_generation_simulation",
            "passed": {
                "ai-terminal",
                "ai-tools",
                "ai-plan-generation",
                "ai-desktop-loop",
                "ai-real-desktop-loop",
                "ai-real-execution-line",
            }.issubset(main_self_check_commands),
            "detail": {"commands": sorted(main_self_check_commands)},
        },
        {
            "name": "cplan_create_requires_automation_type",
            "passed": _parse_rejected(build_cplan_parser(), ["create", "--path", "plans/demo"])
            and _parse_accepted(
                build_cplan_parser(),
                ["create", "--path", "plans/demo", "--automation-type", "browser"],
            )
            and _parse_accepted(
                build_cplan_parser(),
                ["create", "--path", "plans/demo", "--automation-type", "desktop"],
            ),
            "detail": {},
        },
        manual_confirm_check,
        manual_confirm_headed_check,
        debug_patch_delete_check,
        debug_patch_forbidden_check,
        output_dir_check,
        trigger_parent_action_check,
        schedule_management_check,
        cplan_debug_prepare_boundary_check,
        cplan_error_boundary_check,
    ]
    return {
        "ok": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }


def _subcommands(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def _subcommands_for(parser: argparse.ArgumentParser, command: str) -> set[str]:
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        subparser = action.choices.get(command)
        if subparser is None:
            return set()
        return _subcommands(subparser)
    return set()


def _parse_accepted(parser: argparse.ArgumentParser, argv: list[str]) -> bool:
    try:
        parser.parse_args(argv)
    except (SystemExit, UserFacingError):
        return False
    return True


def _parse_rejected(parser: argparse.ArgumentParser, argv: list[str]) -> bool:
    try:
        parser.parse_args(argv)
    except (SystemExit, UserFacingError):
        return True
    return False


def _check_cplan_debug_prepare_uses_neutral_debug_core() -> dict[str, Any]:
    cli_path = Path(__file__).resolve().parent / "cli.py"
    debug_analysis_path = Path(__file__).resolve().parents[1] / "debug" / "run_failure_analysis.py"
    if not cli_path.exists() or not debug_analysis_path.exists():
        return {
            "name": "cplan_debug_prepare_uses_neutral_debug_core",
            "passed": True,
            "detail": {
                "skipped": True,
                "reason": "source files are not available in the packaged executable",
                "cli_path": str(cli_path),
                "debug_analysis_path": str(debug_analysis_path),
            },
        }
    source = cli_path.read_text(encoding="utf-8")
    has_terminal_tool_import = "ai_automate_contro.ai.terminal_tools import prepare_failure_debug_workspace_tool" in source
    has_ai_failure_analysis_import = "ai_automate_contro.ai.run_failure_analysis" in source
    has_neutral_core = "ai_automate_contro.debug.failure_prepare import" in source
    debug_analysis_source = debug_analysis_path.read_text(encoding="utf-8")
    nested_ai_actions = [
        token
        for token in ("patch_debug_workspace_json", "run_debug_plan")
        if token in debug_analysis_source
    ]
    return {
        "name": "cplan_debug_prepare_uses_neutral_debug_core",
        "passed": (
            has_neutral_core
            and not has_terminal_tool_import
            and not has_ai_failure_analysis_import
            and not nested_ai_actions
        ),
        "detail": {
            "has_neutral_core": has_neutral_core,
            "has_terminal_tool_import": has_terminal_tool_import,
            "has_ai_failure_analysis_import": has_ai_failure_analysis_import,
            "nested_ai_actions": nested_ai_actions,
        },
    }


def _check_cplan_error_fix_does_not_reference_ai_side() -> dict[str, Any]:
    import contextlib
    import io

    from ai_automate_contro.app.errors import print_cli_error

    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        exit_code = print_cli_error(ValueError("bad input"), surface="cplan")
    output = stderr.getvalue()
    return {
        "name": "cplan_error_fix_does_not_reference_ai_side",
        "passed": (
            exit_code == 1
            and "AI 侧" not in output
            and "self-check env" not in output
            and "cplan self-check runtime" in output
        ),
        "detail": {
            "exit_code": exit_code,
            "output": output,
        },
    }


def _check_cplan_manual_confirm_closed_loop() -> dict[str, Any]:
    import builtins
    import contextlib
    import io

    from ai_automate_contro.app import cli as cli_module
    from ai_automate_contro.engine.executor import execute_plan

    with TemporaryDirectory(prefix="cplan-manual-confirm-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        plan = {
            "name": "cplan manual confirm self-check",
            "automation_type": "browser",
            "variables": {},
            "steps": [
                {"action": "print", "message": "before manual confirm"},
                {"action": "manual_confirm", "prompt": "请确认后继续"},
                {
                    "action": "write",
                    "type": "text",
                    "path": "after-confirm.txt",
                    "value": "continued",
                },
            ],
        }
        package_dir = project_root / "plans" / "manual-confirm-continue"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        prompts: list[str] = []
        continue_output = package_dir / "output" / "continue"
        continue_result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            run_name="continue",
            output_dir=continue_output,
            manual_confirmation_handler=lambda prompt: prompts.append(prompt) or True,
            log_echo=False,
        )
        continued_text_path = package_dir / "output" / "text" / "after-confirm.txt"
        continued_text = continued_text_path.read_text(encoding="utf-8") if continued_text_path.exists() else ""

        stop_package_dir = project_root / "plans" / "manual-confirm-stop"
        stop_package_dir.mkdir(parents=True, exist_ok=True)
        stop_plan_path = stop_package_dir / "plan.json"
        stop_plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stop_output = stop_package_dir / "output" / "stop"
        stop_error = ""
        try:
            execute_plan(
                plan,
                project_root,
                plan_path=stop_plan_path,
                run_name="stop",
                output_dir=stop_output,
                manual_confirmation_handler=lambda _prompt: False,
                log_echo=False,
            )
        except Exception as error:
            stop_error = str(error)
        stop_result_path = stop_output / "result.json"
        stop_result = json.loads(stop_result_path.read_text(encoding="utf-8")) if stop_result_path.exists() else {}

    parse_cases = {
        "y_continue": cli_module._parse_cplan_wait_answer("y") is True,
        "upper_y_continue": cli_module._parse_cplan_wait_answer("Y") is True,
        "n_stop": cli_module._parse_cplan_wait_answer("n") is False,
        "upper_n_stop": cli_module._parse_cplan_wait_answer("N") is False,
        "empty_rejected": cli_module._parse_cplan_wait_answer("") is None,
        "continue_word_rejected": cli_module._parse_cplan_wait_answer("continue") is None,
        "continue_zh_rejected": cli_module._parse_cplan_wait_answer("继续") is None,
        "stop_word_rejected": cli_module._parse_cplan_wait_answer("stop") is None,
        "stop_zh_rejected": cli_module._parse_cplan_wait_answer("停止") is None,
        "unknown": cli_module._parse_cplan_wait_answer("随便输入") is None,
    }
    original_input = builtins.input
    loop_prompts: list[str] = []
    loop_answers = iter(["随便输入", "y"])
    loop_stdout = io.StringIO()

    def fake_input(prompt: str) -> str:
        loop_prompts.append(prompt)
        return next(loop_answers)

    try:
        builtins.input = fake_input
        with contextlib.redirect_stdout(loop_stdout):
            loop_decision = cli_module._confirm_cplan_wait("提示", wait_type="manual_confirm")
    finally:
        builtins.input = original_input

    passed = (
        continue_result.status == "passed"
        and prompts == ["请确认后继续"]
        and continued_text == "continued"
        and "人工确认未通过" in stop_error
        and stop_result.get("status") == "failed"
        and not (stop_package_dir / "output" / "text" / "after-confirm.txt").exists()
        and all(parse_cases.values())
        and loop_decision is True
        and len(loop_prompts) == 2
        and "无法识别输入" in loop_stdout.getvalue()
        and "只接受 y 或 n" in loop_stdout.getvalue()
    )
    return {
        "name": "cplan_manual_confirm_continue_stop_closed_loop",
        "passed": passed,
        "detail": {
            "continue_status": continue_result.status,
            "continue_prompts": prompts,
            "continued_text": continued_text,
            "stop_error": stop_error,
            "stop_status": stop_result.get("status"),
            "parse_cases": parse_cases,
            "input_loop_prompts": loop_prompts,
            "input_loop_output": loop_stdout.getvalue(),
        },
    }


def _check_cplan_output_dir_package_scope() -> dict[str, Any]:
    from ai_automate_contro.engine.executor import execute_plan

    with TemporaryDirectory(prefix="cplan-output-dir-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "output-dir-scope"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "output dir scope",
            "automation_type": "browser",
            "variables": {},
            "steps": [
                {
                    "action": "write",
                    "type": "text",
                    "path": "scoped.txt",
                    "value": "ok",
                }
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = execute_plan(
            plan,
            project_root,
            plan_path=plan_path,
            output_dir="output/custom run",
            log_echo=False,
        )
        relative_output_path = package_dir / "output" / "custom run"
        scoped_text_path = package_dir / "output" / "text" / "scoped.txt"
        scoped_text = scoped_text_path.read_text(encoding="utf-8") if scoped_text_path.exists() else ""
        outside_error = ""
        try:
            execute_plan(
                plan,
                project_root,
                plan_path=plan_path,
                output_dir=project_root / "outside-output",
                log_echo=False,
            )
        except Exception as error:
            outside_error = str(error)

    passed = (
        Path(result.output_dir) == relative_output_path
        and scoped_text == "ok"
        and "运行输出目录必须位于当前 plan 包 output 目录内" in outside_error
    )
    return {
        "name": "cplan_output_dir_relative_output_is_package_scoped",
        "passed": passed,
        "detail": {
            "result_output_dir": result.output_dir,
            "expected_output_dir": str(relative_output_path),
            "scoped_text": scoped_text,
            "outside_error": outside_error,
        },
    }


def _check_cplan_trigger_parent_action() -> dict[str, Any]:
    from ai_automate_contro.engine.executor import execute_plan
    from ai_automate_contro.plans.packages import summarize_plan
    from ai_automate_contro.plans.validator import validate_plan_file

    with TemporaryDirectory(prefix="cplan-trigger-parent-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "trigger-parent"
        sub_plans_dir = package_dir / "sub-plans"
        sub_plans_dir.mkdir(parents=True, exist_ok=True)
        sub_plan_path = sub_plans_dir / "tick-once-plan.json"
        sub_plan_path.write_text(
            json.dumps(
                {
                    "name": "tick once",
                    "automation_type": "browser",
                    "steps": [
                        {
                            "action": "write",
                            "type": "text",
                            "path": "ticks.txt",
                            "value": "sub-plan {{trigger_run_index}}\n",
                            "append": True,
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = package_dir / "plan.json"
        plan = {
            "name": "trigger parent",
            "automation_type": "browser",
            "steps": [
                {"action": "write", "type": "text", "path": "ticks.txt", "value": ""},
                {
                    "action": "trigger",
                    "type": "interval",
                    "name": "inline",
                    "every_seconds": 0.01,
                    "run_immediately": True,
                    "max_runs": 2,
                    "steps": [
                        {
                            "action": "write",
                            "type": "text",
                            "path": "ticks.txt",
                            "value": "inline {{trigger_run_index}}\n",
                            "append": True,
                        }
                    ],
                    "save_as": "inline_status",
                },
                {
                    "action": "trigger",
                    "type": "interval",
                    "name": "sub_plan",
                    "every_seconds": 0.01,
                    "run_immediately": True,
                    "max_runs": 2,
                    "path": "sub-plans/tick-once-plan.json",
                    "save_as": "sub_plan_status",
                },
                {
                    "action": "write",
                    "type": "json",
                    "path": "trigger-status.json",
                    "value": {
                        "inline": "{{inline_status}}",
                        "sub_plan": "{{sub_plan_status}}",
                    },
                    "indent": 2,
                },
            ],
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_plan_file(plan_path, project_root)
        result = execute_plan(plan, project_root, plan_path=plan_path, run_name="trigger-parent", log_echo=False)
        ticks_path = package_dir / "output" / "text" / "ticks.txt"
        status_path = package_dir / "output" / "json" / "trigger-status.json"
        ticks = ticks_path.read_text(encoding="utf-8").splitlines() if ticks_path.exists() else []
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        summary = summarize_plan(plan_path, project_root)

        legacy_dir = project_root / "plans" / "legacy-trigger"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_plan_path = legacy_dir / "plan.json"
        legacy_plan_path.write_text(
            json.dumps(
                {
                    "name": "legacy trigger",
                    "automation_type": "browser",
                    "routines": {"tick": [{"action": "print", "message": "tick"}]},
                    "triggers": [
                        {
                            "name": "tick",
                            "type": "interval",
                            "every_seconds": 1,
                            "routine": "tick",
                            "max_runs": 1,
                        }
                    ],
                    "steps": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_validation = validate_plan_file(legacy_plan_path, project_root)

        invalid_name_dir = project_root / "plans" / "invalid-trigger-name"
        invalid_name_dir.mkdir(parents=True, exist_ok=True)
        invalid_name_plan_path = invalid_name_dir / "plan.json"
        invalid_name_plan_path.write_text(
            json.dumps(
                {
                    "name": "invalid trigger name",
                    "automation_type": "browser",
                    "steps": [
                        {
                            "action": "trigger",
                            "type": "interval",
                            "name": "   ",
                            "every_seconds": 1,
                            "max_runs": 1,
                            "steps": [{"action": "print", "message": "tick"}],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        invalid_name_validation = validate_plan_file(invalid_name_plan_path, project_root)

        rendered_invalid_dir = project_root / "plans" / "rendered-invalid-trigger"
        rendered_invalid_dir.mkdir(parents=True, exist_ok=True)
        rendered_invalid_plan_path = rendered_invalid_dir / "plan.json"
        rendered_invalid_plan = {
            "name": "rendered invalid trigger",
            "automation_type": "browser",
            "variables": {"bad_bool": "maybe", "bad_runs": "2.5"},
            "steps": [
                {
                    "action": "trigger",
                    "type": "interval",
                    "every_seconds": 0.01,
                    "run_immediately": "{{bad_bool}}",
                    "max_runs": "{{bad_runs}}",
                    "steps": [{"action": "print", "message": "tick"}],
                }
            ],
        }
        rendered_invalid_error = ""
        try:
            execute_plan(
                rendered_invalid_plan,
                project_root,
                plan_path=rendered_invalid_plan_path,
                run_name="rendered-invalid-trigger",
                log_echo=False,
            )
        except Exception as error:
            rendered_invalid_error = str(error)

    inline_status = status.get("inline", {}) if isinstance(status, dict) else {}
    sub_plan_status = status.get("sub_plan", {}) if isinstance(status, dict) else {}
    legacy_errors = [issue.message for issue in legacy_validation.errors]
    invalid_name_errors = [issue.message for issue in invalid_name_validation.errors]
    passed = (
        validation.ok
        and result.status == "passed"
        and ticks == ["inline 1", "inline 2", "sub-plan 1", "sub-plan 2"]
        and inline_status.get("status") == "completed"
        and inline_status.get("run_count") == 2
        and sub_plan_status.get("status") == "completed"
        and sub_plan_status.get("run_count") == 2
        and "sub-plans/tick-once-plan.json" in summary.get("sub_plans", [])
        and not legacy_validation.ok
        and any("routines 已移除" in message for message in legacy_errors)
        and any("triggers 已移除" in message for message in legacy_errors)
        and not invalid_name_validation.ok
        and any("trigger.name 必须是非空字符串" in message for message in invalid_name_errors)
        and "trigger.run_immediately 必须是布尔值" in rendered_invalid_error
    )
    return {
        "name": "cplan_trigger_parent_action_roundtrip",
        "passed": passed,
        "detail": {
            "validation_ok": validation.ok,
            "run_status": result.status,
            "ticks": ticks,
            "inline_status": inline_status,
            "sub_plan_status": sub_plan_status,
            "summary_sub_plans": summary.get("sub_plans", []),
            "legacy_validation_ok": legacy_validation.ok,
            "legacy_errors": legacy_errors,
            "invalid_name_validation_ok": invalid_name_validation.ok,
            "invalid_name_errors": invalid_name_errors,
            "rendered_invalid_error": rendered_invalid_error,
        },
    }


def _check_cplan_schedule_management() -> dict[str, Any]:
    from ai_automate_contro.app import schedule_manager

    with TemporaryDirectory(prefix="cplan-schedule-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "scheduled-plan"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "scheduled plan",
                    "automation_type": "browser",
                    "steps": [
                        {
                            "action": "write",
                            "type": "text",
                            "path": "scheduled.txt",
                            "value": "ran",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        added = schedule_manager.add_schedule(
            project_root,
            schedule_id="demo",
            plan_file=plan_path,
            trigger={"type": "interval", "every_seconds": 1, "run_immediately": True},
            timeout_seconds=30,
        )
        listed_after_add = schedule_manager.list_schedules(project_root)
        disabled = schedule_manager.set_schedule_enabled(project_root, "demo", False)
        enabled = schedule_manager.set_schedule_enabled(project_root, "demo", True)
        run_now = schedule_manager.run_schedule_now(project_root, "demo")
        due_scan = schedule_manager.run_due_schedules(project_root)
        state_with_orphan = schedule_manager.load_schedule_state(project_root)
        state_with_orphan["orphan"] = {"last_status": "stale"}
        schedule_manager.save_schedule_state(project_root, state_with_orphan)
        removed = schedule_manager.remove_schedule(project_root, "demo")
        listed_after_remove = schedule_manager.list_schedules(project_root)
        output_text_path = package_dir / "output" / "text" / "scheduled.txt"
        output_text = output_text_path.read_text(encoding="utf-8") if output_text_path.exists() else ""
        state_after_remove = schedule_manager.load_schedule_state(project_root)
        config_exists_after_remove = schedule_manager.schedule_config_path(project_root).exists()
        state_exists_after_remove = schedule_manager.schedule_state_path(project_root).exists()

    passed = (
        added.get("ok") is True
        and listed_after_add.get("schedules")
        and disabled.get("schedule", {}).get("enabled") is False
        and enabled.get("schedule", {}).get("enabled") is True
        and run_now.get("ok") is True
        and run_now.get("status") == "passed"
        and isinstance(due_scan.get("results"), list)
        and removed.get("removed") is True
        and listed_after_remove.get("schedules") == []
        and "demo" not in state_after_remove
        and not config_exists_after_remove
        and not state_exists_after_remove
        and output_text == "ran"
    )
    return {
        "name": "cplan_schedule_management_roundtrip",
        "passed": passed,
        "detail": {
            "added": added,
            "listed_after_add_count": len(listed_after_add.get("schedules", [])),
            "disabled_enabled": disabled.get("schedule", {}).get("enabled"),
            "enabled_enabled": enabled.get("schedule", {}).get("enabled"),
            "run_now": run_now,
            "due_scan": due_scan,
            "removed": removed,
            "listed_after_remove_count": len(listed_after_remove.get("schedules", [])),
            "state_after_remove": state_after_remove,
            "config_exists_after_remove": config_exists_after_remove,
            "state_exists_after_remove": state_exists_after_remove,
            "output_text": output_text,
        },
    }


def _check_manual_confirm_requires_visible_browser() -> dict[str, Any]:
    from ai_automate_contro.engine.actions.basic import action_manual_confirm
    from ai_automate_contro.plans.validator import validate_plan_file

    blocked_error = ""
    blocked_handler_calls: list[str] = []
    try:
        action_manual_confirm(
            SimpleNamespace(
                state=SimpleNamespace(
                    sessions={"main": SimpleNamespace(headed=False)},
                    manual_confirmation_handler=lambda prompt: blocked_handler_calls.append(prompt) or True,
                )
            ),
            {"prompt": "请在浏览器中操作"},
        )
    except Exception as error:
        blocked_error = str(error)

    headed_handler_calls: list[str] = []
    action_manual_confirm(
        SimpleNamespace(
            state=SimpleNamespace(
                sessions={"main": SimpleNamespace(headed=True)},
                manual_confirmation_handler=lambda prompt: headed_handler_calls.append(prompt) or True,
                logger=SimpleNamespace(log=lambda *args, **kwargs: None),
                state_writer=SimpleNamespace(mark_waiting=lambda **kwargs: None, mark_resumed=lambda: None),
            )
        ),
        {"prompt": "请在浏览器中操作"},
    )

    mismatched_error = ""
    mismatched_handler_calls: list[str] = []
    try:
        action_manual_confirm(
            SimpleNamespace(
                state=SimpleNamespace(
                    sessions={"target": SimpleNamespace(headed=False), "decoy": SimpleNamespace(headed=True)},
                    manual_confirmation_handler=lambda prompt: mismatched_handler_calls.append(prompt) or True,
                )
            ),
            {"browser": "target", "prompt": "请在 target 浏览器中操作"},
        )
    except Exception as error:
        mismatched_error = str(error)

    ambiguous_error = ""
    ambiguous_handler_calls: list[str] = []
    try:
        action_manual_confirm(
            SimpleNamespace(
                state=SimpleNamespace(
                    sessions={"main": SimpleNamespace(headed=True), "other": SimpleNamespace(headed=True)},
                    manual_confirmation_handler=lambda prompt: ambiguous_handler_calls.append(prompt) or True,
                )
            ),
            {"prompt": "请在浏览器中操作"},
        )
    except Exception as error:
        ambiguous_error = str(error)

    with TemporaryDirectory(prefix="manual-confirm-headed-validation-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "headless-manual-confirm"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "headless manual confirm",
                    "automation_type": "browser",
                    "variables": {},
                    "steps": [
                        {"action": "open_browser", "name": "main"},
                        {"action": "manual_confirm", "prompt": "请在浏览器里继续"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        validation = validate_plan_file(plan_path, project_root)

        branch_package_dir = project_root / "plans" / "branch-headless-manual-confirm"
        branch_package_dir.mkdir(parents=True, exist_ok=True)
        branch_plan_path = branch_package_dir / "plan.json"
        branch_plan_path.write_text(
            json.dumps(
                {
                    "name": "branch headless manual confirm",
                    "automation_type": "browser",
                    "variables": {"needs_browser": True},
                    "steps": [
                        {
                            "action": "if",
                            "condition": {"var": "needs_browser", "equals": True},
                            "then": [{"action": "open_browser", "name": "branch"}],
                            "else": [],
                        },
                        {"action": "manual_confirm", "prompt": "请在分支打开的浏览器里继续"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        branch_validation = validate_plan_file(branch_plan_path, project_root)

        sub_plan_package_dir = project_root / "plans" / "sub-plan-headless-manual-confirm"
        sub_plan_dir = sub_plan_package_dir / "sub-plans"
        sub_plan_dir.mkdir(parents=True, exist_ok=True)
        sub_plan_plan_path = sub_plan_package_dir / "plan.json"
        sub_plan_plan_path.write_text(
            json.dumps(
                {
                    "name": "sub plan headless manual confirm",
                    "automation_type": "browser",
                    "steps": [
                        {"action": "run_sub_plan", "path": "sub-plans/open-headless-plan.json"},
                        {"action": "manual_confirm", "prompt": "请在子计划打开的浏览器里继续"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (sub_plan_dir / "open-headless-plan.json").write_text(
            json.dumps(
                {
                    "name": "open headless sub plan",
                    "steps": [{"action": "open_browser", "name": "from_sub_plan"}],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sub_plan_validation = validate_plan_file(sub_plan_plan_path, project_root)

        mismatched_package_dir = project_root / "plans" / "mismatched-manual-confirm"
        mismatched_package_dir.mkdir(parents=True, exist_ok=True)
        mismatched_plan_path = mismatched_package_dir / "plan.json"
        mismatched_plan_path.write_text(
            json.dumps(
                {
                    "name": "mismatched manual confirm",
                    "automation_type": "browser",
                    "steps": [
                        {"action": "open_browser", "name": "target", "headed": False},
                        {"action": "open_browser", "name": "decoy", "headed": True},
                        {"action": "manual_confirm", "browser": "target", "prompt": "请在 target 页面继续"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        mismatched_validation = validate_plan_file(mismatched_plan_path, project_root)

        bound_package_dir = project_root / "plans" / "bound-manual-confirm"
        bound_package_dir.mkdir(parents=True, exist_ok=True)
        bound_plan_path = bound_package_dir / "plan.json"
        bound_plan_path.write_text(
            json.dumps(
                {
                    "name": "bound manual confirm",
                    "automation_type": "browser",
                    "steps": [
                        {"action": "open_browser", "name": "target", "headed": True},
                        {"action": "open_browser", "name": "decoy", "headed": False},
                        {"action": "manual_confirm", "browser": "target", "prompt": "请在 target 页面继续"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        bound_validation = validate_plan_file(bound_plan_path, project_root)

    validation_messages = [issue.message for issue in validation.errors]
    branch_validation_messages = [issue.message for issue in branch_validation.errors]
    sub_plan_validation_messages = [issue.message for issue in sub_plan_validation.errors]
    mismatched_validation_messages = [issue.message for issue in mismatched_validation.errors]
    bound_validation_messages = [issue.message for issue in bound_validation.errors]
    passed = (
        "manual_confirm 需要同一个可见 Playwright 浏览器窗口" in blocked_error
        and not blocked_handler_calls
        and headed_handler_calls == ["请在浏览器中操作"]
        and "指定浏览器 target 不是 headed=true" in mismatched_error
        and not mismatched_handler_calls
        and "多个浏览器会话" in ambiguous_error
        and not ambiguous_handler_calls
        and any("没有 headed=true 的可见浏览器" in message for message in validation_messages)
        and any("没有 headed=true 的可见浏览器" in message for message in branch_validation_messages)
        and any("没有 headed=true 的可见浏览器" in message for message in sub_plan_validation_messages)
        and any("指定浏览器 target 不是 headed=true" in message for message in mismatched_validation_messages)
        and not bound_validation_messages
    )
    return {
        "name": "manual_confirm_requires_visible_browser_when_browser_open",
        "passed": passed,
        "detail": {
            "blocked_error": blocked_error,
            "blocked_handler_calls": blocked_handler_calls,
            "headed_handler_calls": headed_handler_calls,
            "mismatched_error": mismatched_error,
            "mismatched_handler_calls": mismatched_handler_calls,
            "ambiguous_error": ambiguous_error,
            "ambiguous_handler_calls": ambiguous_handler_calls,
            "validation_messages": validation_messages,
            "branch_validation_messages": branch_validation_messages,
            "sub_plan_validation_messages": sub_plan_validation_messages,
            "mismatched_validation_messages": mismatched_validation_messages,
            "bound_validation_messages": bound_validation_messages,
        },
    }


def _check_debug_patch_deletion_backup() -> dict[str, Any]:
    from ai_automate_contro.debug.workspace import apply_debug_patch, create_debug_workspace, generate_debug_patch

    with TemporaryDirectory(prefix="cplan-debug-patch-delete-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "debug-delete-backup"
        docs_dir = package_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "debug delete backup",
                    "automation_type": "browser",
                    "variables": {},
                    "steps": [{"action": "print", "message": "debug patch deletion"}],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        removable_path = docs_dir / "remove-me.md"
        removable_path.write_text("remove me\n", encoding="utf-8")
        spaced_removable_path = docs_dir / "remove me too.md"
        spaced_removable_path.write_text("", encoding="utf-8")
        header_lines_path = docs_dir / "header-lines.md"
        header_lines_path.write_text("before\n-- not a file header\n++ not a file header\n", encoding="utf-8")

        workspace = create_debug_workspace(plan_path, project_root, name="delete-backup")
        injected_removable_path = workspace.injected_plan_dir / "docs" / "remove-me.md"
        injected_removable_path.unlink()
        injected_spaced_removable_path = workspace.injected_plan_dir / "docs" / "remove me too.md"
        injected_spaced_removable_path.unlink()
        injected_header_lines_path = workspace.injected_plan_dir / "docs" / "header-lines.md"
        injected_header_lines_path.write_text(
            "before\n-- not a file header changed\n++ not a file header changed\n",
            encoding="utf-8",
        )

        generated = generate_debug_patch(workspace.root)
        patch_text = generated.patch_path.read_text(encoding="utf-8")
        applied = apply_debug_patch(workspace.root, yes=True)
        backup_files = sorted((workspace.root / "original-backups").rglob("docs/remove-me.md"))
        backup_text = backup_files[0].read_text(encoding="utf-8") if backup_files else ""
        spaced_backup_files = sorted((workspace.root / "original-backups").rglob("docs/remove me too.md"))
        header_text_after_apply = header_lines_path.read_text(encoding="utf-8")
        notes_text = workspace.notes_path.read_text(encoding="utf-8")
        original_exists_after_apply = removable_path.exists()
        spaced_original_exists_after_apply = spaced_removable_path.exists()

    expected_files = ["docs/header-lines.md", "docs/remove me too.md", "docs/remove-me.md"]
    passed = (
        generated.changed_files == expected_files
        and applied.changed_files == expected_files
        and "deleted file mode" in patch_text
        and "--- not a file header" in patch_text
        and not original_exists_after_apply
        and not spaced_original_exists_after_apply
        and backup_text == "remove me\n"
        and bool(spaced_backup_files)
        and header_text_after_apply == "before\n-- not a file header changed\n++ not a file header changed\n"
        and "docs/remove-me.md" in notes_text
        and "docs/remove me too.md" in notes_text
    )
    return {
        "name": "debug_patch_deletion_backs_up_and_reports_deleted_file",
        "passed": passed,
        "detail": {
            "generated_changed_files": generated.changed_files,
            "applied_changed_files": applied.changed_files,
            "patch_has_deleted_file_mode": "deleted file mode" in patch_text,
            "original_exists_after_apply": original_exists_after_apply,
            "spaced_original_exists_after_apply": spaced_original_exists_after_apply,
            "backup_files": [str(path) for path in backup_files],
            "spaced_backup_files": [str(path) for path in spaced_backup_files],
            "backup_text": backup_text,
            "header_text_after_apply": header_text_after_apply,
        },
    }


def _check_debug_patch_rejects_forbidden_paths() -> dict[str, Any]:
    from ai_automate_contro.debug.workspace import apply_debug_patch, create_debug_workspace

    with TemporaryDirectory(prefix="cplan-debug-patch-forbidden-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "debug-forbidden-patch"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "debug forbidden patch",
                    "automation_type": "browser",
                    "steps": [{"action": "print", "message": "debug forbidden patch"}],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        workspace = create_debug_workspace(plan_path, project_root, name="forbidden")
        workspace.patch_path.write_text(
            "\n".join(
                [
                    "diff --git a/output/leak.txt b/output/leak.txt",
                    "new file mode 100644",
                    "index 0000000..0000000",
                    "--- /dev/null",
                    "+++ b/output/leak.txt",
                    "@@ -0,0 +1 @@",
                    "+leak",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        forbidden_error = ""
        try:
            apply_debug_patch(workspace.root, yes=True)
        except Exception as error:
            forbidden_error = str(error)
        output_file_exists = (package_dir / "output" / "leak.txt").exists()

    passed = "debug patch 不允许修改 output" in forbidden_error and not output_file_exists
    return {
        "name": "debug_patch_rejects_forbidden_output_paths",
        "passed": passed,
        "detail": {
            "forbidden_error": forbidden_error,
            "output_file_exists": output_file_exists,
        },
    }
