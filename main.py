from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from keygen_automation.executor import execute_plan
from keygen_automation.plan_loader import detect_document_type, load_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Playwright automation plan described in JSON.")
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a plan.json file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = load_plan(args.file)
    document_type = detect_document_type(document)
    if document_type == "plan":
        execute_plan(document, PROJECT_ROOT, plan_path=args.file)
        return


if __name__ == "__main__":
    main()
