from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from keygen_automation.cli import run_cli


def main() -> None:
    raise SystemExit(run_cli(PROJECT_ROOT))


if __name__ == "__main__":
    main()
