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
FILE_DATA_TOKENS = ("excel", ".xlsx", "csv", ".csv", "表格", "人员名单", "财务表", "报表", "流水", "台账", "清单")
FILE_DATA_CONCRETE_RULE_TOKENS = (
    "筛选",
    "过滤",
    "只保留",
    "剔除",
    "去掉",
    "删除",
    "去重",
    "排序",
    "汇总",
    "统计",
    "分组",
    "聚合",
    "透视",
    "匹配",
    "关联",
    "连接",
    "lookup",
    "vlookup",
    "合并列",
    "拆分",
    "替换",
    "日期",
    "公式",
    "标题区",
    "汇总区",
    "指定区域",
    "保留样式",
    "sheet",
    "工作表",
    "列",
    "字段",
)
FILE_DATA_TRANSFORM_ACTION_TYPES = {
    "add_column",
    "date_parse",
    "dedupe",
    "fill_empty",
    "filter",
    "group",
    "join",
    "lookup",
    "merge_columns",
    "pivot",
    "replace",
    "sort",
    "split_column",
    "type_convert",
}
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
BROWSER_DATA_COLLECTION_ACTIONS = {"extract", "script", "ai", "storage", "wait_for_download", "read", "table"}
FINAL_DESKTOP_OUTPUT_ACTIONS = {"write", "desktop_capture", "desktop_assert", "desktop_vision", "ai", "command"}
DESKTOP_DATA_COLLECTION_ACTIONS = {"desktop_capture", "desktop_wait", "desktop_assert", "desktop_vision", "ai", "command", "read", "table"}
DESKTOP_COORDINATE_INPUT_TYPES = {"click", "double_click", "right_click", "scroll", "drag"}
DESKTOP_COORDINATE_TARGETS = {
    "bounds_center",
    "candidate",
    "current_window_center",
    "focused_window_center",
    "current_window_offset",
    "focused_window_offset",
}
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
DESKTOP_MESSAGE_SEND_TOKENS = (
    "微信",
    "wechat",
    "qq",
    "聊天",
    "消息",
    "发送",
    "发给",
    "群",
    "联系人",
    "好友",
    "祝福",
    "私信",
)
DESKTOP_MESSAGE_RECIPIENT_TOKENS = (
    "recipient",
    "contact",
    "group",
    "chat",
    "to=",
    "to:",
    "收件人",
    "联系人",
    "群",
    "好友",
    "白名单",
    "发送给",
    "发给",
)
DESKTOP_MESSAGE_CONTENT_TOKENS = (
    "message",
    "content",
    "body",
    "text",
    "消息",
    "内容",
    "正文",
    "祝福",
)
DESKTOP_MESSAGE_SEND_ACTION_TOKENS = (
    "send",
    "submit",
    "发送",
    "确定发送",
    "发送按钮",
)
DESKTOP_GAME_TASK_TOKENS = (
    "游戏",
    "game",
    "签到",
    "日常",
    "副本",
    "刷图",
    "奖励",
    "战斗",
    "任务",
    "领取",
    "关卡",
)
DESKTOP_LONG_RUNNING_TOKENS = (
    "定时",
    "每天",
    "每日",
    "每隔",
    "循环",
    "重复",
    "一直",
    "长期",
    "自动刷",
    "刷图",
    "日常",
)
DESKTOP_SCENARIO_NEGATIVE_TOKENS = (
    "没有确认",
    "未确认",
    "缺少确认",
    "没有草稿",
    "未验证",
    "缺少验证",
    "没有游戏状态",
    "没有状态",
    "没有截图",
    "没有完成断言",
    "缺少状态",
    "缺少截图",
    "缺少完成断言",
    "无状态",
    "无截图",
    "无完成断言",
    "没有停止边界",
    "缺少停止边界",
    "无停止边界",
)


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
    _review_desktop_scenario_flow(
        profile,
        step_records,
        variables,
        evidence_summary,
        evidence_context or {},
        checks,
        issues,
        facts,
        missing_facts,
    )
    _review_credentials(profile, step_records, variables, raw_plan_text, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_login_progression(profile, step_records, variables, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_output(profile, step_records, variables, planned_output_path, strict, checks, issues, facts, missing_facts, uncertain_facts)
    _review_file_data_transform_intent(profile, step_records, strict, checks, issues, facts, missing_facts)
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
                "补充 desktop_window list、desktop_element list/dump/find/get_text/get_state/get_table/get_tree、desktop_capture observe/screenshot/snapshot、desktop_wait window 或 desktop_assert。",
            )
        )
    else:
        facts.append("已覆盖桌面窗口、控件或截图证据")

    coordinate_actions = _desktop_coordinate_action_records(steps)
    coordinate_locations = [record["location"] for _index, record in coordinate_actions]
    coordinate_evidence_ok = not coordinate_actions or _has_desktop_coordinate_evidence(evidence_summary, evidence_context)
    result_evidence_ok = not coordinate_actions or all(
        _has_later_desktop_result_evidence(steps, index) for index, _record in coordinate_actions
    )
    checks.append(
        {
            "name": "desktop_coordinate_evidence",
            "passed": coordinate_evidence_ok,
            "detail": {
                "coordinate_action_locations": coordinate_locations,
                "evidence_summary_present": bool(str(evidence_summary or "").strip()),
            },
        }
    )
    if not coordinate_evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_coordinate_evidence",
                "desktop plan 使用鼠标坐标类操作，但缺少 target_candidates、coordinate_profile、coordinate_diagnostics、窗口/控件 bounds 或人工确认等坐标证据。",
                ", ".join(coordinate_locations[:8]),
                "先用 inspect_desktop、desktop_capture observe、desktop_element find/dump、desktop_vision 或 manual_confirm 获取定位证据；裸 x/y 必须说明坐标来源和坐标空间。",
            )
        )
        missing_facts.append("桌面坐标/定位候选证据")
    elif coordinate_actions:
        facts.append("已有桌面坐标/定位候选证据")

    raw_coordinate_locations = [record["location"] for _index, record in coordinate_actions if _is_raw_desktop_coordinate_step(record)]
    if raw_coordinate_locations and not coordinate_evidence_ok:
        issues.append(
            _issue(
                "fail",
                "unsafe_raw_desktop_coordinates",
                "desktop_input 直接使用 x/y 或 drag 绝对坐标，但没有坐标空间和截图/控件 bounds 证据。",
                ", ".join(raw_coordinate_locations[:8]),
                "优先使用 semantic locator、target=element_center 或 target=bounds_center；必须用 x/y 时，在 evidence_summary 中写明 target_candidates/coordinate_profile/截图来源。",
            )
        )
    if coordinate_actions and _has_low_confidence_coordinate_evidence(evidence_summary, evidence_context) and not _has_manual_confirm_after_coordinate(steps, coordinate_actions):
        issues.append(
            _issue(
                "fail",
                "low_confidence_coordinate_without_handoff",
                "桌面定位候选低置信或建议人工确认，但 plan 直接执行坐标操作。",
                str(evidence_summary or "").strip()[:500],
                "低置信 visual_bounds、visual_evidence 或 manual_confirm_recommended=true 时，先 manual_confirm 或补充 desktop_vision/desktop_element 证据后再操作。",
            )
        )
    if coordinate_actions and _has_non_clickable_coordinate_evidence(evidence_summary, evidence_context):
        issues.append(
            _issue(
                "fail",
                "non_clickable_candidate_used_as_coordinate",
                "证据显示候选来自离线图片或 screen_clickable=false，但 plan 仍执行坐标类输入。",
                str(evidence_summary or "").strip()[:500],
                "source_path、visual_evidence、not_screen_clickable 或 screen_clickable=false 只能作为证据；请重新 observe/vision 当前屏幕，或加入 manual_confirm。",
            )
        )
    candidate_actions = [record for _index, record in coordinate_actions if str(record["step"].get("target", "")) == "candidate"]
    candidate_evidence_ok = not candidate_actions or _has_candidate_target_evidence(evidence_summary, evidence_context)
    checks.append(
        {
            "name": "desktop_candidate_target_evidence",
            "passed": candidate_evidence_ok,
            "detail": {
                "candidate_action_locations": [record["location"] for record in candidate_actions],
                "evidence_summary_present": bool(str(evidence_summary or "").strip()),
            },
        }
    )
    if not candidate_evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_candidate_target_evidence",
                "desktop_input target=candidate 缺少 candidate_id、strategy、confidence、screen_clickable 或 target_candidates 证据。",
                ", ".join(record["location"] for record in candidate_actions[:8]),
                "使用 target=candidate 前，evidence_summary 必须说明 candidate_id、strategy、confidence、screen_clickable 和坐标/语义来源；低置信或不可点击候选不能直接执行。",
            )
        )
    legacy_coordinate_actions = [
        record
        for _index, record in coordinate_actions
        if str(record["step"].get("target", "")) not in {"candidate", "element_center"}
    ]
    if legacy_coordinate_actions and _has_high_confidence_semantic_candidate(evidence_summary, evidence_context):
        issues.append(
            _issue(
                "warn",
                "coordinate_over_semantic_candidate",
                "证据里存在高置信 semantic_locator，但 plan 使用坐标类输入；这通常比 desktop_element 更脆弱。",
                ", ".join(record["location"] for record in legacy_coordinate_actions[:8]),
                "优先使用 desktop_element、desktop_input target=element_center 或 target=candidate；只有需要真实鼠标事件时再用 bounds_center/绝对坐标，并在 evidence_summary 说明原因。",
            )
        )
    checks.append(
        {
            "name": "desktop_coordinate_result_evidence",
            "passed": result_evidence_ok,
            "detail": {
                "coordinate_action_locations": coordinate_locations,
            },
        }
    )
    if not result_evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_coordinate_result_evidence",
                "坐标点击、滚轮或拖拽后缺少截图、等待、断言或控件状态读取来证明结果。",
                ", ".join(coordinate_locations[:8]),
                "坐标操作后补充 desktop_capture screenshot/observe、desktop_wait、desktop_assert 或 desktop_element get_state/get_text。",
            )
        )


