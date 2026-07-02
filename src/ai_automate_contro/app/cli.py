from __future__ import annotations

import json
import sys
from pathlib import Path


from ai_automate_contro.app.command_helpers import (
    load_tool_arguments,
    print_json,
    print_plan_list,
    print_validation_result,
    run_plan,
)
from ai_automate_contro.app.errors import format_error_for_terminal, print_cli_error
from ai_automate_contro.app.parser import build_cplan_parser, build_parser
from ai_automate_contro.debug.failure_prepare import (
    CPLAN_DEBUG_NEXT_ACTIONS,
    prepare_failure_debug_workspace,
)
from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    create_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
)
from ai_automate_contro.plans.packages import (
    create_plan_package,
    find_latest_run_output,
)
from ai_automate_contro.plans.validator import validate_plan_file
from ai_automate_contro.support.paths import path_from_text


def run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    try:
        if _is_cplan_invocation(argv):
            return _run_cplan_cli(project_root, argv)
        return _run_cli(project_root, argv)
    except KeyboardInterrupt as error:
        return print_cli_error(error, project_root=project_root, surface=_cli_error_surface(argv))
    except Exception as error:
        return print_cli_error(error, project_root=project_root, surface=_cli_error_surface(argv))


def _run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        from ai_automate_contro.client import run_textual_client

        run_textual_client(project_root)
        return 0

    browser_install_result = _run_install_browser_command(args)
    if browser_install_result is not None:
        return browser_install_result

    if args.command == "ai":
        if args.ai_command == "check":
            from ai_automate_contro.ai.terminal import check_ai_terminal_service

            result = check_ai_terminal_service(
                project_root,
                service=args.service,
                thread_id=f"{args.thread}-service-check",
                message=args.message,
            )
            if args.json:
                print_json(result, compact=args.compact)
            elif result.get("ok"):
                print(f"AI 服务可用：service={result.get('service')} model={result.get('model')}")
                assistant_message = str(result.get("assistant_message") or "").strip()
                if assistant_message:
                    print(f"回复：{assistant_message}")
            else:
                print(str(result.get("formatted_error") or result.get("error") or "AI 服务检查失败。"))
            return 0 if result.get("ok") else 1
        if args.ai_command == "ask":
            from ai_automate_contro.ai.terminal import AITerminal

            app: AITerminal | None = None
            try:
                app = AITerminal(project_root, service=args.service, thread_id=args.thread)
                event_sink = _print_ai_ask_event_jsonl if args.events else None
                try:
                    result = app.ask_once(args.message, event_sink=event_sink)
                except Exception as error:
                    if args.json:
                        print_json(
                            {
                                "ok": False,
                                "thread_id": args.thread,
                                "error_type": type(error).__name__,
                                "error": str(error),
                                "formatted_error": app.format_error_message(error),
                                "checkpoint_path": str(app.checkpoint_path),
                                "context_state": app._context_state(),
                            },
                            compact=args.compact,
                        )
                        return 1
                    raise
                if args.json:
                    print_json(result, compact=args.compact)
                else:
                    assistant_message = result.get("assistant_message") or ""
                    if assistant_message:
                        print(assistant_message)
                    if result.get("pending_approval"):
                        print("approval needed: 请进入 Textual 客户端后输入 /approve，或输入 /reject <原因>。")
                return 0 if result.get("ok") else 1
            except Exception as error:
                if args.json:
                    payload = {
                        "ok": False,
                        "thread_id": args.thread,
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "formatted_error": (
                            app.format_error_message(error)
                            if app is not None
                            else format_error_for_terminal(error, project_root=project_root)
                        ),
                    }
                    if app is not None:
                        payload["checkpoint_path"] = str(app.checkpoint_path)
                        payload["context_state"] = app._context_state()
                    print_json(payload, compact=args.compact)
                    return 1
                raise
            finally:
                if app is not None:
                    app.close()
        from ai_automate_contro.client import run_textual_client

        run_textual_client(project_root, service=args.service, thread_id=args.thread)
        return 0

    if args.command == "self-check":
        if args.self_check_command == "env":
            from ai_automate_contro.app.environment_check import self_check_environment

            result = self_check_environment(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "textual-client":
            from ai_automate_contro.client.self_check import self_check_textual_client

            result = self_check_textual_client(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-stream":
            from ai_automate_contro.ai.response_parsing import self_check_chat_completion_stream_parser

            result = self_check_chat_completion_stream_parser()
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-terminal":
            from ai_automate_contro.ai.terminal_self_check import self_check_ai_terminal_state

            result = self_check_ai_terminal_state(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-tools":
            from ai_automate_contro.ai.langgraph_tools import self_check_langchain_tools

            result = self_check_langchain_tools(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-plan-generation":
            from ai_automate_contro.ai.terminal_plan_generation_self_check import (
                self_check_ai_plan_generation_simulation,
            )

            result = self_check_ai_plan_generation_simulation(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-desktop-loop":
            from ai_automate_contro.ai.desktop_loop_self_check import self_check_ai_desktop_loop

            result = self_check_ai_desktop_loop(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-real-desktop-loop":
            from ai_automate_contro.ai.real_desktop_loop_self_check import self_check_real_ai_desktop_loop

            result = self_check_real_ai_desktop_loop(
                project_root,
                service=args.service,
                thread_id=args.thread,
                api_key_file=args.api_key_file,
                api_key_env=args.api_key_env,
                base_url=args.base_url,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                max_attempts=args.max_attempts,
                retry_delay_seconds=args.retry_delay_seconds,
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "ai-real-execution-line":
            from ai_automate_contro.ai.real_execution_line_self_check import self_check_real_ai_execution_line

            result = self_check_real_ai_execution_line(
                project_root,
                service=args.service,
                thread_id=args.thread,
                api_key_file=args.api_key_file,
                api_key_env=args.api_key_env,
                base_url=args.base_url,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                max_attempts=args.max_attempts,
                retry_delay_seconds=args.retry_delay_seconds,
            )
            print_json(result)
            return 0 if result.get("ok") else 1

    if args.command == "tool":
        from ai_automate_contro.ai.terminal_tool_registry import (
            call_ai_terminal_tool,
            check_ai_terminal_tool_registry,
            describe_ai_terminal_tool,
            list_ai_terminal_tools,
        )

        if args.tool_command == "list":
            print_json(list_ai_terminal_tools())
            return 0
        if args.tool_command == "check":
            result = check_ai_terminal_tool_registry()
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.tool_command == "schema":
            try:
                print_json(describe_ai_terminal_tool(args.name))
            except Exception as error:
                print_json({"ok": False, "error": str(error)})
                return 1
            return 0
        if args.tool_command == "call":
            try:
                tool_arguments = load_tool_arguments(args.args_json, args.args_file)
                result = call_ai_terminal_tool(args.name, project_root, tool_arguments)
            except Exception as error:
                print_json({"ok": False, "error": str(error)}, compact=args.compact)
                return 1
            print_json(result, compact=args.compact)
            return 0

    parser.print_help()
    return 1


def run_cplan_cli(project_root: Path, argv: list[str] | None = None) -> int:
    try:
        return _run_cplan_cli(project_root, argv)
    except KeyboardInterrupt as error:
        return print_cli_error(error, project_root=project_root, surface="cplan")
    except Exception as error:
        return print_cli_error(error, project_root=project_root, surface="cplan")


def _run_cplan_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_cplan_parser()
    args = parser.parse_args(argv)

    browser_install_result = _run_install_browser_command(args)
    if browser_install_result is not None:
        return browser_install_result

    if args.cplan_command == "self-check":
        if args.self_check_command == "cli":
            from ai_automate_contro.app.cli_self_check import self_check_cli_boundaries

            result = self_check_cli_boundaries()
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "runtime":
            from ai_automate_contro.app.environment_check import self_check_runtime_config

            result = self_check_runtime_config(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "handbook":
            from ai_automate_contro.app.handbook_check import self_check_handbook_hygiene

            result = self_check_handbook_hygiene(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "workspace-clean":
            from ai_automate_contro.app.workspace_check import self_check_workspace_clean

            result = self_check_workspace_clean(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "release-matrix":
            from ai_automate_contro.app.release_matrix_check import self_check_release_matrix

            strict_desktop = bool(args.strict_desktop)
            result = self_check_release_matrix(
                project_root,
                include_real_ai=bool(args.include_real_ai),
                api_key_file=args.api_key_file,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                max_attempts=args.max_attempts,
                retry_delay_seconds=args.retry_delay_seconds,
                step_timeout_seconds=args.step_timeout_seconds,
                strict_desktop=strict_desktop,
                require_desktop_input=strict_desktop or bool(args.require_desktop_input),
                require_desktop_vision=strict_desktop or bool(args.require_desktop_vision),
                require_desktop_ocr=strict_desktop or bool(args.require_desktop_ocr),
                require_desktop_ocr_zh=strict_desktop or bool(args.require_desktop_ocr_zh),
                require_desktop_wpf=bool(args.require_desktop_wpf),
                only=list(args.only or []),
                list_steps=bool(args.list),
                fail_fast=bool(args.fail_fast),
                repeat=int(args.repeat),
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "browser-components":
            from ai_automate_contro.app.browser_component_check import self_check_browser_components

            result = self_check_browser_components(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "data-components":
            from ai_automate_contro.app.data_component_check import self_check_data_components

            result = self_check_data_components(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "database-components":
            from ai_automate_contro.app.database_component_check import self_check_database_components

            result = self_check_database_components(
                project_root,
                include_real_db=bool(args.include_real_db),
                allow_writes=bool(args.allow_writes),
                database_config=args.database_config,
                only=list(args.only or []),
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-env":
            from ai_automate_contro.app.desktop_env_check import self_check_desktop_env

            result = self_check_desktop_env(
                project_root,
                require_input=bool(args.require_input),
                require_vision=bool(args.require_vision),
                require_ocr=bool(args.require_ocr),
                require_ocr_zh=bool(args.require_ocr_zh),
                request_permissions=bool(args.request_permissions),
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-components":
            from ai_automate_contro.app.desktop_component_check import self_check_desktop_components

            result = self_check_desktop_components(
                project_root,
                require_input=bool(args.require_input),
                require_wpf=bool(args.require_wpf),
                require_vision=bool(args.require_vision),
                require_ocr=bool(args.require_ocr),
                require_ocr_zh=bool(args.require_ocr_zh),
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-examples":
            from ai_automate_contro.app.desktop_examples_check import self_check_desktop_examples

            result = self_check_desktop_examples(
                project_root,
                require_vision=bool(args.require_vision),
            )
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-scenarios":
            from ai_automate_contro.app.desktop_scenarios_check import self_check_desktop_scenarios

            result = self_check_desktop_scenarios(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-scenario-apps":
            from ai_automate_contro.app.desktop_scenario_apps_check import self_check_desktop_scenario_apps

            result = self_check_desktop_scenario_apps(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "desktop-real-app":
            from ai_automate_contro.app.desktop_component_check import self_check_desktop_real_app

            result = self_check_desktop_real_app(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1

    schedule_command_result = _run_cplan_schedule_command(project_root, args)
    if schedule_command_result is not None:
        return schedule_command_result

    plan_command_result = _run_cplan_plan_command(project_root, args)
    if plan_command_result is not None:
        return plan_command_result

    parser.print_help()
    return 1


def _run_install_browser_command(args: object) -> int | None:
    command = str(getattr(args, "command", "") or getattr(args, "cplan_command", "") or "")
    if command != "install-browser":
        return None

    from ai_automate_contro.support.playwright_browsers import install_playwright_browser

    json_output = bool(getattr(args, "json", False))
    result = install_playwright_browser(
        str(getattr(args, "browser", "chromium") or "chromium"),
        force=bool(getattr(args, "force", False)),
        capture_output=json_output,
    )
    if json_output:
        print_json(result, compact=bool(getattr(args, "compact", False)))
    elif result.get("ok"):
        print(f"Playwright {result.get('browser')} 浏览器安装完成。")
        print(f"Playwright 版本：{result.get('playwright_version')}")
        print(f"浏览器目录：{result.get('browser_path')}")
    else:
        print(f"Playwright {result.get('browser')} 浏览器安装失败。", file=sys.stderr)
    return 0 if result.get("ok") else int(result.get("returncode") or 1)


def _run_cplan_schedule_command(project_root: Path, args: object) -> int | None:
    if str(getattr(args, "cplan_command", "") or "") != "schedule":
        return None

    from ai_automate_contro.app import schedule_manager

    schedule_command = str(getattr(args, "schedule_command", "") or "")
    if schedule_command == "list":
        result = schedule_manager.list_schedules(project_root)
        if bool(getattr(args, "json", False)):
            print_json(result)
        else:
            _print_schedule_list(result)
        return 0
    if schedule_command == "add":
        trigger = (
            {"type": "daily", "at": getattr(args, "daily_at")}
            if getattr(args, "daily_at", None)
            else {
                "type": "interval",
                "every_seconds": getattr(args, "every_seconds"),
                "run_immediately": bool(getattr(args, "run_immediately", False)),
            }
        )
        result = schedule_manager.add_schedule(
            project_root,
            schedule_id=getattr(args, "id"),
            plan_file=getattr(args, "file"),
            trigger=trigger,
            schedule_project_root=getattr(args, "project_root", None),
            timezone_name=getattr(args, "timezone", "Asia/Shanghai"),
            enabled=not bool(getattr(args, "disabled", False)),
            timeout_seconds=getattr(args, "timeout_seconds", None),
            run_name=getattr(args, "run_name", None),
            replace=bool(getattr(args, "replace", False)),
        )
        print(f"已写入 schedule：{result['schedule']['id']}")
        return 0
    if schedule_command == "remove":
        result = schedule_manager.remove_schedule(project_root, getattr(args, "id"))
        print(f"已删除 schedule：{result['id']}")
        return 0
    if schedule_command == "enable":
        result = schedule_manager.set_schedule_enabled(project_root, getattr(args, "id"), True)
        print(f"已启用 schedule：{result['schedule']['id']}")
        return 0
    if schedule_command == "disable":
        result = schedule_manager.set_schedule_enabled(project_root, getattr(args, "id"), False)
        print(f"已禁用 schedule：{result['schedule']['id']}")
        return 0
    if schedule_command == "run-now":
        result = schedule_manager.run_schedule_now(project_root, getattr(args, "id"))
        if bool(getattr(args, "json", False)):
            print_json(result)
        elif result.get("ok"):
            print(f"schedule 运行结果 {result.get('status')}：{result.get('output_dir')}")
        else:
            print(f"schedule 运行失败：{result.get('error')}")
        return 0 if result.get("ok") else 1
    if schedule_command == "daemon":
        result = schedule_manager.run_schedule_daemon(
            project_root,
            poll_seconds=float(getattr(args, "poll_seconds", 60.0)),
            once=bool(getattr(args, "once", False)),
        )
        if bool(getattr(args, "json", False)):
            print_json(result)
        elif bool(getattr(args, "once", False)):
            ran = result.get("last_result", {}).get("ran", [])
            print(f"schedule daemon 扫描完成：运行 {len(ran)} 个 schedule")
        return 0 if result.get("ok") else 1
    return None


def _print_schedule_list(result: dict[str, object]) -> None:
    schedules = result.get("schedules", [])
    if not schedules:
        print("暂无 schedule。")
        return
    for index, schedule in enumerate(schedules, start=1):
        trigger = schedule.get("trigger", {}) if isinstance(schedule, dict) else {}
        if isinstance(trigger, dict) and trigger.get("type") == "daily":
            trigger_text = f"daily@{trigger.get('at')}"
        elif isinstance(trigger, dict) and trigger.get("type") == "interval":
            trigger_text = f"interval/{trigger.get('every_seconds')}s"
        else:
            trigger_text = str(trigger)
        state = schedule.get("state", {}) if isinstance(schedule, dict) else {}
        last_status = state.get("last_status", "") if isinstance(state, dict) else ""
        print(
            f"{index:02d}. {schedule.get('id')} "
            f"| enabled={schedule.get('enabled')} "
            f"| trigger={trigger_text} "
            f"| next={schedule.get('next_run_at') or '-'} "
            f"| last={last_status or '-'}"
        )


def _run_cplan_plan_command(project_root: Path, args: object) -> int | None:
    command = str(getattr(args, "cplan_command", "") or "")
    if command == "list":
        print_plan_list(project_root, getattr(args, "filter", "") or "")
        return 0
    if command == "create":
        package_dir = create_plan_package(
            getattr(args, "path"),
            project_root=project_root,
            automation_type=getattr(args, "automation_type"),
            name=getattr(args, "name", None),
            force=bool(getattr(args, "force", False)),
        )
        print(f"已创建 plan 包：{package_dir}")
        return 0
    if command == "validate":
        return print_validation_result(getattr(args, "file"), project_root)
    if command == "run":
        result_code = print_validation_result(getattr(args, "file"), project_root)
        if result_code != 0:
            return result_code
        plan_result = run_plan(
            getattr(args, "file"),
            project_root,
            run_name=getattr(args, "run_name", None),
            output_dir=getattr(args, "output_dir", None),
            variable_overrides={},
            manual_confirmation_handler=_confirm_cplan_manual_confirmation,
            inspection_confirmation_handler=_confirm_post_run_inspection,
        )
        print(f"计划运行结果 {plan_result.status}：{plan_result.output_dir}")
        return 0 if plan_result.status == "passed" else 1
    if command == "debug-create":
        workspace = create_debug_workspace(getattr(args, "file"), project_root, name=getattr(args, "name", None))
        print(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if command == "debug-prepare":
        result = prepare_failure_debug_workspace(
            project_root,
            getattr(args, "file"),
            analyze_latest_run_failure=_analyze_latest_run_failure_for_cplan,
            validate_plan=_validate_plan_for_cplan,
            output_dir=getattr(args, "output_dir", None),
            name=getattr(args, "name", None),
            include_manual_confirm=bool(getattr(args, "manual_confirm", False)),
            recommended_next_actions=CPLAN_DEBUG_NEXT_ACTIONS,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if command == "debug-inject":
        result = inject_debug_steps(
            getattr(args, "workspace"),
            presets=getattr(args, "preset"),
            message=getattr(args, "message", None),
            browser=getattr(args, "browser", None),
            page=getattr(args, "page", None),
            desktop=getattr(args, "desktop", None),
            position=getattr(args, "position", "end"),
            step=getattr(args, "step", None),
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if command == "debug-patch":
        result = generate_debug_patch(getattr(args, "workspace"))
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.patch_path.exists():
            print(result.patch_path.read_text(encoding="utf-8"))
        return 0
    if command == "debug-apply":
        result = apply_debug_patch(getattr(args, "workspace"), yes=bool(getattr(args, "yes", False)))
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    return None


def _is_cplan_invocation(argv: list[str] | None) -> bool:
    if argv is not None:
        return False
    return Path(sys.argv[0]).stem.lower() == "cplan"


def _cli_error_surface(argv: list[str] | None) -> str:
    return "cplan" if _is_cplan_invocation(argv) else "ai"


def _confirm_cplan_manual_confirmation(prompt: str) -> bool:
    return _confirm_cplan_wait(prompt, wait_type="manual_confirm")


def _confirm_post_run_inspection(prompt: str) -> bool:
    return _confirm_cplan_wait(prompt, wait_type="post_run_inspection")


def _confirm_cplan_wait(prompt: str, *, wait_type: str) -> bool:
    label = "人工确认" if wait_type == "manual_confirm" else "运行后检查"
    text = str(prompt or "").strip()
    if text:
        print(text)
    while True:
        answer = input(f"cplan {label}：输入 y 继续/确认，输入 n 停止/拒绝 > ")
        decision = _parse_cplan_wait_answer(answer)
        if decision is not None:
            return decision
        print("无法识别输入。cplan 是确定性管理命令，这里只接受 y 或 n。")


def _analyze_latest_run_failure_for_cplan(
    plan_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    log_lines: int = 80,
    event_lines: int = 80,
) -> dict[str, object]:
    from ai_automate_contro.debug.run_failure_analysis import analyze_latest_run_failure_tool

    return analyze_latest_run_failure_tool(
        _resolve_plan_path_for_cplan,
        _resolve_run_output_dir_for_cplan,
        plan_path,
        output_dir=output_dir,
        log_lines=log_lines,
        event_lines=event_lines,
    )


def _validate_plan_for_cplan(project_root: str | Path, plan_path: str | Path) -> dict[str, object]:
    result = validate_plan_file(plan_path, project_root)
    return {
        "ok": result.ok,
        "plan_path": str(result.plan_path),
        "errors": [
            {
                "path": issue.location,
                "message": issue.message,
                "formatted": issue.format(),
            }
            for issue in result.errors
        ],
    }


def _resolve_plan_path_for_cplan(raw_plan_path: str | Path) -> Path:
    plan_path = path_from_text(raw_plan_path).resolve()
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"
    return plan_path


def _resolve_run_output_dir_for_cplan(plan_path: str | Path, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return path_from_text(output_dir).resolve()
    resolved_plan_path = _resolve_plan_path_for_cplan(plan_path)
    latest_output = find_latest_run_output(resolved_plan_path.parent)
    if latest_output is None:
        return resolved_plan_path.parent / "output"
    return latest_output


def _parse_cplan_wait_answer(answer: str) -> bool | None:
    normalized = str(answer or "").strip().lower()
    if normalized == "y":
        return True
    if normalized == "n":
        return False
    return None


def _print_ai_ask_event_jsonl(event: object) -> None:
    payload = {
        "event": getattr(event, "kind", ""),
        "title": getattr(event, "title", ""),
        "text": getattr(event, "text", ""),
        "data": getattr(event, "data", {}),
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)
