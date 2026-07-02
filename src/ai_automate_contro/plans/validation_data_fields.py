from __future__ import annotations

from typing import Any

from ai_automate_contro.plans.validation_field_helpers import (
    EXCEL_A1_RE,
    TABLE_ADD_COLUMN_OPERATORS,
    TABLE_AGGREGATION_OPERATORS,
    TABLE_FILTER_OPERATORS,
    TABLE_TYPE_CONVERT_TYPES,
    _is_template,
    _validate_a1_cell,
    _validate_a1_range,
    _validate_a1_write_range,
    _validate_bool,
    _validate_dict,
    _validate_enum,
    _validate_int,
    _validate_list,
    _validate_number,
    _validate_nonempty_string_list,
    _validate_sheet_field,
    _validate_string,
    _validate_string_or_nonempty_string_list,
)
from ai_automate_contro.plans.validation_models import ValidationIssue


def _validate_read_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "text":
        _validate_bool(step, "split_lines", location, issues)
        return
    if step_type != "excel":
        return
    _validate_sheet_field(step, "sheet", location, issues)
    _validate_list(step, "sheets", location, issues)
    _validate_a1_range(step, "range", location, issues)
    _validate_int(step, "header_row", location, issues, minimum=1)
    _validate_nonempty_string_list(step, "headers", location, issues)
    _validate_bool(step, "skip_blank_rows", location, issues)
    _validate_int(step, "max_rows", location, issues, minimum=1)
    _validate_int(step, "max_cells", location, issues, minimum=1)
    _validate_int(step, "preview_rows", location, issues, minimum=1)
    _validate_int(step, "offset_rows", location, issues, minimum=0)
    _validate_int(step, "limit_rows", location, issues, minimum=1)
    _validate_enum(step, "mode", {"records", "matrix", "cells"}, location, issues)
    _validate_enum(step, "formula_mode", {"cached", "formula"}, location, issues)
    _validate_enum(step, "date_format", {"iso", "text"}, location, issues)
    sheets = step.get("sheets")
    if isinstance(sheets, list) and not _is_template(sheets):
        if not sheets:
            issues.append(ValidationIssue(location, "sheets 必须是非空数组"))
        for index, sheet in enumerate(sheets):
            _validate_excel_read_sheet(sheet, f"{location}.sheets[{index}]", issues)


def _validate_write_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "json":
        _validate_int(step, "indent", location, issues, minimum=0)
        return
    if step_type == "variables":
        _validate_int(step, "indent", location, issues, minimum=0)
        return
    if step_type == "text":
        _validate_bool(step, "append", location, issues)
        return
    if step_type == "csv":
        _validate_nonempty_string_list(step, "headers", location, issues)
        return
    if step_type != "excel":
        return
    _validate_sheet_field(step, "sheet", location, issues)
    _validate_a1_cell(step, "start_cell", location, issues)
    _validate_a1_write_range(step, "range", location, issues)
    _validate_string(step, "named_range", location, issues)
    _validate_string(step, "template_path", location, issues)
    _validate_string(step, "table_name", location, issues)
    _validate_nonempty_string_list(step, "headers", location, issues)
    _validate_dict(step, "formula_columns", location, issues)
    _validate_dict(step, "cells", location, issues)
    _validate_list(step, "sheets", location, issues)
    _validate_dict(step, "number_format", location, issues)
    _validate_dict(step, "column_widths", location, issues)
    _validate_bool(step, "include_header", location, issues)
    _validate_bool(step, "freeze_header", location, issues)
    _validate_bool(step, "auto_filter", location, issues)
    _validate_bool(step, "table", location, issues)
    _validate_bool(step, "copy_row_style", location, issues)
    _validate_bool(step, "extend_conditional_formatting", location, issues)
    _validate_int(step, "style_source_row", location, issues, minimum=1)
    _validate_enum(step, "write_mode", {"create", "replace_sheet", "append_rows", "overlay_cells"}, location, issues)
    _validate_string(step, "date_format", location, issues)
    _validate_excel_cells(step.get("cells"), location, "cells", issues)
    _validate_excel_formula_columns(step.get("formula_columns"), location, "formula_columns", issues)
    if "named_range" in step and "range" in step:
        issues.append(ValidationIssue(location, "write.type=excel.named_range 不能和 range 同时使用"))
    sheets = step.get("sheets")
    if isinstance(sheets, list) and not _is_template(sheets):
        if not sheets:
            issues.append(ValidationIssue(location, "sheets 必须是非空数组"))
        for index, sheet in enumerate(sheets):
            _validate_excel_write_sheet(sheet, f"{location}.sheets[{index}]", issues)