def _review_desktop_scenario_flow(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
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
                "name": "desktop_scenario_quality",
                "passed": True,
                "detail": {"automation_type": automation_type, "not_applicable": True},
            }
        )
        return

    chat_needed = _needs_desktop_message_send(profile, steps, variables, evidence_summary, evidence_context)
    game_needed = _needs_desktop_game_task(profile, steps, variables, evidence_summary, evidence_context)
    _review_desktop_message_scenario(
        chat_needed,
        steps,
        variables,
        evidence_summary,
        evidence_context,
        checks,
        issues,
        facts,
        missing_facts,
    )
    _review_desktop_game_scenario(
        game_needed,
        steps,
        variables,
        evidence_summary,
        evidence_context,
        checks,
        issues,
        facts,
        missing_facts,
    )


def _review_desktop_message_scenario(
    needed: bool,
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
) -> None:
    send_actions = _desktop_message_send_action_records(steps, variables)
    send_indexes = [index for index, _record in send_actions]
    manual_confirm_before_send = _has_manual_confirm_before_first_index(steps, send_indexes)
    recipient_ok = not needed or manual_confirm_before_send or _has_desktop_message_recipient_confirmation(
        steps,
        variables,
        evidence_summary,
        evidence_context,
        send_indexes,
    )
    message_ok = not needed or manual_confirm_before_send or _has_desktop_message_content_confirmation(
        steps,
        variables,
        evidence_summary,
        evidence_context,
        send_indexes,
    )
    pre_send_ok = not needed or manual_confirm_before_send or _has_desktop_pre_send_evidence(steps, send_indexes)
    send_action_ok = not needed or bool(send_actions) or any(_action(record) == "manual_confirm" for record in steps)
    checks.append(
        {
            "name": "desktop_message_send_scenario",
            "passed": send_action_ok and recipient_ok and message_ok and pre_send_ok,
            "detail": {
                "needed": needed,
                "send_action_locations": [record["location"] for _index, record in send_actions],
                "manual_confirm_before_send": manual_confirm_before_send,
                "recipient_confirmation": recipient_ok,
                "message_confirmation": message_ok,
                "pre_send_evidence": pre_send_ok,
            },
        }
    )
    if not needed:
        return
    if not send_action_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_message_send_action",
                "用户需求是桌面聊天或消息发送，但 plan 没有可识别的发送步骤或人工确认交接。",
                "未找到 Send/发送按钮 click/invoke 或 Enter 发送步骤。",
                "补充明确的发送按钮 desktop_element click/invoke，或在信息不确定时使用 manual_confirm。",
            )
        )
        missing_facts.append("桌面消息发送步骤")
    if not recipient_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_message_recipient_verification",
                "桌面消息发送前缺少收件人、联系人或群的确认，容易发错对象。",
                ", ".join(record["location"] for _index, record in send_actions[:8]) or "未找到发送前目标确认。",
                "发送前用 desktop_assert element、desktop_element get_text/get_state、desktop_capture observe/screenshot 或 manual_confirm 确认当前会话、联系人或群名。",
            )
        )
        missing_facts.append("消息收件人/群确认")
    if not message_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_message_content_verification",
                "桌面消息发送前缺少消息内容或草稿框确认，容易发送空消息、旧草稿或错误文本。",
                ", ".join(record["location"] for _index, record in send_actions[:8]) or "未找到发送前消息内容确认。",
                "写入消息后读取或断言草稿框内容，或用截图/observe/manual_confirm 确认发送内容。",
            )
        )
        missing_facts.append("消息内容确认")
    if not pre_send_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_message_pre_send_evidence",
                "桌面消息发送动作前没有运行证据步骤，不能证明发送前状态正确。",
                ", ".join(record["location"] for _index, record in send_actions[:8]) or "未找到发送前证据。",
                "把收件人和消息内容验证放在发送动作之前；可用 desktop_assert element、desktop_capture observe/screenshot、desktop_element get_text/get_state 或 manual_confirm。",
            )
        )
        missing_facts.append("消息发送前证据")
    if send_action_ok and recipient_ok and message_ok and pre_send_ok:
        facts.append("已覆盖桌面消息发送前目标和内容确认")


