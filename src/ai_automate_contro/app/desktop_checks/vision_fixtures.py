from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _write_vision_fixture_images(source_path: Path, template_path: Path) -> dict[str, int]:
    from PIL import Image, ImageDraw

    source_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template = Image.new("RGB", (64, 42), (21, 92, 184))
    draw = ImageDraw.Draw(template)
    draw.rectangle((0, 0, 63, 41), outline=(255, 255, 255), width=3)
    draw.line((6, 35, 58, 6), fill=(255, 210, 64), width=4)
    draw.rectangle((14, 12, 30, 28), fill=(41, 196, 128))
    draw.ellipse((39, 13, 55, 29), fill=(230, 72, 92))
    source = Image.new("RGB", (320, 220), (238, 241, 245))
    background = ImageDraw.Draw(source)
    for x in range(0, 320, 20):
        background.line((x, 0, x, 220), fill=(226, 230, 236))
    for y in range(0, 220, 20):
        background.line((0, y, 320, y), fill=(226, 230, 236))
    bounds = {"x": 123, "y": 77, "width": template.width, "height": template.height}
    source.paste(template, (bounds["x"], bounds["y"]))
    template.save(template_path)
    source.save(source_path)
    return bounds


def _write_ocr_fixture_image(source_path: Path, *, text: str, language: str = "latin") -> None:
    from PIL import Image, ImageDraw, ImageFont

    source_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 180), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _ocr_fixture_font(ImageFont, language=language)
    draw.rectangle((18, 18, 622, 162), outline=(35, 35, 35), width=2)
    draw.text((54, 58), text, fill=(0, 0, 0), font=font)
    image.save(source_path)


def _ocr_fixture_font(image_font_module: Any, *, language: str = "latin") -> Any:
    for candidate in _ocr_fixture_font_candidates(language):
        if candidate.exists():
            try:
                return image_font_module.truetype(str(candidate), 44)
            except Exception:
                continue
    return image_font_module.load_default()


def _ocr_fixture_font_available(language: str = "latin") -> bool:
    try:
        from PIL import ImageFont
    except Exception:
        return False
    for candidate in _ocr_fixture_font_candidates(language):
        if not candidate.exists():
            continue
        try:
            ImageFont.truetype(str(candidate), 44)
            return True
        except Exception:
            continue
    return language != "zh"


def _ocr_fixture_font_candidates(language: str = "latin") -> list[Path]:
    if language == "zh":
        return [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msyh.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("C:/Windows/Fonts/simsun.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
            Path("/Library/Fonts/NotoSansCJK-Regular.ttc"),
        ]
    return [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]


def _ocr_raw_text_contains(normalized_raw_text: str, expected: str) -> bool:
    normalized_expected = re.sub(r"\s+", "", expected)
    if normalized_expected.upper().isascii():
        return normalized_expected.upper() in normalized_raw_text.upper()
    return normalized_expected in normalized_raw_text


def _write_vision_missing_template(template_path: Path) -> None:
    from PIL import Image, ImageDraw

    template_path.parent.mkdir(parents=True, exist_ok=True)
    template = Image.new("RGB", (58, 38), (35, 31, 32))
    draw = ImageDraw.Draw(template)
    draw.rectangle((0, 0, 57, 37), outline=(248, 248, 242), width=3)
    draw.line((5, 5, 52, 33), fill=(165, 42, 214), width=5)
    draw.line((7, 31, 50, 4), fill=(255, 88, 34), width=3)
    draw.rectangle((20, 9, 38, 27), fill=(0, 210, 230))
    template.save(template_path)


def _image_size(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        from PIL import Image

        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return {}


def _image_size_matches_bounds(size: dict[str, int], bounds: dict[str, Any], *, tolerance: int = 4) -> bool:
    if not size or not bounds:
        return False
    try:
        width = int(size.get("width", 0) or 0)
        height = int(size.get("height", 0) or 0)
        expected_width = int(float(bounds.get("width", 0) or 0))
        expected_height = int(float(bounds.get("height", 0) or 0))
    except (TypeError, ValueError):
        return False
    return (
        width > 0
        and height > 0
        and expected_width > 0
        and expected_height > 0
        and abs(width - expected_width) <= tolerance
        and abs(height - expected_height) <= tolerance
    )
