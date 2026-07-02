from __future__ import annotations

import math
import re
from typing import Any

from jsonschema import Draft202012Validator


VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TYPE_ALIASES = {
    "str": "string",
    "text": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "dict": "object",
    "list": "array",
}
JSON_TYPES = {"null", "string", "number", "integer", "boolean", "object", "array"}


def publish_step_output(executor: Any, step: dict[str, Any], raw_value: Any, *, action: str) -> None:
    output = step.get("output")
    if output is None:
        return
    spec = _normalize_output_spec(output)
    name = spec["as"]
    value = _select_value(raw_value, spec.get("from", ""))
    _ensure_json_safe(value, f"{action}.output")
    if "type" in spec:
        _validate_type_spec(value, spec["type"], f"{action}.output")
    if "fields" in spec:
        _validate_fields(value, spec["fields"], f"{action}.output.fields")
    if "schema" in spec:
        _validate_json_schema(value, spec["schema"], f"{action}.output.schema")
    executor.state.variables[name] = value
    executor.state.variables["last"] = value
    executor.state.logger.log("info", "output published", action=action, name=name, from_path=spec.get("from", ""))


def validate_output_contract_spec(output: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return ["output 必须是对象，例如 {\"as\":\"result\"}。"]
    allowed = {"as", "from", "type", "fields", "schema"}
    unknown = sorted(str(key) for key in output if key not in allowed)
    if unknown:
        errors.append(f"output 包含不支持的字段：{', '.join(unknown)}")
    name = output.get("as")
    if not isinstance(name, str) or not name:
        errors.append("output.as 必须是非空字符串")
    elif not VARIABLE_NAME_RE.match(name):
        errors.append("output.as 必须是简单变量名，只能包含字母、数字和下划线，且不能以数字开头")
    elif name == "last":
        errors.append("output.as 不能使用保留变量名 last")
    if "from" in output and not isinstance(output["from"], str):
        errors.append("output.from 必须是字符串路径，例如 body.data 或 /body/data")
    if "type" in output:
        type_error = _validate_type_spec_syntax(output["type"])
        if type_error:
            errors.append(type_error)
    if "fields" in output:
        fields = output["fields"]
        if not isinstance(fields, dict):
            errors.append("output.fields 必须是对象")
        else:
            for field, spec in fields.items():
                if not isinstance(field, str) or not field:
                    errors.append("output.fields 的 key 必须是非空字符串")
                    continue
                spec_error = _validate_type_spec_syntax(spec)
                if spec_error:
                    errors.append(f"output.fields.{field}: {spec_error}")
    if "schema" in output and not isinstance(output["schema"], dict):
        errors.append("output.schema 必须是 JSON Schema 对象")
    elif "schema" in output:
        try:
            Draft202012Validator.check_schema(output["schema"])
        except Exception as error:
            errors.append(f"output.schema 不是有效 JSON Schema：{error}")
    return errors


def _normalize_output_spec(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("output 必须是对象。")
    name = output.get("as")
    if not isinstance(name, str) or not name or not VARIABLE_NAME_RE.match(name) or name == "last":
        raise ValueError("output.as 必须是合法变量名，且不能是 last。")
    return dict(output)


def _select_value(value: Any, raw_path: str) -> Any:
    path = str(raw_path or "").strip()
    if not path:
        return value
    segments = _json_pointer_segments(path) if path.startswith("/") else path.split(".")
    current = value
    for segment in segments:
        if segment == "":
            continue
        if isinstance(current, dict):
            if segment not in current:
                raise KeyError(f"output.from 路径不存在：{path}")
            current = current[segment]
            continue
        if isinstance(current, list):
            try:
                index = int(segment)
            except ValueError as error:
                raise KeyError(f"output.from 数组索引必须是整数：{path}") from error
            try:
                current = current[index]
            except IndexError as error:
                raise KeyError(f"output.from 数组索引越界：{path}") from error
            continue
        raise KeyError(f"output.from 无法继续读取路径：{path}")
    return current


def _json_pointer_segments(path: str) -> list[str]:
    return [segment.replace("~1", "/").replace("~0", "~") for segment in path.split("/")[1:]]


def _ensure_json_safe(value: Any, location: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{location} 包含非有限数字，不能作为 JSON 输出。")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_safe(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{location} 包含非字符串 key，不能作为 JSON 输出。")
            _ensure_json_safe(item, f"{location}.{key}")
        return
    raise TypeError(f"{location} 包含非 JSON 值：{type(value).__name__}")


def _validate_fields(value: Any, fields: Any, location: str) -> None:
    if not isinstance(fields, dict):
        raise ValueError(f"{location} 必须是对象。")
    if not isinstance(value, dict):
        raise TypeError("output.fields 只能校验对象输出。")
    for field_path, raw_spec in fields.items():
        if not isinstance(field_path, str) or not field_path:
            raise ValueError(f"{location} 的字段名必须是非空字符串。")
        spec = _parse_type_spec(raw_spec)
        try:
            field_value = _select_value(value, field_path)
        except KeyError:
            if spec["required"]:
                raise
            continue
        _validate_type_spec(field_value, raw_spec, f"{location}.{field_path}")


def _validate_type_spec(value: Any, raw_spec: Any, location: str) -> None:
    spec = _parse_type_spec(raw_spec)
    if value is None:
        if spec["required"]:
            raise TypeError(f"{location} 不能为空。")
        return
    expected = spec["type"]
    if expected == "null":
        if value is not None:
            raise TypeError(f"{location} 必须是 null。")
        return
    if expected == "string" and not isinstance(value, str):
        raise TypeError(f"{location} 必须是 string。")
    if expected == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise TypeError(f"{location} 必须是 integer。")
    if expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise TypeError(f"{location} 必须是 number。")
    if expected == "boolean" and not isinstance(value, bool):
        raise TypeError(f"{location} 必须是 boolean。")
    if expected == "object" and not isinstance(value, dict):
        raise TypeError(f"{location} 必须是 object。")
    if expected == "array" and not isinstance(value, list):
        raise TypeError(f"{location} 必须是 array。")


def _parse_type_spec(raw_spec: Any) -> dict[str, Any]:
    if not isinstance(raw_spec, str) or not raw_spec:
        raise ValueError("类型声明必须是非空字符串，例如 string!、object、array。")
    required = raw_spec.endswith("!")
    raw_type = raw_spec[:-1] if required else raw_spec
    expected = TYPE_ALIASES.get(raw_type, raw_type)
    if expected not in JSON_TYPES:
        raise ValueError(f"不支持的输出类型：{raw_spec}")
    return {"type": expected, "required": required}


def _validate_type_spec_syntax(raw_spec: Any) -> str:
    try:
        _parse_type_spec(raw_spec)
    except ValueError as error:
        return str(error)
    return ""


def _validate_json_schema(value: Any, schema: dict[str, Any], location: str) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(part) for part in first.path) or "<root>"
    raise ValueError(f"{location} 校验失败，位置 {path}：{first.message}")