def _review_desktop_game_scenario(
    needed: bool,
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
) -> None:
    state_evidence_locations = [
        record["location"]
        for record in steps
        if _is_desktop_game_state_evidence_step(record)
    ]
    stop_boundary_ok = not needed or _has_desktop_game_stop_boundary(steps, evidence_summary, evidence_context)
    state_evidence_ok = not needed or bool(state_evidence_locations) or _has_desktop_game_state_evidence(
        evidence_summary,
        evidence_context,
    )
    infinite_loop_locations = _desktop_unbounded_loop_locations(steps)
    checks.append(
        {
            "name": "desktop_game_task_scenario",
            "passed": state_evidence_ok and stop_boundary_ok and not infinite_loop_locations,
            "detail": {
                "needed": needed,
                "state_evidence_locations": state_evidence_locations,
                "stop_boundary_ok": stop_boundary_ok,
                "unbounded_loop_locations": infinite_loop_locations,
            },
        }
    )
    if not needed:
        return
    if not state_evidence_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_game_progress_evidence",
                "桌面游戏、日常或副本 plan 缺少可证明当前阶段和结果的视觉/状态证据。",
                "未找到 desktop_capture、desktop_vision、desktop_assert 或状态读取类 desktop_element 步骤。",
                "在进入阶段、操作后和完成时加入 desktop_capture observe/screenshot、desktop_vision、desktop_element get_text/get_state 或 desktop_assert。",
            )
        )
        missing_facts.append("桌面游戏进度/状态证据")
    if not stop_boundary_ok:
        issues.append(
            _issue(
                "fail",
                "missing_desktop_scenario_stop_budget",
                "桌面游戏、日常、签到或副本 plan 缺少次数、时长、完成断言或其他停止边界。",
                "未找到 max_runs、duration_seconds、有限 foreach/retry、完成断言或 evidence_summary 中的 bounded_runtime/stop_condition。",
                "循环必须设置 max_runs/duration_seconds 或明确完成断言；一次性流程也要用状态断言证明完成，不能依赖无限点击。",
            )
        )
        missing_facts.append("桌面场景停止边界")
    if infinite_loop_locations:
        issues.append(
            _issue(
                "fail",
                "unsafe_desktop_game_infinite_loop",
                "桌面游戏或副本场景使用了无边界无限 trigger，容易在错误窗口或错误状态里无限循环。",
                ", ".join(infinite_loop_locations[:8]),
                "去掉 allow_infinite=true，改为 max_runs、duration_seconds、完成断言或人工确认后的有限执行。",
            )
        )
        missing_facts.append("禁止无边界无限循环")
    if state_evidence_ok and stop_boundary_ok and not infinite_loop_locations:
        facts.append("已覆盖桌面游戏/日常场景状态证据和停止边界")


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


