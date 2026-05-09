from __future__ import annotations

from typing import Iterable


def parse_tag_text(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def matches_tags(
    tags: Iterable[str],
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    tag_mode: str = "any",
) -> bool:
    current_tags = set(tags)
    required = set(include_tags or [])
    blocked = set(exclude_tags or [])

    if blocked and current_tags.intersection(blocked):
        return False

    if not required:
        return True

    if tag_mode == "all":
        return required.issubset(current_tags)
    if tag_mode == "any":
        return bool(required.intersection(current_tags))

    raise ValueError(f"Unsupported tag mode: {tag_mode}")
