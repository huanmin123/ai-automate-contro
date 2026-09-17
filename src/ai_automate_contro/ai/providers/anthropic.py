from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from ai_automate_contro.ai.response_parsing import extract_anthropic_stream_text, model_dump
from ai_automate_contro.ai.service_config import AIServiceOptions


def build_anthropic_client(options: AIServiceOptions) -> Anthropic:
    kwargs: dict[str, Any] = {
        "api_key": options.api_key,
        "timeout": options.timeout_seconds,
    }
    if options.max_retries is not None:
        kwargs["max_retries"] = options.max_retries
    if options.base_url:
        kwargs["base_url"] = options.base_url
    return Anthropic(**kwargs)


def call_anthropic_messages(
    *,
    client: Any,
    options: AIServiceOptions,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    del schema_name
    system, anthropic_messages = _convert_messages(messages)
    kwargs: dict[str, Any] = {
        "model": options.model,
        "max_tokens": options.max_output_tokens or 4096,
        "messages": anthropic_messages,
    }
    if system:
        kwargs["system"] = system
    if options.stop is not None:
        kwargs["stop_sequences"] = options.stop

    output_config: dict[str, Any] = {}
    if options.reasoning_effort is not None:
        output_config["effort"] = options.reasoning_effort
    if options.response_format == "json_schema":
        output_config["format"] = {"type": "json_schema", "schema": schema}
    elif options.response_format == "json_object":
        output_config["format"] = {"type": "json_schema", "schema": {"type": "object"}}
    if output_config:
        kwargs["output_config"] = output_config
    if options.stream:
        kwargs["stream"] = True

    response = client.messages.create(**kwargs)
    if options.stream:
        return extract_anthropic_stream_text(response)
    raw_response = model_dump(response)
    raw_text = _extract_anthropic_text(raw_response)
    if not raw_text:
        raise ValueError("Anthropic Messages 响应没有文本内容。")
    return raw_text, raw_response


def _convert_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    converted: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        else:
            converted.append({"role": "assistant" if role == "assistant" else "user", "content": content})
    return "\n\n".join(system_parts), converted


def _extract_anthropic_text(raw_response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for block in raw_response.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            chunks.append(str(block["text"]))
    return "".join(chunks)