def _review_file_data_transform_intent(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    strict: bool,
    checks: list[dict[str, Any]],
    issues: list[dict[str, str]],
    facts: list[str],
    missing_facts: list[str],
) -> None:
    if not profile.get("file_data_intent"):
        return
    transform_records = [record for record in steps if _is_file_data_transform_record(record)]
    has_explicit_rule = bool(profile.get("file_data_transform_explicit"))
    passed = has_explicit_rule or not transform_records
    checks.append(
        {
            "name": "file_data_transform_intent",
            "passed": passed,
            "detail": {
                "file_data_transform_explicit": has_explicit_rule,
                "transform_step_locations": [record["location"] for record in transform_records],
            },
        }
    )
    if passed:
        if has_explicit_rule:
            facts.append("已覆盖明确表格处理规则")
        return
    issues.append(
        _issue(
            "fail" if strict else "warn",
            "ambiguous_file_data_transformation",
            "用户只给了模糊表格处理目标，但 plan 已写入具体筛选、汇总、连接、公式或清洗转换。",
            ", ".join(record["location"] for record in transform_records[:5]),
            "先读取 workbook 预览和 meta，或向用户确认筛选、分组、汇总、连接、公式列、输出模板/区域等规则，再生成最终 plan。",
        )
    )
    missing_facts.append("Excel/CSV 具体转换规则")


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
    request_context = f"{request}\n{planned_output_path or ''}"
    urls = _dedupe(URL_RE.findall(request))
    output_hint = planned_output_path or _extract_output_hint(request)
    output_filename = _extract_output_filename(planned_output_path, request)
    account_values = _credential_values(ACCOUNT_VALUE_RE.findall(request))
    password_values = _credential_values(PASSWORD_VALUE_RE.findall(request))
    login_intent = _contains_any(request, LOGIN_TOKENS)
    file_data_intent = _contains_any(request_context, FILE_DATA_TOKENS)
    file_data_transform_explicit = _has_explicit_file_data_transform_request(
        request_context
    ) or _has_explicit_file_data_transform_request(evidence_summary)
    is_real_site = any(_is_real_http_url(url) for url in urls)
    message_target_hint = _contains_any(
        request_context,
        ("微信", "wechat", "qq", "聊天", "群", "联系人", "好友", "私信", "收件人", "消息"),
    )
    message_send_hint = _contains_any(
        request_context,
        ("发送消息", "发消息", "send message", "发送", "发给", "群发", "祝福", "定时给"),
    )
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
        "needs_extraction": file_data_intent or _contains_any(request, EXTRACTION_TOKENS),
        "file_data_intent": file_data_intent,
        "file_data_transform_explicit": file_data_transform_explicit,
        "one_per_line": _contains_any(request, ("一行一个", "每行一个", "一行一条", "每行一条")),
        "output_filename": output_filename,
        "requested_output_hint": output_hint,
        "request_text": request,
        "needs_desktop_message_send": message_target_hint and message_send_hint,
        "needs_desktop_game_task": _contains_any(request_context, DESKTOP_GAME_TASK_TOKENS),
        "needs_long_running_loop": _contains_any(request_context, DESKTOP_LONG_RUNNING_TOKENS),
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
    if str(profile.get("automation_type") or "") == "desktop":
        plan_text = _desktop_records_text(steps, variables)
        if not profile.get("needs_desktop_message_send"):
            profile["needs_desktop_message_send"] = (
                _contains_any(plan_text, ("微信", "wechat", "qq", "聊天", "群", "联系人", "好友", "收件人"))
                and bool(_desktop_message_send_action_records(steps, variables))
            )
        if not profile.get("needs_desktop_game_task"):
            profile["needs_desktop_game_task"] = _contains_any(plan_text, DESKTOP_GAME_TASK_TOKENS)


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


