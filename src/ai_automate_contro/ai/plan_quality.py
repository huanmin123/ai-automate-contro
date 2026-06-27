from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_automate_contro.ai.plan_tools import issue_to_dict, resolve_plan_path
from ai_automate_contro.plans.loader import load_plan
from ai_automate_contro.plans.validator import validate_plan_file
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text
from ai_automate_contro.support.redaction import redact_secret_text


URL_RE = re.compile(r"https?://[^\s，。；;,）)\"']+", re.IGNORECASE)
FILENAME_RE = re.compile(r"[\w\u4e00-\u9fff ._-]+\.(?:txt|csv|json|xlsx|md|html|png|jpg|jpeg|webp|pdf)", re.IGNORECASE)
LABELED_FILENAME_RE = re.compile(
    r"(?:文件名称|文件名|filename|file name)\s*(?:[:：=是为]|就是|叫|命名为|保存为)?\s*"
    r"([^\s，。；;,/\\]+?\.(?:txt|csv|json|xlsx|md|html|png|jpg|jpeg|webp|pdf))",
    re.IGNORECASE,
)
TEMPLATE_RE = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
ACCOUNT_VALUE_RE = re.compile(
    r"(?:账户名称|登录账号|账号|账户|用户名|用户|邮箱|email|username|user)\s*(?:[:：=是为]\s*)?([A-Za-z0-9_@+\-][A-Za-z0-9._@+\-]{1,})",
    re.IGNORECASE,
)
PASSWORD_VALUE_RE = re.compile(
    r"(?:登录密码|密码|password|passwd|pwd|pass)\s*(?:[:：=是为]\s*)?([^\s，。；;,]+)",
    re.IGNORECASE,
)

ACCOUNT_FIELD_TOKENS = (
    "account",
    "email",
    "login",
    "username",
    "user-name",
    "user_name",
    "mobile",
    "phone",
    "账号",
    "账户",
    "账户名称",
    "用户名",
    "登录名",
    "邮箱",
    "手机号",
    "手机",
)
PASSWORD_FIELD_TOKENS = ("password", "passwd", "pwd", "pass", "密码", "口令")
LOGIN_TOKENS = (
    "登录",
    "登陆",
    "login",
    "sign in",
    "signin",
    "认证",
    "验证",
    "验证码",
    "二次验证",
    "双重验证",
    "2fa",
    "mfa",
    "滑块",
    "真人验证",
    "授权",
    "权限",
)
ACCOUNT_REQUEST_TOKENS = (
    "账号",
    "用户名",
    "登录名",
    "account",
    "username",
    "email",
    "邮箱",
    "手机号",
    "手机",
)
PASSWORD_REQUEST_TOKENS = ("密码", "password", "passwd", "pwd", "口令")
OUTPUT_TOKENS = ("写到", "写入", "保存", "导出", "输出", "文件", "产出", "一行一个", "下载", "Downloads", "Desktop")
EXTRACTION_TOKENS = ("拿出来", "提取", "读取", "获取", "抓取", "导出", "列表", "全部", "所有", "一行一个")
NEGATIVE_EVIDENCE_TOKENS = (
    "没有探测",
    "未探测",
    "没探测",
    "缺少探测",
    "没有探索",
    "未探索",
    "缺少探索",
    "没有证据",
    "缺少证据",
    "无证据",
)
AUTOMATION_EVIDENCE_TOKENS = (
    "inspect_web_page",
    "output_dir",
    "final_url",
    "forms",
    "inputs",
    "Playwright",
    "headed=true",
    "headed 探索",
    "探索 plan",
)
RUN_EVIDENCE_TOKENS = ("run_plan", "run_debug_plan")
RUN_RESULT_EVIDENCE_TOKENS = ("output_dir", "final_url", "report.md", "state.json", "events.jsonl", "passed", "failed", "已运行", "跑通")
MANUAL_CONFIRM_EVIDENCE_TOKENS = ("manual_confirm", "人工确认")
MANUAL_CONFIRM_CONTEXT_TOKENS = ("同一个 Playwright", "当前浏览器", "可见浏览器", "headed", "headed=true", "探索 plan")
CREDENTIAL_VALUE_STOPWORDS = {
    "field",
    "fields",
    "input",
    "inputs",
    "selector",
    "name",
    "list",
    "policy",
    "required",
    "optional",
    "placeholder",
    "输入框",
    "字段",
    "控件",
    "选择器",
    "列表",
    "策略",
    "要求",
    "可选",
    "必填",
    "为空",
    "错误",
    "正确",
    "泄露",
    "明文",
    "星号",
}
FINAL_BROWSER_OUTPUT_ACTIONS = {"write", "capture", "wait_for_download", "ai", "trace", "event", "coverage"}
BROWSER_DATA_COLLECTION_ACTIONS = {"extract", "script", "ai", "storage", "wait_for_download"}
FINAL_DESKTOP_OUTPUT_ACTIONS = {"write", "desktop_capture", "desktop_assert", "desktop_vision", "ai", "command"}
DESKTOP_DATA_COLLECTION_ACTIONS = {"desktop_capture", "desktop_wait", "desktop_assert", "desktop_vision", "ai", "command"}
BROWSER_POST_MANUAL_ACTIONS = {"extract", "write", "capture", "assert", "script", "storage", "wait_for_download", "ai"}
DESKTOP_POST_MANUAL_ACTIONS = {
    "desktop_app",
    "desktop_element",
    "desktop_window",
    "desktop_input",
    "desktop_capture",
    "desktop_vision",
    "desktop_wait",
    "desktop_assert",
    "write",
    "ai",
    "command",
}


