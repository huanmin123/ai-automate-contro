from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    lines = sys.stdin.read().splitlines()
    if len(lines) < 3:
        raise RuntimeError("expected upload sha256, download path and label on stdin")
    upload_sha256, download_path_text, label = lines[:3]
    download_path = Path(download_path_text)
    content = download_path.read_bytes()
    rows = list(csv.DictReader(content.decode("utf-8").splitlines()))
    result = {
        "processed": bool(upload_sha256) and label == "combo" and rows and rows[0].get("name") == "combo",
        "upload_sha256": upload_sha256,
        "download_sha256": hashlib.sha256(content).hexdigest(),
        "rows": len(rows),
        "label": label,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
