from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ai_automate_contro.plans.config import load_plan_config
from ai_automate_contro.plans.validation_models import ValidationIssue


def load_json_document(path: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as file:
            document = json.load(file)
    except JSONDecodeError as error:
        issues.append(ValidationIssue(str(path), f"JSON 无效：{error.msg}"))
        return None
    except OSError as error:
        issues.append(ValidationIssue(str(path), str(error)))
        return None
    if not isinstance(document, dict):
        issues.append(ValidationIssue(str(path), "plan 文档必须是 JSON 对象"))
        return None
    return document


def validate_config(project_root: Path, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        config = load_plan_config(project_root, plan_dir)
    except Exception as error:
        issues.append(ValidationIssue(str(plan_dir / "config.json"), f"合并后的配置无效：{error}"))
        return
    if "variables" in config:
        issues.append(
            ValidationIssue(
                str(plan_dir / "config.json") + ":variables",
                "config.json 不支持 variables；plan 变量请写在 plan.json.variables",
            )
        )
    validate_post_run_inspection_config(config.get("post_run_inspection"), plan_dir, issues)
    validate_desktop_config(config.get("desktop"), plan_dir, issues)
    validate_desktop_profiles_config(config.get("desktop_profiles"), plan_dir, issues, field_name="desktop_profiles")
    validate_desktop_profiles_config(config.get("desktop_app_profiles"), plan_dir, issues, field_name="desktop_app_profiles")


def validate_post_run_inspection_config(value: Any, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    location = str(plan_dir / "config.json") + ":post_run_inspection"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "post_run_inspection 必须是 JSON 对象"))
        return
    enabled = value.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        issues.append(ValidationIssue(location, "enabled 必须是布尔值"))
    prompt = value.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        issues.append(ValidationIssue(location, "prompt 必须是字符串"))


def validate_desktop_config(value: Any, plan_dir: Path, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    location = str(plan_dir / "config.json") + ":desktop"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, "desktop 必须是 JSON 对象"))
        return
    ocr = value.get("ocr")
    if ocr is not None:
        ocr_location = location + ".ocr"
        if not isinstance(ocr, dict):
            issues.append(ValidationIssue(ocr_location, "desktop.ocr 必须是 JSON 对象"))
        else:
            for field in ("tesseract_path", "tessdata_dir", "default_language"):
                field_value = ocr.get(field)
                if field_value is not None and not isinstance(field_value, str):
                    issues.append(ValidationIssue(f"{ocr_location}.{field}", f"desktop.ocr.{field} 必须是字符串"))
    validate_desktop_run_mutex_config(value.get("run_mutex"), location, issues)
    validate_desktop_foreground_protection_config(value.get("foreground_protection"), location, issues)


def validate_desktop_run_mutex_config(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    mutex_location = location + ".run_mutex"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(mutex_location, "desktop.run_mutex 必须是 JSON 对象"))
        return
    enabled = value.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        issues.append(ValidationIssue(f"{mutex_location}.enabled", "desktop.run_mutex.enabled 必须是布尔值"))
    scope = value.get("scope")
    if scope is not None and scope not in {"project", "plan_package"}:
        issues.append(ValidationIssue(f"{mutex_location}.scope", "desktop.run_mutex.scope 只能是 project 或 plan_package"))
    on_conflict = value.get("on_conflict")
    if on_conflict is not None and on_conflict not in {"fail", "wait"}:
        issues.append(ValidationIssue(f"{mutex_location}.on_conflict", "desktop.run_mutex.on_conflict 只能是 fail 或 wait"))
    _validate_non_negative_int(value, "wait_timeout_seconds", mutex_location, issues)
    _validate_positive_int(value, "stale_after_seconds", mutex_location, issues)


def validate_desktop_foreground_protection_config(value: Any, location: str, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    protection_location = location + ".foreground_protection"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(protection_location, "desktop.foreground_protection 必须是 JSON 对象"))
        return
    for field in ("enabled", "strict"):
        field_value = value.get(field)
        if field_value is not None and not isinstance(field_value, bool):
            issues.append(ValidationIssue(f"{protection_location}.{field}", f"desktop.foreground_protection.{field} 必须是布尔值"))
    _validate_positive_int(value, "activation_attempts", protection_location, issues)
    _validate_non_negative_int(value, "retry_delay_ms", protection_location, issues)


