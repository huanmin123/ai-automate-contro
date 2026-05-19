from __future__ import annotations

from typing import Any


CONTROLLED_AI_SYSTEM_PROMPT = (
    "你是受控数据处理组件。只处理输入，不控制浏览器/命令/文件，不追问用户；只返回匹配 JSON Schema 的 JSON。"
)

CONTROLLED_AI_TASK_PROMPTS: dict[str, str] = {
    "connectivity": "确认模型端点可用，返回 ok=true 和简短消息。",
    "extract_data": "从输入中抽取指定的结构化字段。",
    "classify_text": "把输入分类为且仅分类为一个允许的标签。",
    "transform_data": "按 instruction 转换输入内容。",
    "summarize_text": "按 instruction 摘要输入内容。",
}


def build_controlled_ai_payload(
    *,
    task_type: str,
    input_value: Any,
    instruction: str,
    schema: dict[str, Any],
    labels: list[Any],
) -> dict[str, Any]:
    return {
        "task_type": task_type,
        "task": CONTROLLED_AI_TASK_PROMPTS[task_type],
        "instruction": instruction,
        "labels": labels,
        "json_schema": schema,
        "input": input_value,
    }
