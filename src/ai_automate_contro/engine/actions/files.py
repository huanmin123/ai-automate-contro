from __future__ import annotations

import csv
import json
from typing import Any


def write_json_file(executor: Any, raw_path: str, value: Any, *, category: str = "json", indent: int = 2) -> None:
    output_path = executor._resolve_output_path(raw_path, category=category)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=indent)
    executor.state.logger.log("info", "json written", path=str(output_path))


def write_text_file(executor: Any, raw_path: str, content: str, *, append: bool) -> None:
    output_path = executor._resolve_output_path(raw_path, category="text")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with output_path.open(mode, encoding="utf-8") as file:
        file.write(content)
    log_message = "text appended" if append else "text written"
    executor.state.logger.log("info", log_message, path=str(output_path))


def write_csv_file(executor: Any, raw_path: str, rows: list[Any], headers: list[str] | None = None) -> None:
    output_path = executor._resolve_output_path(raw_path, category="csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        if headers:
            writer = csv.writer(file)
            writer.writerow(headers)
            for row in rows:
                if isinstance(row, dict):
                    writer.writerow([row.get(header, "") for header in headers])
                else:
                    writer.writerow(row)
        elif not rows:
            file.write("")
        elif isinstance(rows[0], dict):
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        else:
            writer = csv.writer(file)
            writer.writerows(rows)
    executor.state.logger.log("info", "csv written", path=str(output_path))


def read_file(executor: Any, step: dict[str, Any]) -> Any:
    file_type = step["type"]
    path = executor._resolve_path(step["path"])
    if file_type == "json":
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    if file_type == "text":
        with path.open("r", encoding="utf-8") as file:
            content = file.read()
        if step.get("split_lines", False):
            return [line.strip() for line in content.splitlines() if line.strip()]
        return content
    if file_type == "csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return list(reader)
    if file_type == "storage_state":
        return str(path)
    raise ValueError(f"Unsupported read type: {file_type}")
