from __future__ import annotations

import csv
import io
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_automate_contro.engine.desktop.backends import DesktopBackendError
from ai_automate_contro.engine.desktop.backends.capabilities import (
    resolve_tesseract_binary,
    tesseract_binary_details,
    tesseract_common_options,
)
from ai_automate_contro.engine.desktop.coordinates import (
    CoordinateMapper,
    build_coordinate_diagnostics,
    build_coordinate_profile,
)
from ai_automate_contro.engine.desktop.output_paths import output_relative_path
from ai_automate_contro.engine.desktop.targeting import build_vision_targeting, confidence_meets


def _desktop_vision_artifact_paths(output_path: Path) -> dict[str, Path]:
    stem = output_path.stem or "vision"
    return {
        "source": output_path.with_name(f"{stem}-source.png"),
        "crop": output_path.with_name(f"{stem}-crop.png"),
        "annotation": output_path.with_name(f"{stem}-annotated.png"),
    }


def _desktop_vision_text_query(step: dict[str, Any]) -> dict[str, str]:
    query = {
        field: str(step[field])
        for field in ("text", "text_contains", "text_regex")
        if field in step and step[field] not in (None, "")
    }
    if not query:
        raise ValueError("desktop_vision.locate_text 需要 text、text_contains 或 text_regex 之一。")
    return query


def _source_coordinate_profile(
    session: DesktopSession,
    *,
    source_kind: str,
    source_bounds: dict[str, Any],
    source_size: dict[str, Any],
    coordinate_space: dict[str, Any],
    region: dict[str, Any] | None = None,
    screen_clickable: bool | None = None,
) -> dict[str, Any]:
    base = session.coordinate_profile if isinstance(session.coordinate_profile, dict) else {}
    display = base.get("display") if isinstance(base.get("display"), dict) else {}
    return build_coordinate_profile(
        platform=session.platform,
        backend=session.backend_name,
        display=display,
        source_kind=source_kind,
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region,
        screen_clickable=screen_clickable,
    )


