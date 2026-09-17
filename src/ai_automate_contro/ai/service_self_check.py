from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
from anthropic import Anthropic
from google import genai
from google.genai import types as google_types
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from openai import OpenAI

from ai_automate_contro.ai.providers import (
    call_anthropic_messages,
    call_google_generate_content,
    call_openai_chat_completions,
    call_openai_responses,
)
from ai_automate_contro.ai.service_config import resolve_common_model_options, validate_ai_service_config
from ai_automate_contro.ai.terminal_config import build_chat_model


def self_check_ai_services() -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    messages = [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": "Check."},
    ]
    checks: list[dict[str, Any]] = []

    chat_endpoint = _CaptureEndpoint({"choices": [{"message": {"content": '{"ok":true}'}}]})
    chat_options = _options("openai_chat_completions")
    chat_text, _ = call_openai_chat_completions(
        client=SimpleNamespace(chat=SimpleNamespace(completions=chat_endpoint)),
        options=chat_options,
        messages=messages,
        schema=schema,
        schema_name="result",
    )
    chat_request = chat_endpoint.calls[0]
    checks.append(
        _result(
            "openai_chat_completions_mapping",
            chat_text == '{"ok":true}'
            and chat_request.get("reasoning_effort") == "high"
            and chat_request.get("max_completion_tokens") == 123
            and chat_request.get("response_format", {}).get("type") == "json_schema",
            request=chat_request,
        )
    )

    responses_endpoint = _CaptureEndpoint(
        {"output": [{"content": [{"type": "output_text", "text": '{"ok":true}'}]}]}
    )
    responses_options = _options("openai_responses")
    responses_text, _ = call_openai_responses(
        client=SimpleNamespace(responses=responses_endpoint),
        options=responses_options,
        messages=messages,
        schema=schema,
        schema_name="result",
    )
    responses_request = responses_endpoint.calls[0]
    checks.append(
        _result(
            "openai_responses_mapping",
            responses_text == '{"ok":true}'
            and responses_request.get("reasoning") == {"effort": "high"}
            and "reasoning_effort" not in responses_request
            and responses_request.get("text", {}).get("format", {}).get("type") == "json_schema",
            request=responses_request,
        )
    )

    anthropic_endpoint = _AnthropicEndpoint({"content": [{"type": "text", "text": '{"ok":true}'}]})
    anthropic_options = _options("anthropic_messages")
    anthropic_text, _ = call_anthropic_messages(
        client=SimpleNamespace(messages=anthropic_endpoint),
        options=anthropic_options,
        messages=messages,
        schema=schema,
        schema_name="result",
    )
    anthropic_request = anthropic_endpoint.calls[0]
    checks.append(
        _result(
            "anthropic_messages_mapping",
            anthropic_text == '{"ok":true}'
            and anthropic_request.get("output_config", {}).get("effort") == "high"
            and anthropic_request.get("output_config", {}).get("format", {}).get("type") == "json_schema"
            and anthropic_request.get("max_tokens") == 123,
            request=anthropic_request,
        )
    )

    google_models = _GoogleModels()
    google_options = _options("google_generate_content")
    google_text, _ = call_google_generate_content(
        client=SimpleNamespace(models=google_models),
        options=google_options,
        messages=messages,
        schema=schema,
        schema_name="result",
    )
    google_request = google_models.calls[0]
    checks.append(
        _result(
            "google_generate_content_mapping",
            google_text == '{"ok":true}'
            and google_request.get("config", {}).get("thinking_config", {}).get("thinking_level") == "HIGH"
            and google_request.get("config", {}).get("response_mime_type") == "application/json"
            and google_request.get("config", {}).get("response_json_schema") == schema,
            request=google_request,
        )
    )

    checks.extend(_stream_checks(schema=schema, messages=messages))
    checks.extend(_upstream_contract_checks(schema=schema, messages=messages))
    checks.extend(_terminal_model_checks())
    checks.append(_validation_check())
    checks.append(
        _result(
            "default_protocol_is_chat_completions",
            resolve_common_model_options({"model": "test-model"}, api_key="test-key").protocol
            == "openai_chat_completions",
        )
    )
    checks.append(
        _result(
            "legacy_api_alias_is_supported",
            resolve_common_model_options(
                {"api": "responses", "model": "test-model"}, api_key="test-key"
            ).protocol
            == "openai_responses",
        )
    )
    return {"ok": all(check["passed"] for check in checks), "check": "ai_services", "checks": checks}


