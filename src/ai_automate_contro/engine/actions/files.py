from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
import re
from typing import Any


EXCEL_A1_RE = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]*(?::[A-Za-z]{1,3}[1-9][0-9]*)?$")


def write_json_file(executor: Any, raw_path: str, value: Any, *, category: str = "json", indent: int = 2) -> None:
    output_path = executor._resolve_output_path(raw_path, category=category)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=indent)
    executor.state.logger.log("info", "json written", path=str(output_path))


def write_text_file(executor: Any, raw_path: str, content: Any, *, append: bool) -> None:
    output_path = executor._resolve_output_path(raw_path, category="text")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with output_path.open(mode, encoding="utf-8") as file:
        file.write(_coerce_text_content(content))
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


def write_excel_file(executor: Any, step: dict[str, Any]) -> None:
    excel = _load_openpyxl()
    output_path = executor._resolve_output_path(step["path"], category="excel")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    template_path = step.get("template_path")
    if template_path:
        source_path = executor._resolve_path(template_path)
        workbook = excel["load_workbook"](source_path, keep_vba=source_path.suffix.lower() == ".xlsm")
    else:
        workbook = excel["Workbook"]()

    sheet_steps = _excel_write_sheet_steps(step)
    for sheet_step in sheet_steps:
        _write_excel_sheet(
            workbook,
            sheet_step,
            template=bool(template_path),
            get_column_letter=excel["get_column_letter"],
        )

    workbook.save(output_path)
    executor.state.logger.log("info", "excel written", path=str(output_path))


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
    if file_type == "excel":
        value, meta = read_excel_file(path, step)
        if step.get("save_meta_as"):
            executor.state.variables[str(step["save_meta_as"])] = meta
        return value
    if file_type == "storage_state":
        return str(path)
    raise ValueError(f"Unsupported read type: {file_type}")