def _coordinate_diagnostics(
    *,
    source_bounds: dict[str, Any],
    coordinate_space: dict[str, Any],
    source_size: dict[str, Any] | None = None,
    region: dict[str, Any] | None = None,
    coordinate_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = (
        coordinate_profile
        if isinstance(coordinate_profile, dict)
        else build_coordinate_profile(
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region,
        )
    )
    return build_coordinate_diagnostics(
        coordinate_profile=profile,
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region,
    )


def _locate_image_in_source(
    *,
    template_path: Path,
    source_path: Path,
    output_path: Path,
    artifacts: dict[str, Path],
    region: dict[str, Any] | None,
    threshold: float,
    match_index: int,
    max_matches: int,
    coordinate_origin: str,
    started: float,
    source_payload: dict[str, Any],
    source_bounds: dict[str, int],
    desktop: str,
) -> dict[str, Any]:
    if not template_path.exists():
        raise FileNotFoundError(f"desktop_vision.template_path 文件不存在：{template_path}")
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception as error:
        raise DesktopBackendError("desktop_vision.locate_image 需要 opencv-python、numpy 和 Pillow。") from error

    with Image.open(source_path) as raw_source, Image.open(template_path) as raw_template:
        source_image = raw_source.convert("RGB")
        template_image = raw_template.convert("RGB")
        search_image, region_payload = _desktop_vision_search_image(source_image, region)
        source_array = cv2.cvtColor(np.array(search_image), cv2.COLOR_RGB2BGR)
        template_array = cv2.cvtColor(np.array(template_image), cv2.COLOR_RGB2BGR)
        if template_array.shape[0] > source_array.shape[0] or template_array.shape[1] > source_array.shape[1]:
            matches: list[dict[str, Any]] = []
            diagnostics = {
                "method": "opencv.matchTemplate",
                "cv2_version": str(getattr(cv2, "__version__", "")),
                "reason": "template_larger_than_source",
                "source_size": {"width": source_image.width, "height": source_image.height},
                "template_size": {"width": template_image.width, "height": template_image.height},
            }
        else:
            result = cv2.matchTemplate(source_array, template_array, cv2.TM_CCOEFF_NORMED)
            raw_matches = _desktop_vision_template_matches(
                result,
                threshold=threshold,
                max_matches=max(1, max_matches),
                template_width=template_image.width,
                template_height=template_image.height,
                region=region_payload,
            )
            local_matches = raw_matches
            matches = _desktop_vision_global_matches(local_matches, source_bounds)
            diagnostics = {
                "method": "opencv.matchTemplate",
                "cv2_version": str(getattr(cv2, "__version__", "")),
                "max_score": float(result.max()) if result.size else 0.0,
                "candidate_count": len(matches),
                "source_size": {"width": source_image.width, "height": source_image.height},
                "template_size": {"width": template_image.width, "height": template_image.height},
            }

        local_matches = local_matches if "local_matches" in locals() else []
        local_selected = local_matches[match_index] if 0 <= match_index < len(local_matches) else None
        selected = matches[match_index] if "matches" in locals() and 0 <= match_index < len(matches) else None
        if local_selected is not None:
            _save_desktop_vision_crop(source_image, local_selected["bounds"], artifacts["crop"])
            _save_desktop_vision_annotation(source_image, local_matches, local_selected, artifacts["annotation"])

    source_profile = source_payload.get("coordinate_profile") if isinstance(source_payload.get("coordinate_profile"), dict) else {}
    coordinate_space = (
        source_profile.get("space")
        if isinstance(source_profile.get("space"), dict)
        else {"origin": coordinate_origin, "unit": "logical_px", "scale": None}
    )
    source_size = {"width": 0, "height": 0}
    if "diagnostics" in locals() and isinstance(diagnostics.get("source_size"), dict):
        source_size = dict(diagnostics["source_size"])
    if not source_profile:
        source_profile = build_coordinate_profile(
            source_kind=coordinate_origin,
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region_payload if "region_payload" in locals() else region if isinstance(region, dict) else None,
            screen_clickable=coordinate_origin not in {"source_path", "image", "offline_image"},
        )
    coordinate_diagnostics = _coordinate_diagnostics(
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region_payload if "region_payload" in locals() else region if isinstance(region, dict) else None,
        coordinate_profile=source_profile,
    )
    target_candidates = build_vision_targeting(
        desktop=desktop,
        vision_type="locate_image",
        template_path=str(template_path),
        source_target=str(source_payload.get("source_target", "")),
        source_bounds=source_bounds,
        coordinate_profile=source_profile,
        coordinate_diagnostics=coordinate_diagnostics,
        target_query=source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        locator=source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        matches=matches if "matches" in locals() else [],
        selected_match=selected or {},
    )
    payload = {
        "ok": selected is not None,
        "action": "desktop_vision",
        "type": "locate_image",
        "desktop": desktop,
        "source_target": str(source_payload.get("source_target", "")),
        "template_path": str(template_path),
        "source_path": str(source_path),
        "threshold": threshold,
        "match_index": match_index,
        "max_matches": max_matches,
        "coordinate_space": coordinate_space,
        "coordinate_profile": source_profile,
        "coordinate_diagnostics": coordinate_diagnostics,
        "source_bounds": source_bounds,
        "region": region_payload if "region_payload" in locals() else region or {},
        "target_query": source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        "locator": source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        "window": source_payload.get("window") if isinstance(source_payload.get("window"), dict) else {},
        "element": source_payload.get("element") if isinstance(source_payload.get("element"), dict) else {},
        "matches": matches if "matches" in locals() else [],
        "match": selected or {},
        "target_candidates": target_candidates,
        "artifacts": {
            "json_path": str(output_path),
            "json_relative_path": output_relative_path(output_path),
            "source_path": str(artifacts["source"]),
            "source_relative_path": output_relative_path(artifacts["source"]),
            "crop_path": str(artifacts["crop"]) if selected is not None else "",
            "crop_relative_path": output_relative_path(artifacts["crop"]) if selected is not None else "",
            "annotation_path": str(artifacts["annotation"]) if selected is not None else "",
            "annotation_relative_path": output_relative_path(artifacts["annotation"]) if selected is not None else "",
        },
        "diagnostics": diagnostics if "diagnostics" in locals() else {},
        "source": source_payload,
        "elapsed_ms": _elapsed_ms(started),
    }
    return payload


def _locate_text_in_source(
    *,
    source_path: Path,
    output_path: Path,
    artifacts: dict[str, Path],
    region: dict[str, Any] | None,
    match_query: dict[str, str],
    language: str,
    provider: str,
    min_confidence: float,
    case_sensitive: bool,
    match_index: int,
    max_matches: int,
    coordinate_origin: str,
    started: float,
    source_payload: dict[str, Any],
    source_bounds: dict[str, int],
    desktop: str,
    desktop_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except Exception as error:
        raise DesktopBackendError("desktop_vision.locate_text 需要 Pillow。") from error

    with Image.open(source_path) as raw_source:
        source_image = raw_source.convert("RGB")
        search_image, region_payload = _desktop_vision_search_image(source_image, region)
        raw_text, local_blocks, diagnostics = _desktop_vision_ocr_blocks(
            search_image,
            language=language,
            provider=provider,
            region=region_payload,
            desktop_config=desktop_config,
        )
        ocr_blocks = _desktop_vision_global_matches(local_blocks, source_bounds)
        local_matches = _desktop_vision_text_matches(
            local_blocks,
            match_query=match_query,
            min_confidence=min_confidence,
            max_matches=max_matches,
            case_sensitive=case_sensitive,
        )
        matches = _desktop_vision_global_matches(local_matches, source_bounds)
        local_selected = local_matches[match_index] if 0 <= match_index < len(local_matches) else None
        selected = matches[match_index] if 0 <= match_index < len(matches) else None
        if local_selected is not None:
            _save_desktop_vision_crop(source_image, local_selected["bounds"], artifacts["crop"])
            _save_desktop_vision_annotation(source_image, local_matches, local_selected, artifacts["annotation"])

    source_profile = source_payload.get("coordinate_profile") if isinstance(source_payload.get("coordinate_profile"), dict) else {}
    coordinate_space = (
        source_profile.get("space")
        if isinstance(source_profile.get("space"), dict)
        else {"origin": coordinate_origin, "unit": "logical_px", "scale": None}
    )
    source_size = {"width": int(source_image.width), "height": int(source_image.height)}
    if not source_profile:
        source_profile = build_coordinate_profile(
            source_kind=coordinate_origin,
            source_bounds=source_bounds,
            source_size=source_size,
            coordinate_space=coordinate_space,
            region=region_payload,
            screen_clickable=coordinate_origin not in {"source_path", "image", "offline_image"},
        )
    coordinate_diagnostics = _coordinate_diagnostics(
        source_bounds=source_bounds,
        source_size=source_size,
        coordinate_space=coordinate_space,
        region=region_payload,
        coordinate_profile=source_profile,
    )
    target_candidates = build_vision_targeting(
        desktop=desktop,
        vision_type="locate_text",
        match_query=match_query,
        source_target=str(source_payload.get("source_target", "")),
        source_bounds=source_bounds,
        coordinate_profile=source_profile,
        coordinate_diagnostics=coordinate_diagnostics,
        target_query=source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        locator=source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        matches=matches,
        selected_match=selected or {},
    )
    payload = {
        "ok": selected is not None,
        "action": "desktop_vision",
        "type": "locate_text",
        "desktop": desktop,
        "source_target": str(source_payload.get("source_target", "")),
        "source_path": str(source_path),
        "match_query": match_query,
        "language": language,
        "provider": diagnostics.get("provider", provider),
        "min_confidence": min_confidence,
        "case_sensitive": case_sensitive,
        "match_index": match_index,
        "max_matches": max_matches,
        "raw_text": raw_text,
        "ocr_blocks": ocr_blocks,
        "coordinate_space": coordinate_space,
        "coordinate_profile": source_profile,
        "coordinate_diagnostics": coordinate_diagnostics,
        "source_bounds": source_bounds,
        "region": region_payload,
        "target_query": source_payload.get("target_query") if isinstance(source_payload.get("target_query"), dict) else {},
        "locator": source_payload.get("locator") if isinstance(source_payload.get("locator"), dict) else {},
        "window": source_payload.get("window") if isinstance(source_payload.get("window"), dict) else {},
        "element": source_payload.get("element") if isinstance(source_payload.get("element"), dict) else {},
        "matches": matches,
        "match": selected or {},
        "target_candidates": target_candidates,
        "artifacts": {
            "json_path": str(output_path),
            "json_relative_path": output_relative_path(output_path),
            "source_path": str(artifacts["source"]),
            "source_relative_path": output_relative_path(artifacts["source"]),
            "crop_path": str(artifacts["crop"]) if selected is not None else "",
            "crop_relative_path": output_relative_path(artifacts["crop"]) if selected is not None else "",
            "annotation_path": str(artifacts["annotation"]) if selected is not None else "",
            "annotation_relative_path": output_relative_path(artifacts["annotation"]) if selected is not None else "",
        },
        "diagnostics": {
            **diagnostics,
            "candidate_count": len(matches),
            "ocr_block_count": len(ocr_blocks),
            "source_size": source_size,
            "match_query": match_query,
            "min_confidence": min_confidence,
        },
        "source": source_payload,
        "elapsed_ms": _elapsed_ms(started),
    }
    return payload


def _desktop_vision_ocr_blocks(
    image: Any,
    *,
    language: str,
    provider: str,
    region: dict[str, int],
    desktop_config: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    normalized_provider = "tesseract" if provider == "auto" else provider
    if normalized_provider != "tesseract":
        raise DesktopBackendError(f"desktop_vision.locate_text 不支持的 OCR provider：{provider}")
    tsv_text, diagnostics = _run_tesseract_tsv(image, language=language, desktop_config=desktop_config)
    word_blocks = _parse_tesseract_tsv_words(tsv_text, region=region)
    line_blocks = _merge_ocr_words_to_lines(word_blocks)
    raw_text = "\n".join(str(block.get("text", "")) for block in line_blocks if block.get("text"))
    diagnostics.update(
        {
            "provider": "tesseract",
            "language": language,
            "word_count": len(word_blocks),
            "line_count": len(line_blocks),
        }
    )
    return raw_text, line_blocks, diagnostics


def _run_tesseract_tsv(
    image: Any,
    *,
    language: str,
    desktop_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    tesseract_details = tesseract_binary_details(desktop_config)
    binary = resolve_tesseract_binary(desktop_config)
    if not binary:
        source = str(tesseract_details.get("source") or "PATH")
        configured_path = str(tesseract_details.get("configured_path") or "")
        configured_detail = f" 配置路径：{configured_path}" if configured_path else ""
        raise DesktopBackendError(
            "desktop_vision.locate_text 需要系统可执行的 tesseract 命令；"
            "请安装 Tesseract、加入 PATH，或在 config.json 的 desktop.ocr.tesseract_path 指定路径。"
            f" 当前探测来源：{source}.{configured_detail}"
        )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        image.save(temp_path)
        completed = subprocess.run(
            [
                binary,
                str(temp_path),
                "stdout",
                *tesseract_common_options(desktop_config),
                "-l",
                language,
                "--psm",
                "6",
                "tsv",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise DesktopBackendError(f"desktop_vision.locate_text OCR 失败：{message}")
    return completed.stdout, {
        "method": "tesseract.tsv",
        "tesseract_path": binary,
        "tesseract_source": str(tesseract_details.get("source") or ""),
        "configured_tesseract_path": str(tesseract_details.get("configured_path") or ""),
        "tessdata_dir": str(tesseract_details.get("tessdata_dir") or ""),
        "engine_version": _tesseract_version(binary),
    }


def _tesseract_version(binary: str) -> str:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    first_line = (completed.stdout or completed.stderr or "").splitlines()
    return first_line[0].strip() if first_line else ""


def _parse_tesseract_tsv_words(tsv_text: str, *, region: dict[str, int]) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    words: list[dict[str, Any]] = []
    for row in reader:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        confidence = _ocr_confidence(row.get("conf"))
        if confidence < 0:
            continue
        try:
            left = int(float(row.get("left", 0) or 0))
            top = int(float(row.get("top", 0) or 0))
            width = int(float(row.get("width", 0) or 0))
            height = int(float(row.get("height", 0) or 0))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        local_x = int(region.get("x", 0)) + left
        local_y = int(region.get("y", 0)) + top
        bounds = {"x": local_x, "y": local_y, "width": width, "height": height}
        words.append(
            {
                "index": len(words),
                "level": "word",
                "text": text,
                "confidence": confidence,
                "score": confidence,
                "bounds": bounds,
                "point": {"x": local_x + width // 2, "y": local_y + height // 2},
                "line_key": (
                    str(row.get("page_num", "")),
                    str(row.get("block_num", "")),
                    str(row.get("par_num", "")),
                    str(row.get("line_num", "")),
                ),
            }
        )
    return words


def _merge_ocr_words_to_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for word in words:
        grouped.setdefault(tuple(word.get("line_key", ("", "", "", ""))), []).append(word)
    lines: list[dict[str, Any]] = []
    for key, line_words in grouped.items():
        sorted_words = sorted(line_words, key=lambda item: (int(item.get("bounds", {}).get("y", 0)), int(item.get("bounds", {}).get("x", 0))))
        bounds = _union_bounds([word.get("bounds", {}) for word in sorted_words])
        confidence_values = [float(word.get("confidence", 0.0) or 0.0) for word in sorted_words]
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        text = " ".join(str(word.get("text", "")) for word in sorted_words if word.get("text"))
        point = {"x": bounds["x"] + bounds["width"] // 2, "y": bounds["y"] + bounds["height"] // 2}
        lines.append(
            {
                "index": len(lines),
                "level": "line",
                "line_key": list(key),
                "text": text,
                "confidence": confidence,
                "score": confidence,
                "bounds": bounds,
                "point": point,
                "words": [
                    {
                        "text": str(word.get("text", "")),
                        "confidence": float(word.get("confidence", 0.0) or 0.0),
                        "bounds": dict(word.get("bounds", {})),
                    }
                    for word in sorted_words
                ],
            }
        )
    return lines


def _desktop_vision_text_matches(
    blocks: list[dict[str, Any]],
    *,
    match_query: dict[str, str],
    min_confidence: float,
    max_matches: int,
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for block in blocks:
        confidence = float(block.get("confidence", 0.0) or 0.0)
        if confidence < min_confidence:
            continue
        if not _text_query_matches(str(block.get("text", "")), match_query, case_sensitive=case_sensitive):
            continue
        match = dict(block)
        match["index"] = len(matches)
        match["block_index"] = block.get("index")
        match["match_query"] = dict(match_query)
        match["score"] = confidence
        matches.append(match)
        if len(matches) >= max(1, max_matches):
            break
    return matches


def _text_query_matches(text: str, match_query: dict[str, str], *, case_sensitive: bool) -> bool:
    actual = text if case_sensitive else text.casefold()
    if "text" in match_query:
        expected = match_query["text"] if case_sensitive else match_query["text"].casefold()
        return actual == expected
    if "text_contains" in match_query:
        expected = match_query["text_contains"] if case_sensitive else match_query["text_contains"].casefold()
        return expected in actual
    if "text_regex" in match_query:
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(match_query["text_regex"], text, flags=flags) is not None
    return False


def _ocr_confidence(raw_confidence: Any) -> float:
    try:
        value = float(raw_confidence)
    except (TypeError, ValueError):
        return -1.0
    if value < 0:
        return -1.0
    return max(0.0, min(1.0, value / 100.0))


def _union_bounds(bounds_list: list[dict[str, Any]]) -> dict[str, int]:
    normalized = [
        {
            "x": int(bounds.get("x", 0) or 0),
            "y": int(bounds.get("y", 0) or 0),
            "width": int(bounds.get("width", 0) or 0),
            "height": int(bounds.get("height", 0) or 0),
        }
        for bounds in bounds_list
        if isinstance(bounds, dict)
    ]
    if not normalized:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    left = min(bounds["x"] for bounds in normalized)
    top = min(bounds["y"] for bounds in normalized)
    right = max(bounds["x"] + bounds["width"] for bounds in normalized)
    bottom = max(bounds["y"] + bounds["height"] for bounds in normalized)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _desktop_vision_search_image(source_image: Any, region: dict[str, Any] | None) -> tuple[Any, dict[str, int]]:
    if not region:
        return source_image, {"x": 0, "y": 0, "width": int(source_image.width), "height": int(source_image.height)}
    x = int(region.get("x", 0))
    y = int(region.get("y", 0))
    width = int(region.get("width", 0))
    height = int(region.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(f"desktop_vision.region 无效：{region}")
    if x < 0 or y < 0 or x + width > source_image.width or y + height > source_image.height:
        raise ValueError(
            "desktop_vision.region 超出截图范围："
            f"region={region} source={source_image.width}x{source_image.height}"
        )
    return source_image.crop((x, y, x + width, y + height)), {"x": x, "y": y, "width": width, "height": height}


def _desktop_vision_template_matches(
    result: Any,
    *,
    threshold: float,
    max_matches: int,
    template_width: int,
    template_height: int,
    region: dict[str, int],
) -> list[dict[str, Any]]:
    import cv2

    matches: list[dict[str, Any]] = []
    working = result.copy()
    normalized_threshold = float(threshold)
    for _ in range(max(1, max_matches)):
        _min_value, max_value, _min_location, max_location = cv2.minMaxLoc(working)
        score = float(max_value)
        if score < normalized_threshold:
            break
        local_x, local_y = int(max_location[0]), int(max_location[1])
        x = int(region["x"]) + local_x
        y = int(region["y"]) + local_y
        bounds = {"x": x, "y": y, "width": int(template_width), "height": int(template_height)}
        matches.append(
            {
                "index": len(matches),
                "score": score,
                "confidence": score,
                "bounds": bounds,
                "point": {"x": x + int(template_width) // 2, "y": y + int(template_height) // 2},
            }
        )
        suppress_left = max(0, local_x - int(template_width) // 2)
        suppress_top = max(0, local_y - int(template_height) // 2)
        suppress_right = min(working.shape[1], local_x + int(template_width) // 2 + 1)
        suppress_bottom = min(working.shape[0], local_y + int(template_height) // 2 + 1)
        working[suppress_top:suppress_bottom, suppress_left:suppress_right] = -1
    return matches


def _desktop_vision_global_matches(
    local_matches: list[dict[str, Any]],
    source_bounds: dict[str, int],
    *,
    coordinate_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    mapper = CoordinateMapper.from_profile(coordinate_profile or build_coordinate_profile(source_bounds=source_bounds))
    matches: list[dict[str, Any]] = []
    for match in local_matches:
        local_bounds = match.get("bounds") if isinstance(match.get("bounds"), dict) else {}
        local_point = match.get("point") if isinstance(match.get("point"), dict) else {}
        bounds = mapper.local_to_screen_bounds(local_bounds)
        point = mapper.local_to_screen_point(local_point)
        matches.append({**match, "local_bounds": dict(local_bounds), "local_point": dict(local_point), "bounds": bounds, "point": point})
    return matches


def _save_desktop_vision_crop(source_image: Any, bounds: dict[str, Any], path: Path) -> None:
    x = int(bounds["x"])
    y = int(bounds["y"])
    width = int(bounds["width"])
    height = int(bounds["height"])
    path.parent.mkdir(parents=True, exist_ok=True)
    source_image.crop((x, y, x + width, y + height)).save(path)


def _save_desktop_vision_annotation(source_image: Any, matches: list[dict[str, Any]], selected: dict[str, Any], path: Path) -> None:
    from PIL import ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    annotated = source_image.copy()
    draw = ImageDraw.Draw(annotated)
    for match in matches:
        bounds = match.get("bounds", {})
        try:
            x = int(bounds.get("x", 0))
            y = int(bounds.get("y", 0))
            width = int(bounds.get("width", 0))
            height = int(bounds.get("height", 0))
        except (TypeError, ValueError):
            continue
        color = (255, 64, 64) if match is selected else (64, 128, 255)
        draw.rectangle((x, y, x + width, y + height), outline=color, width=3)
        draw.text((x + 4, y + 4), f"{match.get('index', '')}:{float(match.get('score', 0.0)):.3f}", fill=color)
    point = selected.get("point", {}) if isinstance(selected.get("point"), dict) else {}
    if point:
        x = int(point.get("x", 0))
        y = int(point.get("y", 0))
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), outline=(255, 64, 64), width=4)
    annotated.save(path)



def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
