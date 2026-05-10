from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage and run JSON automation plan packages.",
    )

    subparsers = parser.add_subparsers(dest="command")
    plan_parser = subparsers.add_parser("plan", help="Manage plan packages.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command")

    tool_parser = subparsers.add_parser("tool", help="Call structured AI terminal tools.")
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command")
    tool_subparsers.add_parser("list", help="List available structured tools.")
    tool_subparsers.add_parser("check", help="Validate structured tool registry wiring.")
    tool_schema_parser = tool_subparsers.add_parser("schema", help="Print one structured tool JSON schema.")
    tool_schema_parser.add_argument("name", help="Tool name.")
    tool_call_parser = tool_subparsers.add_parser("call", help="Call one structured tool and print JSON.")
    tool_call_parser.add_argument("name", help="Tool name.")
    tool_call_parser.add_argument("--args-json", default="{}", help="Tool arguments as a JSON object.")
    tool_call_parser.add_argument("--args-file", help="Read tool arguments from a JSON file.")
    tool_call_parser.add_argument("--compact", action="store_true", help="Print compact JSON.")

    ai_parser = subparsers.add_parser("ai", help="Start the persistent AI terminal.")
    ai_parser.add_argument("--service", default="default", help="AI service name from test-plans/config.json.")
    ai_parser.add_argument("--thread", default="default", help="Persistent AI terminal thread id.")

    self_check_parser = subparsers.add_parser("self-check", help="Run deterministic local self-checks.")
    self_check_subparsers = self_check_parser.add_subparsers(dest="self_check_command")
    self_check_subparsers.add_parser("ai-stream", help="Check local chat completions streaming parsing.")
    self_check_subparsers.add_parser("ai-tools", help="Check LangChain StructuredTool wiring.")

    list_parser = plan_subparsers.add_parser("list", help="List plan packages.")
    list_parser.add_argument("filter", nargs="?", help="Optional text filter.")

    create_parser = plan_subparsers.add_parser("create", help="Create a plan package template.")
    create_parser.add_argument("--path", required=True, help="Plan package directory to create.")
    create_parser.add_argument("--name", help="Plan name written into plan.json.")
    create_parser.add_argument("--force", action="store_true", help="Allow using an existing non-empty package directory.")

    validate_parser = plan_subparsers.add_parser("validate", help="Validate a plan package.")
    validate_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")

    run_parser = plan_subparsers.add_parser("run", help="Run a plan package.")
    run_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    run_parser.add_argument("--run-name", help="Override the run name used for output directory naming.")
    run_parser.add_argument(
        "--output-dir",
        help="Override the run output directory. Must stay inside the plan package output/ directory.",
    )

    debug_parser = plan_subparsers.add_parser("debug-create", help="Create an isolated debug workspace for a plan package.")
    debug_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    debug_parser.add_argument("--name", help="Debug workspace name suffix.")

    prepare_parser = plan_subparsers.add_parser("debug-prepare", help="Create a debug workspace from the latest failed run and inject diagnostics.")
    prepare_parser.add_argument("--file", required=True, help="Path to the package entry plan.json.")
    prepare_parser.add_argument("--output-dir", help="Specific failed run output directory. Defaults to latest run.")
    prepare_parser.add_argument("--name", help="Debug workspace name suffix.")
    prepare_parser.add_argument("--manual-confirm", action="store_true", help="Inject a manual confirmation checkpoint before the failed step.")

    fix_parser = plan_subparsers.add_parser("debug-fix", help="Propose or apply a clean fix candidate inside a debug workspace.")
    fix_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    fix_parser.add_argument("--hint", default="", help="Optional user hint used to rank fix candidates.")
    fix_parser.add_argument("--apply", action="store_true", help="Write the selected fix candidate to injected-plan/.")
    fix_parser.add_argument("--run", action="store_true", help="Run the debug plan after applying the candidate.")
    fix_parser.add_argument("--run-name", help="Override debug run name when --run is used.")

    inject_parser = plan_subparsers.add_parser("debug-inject", help="Inject diagnostic steps into an existing debug workspace.")
    inject_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    inject_parser.add_argument(
        "--preset",
        action="append",
        required=True,
        choices=["print", "variables", "manual_confirm", "screenshot", "html"],
        help="Diagnostic preset to inject. May be repeated.",
    )
    inject_parser.add_argument("--message", help="Message used by print/manual_confirm presets.")
    inject_parser.add_argument("--browser", help="Browser session name for screenshot/html presets.")
    inject_parser.add_argument("--page", help="Page name for screenshot/html presets.")
    inject_parser.add_argument("--position", choices=["start", "end", "before_step", "after_step"], default="end", help="Where to inject steps.")
    inject_parser.add_argument("--step", type=int, help="1-based anchor step for before_step or after_step.")

    patch_parser = plan_subparsers.add_parser("debug-patch", help="Generate patch.diff from a debug workspace.")
    patch_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")

    apply_parser = plan_subparsers.add_parser("debug-apply", help="Apply patch.diff from a debug workspace to the original plan package.")
    apply_parser.add_argument("--workspace", required=True, help="Path to output/debug/<run> workspace.")
    apply_parser.add_argument("--yes", action="store_true", help="Required confirmation to modify the original plan package.")

    return parser