def _desktop_coordinate_action_records(steps: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for index, record in enumerate(steps):
        if _action(record) != "desktop_input":
            continue
        step = record["step"]
        input_type = str(step.get("type", "")).lower()
        if input_type not in DESKTOP_COORDINATE_INPUT_TYPES:
            continue
        if _is_raw_desktop_coordinate_step(record) or str(step.get("target", "")) in DESKTOP_COORDINATE_TARGETS:
            records.append((index, record))
    return records


def _is_raw_desktop_coordinate_step(record: dict[str, Any]) -> bool:
    step = record["step"]
    if "x" in step and "y" in step:
        return True
    return all(field in step for field in ("start_x", "start_y", "end_x", "end_y"))


def _has_desktop_coordinate_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context)
    if _contains_any(text, NEGATIVE_EVIDENCE_TOKENS):
        return False
    return _contains_any(
        text,
        (
            "target_candidates",
            "best_candidate",
            "candidate_id",
            "target=candidate",
            "semantic_locator",
            "visual_bounds",
            "screen_clickable",
            "coordinate_profile",
            "coordinate_space",
            "coordinate_diagnostics",
            "source_bounds",
            "bounds",
            "selector_hints",
            "manual_confirm",
            "人工确认",
            "控件 bounds",
            "窗口 bounds",
            "坐标空间",
            "定位候选",
        ),
    )


