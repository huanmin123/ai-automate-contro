from __future__ import annotations

from typing import Any


COORDINATE_PROFILE_SCHEMA_VERSION = 1


def normalize_bounds(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    bounds = {
        "x": _int(value.get("x"), 0),
        "y": _int(value.get("y"), 0),
        "width": _int(value.get("width"), 0),
        "height": _int(value.get("height"), 0),
    }
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        return {}
    return bounds


def point_center_from_bounds(value: Any) -> dict[str, int]:
    bounds = normalize_bounds(value)
    if not bounds:
        return {}
    return {
        "x": bounds["x"] + bounds["width"] // 2,
        "y": bounds["y"] + bounds["height"] // 2,
    }


def local_to_screen_bounds(bounds: Any, *, source_bounds: Any) -> dict[str, int]:
    local = normalize_bounds(bounds)
    source = _source_bounds(source_bounds)
    if not local:
        return {}
    return {
        "x": source["x"] + local["x"],
        "y": source["y"] + local["y"],
        "width": local["width"],
        "height": local["height"],
    }


def screen_to_local_bounds(bounds: Any, *, source_bounds: Any) -> dict[str, int]:
    screen = normalize_bounds(bounds)
    source = _source_bounds(source_bounds)
    if not screen:
        return {}
    return {
        "x": screen["x"] - source["x"],
        "y": screen["y"] - source["y"],
        "width": screen["width"],
        "height": screen["height"],
    }


def local_to_screen_point(point: Any, *, source_bounds: Any) -> dict[str, int]:
    local = _point(point)
    source = _source_bounds(source_bounds)
    if not local:
        return {}
    return {"x": source["x"] + local["x"], "y": source["y"] + local["y"]}


def screen_to_local_point(point: Any, *, source_bounds: Any) -> dict[str, int]:
    screen = _point(point)
    source = _source_bounds(source_bounds)
    if not screen:
        return {}
    return {"x": screen["x"] - source["x"], "y": screen["y"] - source["y"]}


def build_coordinate_profile(
    *,
    platform: str = "",
    backend: str = "",
    display: dict[str, Any] | None = None,
    source_kind: str = "screen",
    source_bounds: dict[str, Any] | None = None,
    source_size: dict[str, Any] | None = None,
    coordinate_space: dict[str, Any] | None = None,
    region: dict[str, Any] | None = None,
    screen_clickable: bool | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    source = _source_bounds(source_bounds)
    size = _source_size(source_size, fallback=source)
    display_payload = normalize_display(display or {})
    normalized_space = _coordinate_space(coordinate_space)
    if normalized_space.get("scale") is None and display_payload.get("scale") is not None:
        normalized_space["scale"] = display_payload.get("scale")
    source_kind_text = str(source_kind or "screen")
    inferred_screen_clickable = source_kind_text not in {"source_path", "image", "offline_image"}
    scale = normalized_space.get("scale")
    normalized_warnings = list(warnings or [])
    if scale is None:
        normalized_warnings.append("scale_unknown")
    if source["x"] < 0 or source["y"] < 0:
        normalized_warnings.append("negative_source_origin")
    if not (inferred_screen_clickable if screen_clickable is None else bool(screen_clickable)):
        normalized_warnings.append("not_screen_clickable")
    normalized_warnings = _dedupe_strings(normalized_warnings)
    return {
        "schema_version": COORDINATE_PROFILE_SCHEMA_VERSION,
        "kind": "desktop_coordinate_profile",
        "platform": platform,
        "backend": backend,
        "space": normalized_space,
        "display": display_payload,
        "source": {
            "kind": source_kind_text,
            "bounds": source,
            "size": size,
            "region": normalize_bounds(region or {}) if isinstance(region, dict) else {},
            "screen_clickable": inferred_screen_clickable if screen_clickable is None else bool(screen_clickable),
        },
        "transforms": {
            "local_to_screen": {
                "offset": {"x": source["x"], "y": source["y"]},
                "scale": scale,
            },
            "screen_to_local": {
                "offset": {"x": -source["x"], "y": -source["y"]},
                "scale": scale,
            },
        },
        "warnings": normalized_warnings,
    }


def build_coordinate_diagnostics(
    *,
    coordinate_profile: dict[str, Any],
    source_bounds: dict[str, Any] | None = None,
    source_size: dict[str, Any] | None = None,
    coordinate_space: dict[str, Any] | None = None,
    region: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = coordinate_profile if isinstance(coordinate_profile, dict) else {}
    source = _source_bounds(
        source_bounds
        or (
            profile.get("source", {}).get("bounds")
            if isinstance(profile.get("source"), dict)
            else {}
        )
    )
    size = _source_size(
        source_size
        or (
            profile.get("source", {}).get("size")
            if isinstance(profile.get("source"), dict)
            else {}
        ),
        fallback=source,
    )
    space = _coordinate_space(coordinate_space or (profile.get("space") if isinstance(profile.get("space"), dict) else {}))
    return {
        "source_bounds": source,
        "source_size": size,
        "coordinate_space": space,
        "coordinate_profile": profile,
        "global_origin": {"x": source["x"], "y": source["y"]},
        "local_to_global_offset": {"x": source["x"], "y": source["y"]},
        "scale": space.get("scale"),
        "region": dict(region or {}) if isinstance(region, dict) else {},
        "warnings": list(profile.get("warnings", [])) if isinstance(profile.get("warnings"), list) else [],
    }


def normalize_display(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    existing_bounds = value.get("bounds") if isinstance(value.get("bounds"), dict) else {}
    existing_virtual = value.get("virtual_bounds") if isinstance(value.get("virtual_bounds"), dict) else {}
    width = _int(value.get("width"), _int(existing_bounds.get("width"), 0))
    height = _int(value.get("height"), _int(existing_bounds.get("height"), 0))
    virtual_x = _int(value.get("virtual_x"), _int(existing_virtual.get("x"), 0))
    virtual_y = _int(value.get("virtual_y"), _int(existing_virtual.get("y"), 0))
    virtual_width = _int(value.get("virtual_width"), _int(existing_virtual.get("width"), width))
    virtual_height = _int(value.get("virtual_height"), _int(existing_virtual.get("height"), height))
    dpi = value.get("dpi") if isinstance(value.get("dpi"), dict) else {}
    scale = value.get("scale")
    monitors = value.get("monitors") if isinstance(value.get("monitors"), list) else []
    default_monitor_count = len(monitors) or (1 if width or height else 0)
    return {
        "bounds": {"x": 0, "y": 0, "width": width, "height": height},
        "virtual_bounds": {
            "x": virtual_x,
            "y": virtual_y,
            "width": virtual_width,
            "height": virtual_height,
        },
        "monitor_count": _int(value.get("monitor_count"), default_monitor_count),
        "scale": _float_or_none(scale),
        "dpi": {
            "x": _int(dpi.get("x"), 0) if isinstance(dpi, dict) else 0,
            "y": _int(dpi.get("y"), 0) if isinstance(dpi, dict) else 0,
        },
        "monitors": [_compact_monitor(item) for item in monitors if isinstance(item, dict)],
        "raw": _compact_raw_display(value),
    }


def _compact_monitor(value: dict[str, Any]) -> dict[str, Any]:
    bounds = normalize_bounds(value.get("bounds")) or {
        "x": _int(value.get("x"), 0),
        "y": _int(value.get("y"), 0),
        "width": _int(value.get("width"), 0),
        "height": _int(value.get("height"), 0),
    }
    return {
        "id": value.get("id", ""),
        "primary": bool(value.get("primary", False)),
        "bounds": bounds,
        "scale": _float_or_none(value.get("scale")),
        "dpi": value.get("dpi") if isinstance(value.get("dpi"), dict) else {},
    }


def _compact_raw_display(value: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "width",
        "height",
        "virtual_x",
        "virtual_y",
        "virtual_width",
        "virtual_height",
        "monitor_count",
        "scale",
        "error",
    )
    return {field: value[field] for field in fields if field in value}


def _coordinate_space(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "origin": str(payload.get("origin") or "screen"),
        "unit": str(payload.get("unit") or "logical_px"),
        "scale": _float_or_none(payload.get("scale")),
    }


def _source_bounds(value: Any) -> dict[str, int]:
    bounds = normalize_bounds(value)
    if bounds:
        return bounds
    payload = value if isinstance(value, dict) else {}
    return {
        "x": _int(payload.get("x"), 0),
        "y": _int(payload.get("y"), 0),
        "width": max(0, _int(payload.get("width"), 0)),
        "height": max(0, _int(payload.get("height"), 0)),
    }


def _source_size(value: Any, *, fallback: dict[str, int]) -> dict[str, int]:
    payload = value if isinstance(value, dict) else {}
    return {
        "width": max(0, _int(payload.get("width"), fallback.get("width", 0))),
        "height": max(0, _int(payload.get("height"), fallback.get("height", 0))),
    }


def _point(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    if "x" not in value or "y" not in value:
        return {}
    return {"x": _int(value.get("x"), 0), "y": _int(value.get("y"), 0)}


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
