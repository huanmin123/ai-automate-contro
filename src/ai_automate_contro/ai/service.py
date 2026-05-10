from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ai_automate_contro.ai.response_parsing import (
    extract_chat_completion_stream_text,
    extract_chat_completion_text,
    extract_responses_text,
    model_dump,
    parse_json_response,
)
from ai_automate_contro.ai.schemas import validate_with_schema


@dataclass(frozen=True)
class AIResult:
    parsed: Any
    raw_text: str
    raw_response: dict[str, Any]
    schema: dict[str, Any]
    response_format: str
    attempts: list[dict[str, Any]]


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
    api_key = resolve_api_key(service_name, service_config)
    timeout_seconds = float(service_config.get("timeout_seconds", 60))

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": timeout_seconds,
    }
    if service_config.get("base_url"):
        client_kwargs["base_url"] = str(service_config["base_url"])
    client = OpenAI(**client_kwargs)

    messages = build_ai_task_messages(
        task_type=task_type,
        input_value=input_value,
        instruction=instruction,
        schema=schema,
        labels=labels or [],
    )
    response_api = str(service_config.get("api", "chat_completions"))
    strict = bool(service_config.get("strict_schema", True))
    stream = bool(service_config.get("stream", False))
    response_formats = service_config.get("response_formats", ["json_schema", "json_object", "plain"])
    if not isinstance(response_formats, list) or not response_formats:
        response_formats = ["json_schema", "json_object", "plain"]

    attempts: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for response_format in [str(item) for item in response_formats]:
        try:
            raw_text, raw_response = call_model(
                client=client,
                response_api=response_api,
                model=model,
                messages=messages,
                schema=schema,
                schema_name=f"{task_type}_result",
                response_format=response_format,
                strict=strict,
                stream=stream,
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
                    "error": redact_text(str(error), api_key),
                }
            )

    raise RuntimeError(
        f"AI task failed for service '{service_name}'. Attempts: "
        f"{json.dumps(attempts, ensure_ascii=False)}"
    ) from last_error


def service_config_for_artifact(service_config: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(service_config)
    if "api_key" in redacted:
        redacted["api_key"] = "<redacted>"
    if "api_key_env" in redacted:
        redacted["api_key_env"] = str(redacted["api_key_env"])
    return redacted


def resolve_api_key(service_name: str, service_config: dict[str, Any]) -> str:
    if service_config.get("api_key"):
        return str(service_config["api_key"])
    api_key_env = service_config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            return api_key
    raise ValueError(f"AI service '{service_name}' requires api_key or api_key_env.")


def redact_text(text: str, secret: str) -> str:
    if secret:
        return text.replace(secret, "<redacted>")
    return text


def build_ai_task_messages(
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


def call_model(
    *,
    client: OpenAI,
    response_api: str,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    response_format: str,
    strict: bool,
    stream: bool,
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
            stream=stream,
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
        stream=stream,
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
    stream: bool,
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
    if stream:
        kwargs["stream"] = True

    response = client.chat.completions.create(**kwargs)
    if stream:
        return extract_chat_completion_stream_text(response)
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
    stream: bool,
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
    raw_response = model_dump(response)
    raw_text = getattr(response, "output_text", "") or extract_responses_text(raw_response)
    return raw_text, raw_response