def _has_low_confidence_coordinate_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context).lower()
    return any(
        marker in text
        for marker in (
            "confidence=low",
            '"confidence": "low"',
            "'confidence': 'low'",
            "manual_confirm_recommended=true",
            '"manual_confirm_recommended": true',
            "visual_evidence",
        )
    )


def _has_non_clickable_coordinate_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context).lower()
    return any(
        marker in text
        for marker in (
            "screen_clickable=false",
            '"screen_clickable": false',
            "'screen_clickable': false",
            "not_screen_clickable",
            "source_path",
            "offline_image",
            "离线图片",
            "不可点击",
        )
    )


def _has_candidate_target_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context).lower()
    return (
        ("target=candidate" in text or "candidate_id" in text)
        and "target_candidates" in text
        and ("semantic_locator" in text or "visual_bounds" in text)
        and ("confidence=high" in text or "confidence=medium" in text or '"confidence": "high"' in text or '"confidence": "medium"' in text)
        and (
            "screen_clickable=true" in text
            or '"screen_clickable": true' in text
            or "semantic_locator" in text
        )
    )


def _has_high_confidence_semantic_candidate(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context).lower()
    return "semantic_locator" in text and (
        "confidence=high" in text
        or '"confidence": "high"' in text
        or "'confidence': 'high'" in text
        or "high-stability" in text
        or "stability=high" in text
    )


def _has_manual_confirm_after_coordinate(
    steps: list[dict[str, Any]],
    coordinate_actions: list[tuple[int, dict[str, Any]]],
) -> bool:
    if not coordinate_actions:
        return False
    first_index = min(index for index, _record in coordinate_actions)
    return any(_action(record) == "manual_confirm" for record in steps[first_index + 1 :])


def _has_later_desktop_result_evidence(steps: list[dict[str, Any]], index: int) -> bool:
    return any(_is_desktop_evidence_step(record) or _action(record) == "manual_confirm" for record in steps[index + 1 :])


def _needs_desktop_message_send(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
) -> bool:
    if bool(profile.get("needs_desktop_message_send")):
        return True
    text = "\n".join(
        [
            str(profile.get("request_text") or ""),
            _desktop_records_text(steps, variables),
            _desktop_evidence_text(evidence_summary, evidence_context),
        ]
    )
    chat_target = _contains_any(
        text,
        ("微信", "wechat", "qq", "聊天", "群", "联系人", "好友", "私信", "收件人"),
    )
    send_intent = _contains_any(text, ("发送消息", "发消息", "send message", "群发", "发给", "祝福"))
    return chat_target and (send_intent or bool(_desktop_message_send_action_records(steps, variables)))


def _needs_desktop_game_task(
    profile: dict[str, Any],
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
) -> bool:
    if bool(profile.get("needs_desktop_game_task")):
        return True
    text = "\n".join(
        [
            str(profile.get("request_text") or ""),
            _desktop_records_text(steps, variables),
            _desktop_evidence_text(evidence_summary, evidence_context),
        ]
    )
    return _contains_any(text, DESKTOP_GAME_TASK_TOKENS)


