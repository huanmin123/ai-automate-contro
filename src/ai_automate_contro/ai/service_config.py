from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_AI_PROTOCOL = "openai_chat_completions"
SUPPORTED_AI_PROTOCOLS = {
    DEFAULT_AI_PROTOCOL,
    "openai_responses",
    "anthropic_messages",
    "google_generate_content",
}

_LEGACY_API_PROTOCOLS = {
    "chat_completions": "openai_chat_completions",
    "responses": "openai_responses",
}

_PROTOCOL_PROVIDERS = {
    "openai_chat_completions": {"openai", "openai-compatible"},
    "openai_responses": {"openai", "openai-compatible"},
    "anthropic_messages": {"anthropic"},
    "google_generate_content": {"google", "gemini"},
}

_REASONING_EFFORTS = {
    "openai_chat_completions": {"none", "minimal", "low", "medium", "high", "xhigh", "max"},
    "openai_responses": {"none", "minimal", "low", "medium", "high", "xhigh", "max"},
    "anthropic_messages": {"low", "medium", "high", "xhigh", "max"},
    "google_generate_content": {"minimal", "low", "medium", "high"},
}


@dataclass(frozen=True)
class AIServiceOptions:
    protocol: str
    model: str
    api_key: str
    base_url: str | None
    timeout_seconds: float
    max_retries: int | None
    stream: bool
    response_format: str
    strict_schema: bool
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    stop: list[str] | None
    reasoning_effort: str | None


def resolve_ai_protocol(service_config: dict[str, Any]) -> str:
    raw_protocol = service_config.get("protocol")
    legacy_api = service_config.get("api")
    if raw_protocol is None and legacy_api is not None:
        if not isinstance(legacy_api, str):
            raise ValueError(f"不支持的 AI api：{legacy_api}")
        raw_protocol = _LEGACY_API_PROTOCOLS.get(legacy_api, legacy_api)
    if raw_protocol is None:
        raw_protocol = DEFAULT_AI_PROTOCOL
    if not isinstance(raw_protocol, str) or not raw_protocol.strip():
        raise ValueError("AI 服务 protocol 必须是非空字符串。")
    protocol = raw_protocol.strip()
    if protocol not in SUPPORTED_AI_PROTOCOLS:
        supported = ", ".join(sorted(SUPPORTED_AI_PROTOCOLS))
        raise ValueError(f"不支持的 AI protocol：{protocol}；可选值：{supported}")

    provider = service_config.get("provider")
    if provider is not None:
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("AI 服务 provider 必须是非空字符串。")
        normalized_provider = provider.strip()
        if normalized_provider not in _PROTOCOL_PROVIDERS[protocol]:
            allowed = ", ".join(sorted(_PROTOCOL_PROVIDERS[protocol]))
            raise ValueError(
                f"AI provider={normalized_provider} 与 protocol={protocol} 不匹配；允许 provider：{allowed}"
            )
    return protocol


def resolve_reasoning_effort(service_config: dict[str, Any], *, protocol: str) -> str | None:
    raw_effort = service_config.get("reasoning_effort")
    if raw_effort is None:
        return None
    if not isinstance(raw_effort, str) or not raw_effort.strip():
        raise ValueError("AI 服务 reasoning_effort 必须是非空字符串。")
    effort = raw_effort.strip()
    supported = _REASONING_EFFORTS[protocol]
    if effort not in supported:
        allowed = ", ".join(sorted(supported))
        raise ValueError(
            f"protocol={protocol} 不支持 reasoning_effort={effort}；可选值：{allowed}"
        )
    return effort


def resolve_response_format(service_config: dict[str, Any]) -> str:
    raw_response_format = service_config.get("response_format", "json_schema")
    if not isinstance(raw_response_format, str) or not raw_response_format.strip():
        raise ValueError("AI 服务 response_format 必须是非空字符串。")
    response_format = raw_response_format.strip()
    if response_format not in {"json_schema", "json_object", "plain"}:
        raise ValueError(f"不支持的 AI response_format：{response_format}")
    return response_format