def read_excel_file(path: Any, step: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    excel = _load_openpyxl()
    formula_mode = str(step.get("formula_mode", "cached"))
    workbook = excel["load_workbook"](path, read_only=True, data_only=formula_mode != "formula")
    try:
        if "sheets" in step:
            return _read_excel_sheets(path, step, excel, workbook)
        return _read_excel_workbook(path, step, excel, workbook)
    finally:
        workbook.close()


def _read_excel_sheets(path: Any, step: dict[str, Any], excel: dict[str, Any], workbook: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    sheet_steps = _excel_read_sheet_steps(step)
    values: dict[str, Any] = {}
    sheet_meta: dict[str, Any] = {}
    for sheet_step in sheet_steps:
        value, meta = _read_excel_workbook(path, sheet_step, excel, workbook)
        sheet_name = str(meta.get("sheet") or sheet_step.get("sheet") or "")
        if not sheet_name:
            raise ValueError("read.type=excel.sheets 每一项必须能解析出 sheet 名称。")
        value_name = str(sheet_step.get("name") or sheet_name)
        if not value_name:
            raise ValueError("read.type=excel.sheets 每一项的 name 必须是非空字符串。")
        if value_name in values:
            raise ValueError(f"read.type=excel.sheets 不能重复保存同名结果：{value_name}")
        values[value_name] = value
        sheet_meta[value_name] = meta
    meta = {
        "type": "excel",
        "path": str(path),
        "sheets": list(workbook.sheetnames),
        "selected_sheets": [str(meta.get("sheet") or key) for key, meta in sheet_meta.items()],
        "value_names": list(values.keys()),
        "sheet_meta": sheet_meta,
        "row_count": sum(int(meta.get("row_count", 0) or 0) for meta in sheet_meta.values()),
    }
    return values, meta


def _excel_read_sheet_steps(step: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sheets = step.get("sheets")
    if not isinstance(raw_sheets, list) or not raw_sheets:
        raise ValueError("read.type=excel.sheets 必须是非空数组。")
    sheet_steps: list[dict[str, Any]] = []
    for index, raw_sheet in enumerate(raw_sheets):
        merged = {
            key: value
            for key, value in step.items()
            if key not in {"sheets", "sheet", "save_as", "save_meta_as"}
        }
        if isinstance(raw_sheet, dict):
            merged.update(raw_sheet)
        elif isinstance(raw_sheet, (str, int)):
            merged["sheet"] = raw_sheet
        else:
            raise ValueError(f"read.type=excel.sheets[{index}] 必须是 sheet 名称、索引或读取配置对象。")
        if "sheet" not in merged:
            raise ValueError(f"read.type=excel.sheets[{index}] 缺少 sheet。")
        sheet_steps.append(merged)
    return sheet_steps


def _read_excel_workbook(path: Any, step: dict[str, Any], excel: dict[str, Any], workbook: Any) -> tuple[Any, dict[str, Any]]:
    date_format = str(step.get("date_format", "iso"))
    worksheet = _select_excel_worksheet(workbook, step.get("sheet"))
    min_col, min_row, max_col, max_row = _excel_bounds(worksheet, step.get("range"), excel["range_boundaries"])
    mode = str(step.get("mode", "records"))
    max_rows = int(step.get("max_rows", 10000))
    skip_blank_rows = bool(step.get("skip_blank_rows", True))

    if max_row < min_row or max_col < min_col:
        value: Any = [] if mode in {"records", "matrix"} else {}
        meta = _excel_meta(path, workbook, worksheet, "", [], value)
        return value, meta

    if mode == "matrix":
        rows = [
            [_json_safe_excel_value(cell, date_format=date_format) for cell in row]
            for row in worksheet.iter_rows(
                min_row=min_row,
                max_row=max_row,
                min_col=min_col,
                max_col=max_col,
                values_only=True,
            )
            if not skip_blank_rows or not _excel_row_is_blank(row)
        ]
        _ensure_max_rows(rows, max_rows)
        meta = _excel_meta(
            path,
            workbook,
            worksheet,
            _excel_range_text(min_col, min_row, max_col, max_row, excel["get_column_letter"]),
            [],
            rows,
        )
        return rows, meta

    if mode == "cells":
        cells: dict[str, Any] = {}
        for row in worksheet.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
            for cell in row:
                value = _json_safe_excel_value(cell.value)
                if value is not None and value != "":
                    cells[cell.coordinate] = value
        meta = _excel_meta(
            path,
            workbook,
            worksheet,
            _excel_range_text(min_col, min_row, max_col, max_row, excel["get_column_letter"]),
            [],
            cells,
        )
        return cells, meta

    headers, data_start_row = _excel_headers(worksheet, step, min_row, min_col, max_col)
    records: list[dict[str, Any]] = []
    if data_start_row <= max_row:
        for row in worksheet.iter_rows(
            min_row=data_start_row,
            max_row=max_row,
            min_col=min_col,
            max_col=max_col,
            values_only=True,
        ):
            if skip_blank_rows and _excel_row_is_blank(row):
                continue
            records.append({header: _json_safe_excel_value(value, date_format=date_format) for header, value in zip(headers, row)})
            _ensure_max_rows(records, max_rows)

    meta = _excel_meta(
        path,
        workbook,
        worksheet,
        _excel_range_text(min_col, min_row, max_col, max_row, excel["get_column_letter"]),
        headers,
        records,
    )
    return records, meta


def _coerce_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        lines = [str(item) for item in value]
        return ("\n".join(lines) + "\n") if lines else ""
    return str(value)


def _load_openpyxl() -> dict[str, Any]:
    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.utils import get_column_letter, range_boundaries
    except ImportError as error:
        raise RuntimeError("Excel 读写需要安装 openpyxl：pip install openpyxl>=3.1,<4.0") from error
    return {
        "Workbook": Workbook,
        "Table": Table,
        "TableStyleInfo": TableStyleInfo,
        "get_column_letter": get_column_letter,
        "load_workbook": load_workbook,
        "range_boundaries": range_boundaries,
    }


def _select_excel_worksheet(workbook: Any, raw_sheet: Any) -> Any:
    if raw_sheet in (None, ""):
        return workbook.worksheets[0]
    if isinstance(raw_sheet, int):
        try:
            return workbook.worksheets[raw_sheet]
        except IndexError as error:
            raise ValueError(f"Excel sheet 索引超出范围：{raw_sheet}") from error
    sheet_name = str(raw_sheet)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Excel 工作表不存在：{sheet_name}")
    return workbook[sheet_name]


def _excel_bounds(worksheet: Any, raw_range: Any, range_boundaries: Any) -> tuple[int, int, int, int]:
    if raw_range:
        range_text = str(raw_range)
        if not EXCEL_A1_RE.match(range_text):
            raise ValueError(f"Excel range 必须是 A1 风格范围：{range_text}")
        return range_boundaries(range_text)
    try:
        dimension = worksheet.calculate_dimension()
    except ValueError as error:
        if "unsized" not in str(error):
            raise
        dimension = worksheet.calculate_dimension(force=True)
    min_col, min_row, max_col, max_row = range_boundaries(dimension)
    return _excel_tight_bounds(worksheet, min_col, min_row, max_col, max_row)


def _excel_tight_bounds(worksheet: Any, min_col: int, min_row: int, max_col: int, max_row: int) -> tuple[int, int, int, int]:
    tight_min_col: int | None = None
    tight_min_row: int | None = None
    tight_max_col = 0
    tight_max_row = 0
    for row in worksheet.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            if not _excel_cell_has_value(cell.value):
                continue
            tight_min_col = cell.column if tight_min_col is None else min(tight_min_col, cell.column)
            tight_min_row = cell.row if tight_min_row is None else min(tight_min_row, cell.row)
            tight_max_col = max(tight_max_col, cell.column)
            tight_max_row = max(tight_max_row, cell.row)
    if tight_min_col is None or tight_min_row is None:
        return 1, 1, 0, 0
    return tight_min_col, tight_min_row, tight_max_col, tight_max_row


def _excel_cell_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _excel_headers(worksheet: Any, step: dict[str, Any], min_row: int, min_col: int, max_col: int) -> tuple[list[str], int]:
    raw_headers = step.get("headers")
    if raw_headers is not None:
        headers = [str(header).strip() for header in raw_headers]
        _validate_excel_headers(headers)
        return headers, min_row

    header_row = int(step.get("header_row", min_row))
    values = next(
        worksheet.iter_rows(
            min_row=header_row,
            max_row=header_row,
            min_col=min_col,
            max_col=max_col,
            values_only=True,
        ),
        (),
    )
    headers = [str(_json_safe_excel_value(value) or "").strip() for value in values]
    _validate_excel_headers(headers)
    return headers, header_row + 1


def _validate_excel_headers(headers: list[str]) -> None:
    if not headers:
        raise ValueError("Excel records 模式需要至少一个表头。")
    blank_indexes = [index + 1 for index, header in enumerate(headers) if not header]
    if blank_indexes:
        raise ValueError(f"Excel 表头不能为空，空表头列序号：{blank_indexes}")
    duplicates = sorted({header for header in headers if headers.count(header) > 1})
    if duplicates:
        raise ValueError(f"Excel 表头重复：{', '.join(duplicates)}")


def _excel_row_is_blank(row: Any) -> bool:
    for value in row:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return False
    return True


def _ensure_max_rows(rows: list[Any], max_rows: int) -> None:
    if len(rows) > max_rows:
        raise ValueError(f"Excel 读取行数超过 max_rows={max_rows}，请缩小 range 或提高 max_rows。")


def _excel_meta(path: Any, workbook: Any, worksheet: Any, range_text: str, headers: list[str], value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        row_count = len(value)
    elif isinstance(value, dict):
        row_count = len(value)
    else:
        row_count = 0
    column_count = len(headers)
    if not column_count and isinstance(value, list) and value and isinstance(value[0], list):
        column_count = max(len(row) for row in value)
    return {
        "type": "excel",
        "path": str(path),
        "sheets": list(workbook.sheetnames),
        "sheet": worksheet.title,
        "range": range_text,
        "headers": headers,
        "row_count": row_count,
        "column_count": column_count,
    }


def _excel_range_text(min_col: int, min_row: int, max_col: int, max_row: int, get_column_letter: Any) -> str:
    if max_row < min_row or max_col < min_col:
        return ""
    return f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"


def _json_safe_excel_value(value: Any, *, date_format: str = "iso") -> Any:
    if isinstance(value, (datetime, date, time)):
        if date_format == "text":
            return str(value)
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _prepare_excel_worksheet(workbook: Any, raw_sheet: Any, *, write_mode: str, template: bool) -> Any:
    if isinstance(raw_sheet, int) and workbook.worksheets:
        sheet_name = workbook.worksheets[raw_sheet].title
    elif raw_sheet not in (None, ""):
        sheet_name = str(raw_sheet)
    elif template:
        sheet_name = workbook.worksheets[0].title
    else:
        sheet_name = "Sheet1"

    if write_mode in {"create", "replace_sheet"}:
        if sheet_name in workbook.sheetnames:
            old_sheet = workbook[sheet_name]
            index = workbook.worksheets.index(old_sheet)
            new_sheet = workbook.create_sheet(title=sheet_name, index=index)
            workbook.remove(old_sheet)
            return new_sheet
        if not template and len(workbook.worksheets) == 1 and _worksheet_is_empty(workbook.worksheets[0]):
            worksheet = workbook.worksheets[0]
            worksheet.title = sheet_name
            return worksheet
        return workbook.create_sheet(title=sheet_name)

    if write_mode in {"append_rows", "overlay_cells"}:
        if sheet_name in workbook.sheetnames:
            return workbook[sheet_name]
        return workbook.create_sheet(title=sheet_name)

    raise ValueError(f"不支持的 Excel write_mode：{write_mode}")


def _excel_write_sheet_steps(step: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sheets = step.get("sheets")
    if raw_sheets is None:
        return [_normalize_excel_sheet_step(step)]
    if not isinstance(raw_sheets, list) or not raw_sheets:
        raise ValueError("write.type=excel.sheets 必须是非空数组。")
    sheet_steps: list[dict[str, Any]] = []
    for index, raw_sheet_step in enumerate(raw_sheets):
        if not isinstance(raw_sheet_step, dict):
            raise ValueError(f"write.type=excel.sheets[{index}] 必须是对象。")
        merged = {
            key: value
            for key, value in step.items()
            if key
            not in {
                "path",
                "template_path",
                "sheets",
                "sheet",
                "value",
                "rows",
                "cells",
            }
        }
        merged.update(raw_sheet_step)
        sheet_steps.append(_normalize_excel_sheet_step(merged))
    return sheet_steps


def _normalize_excel_sheet_step(step: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(step)
    if "value" not in normalized and "rows" in normalized:
        normalized["value"] = normalized["rows"]
    if "value" not in normalized and "cells" not in normalized:
        raise ValueError("write.type=excel 需要 value、cells 或 sheets[].value/cells 之一。")
    return normalized


def _write_excel_sheet(workbook: Any, step: dict[str, Any], *, template: bool, get_column_letter: Any) -> None:
    write_mode = str(step.get("write_mode") or ("replace_sheet" if template else "create"))
    worksheet = _prepare_excel_worksheet(
        workbook,
        step.get("sheet"),
        write_mode=write_mode,
        template=template,
    )

    data_range: tuple[int, int, int, int] | None = None
    if "value" in step:
        rows = _coerce_excel_rows(step.get("value"))
        start_row, start_col = _excel_cell_position(step.get("start_cell") or "A1", field_name="start_cell")
        data_range = _write_excel_rows(
            worksheet,
            rows,
            headers=step.get("headers"),
            append=write_mode == "append_rows",
            include_header=bool(step.get("include_header", True)),
            start_row=start_row,
            start_col=start_col,
        )

    cells = step.get("cells")
    if isinstance(cells, dict):
        for address, value in cells.items():
            if not isinstance(address, str) or not EXCEL_A1_RE.match(address):
                raise ValueError(f"Excel cells 的 key 必须是 A1 单元格地址：{address}")
            worksheet[address] = _excel_cell_value(value)

    _apply_excel_sheet_options(worksheet, step, get_column_letter, data_range=data_range)


def _worksheet_is_empty(worksheet: Any) -> bool:
    return worksheet.max_row == 1 and worksheet.max_column == 1 and worksheet["A1"].value is None


def _worksheet_last_nonempty_row(worksheet: Any) -> int:
    for row_number in range(worksheet.max_row, 0, -1):
        for column_number in range(1, worksheet.max_column + 1):
            value = worksheet.cell(row=row_number, column=column_number).value
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return row_number
    return 0


def _coerce_excel_rows(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    return [[value]]


def _write_excel_rows(
    worksheet: Any,
    rows: list[Any],
    *,
    headers: list[str] | None,
    append: bool,
    include_header: bool,
    start_row: int,
    start_col: int,
) -> tuple[int, int, int, int] | None:
    existing_empty = _worksheet_is_empty(worksheet)
    target_row = _worksheet_last_nonempty_row(worksheet) + 1 if append and not existing_empty else start_row
    inferred_headers = _excel_write_headers(rows, headers)
    write_header = include_header and bool(inferred_headers) and (not append or existing_empty)

    current_row = target_row
    max_width = 0
    if write_header:
        _write_excel_row(worksheet, current_row, inferred_headers, start_col=start_col)
        max_width = max(max_width, len(inferred_headers))
        current_row += 1

    for row in rows:
        if isinstance(row, dict):
            values = [row.get(header, "") for header in inferred_headers]
        elif isinstance(row, (list, tuple)):
            values = list(row)
        else:
            values = [row]
        _write_excel_row(worksheet, current_row, values, start_col=start_col)
        max_width = max(max_width, len(values))
        current_row += 1
    if current_row == target_row or max_width == 0:
        return None
    return start_col, target_row, start_col + max_width - 1, current_row - 1


def _excel_write_headers(rows: list[Any], headers: list[str] | None) -> list[str]:
    if headers:
        result = [str(header) for header in headers]
        _validate_excel_headers(result)
        return result
    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            text = str(key)
            if text not in result:
                result.append(text)
    return result


def _write_excel_row(worksheet: Any, row_number: int, values: list[Any], *, start_col: int) -> None:
    for column_number, value in enumerate(values, start=start_col):
        worksheet.cell(row=row_number, column=column_number).value = _excel_cell_value(value)


def _excel_cell_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (datetime, date, time, timedelta, str, int, float, bool)) or value is None:
        return value
    return str(value)


def _excel_cell_position(value: Any, *, field_name: str) -> tuple[int, int]:
    if not isinstance(value, str) or not value or ":" in value or not EXCEL_A1_RE.match(value):
        raise ValueError(f"Excel {field_name} 必须是 A1 风格单元格地址，例如 B3。")
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]*)", value)
    if match is None:
        raise ValueError(f"Excel {field_name} 必须是 A1 风格单元格地址，例如 B3。")
    column_letter, row_text = match.groups()
    return int(row_text), _column_number(column_letter)


def _excel_effective_data_range(
    worksheet: Any,
    data_range: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int]:
    if data_range is not None:
        return data_range
    return 1, 1, worksheet.max_column, worksheet.max_row


def _apply_excel_sheet_options(
    worksheet: Any,
    step: dict[str, Any],
    get_column_letter: Any,
    *,
    data_range: tuple[int, int, int, int] | None,
) -> None:
    range_min_col, range_min_row, range_max_col, range_max_row = _excel_effective_data_range(
        worksheet,
        data_range,
    )
    if bool(step.get("freeze_header", False)):
        worksheet.freeze_panes = f"{get_column_letter(range_min_col)}{range_min_row + 1}"
    if bool(step.get("auto_filter", False)) and range_max_row >= range_min_row and range_max_col >= range_min_col:
        worksheet.auto_filter.ref = _excel_range_text(range_min_col, range_min_row, range_max_col, range_max_row, get_column_letter)
    _apply_excel_column_widths(worksheet, step.get("column_widths"), get_column_letter, header_row=range_min_row)
    _apply_excel_number_formats(worksheet, step.get("number_format"), get_column_letter, header_row=range_min_row)
    if bool(step.get("table", False)) and range_max_row >= range_min_row + 1 and range_max_col >= range_min_col:
        _add_excel_table(worksheet, step, get_column_letter, data_range=(range_min_col, range_min_row, range_max_col, range_max_row))


def _apply_excel_column_widths(worksheet: Any, column_widths: Any, get_column_letter: Any, *, header_row: int) -> None:
    if not isinstance(column_widths, dict):
        return
    header_map = _excel_header_column_map(worksheet, header_row=header_row)
    for key, width in column_widths.items():
        column_letter = _excel_column_letter(str(key), header_map, get_column_letter)
        worksheet.column_dimensions[column_letter].width = float(width)


def _apply_excel_number_formats(worksheet: Any, number_format: Any, get_column_letter: Any, *, header_row: int) -> None:
    if not isinstance(number_format, dict):
        return
    header_map = _excel_header_column_map(worksheet, header_row=header_row)
    for key, fmt in number_format.items():
        column_letter = _excel_column_letter(str(key), header_map, get_column_letter)
        column_index = header_map.get(str(key), None)
        if column_index is None and column_letter.isalpha():
            column_index = _column_number(column_letter)
        if column_index is None:
            continue
        for row_number in range(header_row + 1, worksheet.max_row + 1):
            worksheet.cell(row=row_number, column=column_index).number_format = str(fmt)


def _excel_header_column_map(worksheet: Any, *, header_row: int = 1) -> dict[str, int]:
    mapping: dict[str, int] = {}
    if worksheet.max_row < header_row:
        return mapping
    for column_number in range(1, worksheet.max_column + 1):
        value = worksheet.cell(row=header_row, column=column_number).value
        if value not in (None, ""):
            mapping[str(value)] = column_number
    return mapping


def _excel_column_letter(key: str, header_map: dict[str, int], get_column_letter: Any) -> str:
    if key in header_map:
        return get_column_letter(header_map[key])
    if re.fullmatch(r"[A-Za-z]{1,3}", key):
        return key.upper()
    raise ValueError(f"无法定位 Excel 列：{key}")


def _column_number(column_letter: str) -> int:
    number = 0
    for char in column_letter.upper():
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def _add_excel_table(
    worksheet: Any,
    step: dict[str, Any],
    get_column_letter: Any,
    *,
    data_range: tuple[int, int, int, int] | None,
) -> None:
    excel = _load_openpyxl()
    min_col, min_row, max_col, max_row = _excel_effective_data_range(worksheet, data_range)
    ref = _excel_range_text(min_col, min_row, max_col, max_row, get_column_letter)
    table_name = _safe_excel_table_name(str(step.get("table_name") or worksheet.title or "Table1"))
    existing = {
        table.name
        for workbook_sheet in worksheet.parent.worksheets
        for table in workbook_sheet.tables.values()
    }
    base_name = table_name
    index = 1
    while table_name in existing:
        index += 1
        table_name = f"{base_name}{index}"
    table = excel["Table"](displayName=table_name, ref=ref)
    table.tableStyleInfo = excel["TableStyleInfo"](
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    worksheet.add_table(table)


def _safe_excel_table_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", value.strip()) or "Table1"
    if name[0].isdigit():
        name = f"Table_{name}"
    return name[:255]
