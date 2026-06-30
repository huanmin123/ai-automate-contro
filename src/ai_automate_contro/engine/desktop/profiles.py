from __future__ import annotations

from copy import deepcopy
from typing import Any


WINDOW_QUERY_FIELDS = {
    "title",
    "title_contains",
    "title_regex",
    "app",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "match_index",
}


BUILTIN_DESKTOP_APP_PROFILES: dict[str, dict[str, Any]] = {
    "notepad": {
        "aliases": ["windows_notepad"],
        "platforms": {
            "windows": {
                "launch": {"app": "notepad.exe"},
                "window_query": {"process_name": "notepad.exe"},
                "defaults": {"wait_for_window": True, "focus": True, "window_timeout_ms": 10_000},
            }
        },
    },
    "explorer": {
        "aliases": ["windows_explorer", "file_explorer"],
        "platforms": {
            "windows": {
                "launch": {"app": "explorer.exe"},
                "window_query": {"process_name": "explorer.exe"},
                "defaults": {"wait_for_window": True, "focus": True, "window_timeout_ms": 10_000},
            }
        },
    },
    "powershell": {
        "aliases": ["pwsh", "windows_terminal_shell"],
        "platforms": {
            "windows": {
                "launch": {"app": "pwsh.exe"},
                "window_query": {"process_name": "pwsh.exe"},
                "defaults": {"wait_for_window": True, "focus": True, "window_timeout_ms": 10_000},
            }
        },
    },
    "file_dialog_open": {
        "aliases": ["open_file_dialog", "windows_open_dialog"],
        "platforms": {
            "windows": {
                "window_query": {"title_contains": "Open", "class_name": "#32770"},
                "defaults": {"timeout_ms": 10_000, "interval_ms": 250},
            }
        },
    },
    "file_dialog_save": {
        "aliases": ["save_file_dialog", "windows_save_dialog"],
        "platforms": {
            "windows": {
                "window_query": {"title_contains": "Save", "class_name": "#32770"},
                "defaults": {"timeout_ms": 10_000, "interval_ms": 250},
            }
        },
    },
    "textedit": {
        "aliases": ["macos_textedit"],
        "platforms": {
            "macos": {
                "launch": {"app": "TextEdit"},
                "window_query": {"app": "TextEdit"},
                "defaults": {"wait_for_window": True, "focus": True, "window_timeout_ms": 10_000},
            }
        },
    },
}


def builtin_profile_ids() -> list[str]:
    ids: list[str] = []
    for profile_id, raw_profile in BUILTIN_DESKTOP_APP_PROFILES.items():
        ids.append(profile_id)
        ids.extend(str(alias) for alias in raw_profile.get("aliases", []) if alias)
    return sorted(set(ids))


def apply_desktop_app_profile(
    step: dict[str, Any],
    *,
    platform_name: str,
    desktop_config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_id = _profile_id(step)
    if not profile_id:
        return dict(step), {}
    profile = resolve_desktop_app_profile(profile_id, platform_name=platform_name, desktop_config=desktop_config)
    merged = dict(step)
    explicit_launch_target = any(step.get(field) not in (None, "") for field in ("app", "path", "command"))
    for section in ("launch", "window_query", "defaults"):
        values = profile.get(section) if isinstance(profile.get(section), dict) else {}
        for key, value in values.items():
            if section == "launch" and key in {"app", "path", "command"} and explicit_launch_target:
                continue
            if key not in merged or merged[key] in (None, ""):
                merged[key] = deepcopy(value)
    return merged, {
        "id": profile["id"],
        "requested": profile_id,
        "platform": profile["platform"],
        "source": profile["source"],
        "applied": {
            "launch": profile.get("launch", {}),
            "window_query": profile.get("window_query", {}),
            "defaults": profile.get("defaults", {}),
        },
    }


def resolve_desktop_app_profile(
    profile_id: str,
    *,
    platform_name: str,
    desktop_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_profile_id(profile_id)
    config_profiles = _config_profiles(desktop_config)
    if normalized_id in config_profiles:
        profile = _profile_for_platform(config_profiles[normalized_id], platform_name=platform_name)
        return _normalized_profile_payload(normalized_id, profile, platform_name=platform_name, source="config")
    builtin_id = _builtin_profile_id(normalized_id)
    if builtin_id:
        profile = _profile_for_platform(BUILTIN_DESKTOP_APP_PROFILES[builtin_id], platform_name=platform_name)
        return _normalized_profile_payload(builtin_id, profile, platform_name=platform_name, source="builtin")
    available = ", ".join(builtin_profile_ids())
    raise ValueError(f"未知 desktop app profile：{profile_id}；内置 profile：{available}")


def _profile_id(step: dict[str, Any]) -> str:
    value = step.get("profile", step.get("app_profile", ""))
    return str(value).strip() if value not in (None, "") else ""


def _config_profiles(desktop_config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    config = desktop_config if isinstance(desktop_config, dict) else {}
    raw_profiles = config.get("desktop_profiles")
    if not isinstance(raw_profiles, dict):
        raw_profiles = config.get("desktop_app_profiles")
    if not isinstance(raw_profiles, dict):
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    for key, value in raw_profiles.items():
        if isinstance(key, str) and key.strip() and isinstance(value, dict):
            profiles[_normalize_profile_id(key)] = dict(value)
    return profiles


def _builtin_profile_id(profile_id: str) -> str:
    for builtin_id, raw_profile in BUILTIN_DESKTOP_APP_PROFILES.items():
        if profile_id == _normalize_profile_id(builtin_id):
            return builtin_id
        aliases = raw_profile.get("aliases") if isinstance(raw_profile.get("aliases"), list) else []
        if profile_id in {_normalize_profile_id(str(alias)) for alias in aliases}:
            return builtin_id
    return ""


def _profile_for_platform(raw_profile: dict[str, Any], *, platform_name: str) -> dict[str, Any]:
    platform_profile: dict[str, Any] = {}
    shared = {key: value for key, value in raw_profile.items() if key not in {"aliases", "platforms", "windows", "macos"}}
    platform_profile.update(shared)
    platforms = raw_profile.get("platforms") if isinstance(raw_profile.get("platforms"), dict) else {}
    direct_platform = raw_profile.get(platform_name) if isinstance(raw_profile.get(platform_name), dict) else {}
    selected = platforms.get(platform_name) if isinstance(platforms.get(platform_name), dict) else direct_platform
    platform_profile.update(selected)
    return platform_profile


def _normalized_profile_payload(
    profile_id: str,
    raw_profile: dict[str, Any],
    *,
    platform_name: str,
    source: str,
) -> dict[str, Any]:
    launch = _section_dict(raw_profile, "launch")
    window_query = {
        key: value
        for key, value in _section_dict(raw_profile, "window_query").items()
        if key in WINDOW_QUERY_FIELDS and value not in (None, "")
    }
    defaults = _section_dict(raw_profile, "defaults")
    if not launch and not window_query and not defaults:
        raise ValueError(f"desktop app profile 不支持当前平台或为空：profile={profile_id} platform={platform_name}")
    return {
        "id": profile_id,
        "platform": platform_name,
        "source": source,
        "launch": launch,
        "window_query": window_query,
        "defaults": defaults,
    }


def _section_dict(raw_profile: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw_profile.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _normalize_profile_id(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")