def _desktop_message_send_action_records(
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for index, record in enumerate(steps):
        action = _action(record)
        step = record["step"]
        step_type = str(step.get("type", "")).lower()
        if action == "desktop_input" and step_type == "hotkey":
            keys_text = _json_text(step.get("keys")).lower()
            if "enter" in keys_text or "return" in keys_text:
                records.append((index, record))
        elif action == "desktop_element" and step_type in {"click", "invoke"}:
            if _contains_any(_desktop_record_text(record, variables), DESKTOP_MESSAGE_SEND_ACTION_TOKENS):
                records.append((index, record))
    return records


def _has_manual_confirm_before_first_index(steps: list[dict[str, Any]], indexes: list[int]) -> bool:
    if not indexes:
        return any(_action(record) == "manual_confirm" for record in steps)
    first_index = min(indexes)
    return any(_action(record) == "manual_confirm" for record in steps[:first_index])


def _has_desktop_message_recipient_confirmation(
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    send_indexes: list[int],
) -> bool:
    evidence_text = _desktop_evidence_text(evidence_summary, evidence_context)
    evidence_negative = _contains_any(evidence_text, (*NEGATIVE_EVIDENCE_TOKENS, *DESKTOP_SCENARIO_NEGATIVE_TOKENS))
    if not evidence_negative and _contains_any(evidence_text, DESKTOP_MESSAGE_RECIPIENT_TOKENS):
        return True
    limit = min(send_indexes) if send_indexes else len(steps)
    for record in steps[:limit]:
        if _action(record) == "manual_confirm":
            return True
        if not _is_desktop_evidence_step(record):
            continue
        if _contains_any(_desktop_record_text(record, variables), DESKTOP_MESSAGE_RECIPIENT_TOKENS):
            return True
    return False


def _has_desktop_message_content_confirmation(
    steps: list[dict[str, Any]],
    variables: dict[str, Any],
    evidence_summary: str,
    evidence_context: dict[str, Any],
    send_indexes: list[int],
) -> bool:
    evidence_text = _desktop_evidence_text(evidence_summary, evidence_context)
    evidence_negative = _contains_any(evidence_text, (*NEGATIVE_EVIDENCE_TOKENS, *DESKTOP_SCENARIO_NEGATIVE_TOKENS))
    if not evidence_negative and _contains_any(
        evidence_text,
        ("draft", "draft_text", "message_text", "message confirmed", "草稿", "消息内容", "正文已确认"),
    ):
        return True
    limit = min(send_indexes) if send_indexes else len(steps)
    for record in steps[:limit]:
        if _action(record) == "manual_confirm":
            return True
        if not _is_desktop_evidence_step(record):
            continue
        if _contains_any(_desktop_record_text(record, variables), DESKTOP_MESSAGE_CONTENT_TOKENS):
            return True
    return False


def _has_desktop_pre_send_evidence(steps: list[dict[str, Any]], send_indexes: list[int]) -> bool:
    if not send_indexes:
        return any(_is_desktop_evidence_step(record) or _action(record) == "manual_confirm" for record in steps)
    first_send_index = min(send_indexes)
    return any(
        _is_desktop_evidence_step(record) or _action(record) == "manual_confirm"
        for record in steps[:first_send_index]
    )


def _is_desktop_game_state_evidence_step(record: dict[str, Any]) -> bool:
    action = _action(record)
    step_type = str(record["step"].get("type", "")).lower()
    if action in {"desktop_capture", "desktop_vision", "desktop_assert"}:
        return True
    if action == "desktop_element":
        return step_type in {"get_text", "get_state", "get_table", "get_tree", "wait"}
    return False


def _has_desktop_game_state_evidence(evidence_summary: str, evidence_context: dict[str, Any]) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context)
    if _contains_any(text, (*NEGATIVE_EVIDENCE_TOKENS, *DESKTOP_SCENARIO_NEGATIVE_TOKENS)):
        return False
    return _contains_any(
        text,
        (
            "desktop_capture",
            "desktop_vision",
            "desktop_assert",
            "progress",
            "status",
            "state",
            "battle_complete",
            "dungeon_runs",
            "截图",
            "状态",
            "进度",
            "完成",
            "奖励",
        ),
    )


def _has_desktop_game_stop_boundary(
    steps: list[dict[str, Any]],
    evidence_summary: str,
    evidence_context: dict[str, Any],
) -> bool:
    text = _desktop_evidence_text(evidence_summary, evidence_context)
    if not _contains_any(text, (*NEGATIVE_EVIDENCE_TOKENS, *DESKTOP_SCENARIO_NEGATIVE_TOKENS)) and _contains_any(
        text,
        (
            "max_runs",
            "duration_seconds",
            "stop_condition",
            "bounded_runtime",
            "max_steps",
            "max_recoveries",
            "max_repeated_observations",
            "dungeon_runs=1",
            "target_runs",
            "目标次数",
            "完成断言",
            "有限",
        ),
    ):
        return True
    loop_records = [record for record in steps if _action(record) in {"trigger", "foreach", "retry"}]
    if not loop_records:
        return any(_is_desktop_game_completion_evidence_step(record) for record in steps)
    return all(_is_desktop_bounded_loop_step(record) for record in loop_records)


def _desktop_unbounded_loop_locations(steps: list[dict[str, Any]]) -> list[str]:
    locations: list[str] = []
    for record in steps:
        if _action(record) != "trigger":
            continue
        step = record["step"]
        has_bound = step.get("max_runs") not in (None, "") or step.get("duration_seconds") not in (None, "")
        if bool(step.get("allow_infinite")) and not has_bound:
            locations.append(record["location"])
    return locations