def review_plan_quality_tool(
    project_root: str | Path,
    *,
    plan_path: str | Path,
    user_request: str,
    evidence_summary: str = "",
    planned_output_path: str = "",
    strict: bool = True,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    validation = validate_plan_file(resolved_plan_path, root)
    checks: list[dict[str, Any]] = [
        {
            "name": "validate_plan",
            "passed": validation.ok,
            "detail": "plan 结构校验通过" if validation.ok else "plan 结构校验失败",
        }
    ]
    issues: list[dict[str, str]] = []
    if not validation.ok:
        issues.append(
            _issue(
                "fail",
                "invalid_plan",
                "plan 结构校验未通过，不能继续做质量复查或运行。",
                "\n".join(error.format() for error in validation.errors[:8]),
                "先按 validate_plan 返回的错误修正 plan，再重新调用 review_plan_quality。",
            )
        )
        return _quality_result(
            plan_path=resolved_plan_path,
            checks=checks,
            issues=issues,
            covered_facts=[],
            missing_facts=["plan 结构有效"],
            uncertain_facts=[],
            validation_errors=[issue_to_dict(error) for error in validation.errors],
            planned_output_path=planned_output_path,
        )

    package = _collect_plan_package(resolved_plan_path)
    step_records = package["steps"]
    variables = package["variables"]
    raw_plan_text = package["raw_text"]
    automation_type = _package_automation_type(package)
    profile = _profile_request(user_request, evidence_summary, planned_output_path)
    profile["automation_type"] = automation_type
    _augment_profile_from_plan(profile, step_records, variables)
    _apply_execution_line_profile(profile)
    facts: list[str] = []
    missing_facts: list[str] = []
    uncertain_facts: list[str] = []

    checks.append(
        {
            "name": "steps_present",
            "passed": bool(step_records),
            "detail": f"发现 {len(step_records)} 个可执行步骤",
        }
    )
    if not step_records:
        issues.append(
            _issue(
                "fail",
                "empty_plan",
                "plan 没有可执行步骤。",
                str(resolved_plan_path),
                "补充完成需求所需的浏览器、提取、写出和验证步骤。",
            )
        )
        missing_facts.append("可执行步骤")

    checks.append(
        {
            "name": "automation_type",
            "passed": automation_type in {"browser", "desktop"},
            "detail": automation_type or "<missing>",
        }
    )

    _review_browser_flow(
        profile,
        step_records,
        variables,
        evidence_summary,
        evidence_context or {},
        strict,
        checks,
        issues,
        facts,
        missing_facts,
        uncertain_facts,
    )
    _review_desktop_flow(profile, step_records, evidence_summary, evidence_context or {}, checks, issues, facts, missing_facts)
    _review_credentials(profile, step_records, variables, raw_plan_text, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_login_progression(profile, step_records, variables, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_output(profile, step_records, variables, planned_output_path, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_manual_confirm(profile, step_records, strict, checks, issues, facts, missing_facts, uncertain_facts)

    return _quality_result(
        plan_path=resolved_plan_path,
        checks=checks,
        issues=issues,
        covered_facts=facts,
        missing_facts=missing_facts,
        uncertain_facts=uncertain_facts,
        validation_errors=[],
        planned_output_path=planned_output_path,
    )


def _review_browser_flow(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    if automation_type != "browser":
        checks.append(
            {
                "name": "browser_navigation",
                "passed": True,
                "detail": {"automation_type": automation_type, "not_applicable": True},
            }
        )
        checks.append(
            {
                "name": "real_site_evidence",
                "passed": True,
                "detail": {"automation_type": automation_type, "not_applicable": True},
            }
        )
        return

    has_open_browser = any(_action(record) == "open_browser" for record in steps)
    navigate_steps = [record for record in steps if _action(record) == "navigate" and record["step"].get("type") == "goto"]
    has_manual_confirm = any(_action(record) == "manual_confirm" for record in steps)
    has_browser_evidence = _has_real_site_automation_evidence(
        evidence_summary,
        urls=profile["urls"],
        evidence_context=evidence_context,
    )
    request_urls = profile["urls"]
    url_covered = True
    uncovered_urls: list[str] = []
    for url in request_urls:
        if not _url_covered(url, navigate_steps, variables):
            uncovered_urls.append(url)
    if uncovered_urls:
        url_covered = False

    needs_browser = profile["needs_browser"]
    browser_ok = not needs_browser or (has_open_browser and bool(navigate_steps) and url_covered)
    checks.append(
        {
            "name": "browser_navigation",
            "passed": browser_ok,
            "detail": {
                "needs_browser": needs_browser,
                "open_browser": has_open_browser,
                "navigate_count": len(navigate_steps),
                "uncovered_urls": uncovered_urls,
            },
        }
    )
    if not browser_ok:
        issues.append(
            _issue(
                "fail",
                "missing_browser_navigation",
                "用户需求涉及网站或 URL，但 plan 没有完整覆盖打开浏览器、导航目标页面和目标 URL。",
                ", ".join(uncovered_urls) or "缺少 open_browser/navigate",
                "补充 open_browser、navigate.type=goto，并确保 url 使用用户给出的真实入口或对应变量。",
            )
        )
        missing_facts.append("目标网站导航")
    elif needs_browser:
        facts.append("已覆盖目标网站导航")

    evidence_needed = profile["is_real_site"]
    evidence_ok = not evidence_needed or has_browser_evidence
    checks.append(
        {
            "name": "real_site_evidence",
            "passed": evidence_ok,
            "detail": {
                "needs_evidence": evidence_needed,
                "evidence_summary_present": bool(str(evidence_summary or "").strip()),
                "evidence_context_present": bool(evidence_context),
                "headed_exploration_in_plan": any(
                    _action(record) == "open_browser" and bool(record["step"].get("headed")) for record in steps
                ),
                "manual_confirm": has_manual_confirm,
            },
        }
    )
    if not evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_real_site_evidence",
                "真实网站最终 plan 运行前缺少探测或探索证据，容易按文字猜 selector。",
                "evidence_summary 为空或没有自动化探测/探索证据",
                "先调用 inspect_web_page；涉及登录、菜单、验证码或动态后台时，再运行 headed 探索 plan 并把证据摘要传给 review_plan_quality。",
            )
        )
        missing_facts.append("真实网站探测/探索证据")
    elif evidence_needed:
        facts.append("已有真实网站探测或探索证据")


def _review_desktop_flow(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    if automation_type != "desktop":
        checks.append(
            {
                "name": "desktop_session",
                "passed": True,
                "detail": {"automation_type": automation_type, "not_applicable": True},
            }
        )
        return

    has_open_desktop = any(_action(record) == "open_desktop" for record in steps)
    desktop_action_locations = [
        record["location"]
        for record in steps
        if _action(record).startswith("desktop_") or _action(record) == "close_desktop"
    ]
    evidence_locations = [record["location"] for record in steps if _is_desktop_evidence_step(record)]
    session_ok = not desktop_action_locations or has_open_desktop
    evidence_ok = not desktop_action_locations or bool(evidence_locations)
    inspection_ok = not desktop_action_locations or _has_desktop_inspection_evidence(evidence_summary, evidence_context)
    checks.append(
        {
            "name": "desktop_session",
            "passed": session_ok,
            "detail": {
                "open_desktop": has_open_desktop,
                "desktop_action_locations": desktop_action_locations,
            },
        }
    )
    if not session_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_session",
                "desktop plan 使用了桌面 action，但没有先打开桌面会话。",
                ", ".join(desktop_action_locations[:8]),
                "在桌面 action 前补充 open_desktop，并用 desktop 字段引用同一个会话名。",
            )
        )
        missing_facts.append("桌面会话打开步骤")
    else:
        facts.append("已覆盖桌面会话打开")

    checks.append(
        {
            "name": "desktop_inspection_evidence",
            "passed": inspection_ok,
            "detail": {
                "evidence_summary_present": bool(str(evidence_summary or "").strip()),
                "evidence_context_keys": sorted(evidence_context.keys()) if isinstance(evidence_context, dict) else [],
            },
        }
    )
    if not inspection_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_inspection_evidence",
                "真实桌面 plan 运行前缺少 inspect_desktop、capability_matrix、窗口列表、控件树或截图探测证据。",
                str(evidence_summary or "").strip()[:500] or "evidence_summary 为空，且没有桌面探测上下文。",
                "先调用 inspect_desktop 获取平台、backend、capability_matrix、窗口列表、可选控件树或截图，再把摘要传给 review_plan_quality。",
            )
        )
        missing_facts.append("桌面 inspect_desktop/capability_matrix 探测证据")
    else:
        facts.append("已有桌面 inspect_desktop/capability_matrix 探测证据")

    checks.append(
        {
            "name": "desktop_evidence_step",
            "passed": evidence_ok,
            "detail": {
                "has_window_capture_or_element_step": bool(evidence_locations),
                "evidence_action_locations": evidence_locations,
            },
        }
    )
    if not evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_evidence_step",
                "desktop plan 没有窗口、控件、截图、等待或断言类证据步骤，运行后难以判断桌面状态。",
                ", ".join(desktop_action_locations[:8]) or "无桌面证据 action",
                "补充 desktop_window list、desktop_element list/dump/find/get_text/get_state/get_table/get_tree、desktop_capture screenshot/snapshot、desktop_wait window 或 desktop_assert。",
            )
        )
    else:
        facts.append("已覆盖桌面窗口、控件或截图证据")


