from __future__ import annotations

import json
from typing import Any


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


def extract_chat_completion_stream_text(response: Any) -> tuple[str, dict[str, Any]]:
    chunks: list[str] = []
    raw_chunks: list[Any] = []
    for event in response:
        raw_event = model_dump(event)
        raw_chunks.append(raw_event)
        choices = raw_event.get("choices", [])
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if content:
                    chunks.append(str(content))
            message = choice.get("message")
            if isinstance(message, dict) and message.get("content"):
                chunks.append(str(message["content"]))
            if choice.get("text"):
                chunks.append(str(choice["text"]))
    raw_text = "".join(chunks)
    if not raw_text:
        raise ValueError("AI service returned a streaming response without text content.")
    return raw_text, {"stream": True, "chunks": raw_chunks}


def extract_responses_text(raw_response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in raw_response.get("output", []):
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("text"):
                chunks.append(str(content["text"]))
    return "".join(chunks)


def extract_chat_completion_text(response: Any) -> tuple[str, dict[str, Any]]:
    raw_response = model_dump(response)
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


def self_check_chat_completion_stream_parser() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    dict_stream_text, dict_stream_raw = extract_chat_completion_stream_text(
        [
            {"choices": [{"delta": {"reasoning_content": "internal"}}]},
            {"choices": [{"delta": {"content": '{"ok":'}}]},
            {"choices": [{"delta": {"content": "true}"}}]},
            {"choices": [{"delta": {}}]},
        ]
    )
    checks.append(
        _self_check_result(
            name="dict_stream_chunks",
            passed=dict_stream_text == '{"ok":true}'
            and parse_json_response(dict_stream_text) == {"ok": True}
            and len(dict_stream_raw["chunks"]) == 4,
        )
    )

    class FakeChunk:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def model_dump(self, mode: str = "json") -> dict[str, Any]:
            return self.payload

    object_stream_text, object_stream_raw = extract_chat_completion_stream_text(
        [
            FakeChunk({"choices": [{"message": {"content": '{"label":"valid"}'}}]}),
            FakeChunk({"choices": [{"text": ""}]}),
        ]
    )
    checks.append(
        _self_check_result(
            name="object_stream_chunks",
            passed=object_stream_text == '{"label":"valid"}'
            and parse_json_response(object_stream_text) == {"label": "valid"}
            and len(object_stream_raw["chunks"]) == 2,
        )
    )

    sse_text, _ = extract_chat_completion_text(
        'data: {"choices":[{"delta":{"content":"{\\"message\\":"}}]}\n'
        'data: {"choices":[{"delta":{"content":"\\"ok\\"}"}}]}\n'
        "data: [DONE]\n"
    )
    checks.append(
        _self_check_result(
            name="sse_text_response",
            passed=sse_text == '{"message":"ok"}'
            and parse_json_response(sse_text) == {"message": "ok"},
        )
    )

    empty_stream_rejected = False
    try:
        extract_chat_completion_stream_text([{"choices": [{"delta": {}}]}])
    except ValueError:
        empty_stream_rejected = True
    checks.append(_self_check_result(name="empty_stream_rejected", passed=empty_stream_rejected))

    failures = [check for check in checks if not check["passed"]]
    return {
        "ok": not failures,
        "check": "chat_completion_stream_parser",
        "checks": checks,
    }


def model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return {"value": str(value)}


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


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _self_check_result(*, name: str, passed: bool) -> dict[str, Any]:
    return {"name": name, "passed": passed}
