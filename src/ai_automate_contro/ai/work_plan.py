from __future__ import annotations

from typing import Any


WORK_PLAN_STATUSES = {"pending", "in_progress", "completed"}
WORK_PLAN_LIFECYCLES = {"active", "completed", "canceled"}
WORK_PLAN_OPERATIONS = {"start", "continue", "complete", "cancel"}
MAX_WORK_PLAN_ITEMS = 12
MAX_WORK_PLAN_TITLE_CHARS = 120
MAX_WORK_PLAN_NOTE_CHARS = 180


def normalize_work_plan_items(items: Any) -> list[dict[str, str]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("work plan items 必须是列表。")
    normalized: list[dict[str, str]] = []
    for raw_item in items[:MAX_WORK_PLAN_ITEMS]:
        if not isinstance(raw_item, dict):
            raise ValueError("work plan item 必须是对象。")
        title = _compact_text(raw_item.get("title") or raw_item.get("step"), limit=MAX_WORK_PLAN_TITLE_CHARS)
        if not title:
            raise ValueError("work plan item.title 不能为空。")
        status = str(raw_item.get("status") or "pending").strip()
        if status not in WORK_PLAN_STATUSES:
            raise ValueError("work plan item.status 只能是 pending、in_progress 或 completed。")
        note = _compact_text(raw_item.get("note"), limit=MAX_WORK_PLAN_NOTE_CHARS)
        item = {"title": title, "status": status}
        if note:
            item["note"] = note
        normalized.append(item)
    active_count = sum(1 for item in normalized if item["status"] == "in_progress")
    if active_count > 1:
        raise ValueError("work plan 最多只能有一个 in_progress 步骤。")
    return normalized


def normalize_work_plan_summary(summary: Any) -> str:
    return _compact_text(summary, limit=160)


def normalize_work_plan_operation(operation: Any) -> str:
    normalized = str(operation or "continue").strip()
    if normalized not in WORK_PLAN_OPERATIONS:
        raise ValueError("work plan operation 只能是 start、continue、complete 或 cancel。")
    return normalized


def work_plan_lifecycle_for_operation(operation: Any) -> str:
    normalized = normalize_work_plan_operation(operation)
    return {
        "start": "active",
        "continue": "active",
        "complete": "completed",
        "cancel": "canceled",
    }[normalized]


def normalize_work_plan_lifecycle(lifecycle: Any) -> str:
    normalized = str(lifecycle or "").strip()
    if normalized not in WORK_PLAN_LIFECYCLES:
        raise ValueError("work plan lifecycle 只能是 active、completed 或 canceled。")
    return normalized


def validate_work_plan_transition(
    current_lifecycle: Any,
    *,
    operation: Any,
    items: Any,
) -> str:
    """Reject opening another visible plan before the current one is closed."""
    normalized_operation = normalize_work_plan_operation(operation)
    normalized_items = normalize_work_plan_items(items)
    current = str(current_lifecycle or "").strip()
    has_active_plan = current == "active"
    if normalized_operation == "start" and has_active_plan:
        raise ValueError("当前工作计划仍在进行中；用户后续消息必须作为该计划的引导。请继续、完成或取消当前计划后再开始新计划。")
    if normalized_operation == "continue" and current in {"completed", "canceled"}:
        raise ValueError("当前工作计划已经结束；请用 start 创建新的工作计划，不能用 continue 重新打开旧计划。")
    if normalized_operation in {"complete", "cancel"} and not has_active_plan:
        raise ValueError("当前没有进行中的工作计划，不能结束或取消。")
    if normalized_operation == "complete" and any(item["status"] != "completed" for item in normalized_items):
        raise ValueError("完成工作计划前，所有待办项必须标记为 completed。")
    return normalized_operation


def format_work_plan_for_terminal(items: Any, *, summary: Any = "") -> str:
    normalized_items = normalize_work_plan_items(items)
    normalized_summary = normalize_work_plan_summary(summary)
    if not normalized_items:
        return "当前没有工作计划。复杂任务开始后，AI 会在这里维护一个可见计划。"
    completed = sum(1 for item in normalized_items if item["status"] == "completed")
    lines = [f"当前工作计划：{completed}/{len(normalized_items)} 完成"]
    if normalized_summary:
        lines.append(normalized_summary)
    for item in normalized_items:
        marker = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
        }[item["status"]]
        line = f"{marker} {item['title']}"
        if item.get("note"):
            line += f" - {item['note']}"
        lines.append(line)
    return "\n".join(lines)


def format_work_plan_for_context(items: Any, *, summary: Any = "") -> str:
    normalized_items = normalize_work_plan_items(items)
    if not normalized_items:
        return ""
    normalized_summary = normalize_work_plan_summary(summary)
    lines = ["当前可见工作计划（用户可见，不是隐藏推理）："]
    if normalized_summary:
        lines.append(f"- summary: {normalized_summary}")
    for item in normalized_items:
        line = f"- [{item['status']}] {item['title']}"
        if item.get("note"):
            line += f" - {item['note']}"
        lines.append(line)
    return "\n".join(lines)


def _compact_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
