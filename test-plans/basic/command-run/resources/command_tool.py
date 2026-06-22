from __future__ import annotations

import json
import sys


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    stdin_value = sys.stdin.read()
    sys.stderr.write("command-tool-ok\n")
    print(json.dumps({"arg": arg, "stdin": stdin_value, "combined": f"{arg}:{stdin_value}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