def _is_desktop_bounded_loop_step(record: dict[str, Any]) -> bool:
    action = _action(record)
    step = record["step"]
    if action == "trigger":
        return step.get("max_runs") not in (None, "") or step.get("duration_seconds") not in (None, "")
    if action == "retry":
        return step.get("max_attempts") not in (None, "")
    if action == "foreach":
        return step.get("items") not in (None, "")
    return True


def _is_desktop_game_completion_evidence_step(record: dict[str, Any]) -> bool:
    action = _action(record)
    step_type = str(record["step"].get("type", "")).lower()
    if action == "desktop_assert":
        return True
    if action == "desktop_element" and step_type in {"get_text", "get_state"}:
        return _contains_any(_desktop_record_text(record, {}), ("complete", "done", "完成", "已领取", "成功"))
    return False


def _desktop_records_text(steps: list[dict[str, Any]], variables: dict[str, Any]) -> str:
    return "\n".join(_desktop_record_text(record, variables) for record in steps)


def _desktop_record_text(record: dict[str, Any], variables: dict[str, Any]) -> str:
    return _desktop_step_text(record.get("step", {}), variables)


def _desktop_step_text(step: Any, variables: dict[str, Any]) -> str:
    values = [_json_text(step)]
    for value in _iter_nested_values(step):
        if isinstance(value, str):
            values.append(_resolved_step_text(value, variables))
    return "\n".join(values)


def _iter_nested_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        result: list[Any] = []
        for nested in value.values():
            result.extend(_iter_nested_values(nested))
        return result
    if isinstance(value, list):
        result = []
        for nested in value:
            result.extend(_iter_nested_values(nested))
        return result
    return [value]


def _desktop_evidence_text(evidence_summary: str, evidence_context: dict[str, Any]) -> str:
    text = str(evidence_summary or "")
    if isinstance(evidence_context, dict) and evidence_context:
        text += "\n" + _json_text(evidence_context)
    return text


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
        return "补充 desktop_window list、desktop_element list/dump/find/get_text/get_state/get_table/get_tree、desktop_assert element、desktop_capture observe/screenshot/snapshot、desktop_vision locate_image/locate_text 或 write，把运行证据写入当前 plan output/。"
    return "补充 extract/script/read/table/ai 等数据获取或处理步骤后，用 write.type=text/json/csv/excel 写入当前 plan output/。"


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
        return "用户要求读取/提取桌面状态或文件数据，但 plan 没有 desktop_window/desktop_element 读取类、desktop_assert element、desktop_capture、desktop_vision、read 或 table 等证据/处理步骤。"
    return "用户要求读取/提取页面或文件数据，但 plan 没有 extract/script/read/table/ai/storage/download 等数据获取或处理步骤。"


def _data_extraction_fix_hint(automation_type: str) -> str:
    if automation_type == "desktop":
        return "先用 desktop_window list、desktop_element list/dump/get_text/get_state/get_table/get_tree、desktop_assert element、desktop_capture observe/screenshot/snapshot、desktop_vision locate_image/locate_text、desktop_wait，或用 read.type=excel/csv/json + table 处理文件数据，再按需写出文件。"
    return "网页数据先用 extract.table、extract.all_texts、extract.text 或 script.evaluate；Excel/CSV/JSON 文件先用 read.type=excel/csv/json，再用 table 过滤、排序、聚合、连接或派生列，最后写出文件。"


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
        if any(
            issue.get("code")
            in {
                "missing_real_site_evidence",
                "missing_desktop_inspection_evidence",
                "missing_desktop_message_pre_send_evidence",
                "missing_desktop_game_progress_evidence",
            }
            for issue in issues
        ):
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


def _has_explicit_file_data_transform_request(text: Any) -> bool:
    text_value = str(text or "")
    if not _contains_any(text_value, FILE_DATA_CONCRETE_RULE_TOKENS):
        return False
    if _contains_any(text_value, ("没有确认", "未确认", "缺少确认", "没有规则", "未指定", "不明确", "不清楚")):
        return False
    return True


def _is_file_data_transform_record(record: dict[str, Any]) -> bool:
    step = record.get("step", {})
    action = str(step.get("action") or "")
    step_type = str(step.get("type") or "")
    if action == "table":
        return step_type in FILE_DATA_TRANSFORM_ACTION_TYPES
    if action == "write" and step_type == "excel":
        formula_columns = step.get("formula_columns")
        return isinstance(formula_columns, dict) and bool(formula_columns)
    return False


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
