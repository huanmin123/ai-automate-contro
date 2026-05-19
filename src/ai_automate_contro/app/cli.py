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
from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    create_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
)
from ai_automate_contro.plans.packages import (
    create_plan_package,
)


def run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    try:
        if _is_cplan_invocation(argv):
            return _run_cplan_cli(project_root, argv)
        return _run_cli(project_root, argv)
    except KeyboardInterrupt as error:
        return print_cli_error(error, project_root=project_root)
    except Exception as error:
        return print_cli_error(error, project_root=project_root)


def _run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        from ai_automate_contro.client import run_textual_client

        run_textual_client(project_root)
        return 0

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
        return print_cli_error(error, project_root=project_root)
    except Exception as error:
        return print_cli_error(error, project_root=project_root)


def _run_cplan_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_cplan_parser()
    args = parser.parse_args(argv)

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
        if args.self_check_command == "browser-components":
            from ai_automate_contro.app.browser_component_check import self_check_browser_components

            result = self_check_browser_components(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1

    plan_command_result = _run_cplan_plan_command(project_root, args)
    if plan_command_result is not None:
        return plan_command_result

    parser.print_help()
    return 1


def _run_cplan_plan_command(project_root: Path, args: object) -> int | None:
    command = str(getattr(args, "cplan_command", "") or "")
    if command == "list":
        print_plan_list(project_root, getattr(args, "filter", "") or "")
        return 0
    if command == "create":
        package_dir = create_plan_package(
            getattr(args, "path"),
            project_root=project_root,
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
        return 0
    if command == "debug-create":
        workspace = create_debug_workspace(getattr(args, "file"), project_root, name=getattr(args, "name", None))
        print(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if command == "debug-prepare":
        from ai_automate_contro.ai.terminal_tools import prepare_failure_debug_workspace_tool

        result = prepare_failure_debug_workspace_tool(
            project_root,
            getattr(args, "file"),
            output_dir=getattr(args, "output_dir", None),
            name=getattr(args, "name", None),
            include_manual_confirm=bool(getattr(args, "manual_confirm", False)),
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
