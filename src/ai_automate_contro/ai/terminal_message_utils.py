from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.types import Interrupt


def format_patch_approval_request(tool_call: dict[str, Any], *_: Any) -> str:
    args = tool_call.get("args", {})
    workspace = args.get("workspace", "<unknown>")
    return (
        "即将把调试工作区里的 patch 应用回原始 plan 包。\n"
        "请先确认 patch.diff 已检查过，且这次修改只包含你要应用的最小修复。\n"
        f"workspace: {workspace}"
    )


def extract_interrupts(value: Any) -> tuple[Interrupt, ...]:
    if isinstance(value, dict):
        raw_interrupts = value.get("__interrupt__") or ()
        if isinstance(raw_interrupts, tuple):
            return raw_interrupts
        if isinstance(raw_interrupts, list):
            return tuple(raw_interrupts)
    interrupts = getattr(value, "interrupts", None)
    if isinstance(interrupts, tuple):
        return interrupts
    if isinstance(interrupts, list):
        return tuple(interrupts)
    return ()


def interrupt_action_requests(interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", None)
        if not isinstance(value, dict):
            continue
        action_requests = value.get("action_requests")
        if not isinstance(action_requests, list):
            continue
        for request in action_requests:
            if isinstance(request, dict):
                requests.append(request)
    return requests


def approval_decision_for_request(request: dict[str, Any]) -> dict[str, Any]:
    action_name = str(request.get("name", ""))
    args = request.get("args", {})
    if not isinstance(args, dict):
        args = {}
    edited_args = dict(args)
    if action_name == "apply_debug_patch_after_approval":
        edited_args["approved"] = True
        return {
            "type": "edit",
            "edited_action": {
                "name": action_name,
                "args": edited_args,
            },
        }
    return {"type": "approve"}


def latest_human_message_approved(messages: list[BaseMessage]) -> bool:
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        normalized = message_content_to_text(message.content).lower()
        return text_has_approval(normalized)
    return False


def text_has_approval(text: str) -> bool:
    approval_tokens = ("同意", "确认", "批准", "可以应用", "应用补丁", "yes", "approve", "approved", "--yes")
    normalized = text.lower()
    return any(token in normalized for token in approval_tokens)


def text_has_rejection(text: str) -> bool:
    rejection_tokens = ("拒绝", "不同意", "不要应用", "不应用", "取消", "reject", "deny", "no")
    normalized = text.lower()
    return any(token in normalized for token in rejection_tokens)


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                if item.get("text"):
                    chunks.append(str(item["text"]))
                elif item.get("content"):
                    chunks.append(str(item["content"]))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content)
