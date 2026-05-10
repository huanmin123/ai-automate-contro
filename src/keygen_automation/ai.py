from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from openai import OpenAI


AI_TASK_TYPES = {
    "connectivity",
    "extract_data",
    "classify_text",
    "transform_data",
    "summarize_text",
}


@dataclass(frozen=True)
class AIResult:
    parsed: Any
    raw_text: str
    raw_response: dict[str, Any]
    schema: dict[str, Any]
    response_format: str
    attempts: list[dict[str, Any]]


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


def run_ai_task(
    *,
    service_name: str,
    service_config: dict[str, Any],
    task_type: str,
    input_value: Any,
    instruction: str,
    schema: dict[str, Any],
    labels: list[Any] | None = None,
) -> AIResult:
    if not isinstance(service_config, dict):
        raise ValueError(f"AI service config must be an object: {service_name}")
    provider = str(service_config.get("provider", "openai-compatible"))
    if provider not in {"openai", "openai-compatible"}:
        raise ValueError(f"Unsupported AI provider for service '{service_name}': {provider}")

    model = service_config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"AI service '{service_name}' requires model.")
    api_key = _resolve_api_key(service_name, service_config)
    timeout_seconds = float(service_config.get("timeout_seconds", 60))

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": timeout_seconds,
    }
    if service_config.get("base_url"):
        client_kwargs["base_url"] = str(service_config["base_url"])
    client = OpenAI(**client_kwargs)

    messages = _build_messages(
        task_type=task_type,
        input_value=input_value,
        instruction=instruction,
        schema=schema,
        labels=labels or [],
    )
    response_api = str(service_config.get("api", "chat_completions"))
    strict = bool(service_config.get("strict_schema", True))
    response_formats = service_config.get("response_formats", ["json_schema", "json_object", "plain"])
    if not isinstance(response_formats, list) or not response_formats:
        response_formats = ["json_schema", "json_object", "plain"]

    attempts: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for response_format in [str(item) for item in response_formats]:
        try:
            raw_text, raw_response = _call_model(
                client=client,
                response_api=response_api,
                model=model,
                messages=messages,
                schema=schema,
                schema_name=f"{task_type}_result",
                response_format=response_format,
                strict=strict,
            )
            parsed = parse_json_response(raw_text)
            validate_with_schema(parsed, schema)
            attempts.append({"response_format": response_format, "status": "passed"})
            return AIResult(
                parsed=parsed,
                raw_text=raw_text,
                raw_response=raw_response,
                schema=schema,
                response_format=response_format,
                attempts=attempts,
            )
        except Exception as error:
            last_error = error
            attempts.append(
                {
                    "response_format": response_format,
                    "status": "failed",
                    "error": _redact_text(str(error), api_key),
                }
            )

    raise RuntimeError(
        f"AI task failed for service '{service_name}'. Attempts: "
        f"{json.dumps(attempts, ensure_ascii=False)}"
    ) from last_error


def parse_json_response(raw_text: str) -> Any:
    text = raw_text.strip()
    if text.startswith("```"):
        text = _strip_code_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
                return value
            except json.JSONDecodeError:
                continue
        raise


