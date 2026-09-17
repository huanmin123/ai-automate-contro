from __future__ import annotations

from typing import Any

from google import genai

from ai_automate_contro.ai.response_parsing import extract_google_stream_text, model_dump
from ai_automate_contro.ai.service_config import AIServiceOptions


def build_google_client(options: AIServiceOptions) -> genai.Client:
    http_options: dict[str, Any] = {"timeout": int(options.timeout_seconds * 1000)}
    if options.base_url:
        http_options["base_url"] = options.base_url
    if options.max_retries is not None:
        http_options["retry_options"] = {"attempts": options.max_retries + 1}
    return genai.Client(api_key=options.api_key, http_options=http_options)


def call_google_generate_content(
    *,
    client: Any,
    options: AIServiceOptions,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    del schema_name
    system_instruction, contents = _convert_messages(messages)
    config: dict[str, Any] = {}
    if system_instruction:
        config["system_instruction"] = system_instruction
    if options.temperature is not None:
        config["temperature"] = options.temperature
    if options.top_p is not None:
        config["top_p"] = options.top_p
    if options.max_output_tokens is not None:
        config["max_output_tokens"] = options.max_output_tokens
    if options.stop is not None:
        config["stop_sequences"] = options.stop
    if options.reasoning_effort is not None:
        config["thinking_config"] = {"thinking_level": options.reasoning_effort.upper()}
    if options.response_format in {"json_schema", "json_object"}:
        config["response_mime_type"] = "application/json"
    if options.response_format == "json_schema":
        config["response_json_schema"] = schema

    if options.stream:
        response = client.models.generate_content_stream(
            model=options.model,
            contents=contents,
            config=config,
        )
        return extract_google_stream_text(response)
    response = client.models.generate_content(
        model=options.model,
        contents=contents,
        config=config,
    )
    raw_response = model_dump(response)
    raw_text = getattr(response, "text", "") or _extract_google_text(raw_response)
    if not raw_text:
        raise ValueError("Google GenerateContent 响应没有文本内容。")
    return str(raw_text), raw_response


def _convert_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        else:
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                }
            )
    return "\n\n".join(system_parts), contents


def _extract_google_text(raw_response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for candidate in raw_response.get("candidates", []):
        content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
        for part in content.get("parts", []):
            if isinstance(part, dict) and part.get("text") and not part.get("thought"):
                chunks.append(str(part["text"]))
    return "".join(chunks)
