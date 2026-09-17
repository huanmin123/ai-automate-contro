from __future__ import annotations

from typing import Any

from openai import OpenAI

from ai_automate_contro.ai.response_parsing import (
    extract_chat_completion_stream_text,
    extract_chat_completion_text,
    extract_responses_stream_text,
    extract_responses_text,
    model_dump,
)
from ai_automate_contro.ai.service_config import AIServiceOptions


def build_openai_client(options: AIServiceOptions) -> OpenAI:
    kwargs: dict[str, Any] = {
        "api_key": options.api_key,
        "timeout": options.timeout_seconds,
    }
    if options.max_retries is not None:
        kwargs["max_retries"] = options.max_retries
    if options.base_url:
        kwargs["base_url"] = options.base_url
    return OpenAI(**kwargs)


def call_openai_chat_completions(
    *,
    client: Any,
    options: AIServiceOptions,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {"model": options.model, "messages": messages}
    _apply_common_generation_options(kwargs, options, max_tokens_key="max_completion_tokens")
    if options.reasoning_effort is not None:
        kwargs["reasoning_effort"] = options.reasoning_effort
    if options.response_format == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": options.strict_schema,
            },
        }
    elif options.response_format == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    if options.stream:
        kwargs["stream"] = True

    response = client.chat.completions.create(**kwargs)
    if options.stream:
        return extract_chat_completion_stream_text(response)
    return extract_chat_completion_text(response)


def call_openai_responses(
    *,
    client: Any,
    options: AIServiceOptions,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    kwargs: dict[str, Any] = {"model": options.model, "input": messages}
    _apply_common_generation_options(kwargs, options, max_tokens_key="max_output_tokens", include_stop=False)
    if options.reasoning_effort is not None:
        kwargs["reasoning"] = {"effort": options.reasoning_effort}
    if options.response_format == "json_schema":
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": options.strict_schema,
            }
        }
    elif options.response_format == "json_object":
        kwargs["text"] = {"format": {"type": "json_object"}}
    if options.stream:
        kwargs["stream"] = True

    response = client.responses.create(**kwargs)
    if options.stream:
        return extract_responses_stream_text(response)
    raw_response = model_dump(response)
    raw_text = getattr(response, "output_text", "") or extract_responses_text(raw_response)
    if not raw_text:
        raise ValueError("AI 服务响应没有文本内容。")
    return str(raw_text), raw_response


def _apply_common_generation_options(
    kwargs: dict[str, Any],
    options: AIServiceOptions,
    *,
    max_tokens_key: str,
    include_stop: bool = True,
) -> None:
    if options.temperature is not None:
        kwargs["temperature"] = options.temperature
    if options.top_p is not None:
        kwargs["top_p"] = options.top_p
    if options.max_output_tokens is not None:
        kwargs[max_tokens_key] = options.max_output_tokens
    if include_stop and options.stop is not None:
        kwargs["stop"] = options.stop