def _validate_excel_write_sheet(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "sheets 每一项必须是对象"))
        return
    _validate_sheet_field(value, "sheet", location, issues)
    _validate_a1_cell(value, "start_cell", location, issues)
    _validate_a1_write_range(value, "range", location, issues)
    _validate_string(value, "named_range", location, issues)
    _validate_nonempty_string_list(value, "headers", location, issues)
    _validate_dict(value, "formula_columns", location, issues)
    _validate_dict(value, "cells", location, issues)
    _validate_dict(value, "number_format", location, issues)
    _validate_dict(value, "column_widths", location, issues)
    _validate_bool(value, "include_header", location, issues)
    _validate_bool(value, "freeze_header", location, issues)
    _validate_bool(value, "auto_filter", location, issues)
    _validate_bool(value, "table", location, issues)
    _validate_bool(value, "copy_row_style", location, issues)
    _validate_bool(value, "extend_conditional_formatting", location, issues)
    _validate_int(value, "style_source_row", location, issues, minimum=1)
    _validate_string(value, "table_name", location, issues)
    _validate_enum(value, "write_mode", {"create", "replace_sheet", "append_rows", "overlay_cells"}, location, issues)
    _validate_excel_cells(value.get("cells"), location, "cells", issues)
    _validate_excel_formula_columns(value.get("formula_columns"), location, "formula_columns", issues)
    if "named_range" in value and "range" in value:
        issues.append(ValidationIssue(location, "write.type=excel.named_range 不能和 range 同时使用"))
    if not any(field in value for field in ("value", "rows", "cells")):
        issues.append(ValidationIssue(location, "sheets 每一项需要 value、rows 或 cells 之一"))


def _validate_excel_read_sheet(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, (str, int)):
        temp_step = {"sheet": value}
        _validate_sheet_field(temp_step, "sheet", location, issues)
        return
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "sheets 每一项必须是 sheet 名称、索引或读取配置对象"))
        return
    if "sheet" not in value:
        issues.append(ValidationIssue(location, "sheets 配置对象缺少必填字段：sheet"))
    _validate_string(value, "name", location, issues)
    _validate_sheet_field(value, "sheet", location, issues)
    _validate_a1_range(value, "range", location, issues)
    _validate_int(value, "header_row", location, issues, minimum=1)
    _validate_nonempty_string_list(value, "headers", location, issues)
    _validate_bool(value, "skip_blank_rows", location, issues)
    _validate_int(value, "max_rows", location, issues, minimum=1)
    _validate_int(value, "max_cells", location, issues, minimum=1)
    _validate_int(value, "preview_rows", location, issues, minimum=1)
    _validate_int(value, "offset_rows", location, issues, minimum=0)
    _validate_int(value, "limit_rows", location, issues, minimum=1)
    _validate_enum(value, "mode", {"records", "matrix", "cells"}, location, issues)
    _validate_enum(value, "formula_mode", {"cached", "formula"}, location, issues)
    _validate_enum(value, "date_format", {"iso", "text"}, location, issues)


