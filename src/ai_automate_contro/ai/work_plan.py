from __future__ import annotations

from typing import Any


WORK_PLAN_STATUSES = {"pending", "in_progress", "completed"}
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
