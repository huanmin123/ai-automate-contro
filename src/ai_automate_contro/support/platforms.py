from __future__ import annotations

import platform


PLATFORM_ALIASES: dict[str, str] = {
    "darwin": "macos",
    "mac": "macos",
    "macos": "macos",
    "osx": "macos",
    "win": "windows",
    "win32": "windows",
    "win64": "windows",
    "windows": "windows",
}

PLATFORM_OVERRIDE_ALIASES: dict[str, tuple[str, ...]] = {
    "macos": ("macos", "darwin", "mac", "osx"),
    "windows": ("windows", "win", "win32", "win64"),
}


def current_platform_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return normalize_platform_name(system)


def normalize_platform_name(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    return PLATFORM_ALIASES.get(raw, raw)


def platform_lookup_keys(value: str | None) -> tuple[str, ...]:
    normalized = normalize_platform_name(value)
    aliases = PLATFORM_OVERRIDE_ALIASES.get(normalized, (normalized,))
    ordered: list[str] = []
    for key in (normalized, *aliases):
        if key and key not in ordered:
            ordered.append(key)
    return tuple(ordered)


def primary_modifier_for_platform(value: str | None = None) -> str:
    platform_name = normalize_platform_name(value) if value else current_platform_name()
    return "command" if platform_name == "macos" else "ctrl"
