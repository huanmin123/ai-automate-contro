from __future__ import annotations

from datetime import date, datetime
import re
import time
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
            raise KeyError(f"变量未定义：{source}")
        executor.state.variables[target] = executor.state.variables[source]
        executor.state.logger.log("info", "variable copied", source=source, target=target)
        return
    raise ValueError(f"不支持的 variable type：{variable_type}")


def action_manual_confirm(executor: Any, step: dict[str, Any]) -> None:
    prompt = step.get("prompt", "Continue? Input y to proceed: ")
    _ensure_manual_confirm_has_visible_browser_if_needed(executor, step)
    if executor.state.manual_confirmation_handler is not None:
        executor.state.logger.log("info", "waiting for manual confirmation", prompt=str(prompt))
        executor.state.state_writer.mark_waiting(prompt=str(prompt))
        accepted = executor.state.manual_confirmation_handler(str(prompt))
        if not accepted:
            raise RuntimeError("人工确认未通过。")
        executor.state.state_writer.mark_resumed()
        executor.state.logger.log("info", "manual confirmation accepted", prompt=str(prompt))
        return
    answer = input(prompt).strip().lower()
    if answer != "y":
        raise RuntimeError("人工确认未通过。")


def _ensure_manual_confirm_has_visible_browser_if_needed(executor: Any, step: dict[str, Any]) -> None:
    sessions = getattr(getattr(executor, "state", None), "sessions", {})
    target_browser = str(step.get("browser") or "").strip()
    if not sessions:
        if target_browser:
            raise RuntimeError(f"manual_confirm 指定了 browser={target_browser}，但当前没有浏览器会话。")
        return
    if target_browser:
        session = sessions.get(target_browser)
        if session is None:
            session_names = ", ".join(str(name) for name in sessions.keys())
            raise RuntimeError(
                f"manual_confirm 指定的浏览器会话不存在：{target_browser}。当前会话：{session_names}。"
            )
        if bool(getattr(session, "headed", False)):
            return
        raise RuntimeError(
            "manual_confirm 需要同一个可见 Playwright 浏览器窗口。"
            f"指定浏览器 {target_browser} 不是 headed=true。"
            "请把对应 open_browser.headed 设置为 true。"
        )
    if len(sessions) > 1:
        session_names = ", ".join(str(name) for name in sessions.keys())
        raise RuntimeError(
            "manual_confirm 前已有多个浏览器会话，无法确定用户应操作哪一个窗口。"
            f"当前会话：{session_names}。请在 manual_confirm.browser 显式指定目标浏览器，并确保它 headed=true。"
        )
    only_session = next(iter(sessions.values()))
    if bool(getattr(only_session, "headed", False)):
        return
    session_names = ", ".join(str(name) for name in sessions.keys())
    raise RuntimeError(
        "manual_confirm 需要同一个可见 Playwright 浏览器窗口。"
        f"当前已有浏览器会话但都不是 headed=true：{session_names}。"
        "请把对应 open_browser.headed 设置为 true，或在没有浏览器会话的纯命令行确认流程中使用 manual_confirm。"
    )


def action_print(executor: Any, step: dict[str, Any]) -> None:
    executor.state.logger.log("info", str(step["message"]))


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
    value = files.read_file(executor, step)
    executor.state.variables[step["save_as"]] = value
    path = executor._resolve_path(step["path"])
    executor.state.logger.log("info", "file read", type=file_type, path=str(path), save_as=step["save_as"])


def action_table(executor: Any, step: dict[str, Any]) -> None:
    table_type = step["type"]
    source = step["source"]
    if not isinstance(source, list):
        raise ValueError("table.source 必须是数组。")

    if table_type == "filter":
        result = _table_filter(source, step.get("where", {}))
    elif table_type == "select":
        result = _table_select(source, step["columns"], step.get("rename", {}))
    elif table_type == "sort":
        result = _table_sort(source, step["by"], step.get("descending", False))
    elif table_type == "dedupe":
        result = _table_dedupe(source, step["by"], str(step.get("keep", "first")))
    elif table_type == "group":
        result = _table_group(source, step["by"], step["aggregations"])
    elif table_type == "join":
        result = _table_join(source, step["right"], step)
    elif table_type == "add_column":
        result = _table_add_columns(source, step["columns"])
    elif table_type == "rename":
        result = _table_rename(source, step["columns"])
    elif table_type == "fill_empty":
        result = _table_fill_empty(source, step["values"])
    elif table_type == "type_convert":
        result = _table_type_convert(source, step["columns"])
    elif table_type == "pivot":
        result = _table_pivot(source, step)
    elif table_type == "replace":
        result = _table_replace(source, step)
    elif table_type == "split_column":
        result = _table_split_column(source, step)
    elif table_type == "merge_columns":
        result = _table_merge_columns(source, step)
    elif table_type == "date_parse":
        result = _table_date_parse(source, step)
    elif table_type == "lookup":
        result = _table_lookup(source, step)
    else:
        raise ValueError(f"不支持的 table type：{table_type}")

    executor.state.variables[step["save_as"]] = result
    executor.state.logger.log("info", "table processed", type=table_type, rows=len(result), save_as=step["save_as"])


