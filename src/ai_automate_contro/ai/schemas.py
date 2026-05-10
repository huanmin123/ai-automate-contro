from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator


AI_TASK_TYPES = {
    "connectivity",
    "extract_data",
    "classify_text",
    "transform_data",
    "summarize_text",
}


def build_ai_schema(task_type: str, schema: Any | None, labels: Any | None = None) -> dict[str, Any]:
    if task_type not in AI_TASK_TYPES:
        raise ValueError(f"Unsupported ai type: {task_type}")
    if schema is not None:
        return normalize_json_schema(schema)
    if task_type == "connectivity":
        return {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "message": {"type": "string"},
            },
            "required": ["ok", "message"],
            "additionalProperties": False,
        }
    if task_type == "classify_text":
        if not isinstance(labels, list) or not labels:
            raise ValueError("ai type 'classify_text' requires labels when schema is not provided.")
        normalized_labels = [str(label) for label in labels]
        return {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": normalized_labels},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
            },
            "required": ["label", "confidence", "reason"],
            "additionalProperties": False,
        }
    if task_type == "summarize_text":
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
            },
            "required": ["summary"],
            "additionalProperties": False,
        }
    if task_type == "transform_data":
        return {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
            },
            "required": ["result"],
            "additionalProperties": False,
        }
    raise ValueError("ai type 'extract_data' requires schema.")


def normalize_json_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("ai.schema must be a JSON object.")
    if "type" in schema:
        return schema
    properties: dict[str, Any] = {}
    for name, field_schema in schema.items():
        properties[str(name)] = _normalize_schema_field(field_schema)
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def validate_with_schema(value: Any, schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        first_error = errors[0]
        path = ".".join(str(part) for part in first_error.path) or "<root>"
        raise ValueError(f"AI response schema validation failed at {path}: {first_error.message}")


def _normalize_schema_field(field_schema: Any) -> dict[str, Any]:
    if isinstance(field_schema, str):
        return {"type": field_schema}
    if isinstance(field_schema, list):
        if len(field_schema) != 1:
            raise ValueError("ai.schema array shorthand must contain exactly one item schema.")
        return {"type": "array", "items": _normalize_schema_field(field_schema[0])}
    if isinstance(field_schema, dict):
        if "type" in field_schema:
            return field_schema
        return normalize_json_schema(field_schema)
    raise ValueError(f"Unsupported ai.schema field shorthand: {field_schema!r}")
