from __future__ import annotations

import json
from typing import Any

from ai_automate_contro.ai.schemas import build_ai_schema
from ai_automate_contro.ai.service import run_ai_task, service_config_for_artifact
from ai_automate_contro.app.errors import UserFacingError


def action_ai(executor: Any, step: dict[str, Any]) -> None:
    ai_type = step["type"]
    service_name = step.get("service", "default")
    ai_services = executor.state.variables.get("config", {}).get("ai_services", {})
    if not isinstance(ai_services, dict):
        raise UserFacingError(
            "专项 AI 配置格式不正确：config.ai_services 必须是 JSON object。",
            fix="检查当前 plan 包 config.json 或集合级 config.json，把 ai_services 改成对象。",
        )
    service_config = ai_services.get(service_name)
    if not isinstance(service_config, dict):
        raise UserFacingError(
            f"专项 AI 服务未配置：{service_name}",
            fix=(
                "在当前 plan 包 config.json 或集合级 config.json 中添加 ai_services 配置，例如：\n"
                "{\n"
                '  "ai_services": {\n'
                f'    "{service_name}": {{\n'
                '      "base_url": "https://your-openai-compatible-endpoint/v1",\n'
                '      "model": "your-model",\n'
                '      "api_key_env": "AIC_TEST_API_KEY"\n'
                "    }\n"
                "  }\n"
                "}"
            ),
        )

    schema = build_ai_schema(ai_type, step.get("schema"), labels=step.get("labels"))
    instruction = str(step.get("instruction", ""))
    input_value = step.get("input", "")
    result = run_ai_task(
        service_name=str(service_name),
        service_config=service_config,
        task_type=ai_type,
        input_value=input_value,
        instruction=instruction,
        schema=schema,
        labels=step.get("labels"),
    )
    executor.state.variables[step["save_as"]] = result.parsed

    artifact_path = executor._resolve_output_path(step.get("path", f"{ai_type}/{step['save_as']}.json"), category="ai")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "type": ai_type,
        "service": str(service_name),
        "service_config": service_config_for_artifact(service_config),
        "instruction": instruction,
        "input": input_value,
        "schema": result.schema,
        "response_format": result.response_format,
        "attempts": result.attempts,
        "parsed": result.parsed,
        "raw_text": result.raw_text,
        "raw_response": result.raw_response,
    }
    with artifact_path.open("w", encoding="utf-8") as file:
        json.dump(artifact, file, ensure_ascii=False, indent=2)
    executor.state.logger.log(
        "info",
        "ai task completed",
        type=ai_type,
        service=str(service_name),
        save_as=step["save_as"],
        path=str(artifact_path),
    )


ACTION_HANDLERS = {
    "ai": action_ai,
}
