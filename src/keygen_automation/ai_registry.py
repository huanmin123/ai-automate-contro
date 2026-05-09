from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


@dataclass(frozen=True)
class OcrServiceConfig:
    name: str
    base_url: str
    timeout_seconds: float = 30.0
    token_env: str | None = None


@dataclass(frozen=True)
class LlmServiceConfig:
    name: str
    provider: str
    base_url: str
    model: str
    api_key_env: str | None = None
    timeout_seconds: float = 60.0


class AiRegistry:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get_ocr_service(self, name: str) -> OcrServiceConfig:
        services = self.config.get("ocr_services", {})
        if name not in services:
            raise KeyError(f"OCR service '{name}' is not defined.")
        raw = services[name]
        return OcrServiceConfig(
            name=name,
            base_url=str(raw["base_url"]).rstrip("/"),
            timeout_seconds=float(raw.get("timeout_seconds", 30)),
            token_env=raw.get("token_env"),
        )

    def get_llm_service(self, name: str) -> LlmServiceConfig:
        services = self.config.get("llm_services", {})
        if name not in services:
            raise KeyError(f"LLM service '{name}' is not defined.")
        raw = services[name]
        return LlmServiceConfig(
            name=name,
            provider=str(raw.get("provider", "openai-compatible")),
            base_url=str(raw["base_url"]).rstrip("/"),
            model=str(raw["model"]),
            api_key_env=raw.get("api_key_env"),
            timeout_seconds=float(raw.get("timeout_seconds", 60)),
        )

    def build_ocr_headers(self, service: OcrServiceConfig) -> dict[str, str]:
        headers: dict[str, str] = {}
        if service.token_env:
            import os

            token = os.getenv(service.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def build_llm_client(self, service: LlmServiceConfig) -> OpenAI:
        import os

        api_key = "dummy"
        if service.api_key_env:
            api_key = os.getenv(service.api_key_env, "")
            if not api_key:
                raise RuntimeError(
                    f"Environment variable '{service.api_key_env}' is required for LLM service '{service.name}'."
                )
        return OpenAI(
            api_key=api_key,
            base_url=service.base_url,
            timeout=service.timeout_seconds,
        )

def data_url_to_bytes(data_url: str) -> tuple[bytes, str]:
    if not data_url.startswith("data:"):
        raise ValueError("Only data URLs are supported.")
    header, encoded = data_url.split(",", 1)
    mime_type = header[5:].split(";")[0] or "application/octet-stream"
    if ";base64" not in header:
        raise ValueError("Only base64 data URLs are supported.")
    return base64.b64decode(encoded), mime_type


def upload_image_to_ocr(
    service: OcrServiceConfig,
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    headers = {}
    if service.token_env:
        import os

        token = os.getenv(service.token_env, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    client = httpx.Client(timeout=service.timeout_seconds)
    try:
        response = client.post(
            f"{service.base_url}/ocr",
            headers=headers,
            files={"file": (filename, image_bytes, content_type)},
        )
        response.raise_for_status()
        return response.json()
    finally:
        client.close()