def _validate_non_negative_int(
    value: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    field_value = value.get(field)
    if field_value is not None and (not isinstance(field_value, int) or isinstance(field_value, bool) or field_value < 0):
        issues.append(ValidationIssue(f"{location}.{field}", f"{field} 必须是非负整数"))


def _validate_positive_int(
    value: dict[str, Any],
    field: str,
    location: str,
    issues: list[ValidationIssue],
) -> None:
    field_value = value.get(field)
    if field_value is not None and (not isinstance(field_value, int) or isinstance(field_value, bool) or field_value <= 0):
        issues.append(ValidationIssue(f"{location}.{field}", f"{field} 必须是正整数"))


def validate_desktop_profiles_config(
    value: Any,
    plan_dir: Path,
    issues: list[ValidationIssue],
    *,
    field_name: str,
) -> None:
    if value is None:
        return
    location = str(plan_dir / "config.json") + f":{field_name}"
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, f"{field_name} 必须是 JSON 对象"))
        return
    for profile_id, profile in value.items():
        profile_location = f"{location}.{profile_id}"
        if not isinstance(profile_id, str) or not profile_id:
            issues.append(ValidationIssue(location, f"{field_name} 的 profile 名称必须是非空字符串"))
            continue
        if not isinstance(profile, dict):
            issues.append(ValidationIssue(profile_location, f"{field_name}.{profile_id} 必须是 JSON 对象"))
            continue
        _validate_desktop_profile(profile, profile_location, issues)


def _validate_desktop_profile(profile: dict[str, Any], location: str, issues: list[ValidationIssue]) -> None:
    aliases = profile.get("aliases")
    if aliases is not None:
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias for alias in aliases):
            issues.append(ValidationIssue(f"{location}.aliases", "aliases 必须是非空字符串数组"))
    for section in ("launch", "window_query", "defaults"):
        _validate_desktop_profile_section(profile.get(section), f"{location}.{section}", section, issues)
    platforms = profile.get("platforms")
    if platforms is None:
        return
    if not isinstance(platforms, dict):
        issues.append(ValidationIssue(f"{location}.platforms", "platforms 必须是 JSON 对象"))
        return
    for platform_name, platform_profile in platforms.items():
        platform_location = f"{location}.platforms.{platform_name}"
        if not isinstance(platform_name, str) or not platform_name:
            issues.append(ValidationIssue(f"{location}.platforms", "platforms 的平台名必须是非空字符串"))
            continue
        if not isinstance(platform_profile, dict):
            issues.append(ValidationIssue(platform_location, f"platforms.{platform_name} 必须是 JSON 对象"))
            continue
        for section in ("launch", "window_query", "defaults"):
            _validate_desktop_profile_section(
                platform_profile.get(section),
                f"{platform_location}.{section}",
                section,
                issues,
            )


def _validate_desktop_profile_section(
    value: Any,
    location: str,
    section: str,
    issues: list[ValidationIssue],
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(ValidationIssue(location, f"{section} 必须是 JSON 对象"))
        return
    if section == "launch":
        _validate_desktop_profile_launch(value, location, issues)
    elif section == "window_query":
        _validate_desktop_profile_window_query(value, location, issues)
    elif section == "defaults":
        _validate_desktop_profile_defaults(value, location, issues)


def _validate_desktop_profile_launch(value: dict[str, Any], location: str, issues: list[ValidationIssue]) -> None:
    for field in ("app", "path", "command"):
        field_value = value.get(field)
        if field_value is not None and not isinstance(field_value, str):
            issues.append(ValidationIssue(f"{location}.{field}", f"launch.{field} 必须是字符串"))
    args = value.get("args")
    if args is not None:
        if not isinstance(args, list) or any(not isinstance(arg, str) or not arg for arg in args):
            issues.append(ValidationIssue(f"{location}.args", "launch.args 必须是非空字符串数组"))
    _validate_profile_bool_fields(value, location, issues, ("wait", "wait_for_window", "focus"))
    _validate_profile_int_fields(value, location, issues, ("timeout_ms", "window_timeout_ms", "interval_ms"))


def _validate_desktop_profile_window_query(value: dict[str, Any], location: str, issues: list[ValidationIssue]) -> None:
    for field in ("title", "title_contains", "title_regex", "app", "process", "process_name", "class_name", "window_id"):
        field_value = value.get(field)
        if field_value is not None and not isinstance(field_value, (str, int) if field == "window_id" else str):
            expected = "字符串或整数" if field == "window_id" else "字符串"
            issues.append(ValidationIssue(f"{location}.{field}", f"window_query.{field} 必须是{expected}"))
    match_index = value.get("match_index")
    if match_index is not None and not isinstance(match_index, int):
        issues.append(ValidationIssue(f"{location}.match_index", "window_query.match_index 必须是整数"))


def _validate_desktop_profile_defaults(value: dict[str, Any], location: str, issues: list[ValidationIssue]) -> None:
    _validate_profile_bool_fields(value, location, issues, ("wait", "wait_for_window", "focus"))
    _validate_profile_int_fields(
        value,
        location,
        issues,
        ("timeout_ms", "window_timeout_ms", "interval_ms", "max_depth", "max_elements"),
    )


def _validate_profile_bool_fields(
    value: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        field_value = value.get(field)
        if field_value is not None and not isinstance(field_value, bool):
            issues.append(ValidationIssue(f"{location}.{field}", f"{field} 必须是布尔值"))


def _validate_profile_int_fields(
    value: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        field_value = value.get(field)
        if field_value is not None and not isinstance(field_value, int):
            issues.append(ValidationIssue(f"{location}.{field}", f"{field} 必须是整数"))
