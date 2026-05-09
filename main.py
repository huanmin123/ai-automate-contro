from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from keygen_automation.executor import execute_plan
from keygen_automation.filters import parse_tag_text
from keygen_automation.plan_loader import detect_document_type, load_plan
from keygen_automation.suite import execute_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Playwright automation plan or suite described in JSON."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a JSON plan or suite file.",
    )
    parser.add_argument(
        "--include-tags",
        default="",
        help="Comma-separated tags to include when running a suite.",
    )
    parser.add_argument(
        "--exclude-tags",
        default="",
        help="Comma-separated tags to exclude when running a suite.",
    )
    parser.add_argument(
        "--tag-mode",
        choices=["any", "all"],
        default="any",
        help="How include tags should match suite items.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = load_plan(args.file)
    document_type = detect_document_type(document)
    if document_type == "plan":
        execute_plan(document, PROJECT_ROOT, plan_path=args.file)
        return
    cli_include_tags = parse_tag_text(args.include_tags)
    cli_exclude_tags = parse_tag_text(args.exclude_tags)
    if cli_include_tags:
        document["include_tags"] = cli_include_tags
    if cli_exclude_tags:
        document["exclude_tags"] = cli_exclude_tags
    document["tag_mode"] = args.tag_mode
    execute_suite(document, PROJECT_ROOT, args.file)


if __name__ == "__main__":
    main()