def _table_filter(rows: list[Any], where: Any) -> list[Any]:
    if not isinstance(where, dict):
        raise ValueError("table.filter.where 必须是对象。")
    return [row for row in rows if _table_row_matches(row, where)]


def _table_row_matches(row: Any, where: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        raise ValueError("table.filter 当前只支持字典行。")
    for field, expected in where.items():
        actual = row.get(field)
        if not _table_value_matches(actual, expected):
            return False
    return True


def _table_value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        for operator, operand in expected.items():
            if not _table_operator_matches(actual, str(operator), operand):
                return False
        return True
    return actual == expected


def _table_operator_matches(actual: Any, operator: str, operand: Any) -> bool:
    if operator in {"eq", "equals"}:
        return actual == operand
    if operator in {"ne", "not_equals"}:
        return actual != operand
    if operator == "contains":
        return str(operand) in str(actual or "")
    if operator == "not_contains":
        return str(operand) not in str(actual or "")
    if operator == "in":
        return isinstance(operand, list) and actual in operand
    if operator == "not_in":
        return isinstance(operand, list) and actual not in operand
    if operator == "empty":
        return _table_is_empty(actual) is bool(operand)
    if operator == "not_empty":
        return _table_is_empty(actual) is not bool(operand)
    if operator in {"gt", "gte", "lt", "lte"}:
        return _compare_table_values(actual, operand, operator)
    raise ValueError(f"不支持的 table.filter 操作符：{operator}")


def _compare_table_values(actual: Any, operand: Any, operator: str) -> bool:
    left = _table_comparable(actual)
    right = _table_comparable(operand)
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    return left <= right


def _table_select(rows: list[Any], columns: Any, rename: Any) -> list[Any]:
    if not isinstance(columns, list) or not all(isinstance(column, str) and column for column in columns):
        raise ValueError("table.select.columns 必须是非空字符串数组。")
    if rename in (None, ""):
        rename = {}
    if not isinstance(rename, dict):
        raise ValueError("table.select.rename 必须是对象。")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.select 当前只支持字典行。")
        selected: dict[str, Any] = {}
        for column in columns:
            selected[str(rename.get(column, column))] = row.get(column)
        result.append(selected)
    return result


def _table_sort(rows: list[Any], by: Any, descending: Any) -> list[Any]:
    columns = _table_columns(by, "table.sort.by")
    descending_flags = _table_descending_flags(descending, len(columns))

    result = list(rows)
    for column, reverse in reversed(list(zip(columns, descending_flags))):
        result.sort(key=lambda row, key=column: _table_sort_key(row, key), reverse=reverse)
    return result


def _table_dedupe(rows: list[Any], by: Any, keep: str) -> list[Any]:
    columns = _table_columns(by, "table.dedupe.by")
    if keep not in {"first", "last"}:
        raise ValueError("table.dedupe.keep 只能是 first 或 last。")
    iterable = rows if keep == "first" else list(reversed(rows))
    seen: set[tuple[Any, ...]] = set()
    result: list[Any] = []
    for row in iterable:
        key = tuple(_table_row_value(row, column) for column in columns)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    if keep == "last":
        result.reverse()
    return result


def _table_group(rows: list[Any], by: Any, aggregations: Any) -> list[dict[str, Any]]:
    columns = _table_columns(by, "table.group.by")
    if not isinstance(aggregations, dict) or not aggregations:
        raise ValueError("table.group.aggregations 必须是非空对象。")

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.group 当前只支持字典行。")
        key = tuple(row.get(column) for column in columns)
        grouped.setdefault(key, []).append(row)

    result: list[dict[str, Any]] = []
    for key, group_rows in grouped.items():
        output = {column: value for column, value in zip(columns, key)}
        for output_column, raw_spec in aggregations.items():
            if not isinstance(output_column, str) or not output_column:
                raise ValueError("table.group.aggregations 的输出列名必须是非空字符串。")
            operator, source_column = _table_aggregation_spec(raw_spec)
            output[output_column] = _table_aggregate(group_rows, operator, source_column)
        result.append(output)
    return result


def _table_join(rows: list[Any], right_rows: Any, step: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(right_rows, list):
        raise ValueError("table.join.right 必须是数组。")
    how = str(step.get("how", "inner"))
    if how not in {"inner", "left"}:
        raise ValueError("table.join.how 只能是 inner 或 left。")
    left_columns, right_columns = _table_join_columns(step)
    right_prefix = str(step.get("right_prefix", "right_"))

    index: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in right_rows:
        if not isinstance(row, dict):
            raise ValueError("table.join.right 当前只支持字典行。")
        key = tuple(row.get(column) for column in right_columns)
        index.setdefault(key, []).append(row)

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.join.source 当前只支持字典行。")
        key = tuple(row.get(column) for column in left_columns)
        matches = index.get(key, [])
        if matches:
            for right_row in matches:
                result.append(_table_join_merge(row, right_row, right_columns, right_prefix))
        elif how == "left":
            result.append(dict(row))
    return result


def _table_add_columns(rows: list[Any], columns: Any) -> list[dict[str, Any]]:
    if not isinstance(columns, dict) or not columns:
        raise ValueError("table.add_column.columns 必须是非空对象。")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.add_column 当前只支持字典行。")
        output = dict(row)
        for column, spec in columns.items():
            if not isinstance(column, str) or not column:
                raise ValueError("table.add_column.columns 的列名必须是非空字符串。")
            output[column] = _table_add_column_value(row, spec)
        result.append(output)
    return result


def _table_rename(rows: list[Any], columns: Any) -> list[dict[str, Any]]:
    if not isinstance(columns, dict) or not columns:
        raise ValueError("table.rename.columns 必须是非空对象。")
    rename_map = _table_string_mapping(columns, "table.rename.columns")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.rename 当前只支持字典行。")
        output = dict(row)
        for old_name, new_name in rename_map.items():
            if old_name not in output:
                continue
            output[new_name] = output.pop(old_name) if new_name != old_name else output[old_name]
        result.append(output)
    return result


def _table_fill_empty(rows: list[Any], values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, dict) or not values:
        raise ValueError("table.fill_empty.values 必须是非空对象。")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.fill_empty 当前只支持字典行。")
        output = dict(row)
        for column, default in values.items():
            if not isinstance(column, str) or not column:
                raise ValueError("table.fill_empty.values 的列名必须是非空字符串。")
            if _table_is_empty(output.get(column)):
                output[column] = default
        result.append(output)
    return result


def _table_type_convert(rows: list[Any], columns: Any) -> list[dict[str, Any]]:
    if not isinstance(columns, dict) or not columns:
        raise ValueError("table.type_convert.columns 必须是非空对象。")
    conversions = _table_string_mapping(columns, "table.type_convert.columns")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.type_convert 当前只支持字典行。")
        output = dict(row)
        for column, target_type in conversions.items():
            output[column] = _table_convert_value(output.get(column), target_type, column)
        result.append(output)
    return result


def _table_pivot(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    index_columns = _table_columns(step["index"], "table.pivot.index")
    pivot_column = str(step["columns"])
    if not pivot_column:
        raise ValueError("table.pivot.columns 必须是非空字符串。")
    has_value_column = "values" in step and not _table_is_empty(step.get("values"))
    value_column = str(step.get("values")) if has_value_column else "*"
    agg = str(step.get("agg") or ("sum" if has_value_column else "count"))
    if agg not in {"count", "sum", "avg", "min", "max"}:
        raise ValueError("table.pivot.agg 只能是 count、sum、avg、min 或 max。")
    if not has_value_column and agg != "count":
        raise ValueError("table.pivot 使用 sum、avg、min 或 max 时必须提供 values。")
    fill_value = step.get("fill_value", 0)

    grouped: dict[tuple[Any, ...], dict[str, list[dict[str, Any]]]] = {}
    pivot_values: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.pivot 当前只支持字典行。")
        key = tuple(row.get(column) for column in index_columns)
        pivot_value = str(row.get(pivot_column, ""))
        if pivot_value not in pivot_values:
            pivot_values.append(pivot_value)
        grouped.setdefault(key, {}).setdefault(pivot_value, []).append(row)

    result: list[dict[str, Any]] = []
    for key, pivot_groups in grouped.items():
        output = {column: value for column, value in zip(index_columns, key)}
        for pivot_value in pivot_values:
            group_rows = pivot_groups.get(pivot_value, [])
            output[pivot_value] = _table_aggregate(group_rows, agg, value_column) if group_rows else fill_value
        result.append(output)
    return result


def _table_replace(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    column_replacements = step.get("columns", {})
    global_replacements = step.get("values", {})
    if not isinstance(column_replacements, dict):
        raise ValueError("table.replace.columns 必须是对象。")
    if not isinstance(global_replacements, dict):
        raise ValueError("table.replace.values 必须是对象。")
    if not column_replacements and not global_replacements:
        raise ValueError("table.replace 需要 columns 或 values 至少一个非空对象。")

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.replace 当前只支持字典行。")
        output = dict(row)
        for column, value in list(output.items()):
            output[column] = _table_replacement_value(value, global_replacements)
        for column, replacements in column_replacements.items():
            if not isinstance(column, str) or not column:
                raise ValueError("table.replace.columns 的列名必须是非空字符串。")
            if not isinstance(replacements, dict):
                raise ValueError("table.replace.columns 每列替换规则必须是对象。")
            output[column] = _table_replacement_value(output.get(column), replacements)
        result.append(output)
    return result


def _table_split_column(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    column = str(step["column"])
    output_columns = _table_columns(step["into"], "table.split_column.into")
    separator = step.get("separator")
    regex = bool(step.get("regex", False))
    maxsplit = int(step.get("maxsplit", len(output_columns) - 1))
    remove_source = bool(step.get("remove_source", False))
    if not isinstance(separator, str) or separator == "":
        raise ValueError("table.split_column.separator 必须是非空字符串。")

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.split_column 当前只支持字典行。")
        output = dict(row)
        text = "" if row.get(column) is None else str(row.get(column))
        parts = re.split(separator, text, maxsplit=maxsplit) if regex else text.split(separator, maxsplit)
        padded = [*parts[: len(output_columns)], *[""] * max(0, len(output_columns) - len(parts))]
        for output_column, value in zip(output_columns, padded):
            output[output_column] = value
        if remove_source:
            output.pop(column, None)
        result.append(output)
    return result


def _table_merge_columns(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    columns = _table_columns(step["columns"], "table.merge_columns.columns")
    output_column = str(step["into"])
    if not output_column:
        raise ValueError("table.merge_columns.into 必须是非空字符串。")
    separator = str(step.get("separator", ""))
    skip_empty = bool(step.get("skip_empty", False))
    remove_sources = bool(step.get("remove_sources", False))

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.merge_columns 当前只支持字典行。")
        output = dict(row)
        values = ["" if row.get(column) is None else str(row.get(column)) for column in columns]
        if skip_empty:
            values = [value for value in values if value.strip()]
        output[output_column] = separator.join(values)
        if remove_sources:
            for column in columns:
                if column != output_column:
                    output.pop(column, None)
        result.append(output)
    return result


def _table_date_parse(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    columns = _table_date_columns(step["columns"])
    output_format = str(step.get("output_format", "iso"))
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.date_parse 当前只支持字典行。")
        output = dict(row)
        for column, formats in columns.items():
            value = output.get(column)
            output[column] = None if _table_is_empty(value) else _format_table_date(_parse_table_date(value, formats, column), output_format)
        result.append(output)
    return result


def _table_lookup(rows: list[Any], step: dict[str, Any]) -> list[dict[str, Any]]:
    right_rows = step["right"]
    if not isinstance(right_rows, list):
        raise ValueError("table.lookup.right 必须是数组。")
    left_columns, right_columns = _table_join_columns(step)
    value_map = _table_lookup_value_map(step.get("values"), right_rows, right_columns)
    default_value = step.get("default")

    index: dict[tuple[Any, ...], dict[str, Any]] = {}
    for right_row in right_rows:
        if not isinstance(right_row, dict):
            raise ValueError("table.lookup.right 当前只支持字典行。")
        key = tuple(right_row.get(column) for column in right_columns)
        index.setdefault(key, right_row)

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("table.lookup.source 当前只支持字典行。")
        output = dict(row)
        match = index.get(tuple(row.get(column) for column in left_columns))
        for right_column, output_column in value_map.items():
            output[output_column] = match.get(right_column, default_value) if match is not None else default_value
        result.append(output)
    return result


def _table_aggregation_spec(raw_spec: Any) -> tuple[str, str]:
    if not isinstance(raw_spec, dict) or len(raw_spec) != 1:
        raise ValueError("table.group.aggregations 每个聚合必须是只包含一个操作符的对象。")
    operator, source_column = next(iter(raw_spec.items()))
    operator = str(operator)
    if operator not in {"count", "sum", "avg", "min", "max"}:
        raise ValueError(f"不支持的 table.group 聚合操作符：{operator}")
    if operator == "count" and source_column == "*":
        return operator, "*"
    if not isinstance(source_column, str) or not source_column:
        raise ValueError("table.group 聚合源列必须是非空字符串，count 可使用 \"*\"。")
    return operator, source_column


def _table_aggregate(rows: list[dict[str, Any]], operator: str, source_column: str) -> Any:
    if operator == "count":
        if source_column == "*":
            return len(rows)
        return sum(0 if _table_is_empty(row.get(source_column)) else 1 for row in rows)

    values = [_table_number(row.get(source_column), source_column) for row in rows if not _table_is_empty(row.get(source_column))]
    if not values:
        return None
    if operator == "sum":
        return _table_normalize_number(sum(values))
    if operator == "avg":
        return _table_normalize_number(sum(values) / len(values))
    if operator == "min":
        return _table_normalize_number(min(values))
    if operator == "max":
        return _table_normalize_number(max(values))
    raise ValueError(f"不支持的 table.group 聚合操作符：{operator}")


def _table_join_columns(step: dict[str, Any]) -> tuple[list[str], list[str]]:
    if "on" in step:
        columns = _table_columns(step["on"], "table.join.on")
        return columns, columns
    left_columns = _table_columns(step.get("left_on"), "table.join.left_on")
    right_columns = _table_columns(step.get("right_on"), "table.join.right_on")
    if len(left_columns) != len(right_columns):
        raise ValueError("table.join.left_on 和 right_on 长度必须一致。")
    return left_columns, right_columns


def _table_join_merge(left: dict[str, Any], right: dict[str, Any], right_key_columns: list[str], right_prefix: str) -> dict[str, Any]:
    output = dict(left)
    for column, value in right.items():
        if column in right_key_columns:
            continue
        target_column = column
        if target_column in output:
            target_column = f"{right_prefix}{column}"
        output[target_column] = value
    return output


def _table_add_column_value(row: dict[str, Any], spec: Any) -> Any:
    if not isinstance(spec, dict):
        return spec
    if "value" in spec:
        return spec["value"]
    if "copy" in spec:
        return row.get(str(spec["copy"]))
    if "format" in spec:
        template = str(spec["format"])
        return re.sub(r"\{([^{}]+)\}", lambda match: str(row.get(match.group(1), "")), template)
    if "sum" in spec:
        columns = _table_columns(spec["sum"], "table.add_column.columns[].sum")
        total = sum(_table_number(row.get(column), column) for column in columns)
        return _table_normalize_number(total)
    raise ValueError("table.add_column.columns 每个对象必须包含 value、copy、format 或 sum 之一。")


def _table_string_mapping(value: dict[Any, Any], field_name: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} 必须是非空字符串到非空字符串的对象。")
        result[key] = item
    return result


def _table_replacement_value(value: Any, replacements: dict[Any, Any]) -> Any:
    try:
        if value in replacements:
            return replacements[value]
    except TypeError:
        pass
    text = str(value)
    if text in replacements:
        return replacements[text]
    return value


def _table_date_columns(value: Any) -> dict[str, list[str]]:
    if isinstance(value, str) and value:
        return {value: []}
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return {item: [] for item in value}
    if isinstance(value, dict) and value:
        result: dict[str, list[str]] = {}
        for column, formats in value.items():
            if not isinstance(column, str) or not column:
                raise ValueError("table.date_parse.columns 的列名必须是非空字符串。")
            if isinstance(formats, str) and formats:
                result[column] = [formats]
            elif isinstance(formats, list) and all(isinstance(item, str) and item for item in formats):
                result[column] = list(formats)
            elif formats in (None, ""):
                result[column] = []
            else:
                raise ValueError("table.date_parse.columns 的格式必须是字符串或字符串数组。")
        return result
    raise ValueError("table.date_parse.columns 必须是非空字符串、字符串数组或对象。")


def _parse_table_date(value: Any, formats: list[str], column: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        raise ValueError(f"table.date_parse 日期列为空：{column}")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"table.date_parse 无法解析日期列：{column}")


def _format_table_date(value: datetime, output_format: str) -> str:
    if output_format == "iso":
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat()
    return value.strftime(output_format)


def _table_lookup_value_map(value: Any, right_rows: list[Any], right_key_columns: list[str]) -> dict[str, str]:
    if value in (None, ""):
        columns: list[str] = []
        for row in right_rows:
            if isinstance(row, dict):
                columns = [column for column in row if column not in right_key_columns]
                break
        return {column: column for column in columns}
    if isinstance(value, str) and value:
        return {value: value}
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return {item: item for item in value}
    if isinstance(value, dict) and value:
        return _table_string_mapping(value, "table.lookup.values")
    raise ValueError("table.lookup.values 必须是非空字符串、字符串数组或对象。")


def _table_columns(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return list(value)
    raise ValueError(f"{field_name} 必须是非空字符串或非空字符串数组。")


def _table_descending_flags(value: Any, count: int) -> list[bool]:
    if isinstance(value, bool):
        return [value] * count
    if isinstance(value, list) and len(value) == count and all(isinstance(item, bool) for item in value):
        return list(value)
    raise ValueError("table.sort.descending 必须是布尔值，或长度与 by 一致的布尔数组。")


def _table_sort_key(row: Any, column: str) -> tuple[int, Any]:
    value = _table_row_value(row, column)
    if value is None or value == "":
        return (1, "")
    return (0, _table_comparable(value))


def _table_row_value(row: Any, column: str) -> Any:
    if not isinstance(row, dict):
        raise ValueError("table 当前只支持字典行。")
    return row.get(column)


def _table_comparable(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return str(value)


def _table_number(value: Any, column: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"table 数字计算列不是数字：{column}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError as error:
            raise ValueError(f"table 数字计算列不是数字：{column}") from error
    raise ValueError(f"table 数字计算列为空或不是数字：{column}")


def _table_convert_value(value: Any, target_type: str, column: str) -> Any:
    normalized_type = target_type.lower()
    if _table_is_empty(value):
        return None
    if normalized_type in {"str", "string", "text"}:
        return str(value)
    if normalized_type in {"int", "integer"}:
        return int(_table_number(value, column))
    if normalized_type in {"float", "number"}:
        return _table_normalize_number(_table_number(value, column))
    if normalized_type in {"bool", "boolean"}:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "是", "真"}:
            return True
        if text in {"false", "0", "no", "n", "否", "假"}:
            return False
        raise ValueError(f"table.type_convert 无法把列转换为 bool：{column}")
    raise ValueError(f"不支持的 table.type_convert 目标类型：{target_type}")


def _table_normalize_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _table_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


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
    if assert_type == "attribute":
        assertions.assert_attribute(executor, step)
        return
    if assert_type == "css":
        assertions.assert_css(executor, step)
        return
    if assert_type == "checked":
        assertions.assert_checked(executor, step)
        return
    if assert_type == "unchecked":
        assertions.assert_unchecked(executor, step)
        return
    if assert_type == "enabled":
        assertions.assert_enabled(executor, step)
        return
    if assert_type == "disabled":
        assertions.assert_disabled(executor, step)
        return
    if assert_type == "visible":
        assertions.assert_visible(executor, step)
        return
    if assert_type == "hidden":
        assertions.assert_hidden(executor, step)
        return
    if assert_type == "title":
        assertions.assert_title(executor, step)
        return
    raise ValueError(f"不支持的 assert type：{assert_type}")


def action_sleep(executor: Any, step: dict[str, Any]) -> None:
    seconds = float(step.get("seconds", 1))
    if executor.state.sessions:
        first_session = next(iter(executor.state.sessions.values()))
        executor._wait_for_timeout(first_session.require_page(), int(seconds * 1000))
        return
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        checker = getattr(executor.state, "interrupt_requested", None)
        if callable(checker) and checker():
            raise KeyboardInterrupt("用户中断。")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.2))


ACTION_HANDLERS = {
    "assert": action_assert,
    "manual_confirm": action_manual_confirm,
    "print": action_print,
    "read": action_read,
    "sleep": action_sleep,
    "table": action_table,
    "variable": action_variable,
    "write": action_write,
}