def resolve_common_model_options(service_config: dict[str, Any], *, api_key: str) -> AIServiceOptions:
    protocol = resolve_ai_protocol(service_config)
    model = service_config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("AI 服务 model 必须是非空字符串。")

    max_retries = _optional_int(service_config, "max_retries")
    max_output_tokens = _optional_int(service_config, "max_output_tokens")
    if max_retries is not None and max_retries < 0:
        raise ValueError("AI 服务 max_retries 不能小于 0。")
    if max_output_tokens is not None and max_output_tokens <= 0:
        raise ValueError("AI 服务 max_output_tokens 必须大于 0。")

    timeout_seconds = _number(service_config, "timeout_seconds", default=60)
    if timeout_seconds <= 0:
        raise ValueError("AI 服务 timeout_seconds 必须大于 0。")
    stream = _boolean(service_config, "stream", default=False)
    strict_schema = _boolean(service_config, "strict_schema", default=True)
    stop = _optional_stop(service_config)
    temperature = _optional_float(service_config, "temperature")
    top_p = _optional_float(service_config, "top_p")
    _validate_protocol_capabilities(
        protocol=protocol,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )

    return AIServiceOptions(
        protocol=protocol,
        model=model.strip(),
        api_key=api_key,
        base_url=_optional_string(service_config, "base_url"),
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        stream=stream,
        response_format=resolve_response_format(service_config),
        strict_schema=strict_schema,
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=max_output_tokens,
        stop=stop,
        reasoning_effort=resolve_reasoning_effort(service_config, protocol=protocol),
    )


def validate_ai_service_config(service_config: dict[str, Any]) -> None:
    protocol = resolve_ai_protocol(service_config)
    model = service_config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("AI 服务 model 必须是非空字符串。")
    resolve_response_format(service_config)
    resolve_reasoning_effort(service_config, protocol=protocol)
    timeout_seconds = _number(service_config, "timeout_seconds", default=60)
    if timeout_seconds <= 0:
        raise ValueError("AI 服务 timeout_seconds 必须大于 0。")
    _boolean(service_config, "stream", default=False)
    _boolean(service_config, "strict_schema", default=True)
    temperature = _optional_float(service_config, "temperature")
    top_p = _optional_float(service_config, "top_p")
    max_retries = _optional_int(service_config, "max_retries")
    max_output_tokens = _optional_int(service_config, "max_output_tokens")
    if max_retries is not None and max_retries < 0:
        raise ValueError("AI 服务 max_retries 不能小于 0。")
    if max_output_tokens is not None and max_output_tokens <= 0:
        raise ValueError("AI 服务 max_output_tokens 必须大于 0。")
    stop = _optional_stop(service_config)
    _optional_string(service_config, "api_key")
    _optional_string(service_config, "api_key_env")
    _optional_string(service_config, "base_url")
    _validate_protocol_capabilities(
        protocol=protocol,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
    )


def _validate_protocol_capabilities(
    *,
    protocol: str,
    temperature: float | None,
    top_p: float | None,
    stop: list[str] | None,
) -> None:
    if protocol == "openai_responses" and stop is not None:
        raise ValueError("protocol=openai_responses 不支持通用参数 stop，请删除该字段。")
    if protocol == "anthropic_messages" and temperature is not None:
        raise ValueError(
            "protocol=anthropic_messages 不支持通用参数 temperature，请删除该字段。"
        )
    if protocol == "anthropic_messages" and top_p is not None:
        raise ValueError("protocol=anthropic_messages 不支持通用参数 top_p，请删除该字段。")


def _optional_string(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AI 服务 {key} 必须是非空字符串。")
    return value.strip()


def _optional_float(config: dict[str, Any], key: str) -> float | None:
    value = config.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AI 服务 {key} 必须是数字。")
    return float(value)


def _optional_int(config: dict[str, Any], key: str) -> int | None:
    value = config.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"AI 服务 {key} 必须是整数。")
    return value


def _optional_stop(config: dict[str, Any]) -> list[str] | None:
    value = config.get("stop")
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError("AI 服务 stop 必须是非空字符串或非空字符串数组。")
    return list(value)


def _boolean(config: dict[str, Any], key: str, *, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"AI 服务 {key} 必须是布尔值。")
    return value


def _number(config: dict[str, Any], key: str, *, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AI 服务 {key} 必须是数字。")
    return float(value)