def validate_with_schema(value: Any, schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        first_error = errors[0]
        path = ".".join(str(part) for part in first_error.path) or "<root>"
        raise ValueError(f"AI response schema validation failed at {path}: {first_error.message}")


def service_config_for_artifact(service_config: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(service_config)
    if "api_key" in redacted:
        redacted["api_key"] = "<redacted>"
    if "api_key_env" in redacted:
        redacted["api_key_env"] = str(redacted["api_key_env"])
    return redacted


def _resolve_api_key(service_name: str, service_config: dict[str, Any]) -> str:
    if service_config.get("api_key"):
        return str(service_config["api_key"])
    api_key_env = service_config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            return api_key
    raise ValueError(f"AI service '{service_name}' requires api_key or api_key_env.")


def _build_messages(
    *,
    task_type: str,
    input_value: Any,
    instruction: str,
    schema: dict[str, Any],
    labels: list[Any],
) -> list[dict[str, str]]:
    system_prompt = (
        "You are a controlled automation data-processing component. "
        "Only process the provided input. Do not control a browser, execute commands, "
        "modify files, or ask follow-up questions. Return JSON only and make it match "
        "the provided JSON Schema."
    )
    task_prompts = {
        "connectivity": "Confirm the model endpoint is reachable. Return ok=true with a short message.",
        "extract_data": "Extract the requested structured fields from the input.",
        "classify_text": "Classify the input into exactly one allowed label.",
        "transform_data": "Transform the input according to the instruction.",
        "summarize_text": "Summarize the input according to the instruction.",
    }
    payload = {
        "task_type": task_type,
        "task": task_prompts[task_type],
        "instruction": instruction,
        "labels": labels,
        "json_schema": schema,
        "input": input_value,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _call_model(
    *,
    client: OpenAI,
    response_api: str,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    response_format: str,
    strict: bool,
) -> tuple[str, dict[str, Any]]:
    if response_api == "responses":
        return _call_responses_api(
            client=client,
            model=model,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            response_format=response_format,
            strict=strict,
        )
    if response_api != "chat_completions":
        raise ValueError(f"Unsupported AI API mode: {response_api}")
    return _call_chat_completions_api(
        client=client,
        model=model,
        messages=messages,
        schema=schema,
        schema_name=schema_name,
        response_format=response_format,
        strict=strict,
    )


def _call_chat_completions_api(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    response_format: str,
    strict: bool,
) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if response_format == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": strict,
            },
        }
    elif response_format == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    elif response_format != "plain":
        raise ValueError(f"Unsupported AI response format: {response_format}")

    response = client.chat.completions.create(**kwargs)
    return extract_chat_completion_text(response)


def _call_responses_api(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    response_format: str,
    strict: bool,
) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "model": model,
        "input": messages,
    }
    if response_format == "json_schema":
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": strict,
            }
        }
    elif response_format == "json_object":
        kwargs["text"] = {"format": {"type": "json_object"}}
    elif response_format != "plain":
        raise ValueError(f"Unsupported AI response format: {response_format}")

    response = client.responses.create(**kwargs)
    raw_response = _model_dump(response)
    raw_text = getattr(response, "output_text", "") or _extract_responses_text(raw_response)
    return raw_text, raw_response


def _extract_responses_text(raw_response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in raw_response.get("output", []):
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("text"):
                chunks.append(str(content["text"]))
    return "".join(chunks)


def extract_chat_completion_text(response: Any) -> tuple[str, dict[str, Any]]:
    raw_response = _model_dump(response)
    if isinstance(response, str):
        raw_text = _extract_sse_chat_text(response)
        if not raw_text:
            raise ValueError("AI service returned a streaming response without text content.")
        return raw_text, raw_response

    choices = _get_response_field(response, raw_response, "choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI service response missing choices.")
    first_choice = choices[0]
    message = _get_choice_message(first_choice)
    content = _get_response_field(message, message if isinstance(message, dict) else {}, "content")
    if isinstance(content, list):
        raw_text = "".join(_content_part_to_text(item) for item in content)
    else:
        raw_text = content or ""
    if not raw_text:
        raise ValueError("AI service response message had no text content.")
    return str(raw_text), raw_response


def _extract_sse_chat_text(raw_text: str) -> str:
    chunks: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = event.get("choices", [])
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and delta.get("content"):
                chunks.append(str(delta["content"]))
            message = choice.get("message")
            if isinstance(message, dict) and message.get("content"):
                chunks.append(str(message["content"]))
            if choice.get("text"):
                chunks.append(str(choice["text"]))
    return "".join(chunks)


def _get_choice_message(choice: Any) -> Any:
    if isinstance(choice, dict):
        return choice.get("message") or choice.get("delta") or choice
    return getattr(choice, "message", None) or getattr(choice, "delta", None) or choice


def _get_response_field(source: Any, raw_source: dict[str, Any], name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    value = getattr(source, name, None)
    if value is not None:
        return value
    return raw_source.get(name)


def _content_part_to_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if item.get("text"):
            return str(item["text"])
        if item.get("content"):
            return str(item["content"])
    text = getattr(item, "text", None)
    if text:
        return str(text)
    content = getattr(item, "content", None)
    if content:
        return str(content)
    return str(item)


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
        nested = normalize_json_schema(field_schema)
        return nested
    raise ValueError(f"Unsupported ai.schema field shorthand: {field_schema!r}")


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return {"value": str(value)}


def _redact_text(text: str, secret: str) -> str:
    if secret:
        return text.replace(secret, "<redacted>")
    return text
