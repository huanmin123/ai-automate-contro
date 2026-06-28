from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def capture_pointer_annotation(
    backend: Any,
    *,
    output_dir: Path,
    step_number: int,
    desktop: str,
    action: str,
    points: list[dict[str, Any]],
    bounds: list[dict[str, Any]] | None = None,
    connect_points: bool = False,
    label: str = "",
    target: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    annotation_dir = output_dir / "desktop-annotations"
    annotation_dir.mkdir(parents=True, exist_ok=True)
    file_stem = f"step-{int(step_number):03d}-{_slug(desktop)}-{_slug(action)}"
    png_filename = f"{file_stem}.png"
    json_filename = f"{file_stem}.json"
    png_path = annotation_dir / png_filename
    json_path = annotation_dir / json_filename
    normalized_bounds = bounds or []
    normalized_warnings = warnings or []
    screenshot = backend.screenshot(png_path)
    _draw_annotation(png_path, points=points, bounds=normalized_bounds, connect_points=connect_points, label=label)
    coordinate_space = {
        "origin": "screen",
        "unit": "logical_px",
        "scale": None,
    }
    source_bounds = {
        "x": 0,
        "y": 0,
        "width": int(screenshot.get("width", 0) or 0) if isinstance(screenshot, dict) else 0,
        "height": int(screenshot.get("height", 0) or 0) if isinstance(screenshot, dict) else 0,
    }
    payload = {
        "schema_version": 1,
        "ok": True,
        "step": int(step_number),
        "action": action,
        "desktop": desktop,
        "type": "pointer",
        "annotated_screenshot_path": str(png_path),
        "annotated_screenshot_relative_path": str(Path("desktop-annotations") / png_filename),
        "json_path": str(json_path),
        "json_relative_path": str(Path("desktop-annotations") / json_filename),
        "coordinate_space": coordinate_space,
        "coordinate_diagnostics": {
            "source_bounds": source_bounds,
            "source_size": {"width": source_bounds["width"], "height": source_bounds["height"]},
            "coordinate_space": coordinate_space,
            "global_origin": {"x": 0, "y": 0},
            "local_to_global_offset": {"x": 0, "y": 0},
            "scale": None,
            "region": {},
            "warnings": ["scale_unknown"],
        },
        "target": target or {},
        "points": points,
        "bounds": normalized_bounds,
        "connect_points": bool(connect_points),
        "label": label,
        "overlays": _overlay_payload(points=points, bounds=normalized_bounds, connect_points=connect_points),
        "warnings": normalized_warnings,
        "screenshot": screenshot,
    }
    _write_json(json_path, payload)
    return {
        **payload,
        "path": str(png_path),
        "relative_path": str(Path("desktop-annotations") / png_filename),
    }


def _draw_annotation(
    path: Path,
    *,
    points: list[dict[str, Any]],
    bounds: list[dict[str, Any]],
    connect_points: bool,
    label: str,
) -> None:
    from PIL import Image, ImageDraw

    with Image.open(path) as image:
        draw = ImageDraw.Draw(image)
        color = (255, 64, 64)
        secondary = (64, 128, 255)
        for bound in bounds:
            try:
                x = int(float(bound.get("x", 0)))
                y = int(float(bound.get("y", 0)))
                width = int(float(bound.get("width", 0)))
                height = int(float(bound.get("height", 0)))
            except (TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                draw.rectangle((x, y, x + width, y + height), outline=secondary, width=3)
        normalized_points = []
        for point in points:
            try:
                x = int(float(point.get("x", 0)))
                y = int(float(point.get("y", 0)))
            except (TypeError, ValueError):
                continue
            normalized_points.append((x, y, str(point.get("label") or "")))
        if connect_points and len(normalized_points) >= 2:
            draw.line([(x, y) for x, y, _ in normalized_points], fill=color, width=3)
        for x, y, point_label in normalized_points:
            radius = 12
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=4)
            draw.line((x - 18, y, x + 18, y), fill=color, width=3)
            draw.line((x, y - 18, x, y + 18), fill=color, width=3)
            text = point_label or label
            if text:
                draw.text((x + 16, y + 12), text, fill=color)
        if label:
            draw.text((12, 12), label, fill=color)
        image.save(path)


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return text.strip("-") or "desktop"


def _overlay_payload(
    *,
    points: list[dict[str, Any]],
    bounds: list[dict[str, Any]],
    connect_points: bool,
) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for bound in bounds:
        overlays.append({"type": "rect", **dict(bound)})
    for point in points:
        overlays.append({"type": "point", **dict(point)})
    if connect_points and len(points) >= 2:
        overlays.append({"type": "line", "points": points})
    return overlays


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
