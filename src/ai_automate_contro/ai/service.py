from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from typing import Any

from ai_automate_contro.app.errors import UserFacingError
from ai_automate_contro.ai.prompts.controlled_ai import (
    CONTROLLED_AI_SYSTEM_PROMPT,
    build_controlled_ai_payload,
)
from ai_automate_contro.ai.providers import (
    call_anthropic_messages,
    call_google_generate_content,
    call_openai_chat_completions,
    call_openai_responses,
)
from ai_automate_contro.ai.providers.anthropic import build_anthropic_client
from ai_automate_contro.ai.providers.google import build_google_client
from ai_automate_contro.ai.providers.openai import build_openai_client
from ai_automate_contro.ai.response_parsing import parse_json_response
from ai_automate_contro.ai.schemas import validate_with_schema
from ai_automate_contro.ai.service_config import (
    AIServiceOptions,
    resolve_common_model_options,
    validate_ai_service_config,
)


@dataclass(frozen=True)
class AIResult:
    parsed: Any
    raw_text: str
    raw_response: dict[str, Any]
    schema: dict[str, Any]
    response_format: str
    protocol: str
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
    try:
        validate_ai_service_config(service_config)
    except (TypeError, ValueError) as error:
        raise UserFacingError(f"AI 服务配置无效：{service_name}", details=[str(error)]) from error
    model = service_config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise UserFacingError(
            f"AI 服务缺少 model：{service_name}",
            fix=f"在 ai_services.{service_name}.model 填入模型名。",
        )
    api_key = resolve_api_key(service_name, service_config)
    options = resolve_common_model_options(service_config, api_key=api_key)

    messages = build_ai_task_messages(
        task_type=task_type,
        input_value=input_value,
        instruction=instruction,
        schema=schema,
        labels=labels or [],
    )
    raw_text, raw_response = call_model(
        options=options,
        messages=messages,
        schema=schema,
        schema_name=f"{task_type}_result",
    )
    parsed = parse_json_response(raw_text)
    validate_with_schema(parsed, schema)

    return AIResult(
        parsed=parsed,
        raw_text=raw_text,
        raw_response=raw_response,
        schema=schema,
        response_format=options.response_format,
        protocol=options.protocol,
        attempts=[
            {
                "protocol": options.protocol,
                "response_format": options.response_format,
                "status": "passed",
            }
        ],
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
    options: AIServiceOptions,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    if options.protocol == "openai_chat_completions":
        return call_openai_chat_completions(
            client=build_openai_client(options),
            options=options,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
        )
    if options.protocol == "openai_responses":
        return call_openai_responses(
            client=build_openai_client(options),
            options=options,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
        )
    if options.protocol == "anthropic_messages":
        return call_anthropic_messages(
            client=build_anthropic_client(options),
            options=options,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
        )
    if options.protocol == "google_generate_content":
        return call_google_generate_content(
            client=build_google_client(options),
            options=options,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
        )
    raise ValueError(f"Unsupported AI protocol: {options.protocol}")
