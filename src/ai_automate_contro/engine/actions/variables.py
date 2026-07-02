from __future__ import annotations

from typing import Any


RESERVED_OUTPUT_VARIABLES = {"last"}


def action_variable(executor: Any, step: dict[str, Any]) -> None:
    variable_type = step["type"]
    if variable_type == "set":
        name = step["name"]
        _ensure_variable_target_allowed(name)
        value = step["value"]
        executor.state.variables[name] = value
        executor.state.logger.log("info", "variable set", name=name, value=value)
        return
    if variable_type == "set_many":
        values = step["values"]
        for key, value in values.items():
            _ensure_variable_target_allowed(str(key))
            executor.state.variables[key] = value
        executor.state.logger.log("info", "variables set", names=list(values.keys()))
        return
    if variable_type == "copy":
        source = step["source"]
        target = step["target"]
        _ensure_variable_target_allowed(target)
        if source not in executor.state.variables:
            raise KeyError(f"变量未定义：{source}")
        executor.state.variables[target] = executor.state.variables[source]
        executor.state.logger.log("info", "variable copied", source=source, target=target)
        return
    raise ValueError(f"不支持的 variable type：{variable_type}")


def _ensure_variable_target_allowed(name: str) -> None:
    if str(name) in RESERVED_OUTPUT_VARIABLES:
        raise ValueError(f"{name} 是保留输出变量，只能由 output 发布器维护。")
