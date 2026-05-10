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
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        app = ManagementTerminal(project_root)
        app.cmdloop()
        return 0

    if args.command == "ai":
        from ai_automate_contro.ai.terminal import AITerminal

        app = AITerminal(project_root, service=args.service, thread_id=args.thread)
        app.cmdloop()
        return 0

    if args.command == "self-check":
        if args.self_check_command == "ai-stream":
            from ai_automate_contro.ai.response_parsing import self_check_chat_completion_stream_parser

            result = self_check_chat_completion_stream_parser()
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
            print(f"created plan package: {package_dir}")
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
            )
            print(f"plan {plan_result.status}: {plan_result.output_dir}")
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
            try:
                result = apply_debug_patch(args.workspace, yes=args.yes)
            except Exception as error:
                print(f"ERROR {error}")
                return 1
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
