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
    cplan_commands = _subcommands(build_cplan_parser())
    textual_commands = {command.name for command in all_client_commands()}
    manual_confirm_check = _check_cplan_manual_confirm_closed_loop()
    manual_confirm_headed_check = _check_manual_confirm_requires_visible_browser()
    debug_patch_delete_check = _check_debug_patch_deletion_backup()

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
        manual_confirm_check,
        manual_confirm_headed_check,
        debug_patch_delete_check,
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

    with TemporaryDirectory(prefix="manual-confirm-headed-validation-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        package_dir = project_root / "plans" / "headless-manual-confirm"
        package_dir.mkdir(parents=True, exist_ok=True)
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "headless manual confirm",
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

    validation_messages = [issue.message for issue in validation.errors]
    passed = (
        "manual_confirm 需要同一个可见 Playwright 浏览器窗口" in blocked_error
        and not blocked_handler_calls
        and headed_handler_calls == ["请在浏览器中操作"]
        and any("没有 headed=true 的可见浏览器" in message for message in validation_messages)
    )
    return {
        "name": "manual_confirm_requires_visible_browser_when_browser_open",
        "passed": passed,
        "detail": {
            "blocked_error": blocked_error,
            "blocked_handler_calls": blocked_handler_calls,
            "headed_handler_calls": headed_handler_calls,
            "validation_messages": validation_messages,
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

        workspace = create_debug_workspace(plan_path, project_root, name="delete-backup")
        injected_removable_path = workspace.injected_plan_dir / "docs" / "remove-me.md"
        injected_removable_path.unlink()

        generated = generate_debug_patch(workspace.root)
        patch_text = generated.patch_path.read_text(encoding="utf-8")
        applied = apply_debug_patch(workspace.root, yes=True)
        backup_files = sorted((workspace.root / "original-backups").rglob("docs/remove-me.md"))
        backup_text = backup_files[0].read_text(encoding="utf-8") if backup_files else ""
        notes_text = workspace.notes_path.read_text(encoding="utf-8")
        original_exists_after_apply = removable_path.exists()

    passed = (
        generated.changed_files == ["docs/remove-me.md"]
        and applied.changed_files == ["docs/remove-me.md"]
        and "deleted file mode" in patch_text
        and not original_exists_after_apply
        and backup_text == "remove me\n"
        and "docs/remove-me.md" in notes_text
    )
    return {
        "name": "debug_patch_deletion_backs_up_and_reports_deleted_file",
        "passed": passed,
        "detail": {
            "generated_changed_files": generated.changed_files,
            "applied_changed_files": applied.changed_files,
            "patch_has_deleted_file_mode": "deleted file mode" in patch_text,
            "original_exists_after_apply": original_exists_after_apply,
            "backup_files": [str(path) for path in backup_files],
            "backup_text": backup_text,
        },
    }
