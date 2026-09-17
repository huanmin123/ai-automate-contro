from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ai_automate_contro.app.errors import UserFacingError
from ai_automate_contro.app.runtime_config import default_ai_config_dir_for_project
from ai_automate_contro.ai.service_config import resolve_common_model_options, validate_ai_service_config
from ai_automate_contro.plans.config import load_plan_config


@dataclass
class AITerminalConfig:
    service_name: str
    service_config: dict[str, Any]


def load_ai_terminal_config(project_root: Path, *, service_name: str = "default") -> AITerminalConfig:
    ai_config_dir = default_ai_config_dir_for_project(project_root)
    config_path = ai_config_dir / "config.json"
    plan_config = load_plan_config(project_root, ai_config_dir)
    ai_services = plan_config.get("ai_services", {})
    if not isinstance(ai_services, dict):
        raise UserFacingError(
            "AI 服务配置格式不正确：config.ai_services 必须是 JSON object。",
            details=[f"配置文件：{config_path}"],
            fix="把 ai_services 改成对象，并在里面配置 default 服务。",
            verify=[_verify_command("self-check env")],
        )
    service_config = ai_services.get(service_name)
    if not isinstance(service_config, dict):
        raise UserFacingError(
            f"AI 终端服务未配置：{service_name}",
            details=[
                f"运行根目录：{Path(project_root).resolve()}",
                f"配置文件：{config_path}",
            ],
            fix=(
                "编辑上面的 config.json，添加 ai_services.default，例如：\n"
                "{\n"
                '  "ai_services": {\n'
                '    "default": {\n'
                '      "base_url": "https://your-openai-compatible-endpoint/v1",\n'
                '      "model": "your-model",\n'
                '      "api_key_env": "AIC_TEST_API_KEY"\n'
                "    }\n"
                "  }\n"
                "}"
            ),
            verify=[
                _verify_command("self-check env"),
                _verify_command("ai"),
            ],
        )
    if not service_config.get("model"):
        raise UserFacingError(
            f"AI 终端服务缺少 model：{service_name}",
            details=[f"配置文件：{config_path}"],
            fix=f"在 ai_services.{service_name}.model 填入模型名。",
            verify=[_verify_command("self-check env")],
        )
    try:
        validate_ai_service_config(service_config)
    except (TypeError, ValueError) as error:
        raise UserFacingError(
            f"AI 终端服务配置无效：{service_name}",
            details=[str(error), f"配置文件：{config_path}"],
            fix=f"修正 ai_services.{service_name} 的 protocol 和通用模型参数。",
            verify=[_verify_command("self-check env")],
        ) from error
    resolve_ai_terminal_api_key(service_name, service_config)
    return AITerminalConfig(service_name=service_name, service_config=service_config)


def build_chat_model(service_config: dict[str, Any], *, service_name: str = "default") -> BaseChatModel:
    options = resolve_common_model_options(
        service_config,
        api_key=resolve_ai_terminal_api_key(service_name, service_config),
    )
    kwargs: dict[str, Any] = {
        "model": options.model,
        # The terminal renders token events continuously; service-level stream
        # controls the standalone ai action, while terminal streaming remains on.
        "streaming": True,
    }
    if options.temperature is not None:
        kwargs["temperature"] = options.temperature
    if options.top_p is not None:
        kwargs["top_p"] = options.top_p
    if options.max_output_tokens is not None:
        kwargs["max_tokens"] = options.max_output_tokens
    if options.stop is not None:
        kwargs["stop"] = options.stop
    if options.reasoning_effort is not None:
        kwargs["reasoning_effort"] = options.reasoning_effort
    if options.max_retries is not None:
        kwargs["max_retries"] = options.max_retries

    if options.protocol in {"openai_chat_completions", "openai_responses"}:
        kwargs.update(
            {
                "api_key": options.api_key,
                "timeout": options.timeout_seconds,
                "use_responses_api": options.protocol == "openai_responses",
            }
        )
        if options.base_url:
            kwargs["base_url"] = options.base_url
        return ChatOpenAI(**kwargs)

    if options.protocol == "anthropic_messages":
        kwargs.update(
            {
                "api_key": options.api_key,
                "timeout": options.timeout_seconds,
            }
        )
        if options.base_url:
            kwargs["base_url"] = options.base_url
        return ChatAnthropic(**kwargs)

    if options.protocol == "google_generate_content":
        if "max_tokens" in kwargs:
            kwargs["max_output_tokens"] = kwargs.pop("max_tokens")
        kwargs.setdefault("temperature", None)
        kwargs.update(
            {
                "google_api_key": options.api_key,
                "timeout": options.timeout_seconds,
            }
        )
        if options.base_url:
            kwargs["base_url"] = options.base_url
        return ChatGoogleGenerativeAI(**kwargs)

    raise ValueError(f"Unsupported AI protocol: {options.protocol}")


def resolve_ai_terminal_api_key(service_name: str, service_config: dict[str, Any]) -> str:
    if service_config.get("api_key"):
        return str(service_config["api_key"])
    api_key_env = service_config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            return api_key
    raise UserFacingError(
        f"AI 终端服务缺少 api_key 或有效的 api_key_env：{service_name}",
        fix=(
            f"在 ai_services.{service_name} 里配置 api_key，或配置 api_key_env 并在当前终端设置对应环境变量。\n"
            f"示例：{_api_key_env_example()}"
        ),
        verify=[_verify_command("self-check env")],
    )


def _verify_command(arguments: str) -> str:
    executable = ".\\aic.exe" if platform.system() == "Windows" else "./aic"
    return f"{executable} {arguments}"


def _api_key_env_example() -> str:
    if platform.system() == "Windows":
        return "$env:OPENAI_API_KEY='<your-api-key>'"
    return "export OPENAI_API_KEY='<your-api-key>'"
