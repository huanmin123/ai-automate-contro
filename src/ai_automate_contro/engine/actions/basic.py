from __future__ import annotations

from typing import Any

from . import assertions, files


def action_variable(executor: Any, step: dict[str, Any]) -> None:
    variable_type = step["type"]
    if variable_type == "set":
        name = step["name"]
        value = step["value"]
        executor.state.variables[name] = value
        executor.state.logger.log("info", "variable set", name=name, value=value)
        return
    if variable_type == "set_many":
        values = step["values"]
        for key, value in values.items():
            executor.state.variables[key] = value
        executor.state.logger.log("info", "variables set", names=list(values.keys()))
        return
    if variable_type == "copy":
        source = step["source"]
        target = step["target"]
        if source not in executor.state.variables:
            raise KeyError(f"Variable '{source}' is not defined.")
        executor.state.variables[target] = executor.state.variables[source]
        executor.state.logger.log("info", "variable copied", source=source, target=target)
        return
    raise ValueError(f"Unsupported variable type: {variable_type}")


def action_manual_confirm(executor: Any, step: dict[str, Any]) -> None:
    prompt = step.get("prompt", "Continue? Input y to proceed: ")
    if executor.state.manual_confirmation_handler is not None:
        executor.state.logger.log("info", "waiting for manual confirmation", prompt=str(prompt))
        executor.state.state_writer.mark_waiting(prompt=str(prompt))
        accepted = executor.state.manual_confirmation_handler(str(prompt))
        if not accepted:
            raise RuntimeError("Manual confirmation was not accepted.")
        executor.state.state_writer.mark_resumed()
        executor.state.logger.log("info", "manual confirmation accepted", prompt=str(prompt))
        return
    answer = input(prompt).strip().lower()
    if answer != "y":
        raise RuntimeError("Manual confirmation was not accepted.")


def action_print(executor: Any, step: dict[str, Any]) -> None:
    executor.state.logger.log("info", str(step["message"]))


def action_write(executor: Any, step: dict[str, Any]) -> None:
    file_type = step["type"]
    if file_type == "json":
        files.write_json_file(executor, step["path"], step["value"], indent=int(step.get("indent", 2)))
        return
    if file_type == "text":
        files.write_text_file(executor, step["path"], str(step["value"]), append=bool(step.get("append", False)))
        return
    if file_type == "csv":
        files.write_csv_file(executor, step["path"], step["value"], step.get("headers"))
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
    raise ValueError(f"Unsupported write type: {file_type}")


def action_read(executor: Any, step: dict[str, Any]) -> None:
    file_type = step["type"]
    value = files.read_file(executor, step)
    executor.state.variables[step["save_as"]] = value
    path = executor._resolve_path(step["path"])
    executor.state.logger.log("info", "file read", type=file_type, path=str(path), save_as=step["save_as"])


def action_assert(executor: Any, step: dict[str, Any]) -> None:
    assert_type = step["type"]
    if assert_type == "selector":
        assertions.assert_selector(executor, step)
        return
    if assert_type == "text":
        assertions.assert_text(executor, step)
        return
    if assert_type == "value":
        assertions.assert_value(executor, step)
        return
    if assert_type == "url":
        assertions.assert_url(executor, step)
        return
    if assert_type == "count":
        assertions.assert_count(executor, step)
        return
    raise ValueError(f"Unsupported assert type: {assert_type}")


def action_sleep(executor: Any, step: dict[str, Any]) -> None:
    if executor.state.sessions:
        first_session = next(iter(executor.state.sessions.values()))
        first_session.require_page().wait_for_timeout(int(float(step.get("seconds", 1)) * 1000))
        return
    raise RuntimeError("sleep requires at least one opened browser session in current version.")


ACTION_HANDLERS = {
    "assert": action_assert,
    "manual_confirm": action_manual_confirm,
    "print": action_print,
    "read": action_read,
    "sleep": action_sleep,
    "variable": action_variable,
    "write": action_write,
}