def _review_credentials(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    raw_plan_text: str,
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    account_values = profile["account_values"]
    password_values = profile["password_values"]
    account_needed = bool(account_values) or profile["mentions_account"]
    password_needed = bool(password_values) or profile["mentions_password"]
    fill_steps = [
        record
        for record in steps
        if _is_credential_input_step(record, automation_type)
    ]
    account_fills = [record for record in fill_steps if _is_account_fill(record["step"], variables, account_values)]
    password_fills = [record for record in fill_steps if _is_password_fill(record["step"], variables, password_values)]

    credential_ok = (not account_needed or bool(account_fills)) and (not password_needed or bool(password_fills))
    checks.append(
        {
            "name": "credential_inputs",
            "passed": credential_ok,
            "detail": {
                "account_needed": account_needed,
                "password_needed": password_needed,
                "account_fill_locations": [record["location"] for record in account_fills],
                "password_fill_locations": [record["location"] for record in password_fills],
            },
        }
    )
    if account_needed and not account_fills:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_account_fill",
                "用户提供或要求使用账号/账户信息，但 plan 没有可执行的账号输入步骤。",
                _values_evidence(account_values) or "需求包含账号/账户语义",
                "补充 element.type=fill/type，定位用户名/账号/邮箱/手机号输入框，并填入用户提供的值或明确变量。",
            )
        )
        missing_facts.append("账号输入步骤")
    elif account_needed:
        facts.append("已覆盖账号输入")

    if password_needed and not password_fills:
        password_in_text = any(value and value in raw_plan_text for value in password_values)
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_password_fill",
                "用户提供或要求使用密码，但 plan 没有可执行的密码输入步骤。",
                "密码只出现在自然语言文本里" if password_in_text else (_values_evidence(password_values) or "需求包含密码语义"),
                "补充 element.type=fill/type，定位 password/密码输入框，并填入用户提供的密码或明确变量。",
            )
        )
        missing_facts.append("密码输入步骤")
    elif password_needed:
        facts.append("已覆盖密码输入")

    if (account_needed or password_needed) and fill_steps and (not account_fills or not password_fills):
        uncertain_facts.append("存在输入步骤，但无法确认是否分别覆盖账号和密码")