def _upstream_contract_checks(
    *, schema: dict[str, Any], messages: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Run adapters through the installed provider SDKs and a local HTTP transport.

    The handler never leaves the process. This catches SDK parameter and wire-shape
    regressions that permissive fake endpoints cannot detect.
    """

    requests: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        requests.append((request.url.path, payload))
        if request.url.path.endswith("/chat/completions"):
            if payload.get("stream"):
                return _sse_response(
                    [
                        (
                            "message",
                            {
                                "id": "chatcmpl_self_check",
                                "object": "chat.completion.chunk",
                                "created": 0,
                                "model": "test-model",
                                "choices": [{"index": 0, "delta": {"content": '{"ok":'}}],
                            },
                        ),
                        (
                            "message",
                            {
                                "id": "chatcmpl_self_check",
                                "object": "chat.completion.chunk",
                                "created": 0,
                                "model": "test-model",
                                "choices": [{"index": 0, "delta": {"content": "true}"}}],
                            },
                        ),
                    ],
                    done=True,
                )
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl_self_check",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": '{"ok":true}',
                                "refusal": None,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        if request.url.path.endswith("/responses"):
            if payload.get("stream"):
                return _sse_response(
                    [
                        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": '{"ok":'}),
                        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "true}"}),
                        ("response.completed", {"type": "response.completed"}),
                    ]
                )
            return httpx.Response(
                200,
                json={
                    "id": "resp_self_check",
                    "object": "response",
                    "created_at": 0,
                    "model": "test-model",
                    "output": [
                        {
                            "id": "msg_self_check",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"ok":true}',
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                },
            )
        if request.url.path.endswith("/messages"):
            if payload.get("stream"):
                return _sse_response(
                    [
                        (
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": 0,
                                "delta": {"type": "text_delta", "text": '{"ok":'},
                            },
                        ),
                        (
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": 0,
                                "delta": {"type": "text_delta", "text": "true}"},
                            },
                        ),
                    ]
                )
            return httpx.Response(
                200,
                json={
                    "id": "msg_self_check",
                    "type": "message",
                    "role": "assistant",
                    "model": "test-model",
                    "content": [{"type": "text", "text": '{"ok":true}'}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )
        if ":generateContent" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": '{"ok":true}'}],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 1,
                        "candidatesTokenCount": 1,
                        "totalTokenCount": 2,
                    },
                },
            )
        if ":streamGenerateContent" in request.url.path:
            return _sse_response(
                [
                    (
                        None,
                        {
                            "candidates": [
                                {"content": {"role": "model", "parts": [{"text": '{"ok":'}]}}
                            ]
                        },
                    ),
                    (
                        None,
                        {
                            "candidates": [
                                {"content": {"role": "model", "parts": [{"text": "true}"}]}}
                            ]
                        },
                    ),
                ]
            )
        return httpx.Response(404, json={"error": {"message": "unexpected path"}})

    transport = httpx.MockTransport(handler)
    openai_http = httpx.Client(transport=transport)
    anthropic_http = httpx2.Client(
        transport=httpx2.MockTransport(
            lambda request: _httpx2_response_from_httpx(handler, request)
        )
    )
    google_http = httpx.Client(transport=transport)
    try:
        options_by_protocol = {
            protocol: _options(protocol)
            for protocol in (
                "openai_chat_completions",
                "openai_responses",
                "anthropic_messages",
                "google_generate_content",
            )
        }
        openai_client = OpenAI(
            api_key="test-key",
            base_url="https://mock.openai/v1",
            http_client=openai_http,
        )
        chat_text, _ = call_openai_chat_completions(
            client=openai_client,
            options=options_by_protocol["openai_chat_completions"],
            messages=messages,
            schema=schema,
            schema_name="result",
        )
        responses_text, _ = call_openai_responses(
            client=openai_client,
            options=options_by_protocol["openai_responses"],
            messages=messages,
            schema=schema,
            schema_name="result",
        )
        anthropic_client = Anthropic(
            api_key="test-key",
            base_url="https://mock.anthropic",
            http_client=anthropic_http,
        )
        anthropic_text, _ = call_anthropic_messages(
            client=anthropic_client,
            options=options_by_protocol["anthropic_messages"],
            messages=messages,
            schema=schema,
            schema_name="result",
        )
        google_client = genai.Client(
            api_key="test-key",
            http_options=google_types.HttpOptions(
                base_url="https://mock.google",
                httpx_client=google_http,
            ),
        )
        google_text, _ = call_google_generate_content(
            client=google_client,
            options=options_by_protocol["google_generate_content"],
            messages=messages,
            schema=schema,
            schema_name="result",
        )
        stream_texts = [
            call_openai_chat_completions(
                client=openai_client,
                options=_options("openai_chat_completions", stream=True),
                messages=messages,
                schema=schema,
                schema_name="result",
            )[0],
            call_openai_responses(
                client=openai_client,
                options=_options("openai_responses", stream=True),
                messages=messages,
                schema=schema,
                schema_name="result",
            )[0],
            call_anthropic_messages(
                client=anthropic_client,
                options=_options("anthropic_messages", stream=True),
                messages=messages,
                schema=schema,
                schema_name="result",
            )[0],
            call_google_generate_content(
                client=google_client,
                options=_options("google_generate_content", stream=True),
                messages=messages,
                schema=schema,
                schema_name="result",
            )[0],
        ]
    except Exception as error:
        return [_result("installed_sdk_http_mock_contract", False, error=str(error))]
    finally:
        openai_http.close()
        anthropic_http.close()
        google_http.close()

    by_path = {path: payload for path, payload in requests}
    chat_payload = by_path.get("/v1/chat/completions", {})
    responses_payload = by_path.get("/v1/responses", {})
    anthropic_payload = by_path.get("/v1/messages", {})
    google_payload = next(
        (payload for path, payload in requests if ":generateContent" in path), {}
    )
    generation = google_payload.get("generationConfig", {})
    passed = (
        chat_text == responses_text == anthropic_text == google_text == '{"ok":true}'
        and stream_texts == ['{"ok":true}'] * 4
        and chat_payload.get("reasoning_effort") == "high"
        and chat_payload.get("max_completion_tokens") == 123
        and chat_payload.get("response_format", {}).get("type") == "json_schema"
        and responses_payload.get("reasoning") == {"effort": "high"}
        and "reasoning_effort" not in responses_payload
        and responses_payload.get("max_output_tokens") == 123
        and responses_payload.get("text", {}).get("format", {}).get("type")
        == "json_schema"
        and anthropic_payload.get("output_config", {}).get("effort") == "high"
        and anthropic_payload.get("output_config", {}).get("format", {}).get("type")
        == "json_schema"
        and anthropic_payload.get("max_tokens") == 123
        and generation.get("thinkingConfig", {}).get("thinking_level") == "HIGH"
        and generation.get("responseMimeType") == "application/json"
        and generation.get("responseJsonSchema") == schema
    )
    return [
        _result(
            "installed_sdk_http_mock_contract",
            passed,
            request_paths=[path for path, _ in requests],
        )
    ]


def _httpx2_response_from_httpx(
    handler: Any, request: Any
) -> Any:
    response = handler(request)
    return httpx2.Response(
        response.status_code,
        headers=dict(response.headers),
        content=response.content,
        request=request,
    )


def _sse_response(
    events: list[tuple[str | None, dict[str, Any]]], *, done: bool = False
) -> httpx.Response:
    body = "".join(
        "".join(
            part
            for part in (
                f"event: {event_name}\n" if event_name else "",
                f"data: {json.dumps(event)}\n\n",
            )
        )
        for event_name, event in events
    )
    if done:
        body += "event: message\ndata: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def _stream_checks(*, schema: dict[str, Any], messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    fixtures = [
        (
            "openai_responses_stream",
            call_openai_responses,
            SimpleNamespace(
                responses=_CaptureEndpoint(
                    [
                        {"type": "response.output_text.delta", "delta": '{"ok":'},
                        {"type": "response.output_text.delta", "delta": "true}"},
                    ]
                )
            ),
            "openai_responses",
        ),
        (
            "anthropic_messages_stream",
            call_anthropic_messages,
            SimpleNamespace(
                messages=_CaptureEndpoint(
                    [
                        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": '{"ok":'}},
                        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "true}"}},
                    ]
                )
            ),
            "anthropic_messages",
        ),
    ]
    for name, caller, client, protocol in fixtures:
        options = _options(protocol, stream=True)
        text, raw = caller(
            client=client,
            options=options,
            messages=messages,
            schema=schema,
            schema_name="result",
        )
        checks.append(_result(name, text == '{"ok":true}' and len(raw.get("chunks", [])) == 2))

    google_models = _GoogleModels(stream=True)
    text, raw = call_google_generate_content(
        client=SimpleNamespace(models=google_models),
        options=_options("google_generate_content", stream=True),
        messages=messages,
        schema=schema,
        schema_name="result",
    )
    checks.append(_result("google_generate_content_stream", text == '{"ok":true}' and len(raw["chunks"]) == 2))
    return checks


def _terminal_model_checks() -> list[dict[str, Any]]:
    expected = {
        "openai_chat_completions": ChatOpenAI,
        "openai_responses": ChatOpenAI,
        "anthropic_messages": ChatAnthropic,
        "google_generate_content": ChatGoogleGenerativeAI,
    }
    checks: list[dict[str, Any]] = []
    for protocol, expected_type in expected.items():
        model = build_chat_model(_config(protocol), service_name="self-check")
        passed = isinstance(model, expected_type)
        if protocol == "openai_responses":
            passed = passed and model.use_responses_api is True
        checks.append(_result(f"terminal_model_{protocol}", passed, model_type=type(model).__name__))
    return checks


def _validation_check() -> dict[str, Any]:
    rejected_reasoning = False
    try:
        validate_ai_service_config(
            {"protocol": "google_generate_content", "model": "test-model", "reasoning_effort": "xhigh"}
        )
    except ValueError:
        rejected_reasoning = True

    rejected_anthropic_sampling = False
    try:
        validate_ai_service_config(
            {"protocol": "anthropic_messages", "model": "test-model", "temperature": 0.2}
        )
    except ValueError:
        rejected_anthropic_sampling = True
    return _result(
        "protocol_specific_capability_validation",
        rejected_reasoning and rejected_anthropic_sampling,
    )


def _config(protocol: str, *, stream: bool = False) -> dict[str, Any]:
    config = {
        "protocol": protocol,
        "model": "test-model",
        "api_key": "test-key",
        "stream": stream,
        "temperature": 0.3,
        "top_p": 0.8,
        "max_output_tokens": 123,
        "stop": ["STOP"],
        "reasoning_effort": "high",
        "response_format": "json_schema",
        "strict_schema": True,
    }
    if protocol == "openai_responses":
        config.pop("stop")
    if protocol == "anthropic_messages":
        config.pop("temperature")
        config.pop("top_p")
    return config


def _options(protocol: str, *, stream: bool = False):
    return resolve_common_model_options(_config(protocol, stream=stream), api_key="test-key")


class _CaptureEndpoint:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


class _AnthropicEndpoint:
    """Matches the subset of Messages.create kwargs used by this adapter."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict[str, str]],
        system: str | None = None,
        stop_sequences: list[str] | None = None,
        output_config: dict[str, Any] | None = None,
        stream: bool | None = None,
    ) -> Any:
        self.calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                **({"system": system} if system is not None else {}),
                **({"stop_sequences": stop_sequences} if stop_sequences is not None else {}),
                **({"output_config": output_config} if output_config is not None else {}),
                **({"stream": stream} if stream is not None else {}),
            }
        )
        return self.response


class _FakeGoogleResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        del mode
        return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}


class _GoogleModels:
    def __init__(self, *, stream: bool = False) -> None:
        self.stream = stream
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> _FakeGoogleResponse:
        self.calls.append(kwargs)
        return _FakeGoogleResponse('{"ok":true}')

    def generate_content_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        return iter([_FakeGoogleResponse('{"ok":'), _FakeGoogleResponse("true}")])


def _result(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), **detail}
