from __future__ import annotations

from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output

from . import files


def action_write(executor: Any, step: dict[str, Any]) -> None:
    file_type = step["type"]
    if file_type == "json":
        files.write_json_file(executor, step["path"], step["value"], indent=int(step.get("indent", 2)))
        return
    if file_type == "text":
        files.write_text_file(executor, step["path"], step["value"], append=bool(step.get("append", False)))
        return
    if file_type == "csv":
        files.write_csv_file(executor, step["path"], step["value"], step.get("headers"))
        return
    if file_type == "excel":
        files.write_excel_file(executor, step)
        return
    if file_type == "variables":
        files.write_json_file(
            executor,
            step["path"],
            executor.state.variables,
            category="variables",
            indent=int(step.get("indent", 2)),
        )
        return
    raise ValueError(f"不支持的 write type：{file_type}")


def action_read(executor: Any, step: dict[str, Any]) -> None:
    file_type = step["type"]
    meta: dict[str, Any] | None = None
    if file_type == "excel":
        path = executor._resolve_path(step["path"])
        value, meta = files.read_excel_file(path, step)
    else:
        value = files.read_file(executor, step)
    publish_step_output(executor, step, value, action="read")
    if meta is not None:
        _publish_read_meta(executor, step, meta)
    path = executor._resolve_path(step["path"])
    executor.state.logger.log(
        "info",
        "file read",
        type=file_type,
        path=str(path),
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
    )


def _publish_read_meta(executor: Any, step: dict[str, Any], meta: dict[str, Any]) -> None:
    output = step.get("output")
    if not isinstance(output, dict) or not isinstance(output.get("as"), str) or not output.get("as"):
        return
    names = _read_meta_variable_names(output["as"])
    for name in names:
        executor.state.variables[name] = meta
    executor.state.variables["last_meta"] = meta
    executor.state.logger.log("info", "read metadata published", action="read", name=names[0], aliases=names[1:])


def _read_meta_variable_names(output_name: str) -> list[str]:
    names = [f"{output_name}_meta"]
    for suffix in ("_rows", "_workbook"):
        if output_name.endswith(suffix) and len(output_name) > len(suffix):
            alias = f"{output_name[: -len(suffix)]}_meta"
            if alias not in names:
                names.append(alias)
    return names
