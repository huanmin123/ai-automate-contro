from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ai_automate_contro.app.errors import UserFacingError
from ai_automate_contro.ai.prompts.controlled_ai import (
    CONTROLLED_AI_SYSTEM_PROMPT,
    build_controlled_ai_payload,
)
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
        raise UserFacingError(f"AI 服务配置必须是对象：{service_name}")
    provider = str(service_config.get("provider", "openai-compatible"))
    if provider not in {"openai", "openai-compatible"}:
        raise UserFacingError(
            f"不支持的 AI provider：{provider}",
            fix=f"把 ai_services.{service_name}.provider 改成 openai 或 openai-compatible。",
        )

    model = service_config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise UserFacingError(
            f"AI 服务缺少 model：{service_name}",
            fix=f"在 ai_services.{service_name}.model 填入模型名。",
        )
    api_key = resolve_api_key(service_name, service_config)
    timeout_seconds = float(service_config.get("timeout_seconds", 60))

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": timeout_seconds,
    }
    if service_config.get("max_retries") is not None:
        client_kwargs["max_retries"] = int(service_config["max_retries"])
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
    response_format = resolve_response_format(service_config)

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

    return AIResult(
        parsed=parsed,
        raw_text=raw_text,
        raw_response=raw_response,
        schema=schema,
        response_format=response_format,
        attempts=[{"response_format": response_format, "status": "passed"}],
    )


def service_config_for_artifact(service_config: dict[str, Any]) -> dict[str, Any]:
    return dict(service_config)


def resolve_api_key(service_name: str, service_config: dict[str, Any]) -> str:
    if service_config.get("api_key"):
        return str(service_config["api_key"])
    api_key_env = service_config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            return api_key
    raise UserFacingError(
        f"AI 服务缺少 api_key 或有效的 api_key_env：{service_name}",
        fix=(
            f"在 ai_services.{service_name} 里配置 api_key，或配置 api_key_env 并在当前终端设置对应环境变量。\n"
            f"示例：{_api_key_env_example()}"
        ),
    )


def _api_key_env_example() -> str:
    if platform.system() == "Windows":
        return "$env:OPENAI_API_KEY='<your-api-key>'"
    return "export OPENAI_API_KEY='<your-api-key>'"


def resolve_response_format(service_config: dict[str, Any]) -> str:
    raw_response_format = service_config.get("response_format")
    if raw_response_format is None:
        raw_response_format = "json_schema"
    if not isinstance(raw_response_format, str) or not raw_response_format.strip():
        raise ValueError("AI 服务 response_format 必须是非空字符串。")
    response_format = raw_response_format.strip()
    if response_format not in {"json_schema", "json_object", "plain"}:
        raise ValueError(f"不支持的 AI response_format：{response_format}")
    return response_format


def build_ai_task_messages(
    *,
    task_type: str,
    input_value: Any,
    instruction: str,
    schema: dict[str, Any],
    labels: list[Any],
) -> list[dict[str, str]]:
    payload = build_controlled_ai_payload(
        task_type=task_type,
        input_value=input_value,
        instruction=instruction,
        schema=schema,
        labels=labels,
    )
    return [
        {"role": "system", "content": CONTROLLED_AI_SYSTEM_PROMPT},
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
