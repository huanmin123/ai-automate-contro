from __future__ import annotations

import json
from pathlib import Path


from ai_automate_contro.ai.terminal_tool_registry import (
    call_ai_terminal_tool,
    check_ai_terminal_tool_registry,
    describe_ai_terminal_tool,
    list_ai_terminal_tools,
)
from ai_automate_contro.app.command_helpers import (
    load_tool_arguments,
    print_json,
    print_plan_list,
    print_validation_result,
    run_plan,
)
from ai_automate_contro.app.errors import print_cli_error
from ai_automate_contro.app.parser import build_parser
from ai_automate_contro.app.management_terminal import ManagementTerminal
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
        return _run_cli(project_root, argv)
    except KeyboardInterrupt as error:
        return print_cli_error(error, project_root=project_root)
    except Exception as error:
        return print_cli_error(error, project_root=project_root)


def _run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        app = ManagementTerminal(project_root)
        app.cmdloop()
        return 0

    if args.command == "ai":
        from ai_automate_contro.ai.terminal import AITerminal

        app = AITerminal(project_root, service=args.service, thread_id=args.thread)
        try:
            if args.ai_command == "ask":
                result = app.ask_once(args.message)
                if args.json:
                    print_json(result, compact=args.compact)
                else:
                    assistant_message = result.get("assistant_message") or ""
                    if assistant_message:
                        print(assistant_message)
                    if result.get("pending_approval"):
                        print("[等待审批] 当前需要人工审批。请进入交互终端后输入 approve，或输入 reject <原因>。")
                return 0 if result.get("ok") else 1
            terminal = ManagementTerminal(project_root)
            terminal._ai_terminal = app
            terminal.mode = "ai"
            terminal.prompt = "ai> "
            terminal.intro = "AI 自动化控制终端。当前已进入 AI 模式；输入 /help 查看 AI 命令，输入 /exit 或 /back 返回 plan 模式，输入 /quit 退出。"
            terminal.cmdloop()
            app = None
            return 0
        finally:
            if app is not None:
                app.close()

    if args.command == "self-check":
        if args.self_check_command == "env":
            from ai_automate_contro.app.environment_check import self_check_environment

            result = self_check_environment(project_root)
            print_json(result)
            return 0 if result.get("ok") else 1
        if args.self_check_command == "runtime":
            from ai_automate_contro.app.environment_check import self_check_runtime_config

            result = self_check_runtime_config(project_root)
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

    if args.command == "plan":
        if args.plan_command == "list":
            print_plan_list(project_root, args.filter or "")
            return 0
        if args.plan_command == "create":
            package_dir = create_plan_package(
                args.path,
                project_root=project_root,
                name=args.name,
                force=args.force,
            )
            print(f"已创建 plan 包：{package_dir}")
            return 0
        if args.plan_command == "validate":
            return print_validation_result(args.file, project_root)
        if args.plan_command == "run":
            result_code = print_validation_result(args.file, project_root)
            if result_code != 0:
                return result_code
            plan_result = run_plan(
                args.file,
                project_root,
                run_name=args.run_name,
                output_dir=args.output_dir,
                variable_overrides={},
                inspection_confirmation_handler=_confirm_post_run_inspection,
            )
            print(f"计划运行结果 {plan_result.status}：{plan_result.output_dir}")
            return 0
        if args.plan_command == "debug-create":
            workspace = create_debug_workspace(args.file, project_root, name=args.name)
            print(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-prepare":
            result = call_ai_terminal_tool(
                "prepare_failure_debug_workspace",
                project_root,
                {
                    "plan_path": args.file,
                    "output_dir": args.output_dir,
                    "name": args.name,
                    "include_manual_confirm": args.manual_confirm,
                },
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-fix":
            result = call_ai_terminal_tool(
                "propose_debug_fix",
                project_root,
                {
                    "workspace": args.workspace,
                    "user_hint": args.hint,
                    "apply": args.apply,
                    "run_after_apply": args.run,
                    "run_name": args.run_name,
                },
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-inject":
            result = inject_debug_steps(
                args.workspace,
                presets=args.preset,
                message=args.message,
                browser=args.browser,
                page=args.page,
                position=args.position,
                step=args.step,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.plan_command == "debug-patch":
            result = generate_debug_patch(args.workspace)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            if result.patch_path.exists():
                print(result.patch_path.read_text(encoding="utf-8"))
            return 0
        if args.plan_command == "debug-apply":
            result = apply_debug_patch(args.workspace, yes=args.yes)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0

    if args.command == "tool":
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


def _confirm_post_run_inspection(prompt: str) -> bool:
    print(prompt, end="", flush=True)
    input()
    return True