def _review_login_progression(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    login_needed = bool(profile["mentions_login"] or profile["mentions_account"] or profile["mentions_password"])
    account_values = profile["account_values"]
    password_values = profile["password_values"]
    fill_indexes = [
        index
        for index, record in enumerate(steps)
        if _is_credential_input_step(record, automation_type)
        and (
            _is_account_fill(record["step"], variables, account_values)
            or _is_password_fill(record["step"], variables, password_values)
        )
    ]
    last_fill_index = max(fill_indexes) if fill_indexes else -1
    progression_steps = [
        record
        for index, record in enumerate(steps)
        if index > last_fill_index and _is_login_progression_step(record, automation_type)
    ]
    progression_ok = not login_needed or not fill_indexes or bool(progression_steps)
    checks.append(
        {
            "name": "login_submit_or_handoff",
            "passed": progression_ok,
            "detail": {
                "login_needed": login_needed,
                "credential_fill_locations": [steps[index]["location"] for index in fill_indexes],
                "progression_locations": [record["location"] for record in progression_steps],
            },
        }
    )
    if login_needed and fill_indexes and not progression_steps:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_login_submit_or_handoff",
                "plan 填写登录凭据后没有提交、回车、人工交接或后续登录推进步骤。",
                ", ".join(steps[index]["location"] for index in fill_indexes),
                "在密码/账号填入后补充登录按钮 click、Enter 提交、manual_confirm 交接，或可证明进入后台的提交触发步骤。",
            )
        )
        missing_facts.append("登录提交或人工交接步骤")
    elif login_needed and fill_indexes:
        facts.append("已覆盖登录提交或人工交接")


def _review_output(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    planned_output_path: str,
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    needs_output = profile["needs_output"]
    output_filename = profile["output_filename"]
    if automation_type == "desktop":
        output_steps = [record for record in steps if _is_desktop_output_step(record)]
        data_steps = [record for record in steps if _is_desktop_evidence_step(record)]
    else:
        output_steps = [record for record in steps if _action(record) in FINAL_BROWSER_OUTPUT_ACTIONS]
        data_steps = [record for record in steps if _action(record) in BROWSER_DATA_COLLECTION_ACTIONS]
    write_steps = [record for record in steps if _action(record) == "write"]
    target_file_covered = not output_filename or any(
        _path_basename(_resolved_step_text(record["step"].get("path"), variables)).lower() == output_filename.lower()
        for record in output_steps
        if record["step"].get("path") is not None
    )
    has_text_write = any(str(record["step"].get("type", "")).lower() == "text" for record in write_steps)
    requires_text = bool(output_filename and output_filename.lower().endswith(".txt")) or profile["one_per_line"]
    output_ok = (not needs_output or bool(output_steps)) and target_file_covered and (not requires_text or has_text_write)
    checks.append(
        {
            "name": "output_artifact",
            "passed": output_ok,
            "detail": {
                "needs_output": needs_output,
                "output_filename": output_filename,
                "output_step_locations": [record["location"] for record in output_steps],
                "has_text_write": has_text_write,
            },
        }
    )
    if needs_output and not output_steps:
        issues.append(
            _issue(
                "fail",
                "missing_output_artifact",
                "用户要求产出或保存结果，但 plan 没有 write/capture/download/ai 等输出步骤。",
                "未找到输出类 action",
                _output_fix_hint(automation_type),
            )
        )
        missing_facts.append("运行产物写出")
    elif needs_output:
        facts.append("已覆盖运行产物写出")

    if output_filename and not target_file_covered:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_requested_output_filename",
                "用户指定了最终文件名，但 plan 的输出文件名没有对应上。",
                output_filename,
                "在 write/capture/download 等步骤中使用用户指定的文件名；例如 TXT 结果用 write.type=text + path。",
            )
        )
        missing_facts.append(f"输出文件名 {output_filename}")
    elif output_filename:
        facts.append(f"已覆盖输出文件名 {output_filename}")

    if requires_text and output_steps and not has_text_write:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_text_output",
                "用户要求 TXT 或一行一个结果，但 plan 没有 write.type=text。",
                output_filename or "一行一个",
                "使用 write.type=text；value 可以是字符串数组，运行时会按一行一个写出。",
            )
        )
        missing_facts.append("TXT/一行一个写出")

    extraction_ok = not profile["needs_extraction"] or bool(data_steps)
    checks.append(
        {
            "name": "data_collection_before_output",
            "passed": extraction_ok,
            "detail": {
                "needs_extraction": profile["needs_extraction"],
                "data_step_locations": [record["location"] for record in data_steps],
            },
        }
    )
    if not extraction_ok:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "missing_data_extraction",
                _data_extraction_issue_message(automation_type),
                "需求包含提取/读取/全部/列表/一行一个语义",
                _data_extraction_fix_hint(automation_type),
            )
        )
        missing_facts.append("目标数据提取")
    elif profile["needs_extraction"]:
        facts.append("已覆盖目标数据提取")

    if _requires_external_export(planned_output_path, profile):
        issues.append(
            _issue(
                "warn",
                "requires_export_local_file_after_run",
                "用户要求最终交付到项目外本机路径；plan 只能写 output/，运行成功后必须再调用 export_local_file。",
                planned_output_path or profile.get("requested_output_hint", ""),
                "run_plan 成功后，用 export_local_file 从当前 plan output/ 复制到用户指定路径，或直接写入最终整理内容。",
            )
        )
        uncertain_facts.append("运行成功后的 export_local_file 交付")


def _review_manual_confirm(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
) -> None:
    automation_type = str(profile.get("automation_type") or "browser")
    post_manual_actions = DESKTOP_POST_MANUAL_ACTIONS if automation_type == "desktop" else BROWSER_POST_MANUAL_ACTIONS
    manual_indexes = [index for index, record in enumerate(steps) if _action(record) == "manual_confirm"]
    if not manual_indexes:
        checks.append({"name": "manual_confirm_continuation", "passed": True, "detail": "没有 manual_confirm"})
        return
    last_manual_index = max(manual_indexes)
    has_followup = any(
        _action(record) in post_manual_actions
        for index, record in enumerate(steps)
        if index > last_manual_index
    )
    check_passed = has_followup or not (profile["needs_output"] or profile["needs_extraction"])
    checks.append(
        {
            "name": "manual_confirm_continuation",
            "passed": check_passed,
            "detail": {
                "manual_confirm_locations": [steps[index]["location"] for index in manual_indexes],
                "last_manual_confirm_location": steps[last_manual_index]["location"],
                "has_followup_data_or_output_step_after_last": has_followup,
            },
        }
    )
    if not check_passed:
        issues.append(
            _issue(
                "fail" if strict else "warn",
                "manual_confirm_without_followup",
                "plan 停在 manual_confirm 后没有继续提取、验证或写出结果，容易出现“浏览器停住但没有后续”的情况。",
                ", ".join(steps[index]["location"] for index in manual_indexes),
                "manual_confirm 后继续写 wait/extract/assert/write/capture 等步骤；需要用户介入时也要在同一个 Playwright 窗口恢复后继续跑。",
            )
        )
        missing_facts.append("人工介入后的继续执行步骤")
    else:
        facts.append("manual_confirm 后仍有继续执行步骤")