def _validate_excel_cells(value: Any, location: str, field: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        return
    for address in value:
        if not isinstance(address, str) or not EXCEL_A1_RE.match(address):
            issues.append(ValidationIssue(location, f"{field} 的 key 必须是 A1 单元格地址：{address}"))


def _validate_excel_formula_columns(value: Any, location: str, field: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or value in (None, ""):
        return
    if not isinstance(value, dict):
        return
    if not value:
        issues.append(ValidationIssue(location, f"{field} 必须是非空对象"))
        return
    for column, spec in value.items():
        if not isinstance(column, str) or not column:
            issues.append(ValidationIssue(location, f"{field} 的列名必须是非空字符串"))
            continue
        if isinstance(spec, str) and spec:
            continue
        if isinstance(spec, dict) and isinstance(spec.get("formula"), str) and spec["formula"]:
            continue
        issues.append(ValidationIssue(location, f"{field}.{column} 必须是公式字符串或包含 formula 的对象"))


def _validate_table_fields(
    step: dict[str, Any],
    step_type: Any,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    if step_type == "filter":
        _validate_dict(step, "where", location, issues)
        where = step.get("where")
        if isinstance(where, dict):
            for field, condition in where.items():
                if not isinstance(field, str) or not field:
                    issues.append(ValidationIssue(location, "table.filter.where 的字段名必须是非空字符串"))
                if isinstance(condition, dict):
                    for operator in condition:
                        if operator not in TABLE_FILTER_OPERATORS:
                            allowed = ", ".join(sorted(TABLE_FILTER_OPERATORS))
                            issues.append(ValidationIssue(location, f"table.filter 操作符不支持：{operator}；可选值：{allowed}"))
        return
    if step_type == "select":
        _validate_nonempty_string_list(step, "columns", location, issues)
        _validate_dict(step, "rename", location, issues)
        rename = step.get("rename")
        if isinstance(rename, dict):
            for key, value in rename.items():
                if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
                    issues.append(ValidationIssue(location, "table.select.rename 必须是源列名到目标列名的非空字符串对象"))
        return
    if step_type in {"sort", "dedupe"}:
        _validate_string_or_nonempty_string_list(step, "by", location, issues)
    if step_type == "sort":
        value = step.get("descending")
        if value is not None and not _is_template(value):
            if isinstance(value, bool):
                return
            if isinstance(value, list) and all(isinstance(item, bool) for item in value):
                by = step.get("by")
                if isinstance(by, list) and len(value) != len(by):
                    issues.append(ValidationIssue(location, "table.sort.descending 数组长度必须与 by 一致"))
                return
            issues.append(ValidationIssue(location, "table.sort.descending 必须是布尔值或布尔数组"))
        return
    if step_type == "dedupe":
        _validate_enum(step, "keep", {"first", "last"}, location, issues)
        return
    if step_type == "group":
        _validate_string_or_nonempty_string_list(step, "by", location, issues)
        _validate_dict(step, "aggregations", location, issues)
        aggregations = step.get("aggregations")
        if isinstance(aggregations, dict):
            if not aggregations:
                issues.append(ValidationIssue(location, "table.group.aggregations 必须是非空对象"))
            for output_column, spec in aggregations.items():
                if not isinstance(output_column, str) or not output_column:
                    issues.append(ValidationIssue(location, "table.group.aggregations 的输出列名必须是非空字符串"))
                _validate_table_aggregation_spec(spec, location, issues)
        return
    if step_type == "join":
        _validate_list(step, "right", location, issues)
        _validate_string_or_nonempty_string_list(step, "on", location, issues)
        _validate_string_or_nonempty_string_list(step, "left_on", location, issues)
        _validate_string_or_nonempty_string_list(step, "right_on", location, issues)
        _validate_enum(step, "how", {"inner", "left"}, location, issues)
        _validate_string(step, "right_prefix", location, issues)
        if "on" not in step and not ("left_on" in step and "right_on" in step):
            issues.append(ValidationIssue(location, "table.join 需要 on，或同时提供 left_on 和 right_on"))
        if "on" in step and ("left_on" in step or "right_on" in step):
            issues.append(ValidationIssue(location, "table.join 不能同时使用 on 和 left_on/right_on"))
        left_on = step.get("left_on")
        right_on = step.get("right_on")
        if isinstance(left_on, list) and isinstance(right_on, list) and len(left_on) != len(right_on):
            issues.append(ValidationIssue(location, "table.join.left_on 和 right_on 长度必须一致"))
        return
    if step_type == "add_column":
        _validate_dict(step, "columns", location, issues)
        columns = step.get("columns")
        if isinstance(columns, dict):
            if not columns:
                issues.append(ValidationIssue(location, "table.add_column.columns 必须是非空对象"))
            for output_column, spec in columns.items():
                if not isinstance(output_column, str) or not output_column:
                    issues.append(ValidationIssue(location, "table.add_column.columns 的列名必须是非空字符串"))
                _validate_table_add_column_spec(spec, location, issues)
        return
    if step_type == "rename":
        _validate_dict(step, "columns", location, issues)
        _validate_string_mapping(step.get("columns"), location, "table.rename.columns", issues)
        return
    if step_type == "fill_empty":
        _validate_dict(step, "values", location, issues)
        values = step.get("values")
        if isinstance(values, dict):
            if not values:
                issues.append(ValidationIssue(location, "table.fill_empty.values 必须是非空对象"))
            for column in values:
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.fill_empty.values 的列名必须是非空字符串"))
        return
    if step_type == "type_convert":
        _validate_dict(step, "columns", location, issues)
        columns = step.get("columns")
        if isinstance(columns, dict):
            if not columns:
                issues.append(ValidationIssue(location, "table.type_convert.columns 必须是非空对象"))
            for column, target_type in columns.items():
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.type_convert.columns 的列名必须是非空字符串"))
                if not isinstance(target_type, str) or target_type not in TABLE_TYPE_CONVERT_TYPES:
                    allowed = ", ".join(sorted(TABLE_TYPE_CONVERT_TYPES))
                    issues.append(ValidationIssue(location, f"table.type_convert 目标类型不支持：{target_type}；可选值：{allowed}"))
        return
    if step_type == "pivot":
        _validate_string_or_nonempty_string_list(step, "index", location, issues)
        _validate_string(step, "columns", location, issues)
        _validate_string(step, "values", location, issues)
        _validate_enum(step, "agg", TABLE_AGGREGATION_OPERATORS, location, issues)
        agg = step.get("agg", "sum" if step.get("values") else "count")
        if agg != "count" and not step.get("values"):
            issues.append(ValidationIssue(location, "table.pivot 使用 sum、avg、min 或 max 时必须提供 values"))
        return
    if step_type == "replace":
        _validate_dict(step, "columns", location, issues)
        _validate_dict(step, "values", location, issues)
        columns = step.get("columns")
        values = step.get("values")
        if not columns and not values:
            issues.append(ValidationIssue(location, "table.replace 需要 columns 或 values 至少一个非空对象"))
        if isinstance(columns, dict):
            for column, replacements in columns.items():
                if not isinstance(column, str) or not column:
                    issues.append(ValidationIssue(location, "table.replace.columns 的列名必须是非空字符串"))
                if not isinstance(replacements, dict) or not replacements:
                    issues.append(ValidationIssue(location, "table.replace.columns 每列替换规则必须是非空对象"))
        return
    if step_type == "split_column":
        _validate_string(step, "column", location, issues)
        _validate_string_or_nonempty_string_list(step, "into", location, issues)
        _validate_string(step, "separator", location, issues)
        _validate_bool(step, "regex", location, issues)
        _validate_int(step, "maxsplit", location, issues, minimum=0)
        _validate_bool(step, "remove_source", location, issues)
        return
    if step_type == "merge_columns":
        _validate_string_or_nonempty_string_list(step, "columns", location, issues)
        _validate_string(step, "into", location, issues)
        if "separator" in step and not _is_template(step["separator"]) and not isinstance(step["separator"], str):
            issues.append(ValidationIssue(location, "table.merge_columns.separator 必须是字符串"))
        _validate_bool(step, "skip_empty", location, issues)
        _validate_bool(step, "remove_sources", location, issues)
        return
    if step_type == "date_parse":
        _validate_table_date_parse_columns(step.get("columns"), location, issues)
        _validate_string(step, "output_format", location, issues)
        return
    if step_type == "lookup":
        _validate_list(step, "right", location, issues)
        _validate_string_or_nonempty_string_list(step, "on", location, issues)
        _validate_string_or_nonempty_string_list(step, "left_on", location, issues)
        _validate_string_or_nonempty_string_list(step, "right_on", location, issues)
        _validate_table_lookup_values(step.get("values"), location, issues)
        if "on" not in step and not ("left_on" in step and "right_on" in step):
            issues.append(ValidationIssue(location, "table.lookup 需要 on，或同时提供 left_on 和 right_on"))
        if "on" in step and ("left_on" in step or "right_on" in step):
            issues.append(ValidationIssue(location, "table.lookup 不能同时使用 on 和 left_on/right_on"))
        left_on = step.get("left_on")
        right_on = step.get("right_on")
        if isinstance(left_on, list) and isinstance(right_on, list) and len(left_on) != len(right_on):
            issues.append(ValidationIssue(location, "table.lookup.left_on 和 right_on 长度必须一致"))
        return
    if step_type == "normalize_headers":
        _validate_dict(step, "columns", location, issues)
        _validate_enum(step, "case", {"keep", "lower", "upper", "snake"}, location, issues)
        _validate_string(step, "separator", location, issues)
        _validate_bool(step, "strip", location, issues)
        _validate_string_mapping(step.get("columns"), location, "table.normalize_headers.columns", issues)
        return
    if step_type == "union":
        _validate_list(step, "sources", location, issues)
        _validate_string_or_nonempty_string_list(step, "columns", location, issues)
        return
    if step_type == "fuzzy_lookup":
        _validate_list(step, "right", location, issues)
        _validate_string_or_nonempty_string_list(step, "on", location, issues)
        _validate_string_or_nonempty_string_list(step, "left_on", location, issues)
        _validate_string_or_nonempty_string_list(step, "right_on", location, issues)
        _validate_table_lookup_values(step.get("values"), location, issues)
        _validate_number(step, "threshold", location, issues)
        _validate_bool(step, "ignore_case", location, issues)
        _validate_bool(step, "trim", location, issues)
        _validate_bool(step, "ignore_spaces", location, issues)
        _validate_string(step, "score_column", location, issues)
        if "on" not in step and not ("left_on" in step and "right_on" in step):
            issues.append(ValidationIssue(location, "table.fuzzy_lookup 需要 on，或同时提供 left_on 和 right_on"))
        if "on" in step and ("left_on" in step or "right_on" in step):
            issues.append(ValidationIssue(location, "table.fuzzy_lookup 不能同时使用 on 和 left_on/right_on"))
        left_on = step.get("left_on")
        right_on = step.get("right_on")
        if isinstance(left_on, list) and isinstance(right_on, list) and len(left_on) != len(right_on):
            issues.append(ValidationIssue(location, "table.fuzzy_lookup.left_on 和 right_on 长度必须一致"))
        threshold = step.get("threshold")
        if isinstance(threshold, (int, float)) and not 0 <= threshold <= 1:
            issues.append(ValidationIssue(location, "table.fuzzy_lookup.threshold 必须在 0 到 1 之间"))


def _validate_table_aggregation_spec(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value):
        return
    if not isinstance(value, dict) or len(value) != 1:
        issues.append(ValidationIssue(location, "table.group.aggregations 每个值必须是只包含一个操作符的对象"))
        return
    operator, source_column = next(iter(value.items()))
    if operator not in TABLE_AGGREGATION_OPERATORS:
        allowed = ", ".join(sorted(TABLE_AGGREGATION_OPERATORS))
        issues.append(ValidationIssue(location, f"table.group 聚合操作符不支持：{operator}；可选值：{allowed}"))
    if source_column == "*" and operator == "count":
        return
    if not isinstance(source_column, str) or not source_column:
        issues.append(ValidationIssue(location, "table.group 聚合源列必须是非空字符串，count 可使用 *"))


def _validate_table_date_parse_columns(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value):
        return
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return
    if isinstance(value, dict) and value:
        for column, formats in value.items():
            if not isinstance(column, str) or not column:
                issues.append(ValidationIssue(location, "table.date_parse.columns 的列名必须是非空字符串"))
            if isinstance(formats, str) and formats:
                continue
            if isinstance(formats, list) and all(isinstance(item, str) and item for item in formats):
                continue
            if formats in (None, ""):
                continue
            issues.append(ValidationIssue(location, "table.date_parse.columns 的格式必须是字符串或字符串数组"))
        return
    issues.append(ValidationIssue(location, "table.date_parse.columns 必须是非空字符串、字符串数组或对象"))


def _validate_table_lookup_values(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or value in (None, ""):
        return
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return
    if isinstance(value, dict) and value:
        _validate_string_mapping(value, location, "table.lookup.values", issues)
        return
    issues.append(ValidationIssue(location, "table.lookup.values 必须是非空字符串、字符串数组或对象"))


def _validate_string_mapping(value: Any, location: str, field_name: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, dict):
        return
    if not value:
        issues.append(ValidationIssue(location, f"{field_name} 必须是非空对象"))
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
            issues.append(ValidationIssue(location, f"{field_name} 必须是非空字符串到非空字符串的对象"))


def _validate_table_add_column_spec(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if _is_template(value) or not isinstance(value, dict):
        return
    operators = [operator for operator in TABLE_ADD_COLUMN_OPERATORS if operator in value]
    if len(operators) != 1:
        allowed = ", ".join(sorted(TABLE_ADD_COLUMN_OPERATORS))
        issues.append(ValidationIssue(location, f"table.add_column.columns 每个对象必须且只能包含一个操作符：{allowed}"))
        return
    operator = operators[0]
    if operator in {"copy", "format"} and (not isinstance(value[operator], str) or not value[operator]):
        issues.append(ValidationIssue(location, f"table.add_column.{operator} 必须是非空字符串"))
    if operator == "sum":
        temp_step = {"sum": value[operator]}
        _validate_string_or_nonempty_string_list(temp_step, "sum", location, issues)