def _collect_plan_package(plan_path: Path) -> dict[str, Any]:
    package_root = plan_path.parent.resolve()
    documents: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    variables: dict[str, Any] = {}
    _collect_document(plan_path.resolve(), package_root, [], documents, steps, variables)
    input_files = _collect_plan_input_file_hashes(package_root)
    raw_text = "\n".join(json.dumps(document["document"], ensure_ascii=False, default=str) for document in documents)
    return {
        "documents": documents,
        "input_files": input_files,
        "steps": steps,
        "variables": variables,
        "raw_text": raw_text,
    }


def _package_automation_type(package: dict[str, Any]) -> str:
    documents = package.get("documents")
    if not isinstance(documents, list) or not documents:
        return ""
    first = documents[0]
    if not isinstance(first, dict):
        return ""
    document = first.get("document")
    if not isinstance(document, dict):
        return ""
    return str(document.get("automation_type") or "")


def _collect_plan_input_file_hashes(package_root: Path) -> list[dict[str, str]]:
    input_files: list[Path] = []
    local_config = package_root / "config.json"
    if local_config.is_file():
        input_files.append(local_config)
    resources_dir = package_root / "resources"
    if resources_dir.is_dir():
        input_files.extend(path for path in resources_dir.rglob("*") if path.is_file())

    result: list[dict[str, str]] = []
    for path in sorted(input_files, key=lambda item: item.relative_to(package_root).as_posix().lower()):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        result.append(
            {
                "relative_path": path.relative_to(package_root).as_posix(),
                "sha256": digest,
            }
        )
    return result


def _collect_document(
    document_path: Path,
    package_root: Path,
    stack: list[Path],
    documents: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
) -> None:
    resolved_document_path = document_path.resolve()
    if resolved_document_path in stack:
        return
    document = load_plan(resolved_document_path)
    documents.append({"path": resolved_document_path, "document": document})
    raw_variables = document.get("variables")
    if isinstance(raw_variables, dict):
        variables.update(raw_variables)
    _collect_steps(
        document.get("steps", []),
        document_path=resolved_document_path,
        package_root=package_root,
        location_prefix=f"{resolved_document_path}:steps",
        stack=[*stack, resolved_document_path],
        documents=documents,
        steps=steps,
        variables=variables,
    )


def _collect_steps(
    raw_steps: Any,
    *,
    document_path: Path,
    package_root: Path,
    location_prefix: str,
    stack: list[Path],
    documents: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
) -> None:
    if not isinstance(raw_steps, list):
        return
    for index, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            continue
        location = f"{location_prefix}[{index}]"
        steps.append({"location": location, "step": step, "document_path": str(document_path)})
        _capture_variable_assignments(step, variables)
        if "trigger" in step and isinstance(step["trigger"], dict):
            _collect_steps(
                [step["trigger"]],
                document_path=document_path,
                package_root=package_root,
                location_prefix=f"{location}.trigger",
                stack=stack,
                documents=documents,
                steps=steps,
                variables=variables,
            )
        action = str(step.get("action") or "")
        if action == "run_sub_plan":
            sub_plan_path = _resolve_sub_plan_path(package_root, step.get("path"))
            if sub_plan_path is not None and sub_plan_path.exists():
                _collect_document(sub_plan_path, package_root, stack, documents, steps, variables)
        elif action == "if":
            for branch in ("then", "else"):
                _collect_steps(
                    step.get(branch, []),
                    document_path=document_path,
                    package_root=package_root,
                    location_prefix=f"{location}.{branch}",
                    stack=stack,
                    documents=documents,
                    steps=steps,
                    variables=variables,
                )
        elif action in {"foreach", "retry"}:
            _collect_steps(
                step.get("steps", []),
                document_path=document_path,
                package_root=package_root,
                location_prefix=f"{location}.steps",
                stack=stack,
                documents=documents,
                steps=steps,
                variables=variables,
            )


def _capture_variable_assignments(step: dict[str, Any], variables: dict[str, Any]) -> None:
    if step.get("action") != "variable":
        return
    if step.get("type") == "set" and isinstance(step.get("name"), str):
        variables[str(step["name"])] = step.get("value")
    elif step.get("type") == "set_many" and isinstance(step.get("values"), dict):
        variables.update(step["values"])


def _resolve_sub_plan_path(package_root: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path or "{{" in raw_path or "}}" in raw_path:
        return None
    if is_absolute_path_text(raw_path):
        return None
    path = path_from_text(raw_path)
    if not path.parts or path.parts[0] != "sub-plans" or path.name == "plan.json":
        return None
    return (package_root / path).resolve()


def _profile_request(user_request: str, evidence_summary: str, planned_output_path: str) -> dict[str, Any]:
    request = str(user_request or "")
    urls = _dedupe(URL_RE.findall(request))
    output_hint = planned_output_path or _extract_output_hint(request)
    output_filename = _extract_output_filename(planned_output_path, request)
    account_values = _credential_values(ACCOUNT_VALUE_RE.findall(request))
    password_values = _credential_values(PASSWORD_VALUE_RE.findall(request))
    login_intent = _contains_any(request, LOGIN_TOKENS)
    is_real_site = any(_is_real_http_url(url) for url in urls)
    return {
        "urls": urls,
        "needs_browser": bool(urls)
        or _contains_any(request, ("网站", "页面", "浏览器", "后台", "菜单", "表单", "登录", "验证码")),
        "is_real_site": is_real_site,
        "mentions_login": login_intent,
        "mentions_account": bool(account_values) or (login_intent and _contains_any(request, ACCOUNT_REQUEST_TOKENS)),
        "mentions_password": bool(password_values) or (login_intent and _contains_any(request, PASSWORD_REQUEST_TOKENS)),
        "account_values": [value for value in account_values if value],
        "password_values": [value for value in password_values if value],
        "needs_output": bool(output_hint or output_filename) or _contains_any(request, OUTPUT_TOKENS),
        "needs_extraction": _contains_any(request, EXTRACTION_TOKENS),
        "one_per_line": _contains_any(request, ("一行一个", "每行一个", "一行一条", "每行一条")),
        "output_filename": output_filename,
        "requested_output_hint": output_hint,
    }


def _augment_profile_from_plan(profile: dict[str, Any], steps: list[dict[str, Any]], variables: dict[str, Any]) -> None:
    plan_urls = _extract_plan_urls(steps, variables)
    if plan_urls:
        profile["urls"] = _dedupe([*profile.get("urls", []), *plan_urls])
    if any(_is_real_http_url(url) for url in profile.get("urls", [])):
        profile["is_real_site"] = True
        profile["needs_browser"] = True
    if any(_action(record) in {"open_browser", "navigate", "element", "extract"} for record in steps):
        profile["needs_browser"] = bool(profile.get("needs_browser")) or any(
            _is_real_http_url(url) for url in profile.get("urls", [])
        )


def _apply_execution_line_profile(profile: dict[str, Any]) -> None:
    if str(profile.get("automation_type") or "") != "desktop":
        return
    profile["needs_browser"] = False
    profile["is_real_site"] = False


def _extract_plan_urls(steps: list[dict[str, Any]], variables: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for record in steps:
        step = record["step"]
        if _action(record) != "navigate":
            continue
        raw_url = step.get("url")
        resolved_text = _resolved_step_text(raw_url, variables)
        urls.extend(URL_RE.findall(resolved_text))
    for value in variables.values():
        if isinstance(value, str):
            urls.extend(URL_RE.findall(value))
    return _dedupe(urls)


def _has_real_site_automation_evidence(
    evidence_summary: str,
    *,
    urls: list[str],
    evidence_context: dict[str, Any],
) -> bool:
    text = str(evidence_summary or "").strip()
    if not text and not evidence_context:
        return False
    if _contains_any(text, NEGATIVE_EVIDENCE_TOKENS):
        return False
    text_url_ok = _evidence_text_matches_urls(text, urls)
    context_url_ok = _evidence_context_matches_urls(evidence_context, urls)
    has_url_binding = text_url_ok or context_url_ok or not urls
    has_concrete_text_marker = _contains_any(
        text,
        (
            "final_url",
            "resolved_url",
            "requested_url",
            "title=",
            "url=",
            "forms",
            "inputs",
            "buttons",
            "output_dir",
            "report.md",
            "state.json",
            "passed",
            "failed",
        ),
    )
    if _contains_any(text, AUTOMATION_EVIDENCE_TOKENS) and has_url_binding and (has_concrete_text_marker or context_url_ok):
        return True
    if (
        _contains_any(text, RUN_EVIDENCE_TOKENS)
        and _contains_any(text, RUN_RESULT_EVIDENCE_TOKENS)
        and has_url_binding
    ):
        return True
    return (
        _contains_any(text, MANUAL_CONFIRM_EVIDENCE_TOKENS)
        and _contains_any(text, MANUAL_CONFIRM_CONTEXT_TOKENS)
        and has_url_binding
    )


def _has_desktop_inspection_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = str(evidence_summary or "").strip()
    if _contains_any(text, NEGATIVE_EVIDENCE_TOKENS):
        return False
    context = evidence_context if isinstance(evidence_context, dict) else {}
    context_markers = [
        key
        for key, value in context.items()
        if str(key).startswith("latest_desktop_inspection_") and value not in (None, "", [], {})
    ]
    if context_markers:
        return True
    if _contains_any(
        text,
        (
            "inspect_desktop",
            "capability_matrix",
            "desktop inspection",
            "desktop_inspection",
            "window_count",
            "focused_window",
            "include_windows",
            "include_elements",
            "selector_hints",
            "控件树",
            "窗口列表",
            "桌面探测",
            "桌面截图",
            "能力矩阵",
        ),
    ):
        return True
    return False


def _evidence_text_matches_urls(text: str, urls: list[str]) -> bool:
    if not urls:
        return bool(URL_RE.search(text))
    evidence_urls = URL_RE.findall(text)
    if not evidence_urls:
        return False
    return any(_same_url_host(evidence_url, request_url) for evidence_url in evidence_urls for request_url in urls)


def _evidence_context_matches_urls(context: dict[str, Any], urls: list[str]) -> bool:
    if not context:
        return False
    candidates: list[str] = []
    for key, value in context.items():
        if isinstance(value, str) and ("url" in key.lower() or value.startswith(("http://", "https://"))):
            candidates.extend(URL_RE.findall(value))
    if not candidates:
        return False
    if not urls:
        return True
    return any(_same_url_host(candidate, request_url) for candidate in candidates for request_url in urls)


def _same_url_host(left: str, right: str) -> bool:
    left_host = urlparse(left).netloc.lower()
    right_host = urlparse(right).netloc.lower()
    return bool(left_host and right_host and left_host == right_host)


def _credential_values(raw_values: Any) -> list[str]:
    return _dedupe(
        value
        for value in (_clean_labeled_value(match) for match in raw_values)
        if _looks_like_supplied_credential_value(value)
    )


def _looks_like_supplied_credential_value(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower().strip("\"'“”‘’")
    if lowered in CREDENTIAL_VALUE_STOPWORDS:
        return False
    if len(lowered) <= 1:
        return False
    return True


def _extract_output_hint(request: str) -> str:
    if _has_negated_external_output_hint(request):
        return ""
    absolute = re.search(r"(?<![\w.-])(?:~[\\/]|[A-Za-z]:[\\/]|\\\\|/)[^\s，。；;,]+", request)
    if absolute:
        return absolute.group(0)
    if re.search(r"\bDownloads?\b", request, flags=re.IGNORECASE) or re.search(
        r"(?:写到|写入|保存到|导出到|输出到|放到|复制到).{0,12}(?:桌面|下载)",
        request,
    ):
        return "Downloads/Desktop"
    return ""


def _has_negated_external_output_hint(request: str) -> bool:
    text = str(request or "")
    return bool(
        re.search(
            r"(?:不要|不用|无需|别|不需要|禁止).{0,12}(?:导出|写到|写入|保存|输出|复制).{0,12}(?:Downloads?|Desktop|桌面|下载)",
            text,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"(?:不要|不用|无需|别|不需要|禁止).{0,8}(?:Downloads?|Desktop|桌面|下载)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _extract_output_filename(planned_output_path: str, request: str) -> str:
    if planned_output_path:
        name = path_from_text(planned_output_path).name
        if "." in name:
            return name
    labeled_candidates = [_normalize_output_filename_candidate(candidate) for candidate in LABELED_FILENAME_RE.findall(request)]
    labeled_candidates = [candidate for candidate in labeled_candidates if candidate]
    if labeled_candidates:
        return labeled_candidates[-1]
    candidates = [candidate.strip(" ：:，。；;,") for candidate in FILENAME_RE.findall(request)]
    candidates = [_normalize_output_filename_candidate(candidate) for candidate in candidates]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return ""
    return candidates[-1]


def _normalize_output_filename_candidate(candidate: str) -> str:
    text = str(candidate or "").strip(" ：:，。；;,")
    if not text:
        return ""
    text = re.sub(
        r"^.*(?:文件名称|文件名|filename|file name)\s*(?:[:：=是为]|就是|叫|命名为|保存为)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" ：:，。；;,")
    if not text:
        return ""
    filename_match = re.search(
        r"([^\s，。；;,/\\]+?\.(?:txt|csv|json|xlsx|md|html|png|jpg|jpeg|webp|pdf))$",
        text,
        flags=re.IGNORECASE,
    )
    if filename_match:
        text = filename_match.group(1)
    return path_from_text(text).name


def _is_account_fill(step: dict[str, Any], variables: dict[str, Any], account_values: list[str]) -> bool:
    locator_text = _locator_text(step)
    value_text = _resolved_step_text(step.get("value"), variables)
    if _contains_any(locator_text, ACCOUNT_FIELD_TOKENS):
        return bool(value_text)
    return bool(account_values and _value_matches_any(value_text, account_values, variables))


def _is_password_fill(step: dict[str, Any], variables: dict[str, Any], password_values: list[str]) -> bool:
    locator_text = _locator_text(step)
    value_text = _resolved_step_text(step.get("value"), variables)
    if _contains_any(locator_text, PASSWORD_FIELD_TOKENS):
        return bool(value_text)
    if _contains_any(value_text, PASSWORD_FIELD_TOKENS) and "{{" in str(step.get("value", "")):
        return True
    return bool(password_values and _value_matches_any(value_text, password_values, variables))


def _is_credential_input_step(record: dict[str, Any], automation_type: str) -> bool:
    step_type = str(record["step"].get("type", "")).lower()
    if automation_type == "desktop":
        action = _action(record)
        return (action == "desktop_input" and step_type == "type_text") or (
            action == "desktop_element" and step_type == "set_text"
        )
    return _action(record) == "element" and step_type in {"fill", "type"}


def _is_login_progression_step(record: dict[str, Any], automation_type: str = "browser") -> bool:
    action = _action(record)
    step = record["step"]
    step_type = str(step.get("type", "")).lower()
    if action == "manual_confirm":
        return True
    if automation_type == "desktop":
        if action == "desktop_input" and step_type == "hotkey":
            return _contains_any(_json_text(step.get("keys")), ("enter", "return"))
        if action == "desktop_input" and step_type in {"click", "double_click", "right_click"}:
            return True
        if action == "desktop_element" and step_type in {
            "click",
            "invoke",
            "select_cell",
            "expand_tree",
            "collapse_tree",
            "select_tree",
            "invoke_menu",
            "scroll_element",
        }:
            return True
        if action == "desktop_window":
            return step_type in {"list", "focus"}
        return action in {"desktop_wait", "desktop_assert", "desktop_capture"}
    if action == "element":
        if step_type in {"click", "dblclick", "tap"}:
            return True
        if step_type == "press":
            return "enter" in str(step.get("key", "")).lower()
    if action == "keyboard" and step_type == "press":
        return "enter" in str(step.get("key", "")).lower()
    if action == "script" and step_type == "evaluate":
        script_text = str(step.get("js", "")).lower()
        return "submit" in script_text or ".click(" in script_text
    return action in {"wait_for_network", "wait_for_popup"}


def _output_fix_hint(automation_type: str) -> str:
    if automation_type == "desktop":
        return "补充 desktop_window list、desktop_element list/dump/find/get_text/get_state/get_table/get_tree、desktop_assert element、desktop_capture screenshot/snapshot、desktop_vision locate_image 或 write，把运行证据写入当前 plan output/。"
    return "补充 extract/script/ai 等数据获取步骤后，用 write.type=text/json/csv 写入当前 plan output/。"


def _is_desktop_evidence_step(record: dict[str, Any]) -> bool:
    action = _action(record)
    if action == "desktop_window":
        return str(record["step"].get("type", "")).lower() == "list"
    if action == "desktop_element":
        return str(record["step"].get("type", "")).lower() in {
            "list",
            "dump",
            "find",
            "wait",
            "get_text",
            "get_state",
            "get_table",
            "get_tree",
        }
    return action in DESKTOP_DATA_COLLECTION_ACTIONS


def _is_desktop_output_step(record: dict[str, Any]) -> bool:
    action = _action(record)
    if action == "desktop_window":
        step = record["step"]
        return str(step.get("type", "")).lower() == "list" and step.get("path") is not None
    if action == "desktop_element":
        step = record["step"]
        return str(step.get("type", "")).lower() in {
            "list",
            "dump",
            "find",
            "wait",
            "get_text",
            "get_state",
            "get_table",
            "click",
            "set_text",
            "select",
            "invoke",
            "select_cell",
            "get_tree",
            "expand_tree",
            "collapse_tree",
            "select_tree",
            "invoke_menu",
            "scroll_element",
        } and step.get("path") is not None
    return action in FINAL_DESKTOP_OUTPUT_ACTIONS


def _data_extraction_issue_message(automation_type: str) -> str:
    if automation_type == "desktop":
        return "用户要求读取/提取桌面状态，但 plan 没有 desktop_window/desktop_element 读取类、desktop_assert element、desktop_capture 或 desktop_vision 等桌面证据步骤。"
    return "用户要求读取/提取页面数据，但 plan 没有 extract/script/ai/storage/download 等数据获取步骤。"


def _data_extraction_fix_hint(automation_type: str) -> str:
    if automation_type == "desktop":
        return "先用 desktop_window list、desktop_element list/dump/get_text/get_state/get_table/get_tree、desktop_assert element、desktop_capture screenshot/snapshot、desktop_vision locate_image 或 desktop_wait 获取桌面状态，再按需写出文件。"
    return "先用 extract.table、extract.all_texts、extract.text 或 script.evaluate 获取目标数据，再写出文件。"


def _value_matches_any(value_text: str, expected_values: list[str], variables: dict[str, Any]) -> bool:
    if any(expected and expected in value_text for expected in expected_values):
        return True
    for variable_name in TEMPLATE_RE.findall(value_text):
        variable_value = variables.get(variable_name)
        variable_text = _json_text(variable_value)
        if any(expected and expected in variable_text for expected in expected_values):
            return True
    return False


def _url_covered(url: str, navigate_steps: list[dict[str, Any]], variables: dict[str, Any]) -> bool:
    expected = urlparse(url)
    if not expected.netloc:
        return True
    for record in navigate_steps:
        actual_text = _resolved_step_text(record["step"].get("url"), variables)
        if url in actual_text:
            return True
        actual_url_match = URL_RE.search(actual_text)
        if actual_url_match and urlparse(actual_url_match.group(0)).netloc == expected.netloc:
            return True
    return False


def _requires_external_export(planned_output_path: str, profile: dict[str, Any]) -> bool:
    if planned_output_path and is_absolute_path_text(planned_output_path):
        return True
    return _contains_any(profile.get("requested_output_hint", ""), ("Downloads", "Desktop", "桌面", "下载"))


def _quality_result(
    *,
    plan_path: Path,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    covered_facts: list[str],
    missing_facts: list[str],
    uncertain_facts: list[str],
    validation_errors: list[dict[str, str]],
    planned_output_path: str,
) -> dict[str, Any]:
    fail_count = sum(1 for issue in issues if issue.get("severity") == "fail")
    warn_count = sum(1 for issue in issues if issue.get("severity") == "warn")
    passed = fail_count == 0
    severity = "fail" if fail_count else ("warn" if warn_count else "pass")
    next_action = _next_action(severity, issues, planned_output_path)
    return {
        "ok": passed,
        "passed": passed,
        "severity": severity,
        "plan_path": str(plan_path),
        "plan_signature": compute_plan_signature(plan_path),
        "checks": checks,
        "issues": issues,
        "issue_count": len(issues),
        "fail_count": fail_count,
        "warn_count": warn_count,
        "covered_facts": _dedupe(covered_facts),
        "missing_facts": _dedupe(missing_facts),
        "uncertain_facts": _dedupe(uncertain_facts),
        "validation_errors": validation_errors,
        "next_action": next_action,
    }


def _next_action(severity: str, issues: list[dict[str, str]], planned_output_path: str) -> str:
    if severity == "fail":
        if any(issue.get("code") in {"missing_real_site_evidence", "missing_desktop_inspection_evidence"} for issue in issues):
            return "collect_evidence"
        return "fix_plan"
    if planned_output_path and is_absolute_path_text(planned_output_path):
        return "run_plan_then_export_local_file"
    if any(issue.get("code") == "requires_export_local_file_after_run" for issue in issues):
        return "run_plan_then_export_local_file"
    return "run_plan"


def _issue(severity: str, code: str, message: str, evidence: str, fix: str) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "evidence": redact_secret_text(evidence),
        "fix": fix,
    }


def _action(record: dict[str, Any]) -> str:
    return str(record.get("step", {}).get("action") or "")


def _locator_text(step: dict[str, Any]) -> str:
    fields = (
        "selector",
        "role",
        "name",
        "text",
        "label",
        "placeholder",
        "alt_text",
        "title",
        "test_id",
        "frame_selector",
        "frame_name",
        "frame_url",
        "frame_url_contains",
    )
    return " ".join(str(step.get(field, "")) for field in fields if step.get(field) is not None)


def _resolved_step_text(value: Any, variables: dict[str, Any]) -> str:
    text = _json_text(value)
    for variable_name in TEMPLATE_RE.findall(text):
        if variable_name in variables:
            text = f"{text} {_json_text(variables[variable_name])}"
    return text


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _path_basename(path_text: str) -> str:
    if not path_text:
        return ""
    return path_from_text(path_text).name


def _clean_labeled_value(value: str) -> str:
    return str(value or "").strip().strip(" \t\r\n，。；;,.：:")


def _values_evidence(values: list[str]) -> str:
    if not values:
        return ""
    return ", ".join(values[:3])


def _contains_any(text: Any, tokens: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(token.lower() in lowered for token in tokens)


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _is_real_http_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme in {"http", "https"} and host not in {"localhost", "127.0.0.1", "::1"}


def compute_plan_signature(plan_path: str | Path) -> str:
    resolved_plan_path = resolve_plan_path(plan_path)
    package = _collect_plan_package(resolved_plan_path)
    payload = {
        "documents": [
            {
                "relative_path": document["path"].relative_to(resolved_plan_path.parent).as_posix(),
                "document": document["document"],
            }
            for document in package["documents"]
        ],
        "input_files": package["input_files"],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return digest
