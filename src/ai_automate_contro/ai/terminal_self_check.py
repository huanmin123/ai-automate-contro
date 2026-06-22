from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_openai.chat_models.base import _convert_message_to_dict

from ai_automate_contro.ai.session_compression import install_langgraph_warning_filter

install_langgraph_warning_filter()

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from ai_automate_contro.ai.image_attachments import (
    attach_image_file,
    build_human_message_additional_kwargs,
    build_human_message_content,
    expand_message_image_attachments_for_model,
    image_attachment_placeholder,
)
from ai_automate_contro.ai.compression_recall import read_compression_archive_tool
from ai_automate_contro.ai.session_compression import archive_messages, redact_image_data_urls
from ai_automate_contro.ai.session_store import (
    count_images_in_messages,
    list_ai_terminal_sessions,
    remove_ai_terminal_session_from_index,
    resolve_ai_terminal_session,
    session_index_path,
    update_ai_terminal_session_index,
)
from ai_automate_contro.ai.terminal_commands import AITerminalCommandsMixin
from ai_automate_contro.app.errors import UserFacingError, format_error_for_terminal


def self_check_ai_terminal_state(project_root: str | Path) -> dict[str, Any]:
    resolved_project_root = Path(project_root).resolve()
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai-terminal-self-check-") as raw_temp_dir:
        temp_dir = Path(raw_temp_dir)
        storage_root = temp_dir / "project"
        storage_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_dir / "sample.png"
        _write_1x1_png(image_path)

        attachment = attach_image_file(
            storage_root,
            "self-check-thread",
            image_path,
            pending_count=0,
        )
        human_message = HumanMessage(
            content=build_human_message_content("inspect attached screenshot", [attachment]),
            additional_kwargs=build_human_message_additional_kwargs([attachment]),
        )
        expanded_message = expand_message_image_attachments_for_model(human_message)
        expanded_content = getattr(expanded_message, "content", [])
        expanded_kwargs = getattr(expanded_message, "additional_kwargs", {})
        checkpoint_payload = json.dumps(human_message.model_dump(mode="json"), ensure_ascii=False, default=str)
        expanded_payload = json.dumps(expanded_message.model_dump(mode="json"), ensure_ascii=False, default=str)
        checks.append(
            _self_check_result(
                name="image_metadata_checkpoint_safe",
                passed=(
                    "data:image/" not in checkpoint_payload
                    and "data:image/" in expanded_payload
                    and count_images_in_messages([human_message]) == 1
                    and isinstance(expanded_content, list)
                    and len(expanded_content) == 2
                    and "ai_terminal_image_attachments" not in expanded_kwargs
                ),
                detail={
                    "stored_path": str(attachment.stored_path),
                    "checkpoint_chars": len(checkpoint_payload),
                    "expanded_chars": len(expanded_payload),
                    "expanded_additional_kwargs": expanded_kwargs,
                },
            )
        )
        text_content = str(human_message.content)
        checks.append(
            _self_check_result(
                name="image_placeholder_text_stays_inline",
                passed=image_attachment_placeholder(1) in text_content and str(attachment.stored_path) not in text_content,
                detail={"content": text_content},
            )
        )
        openai_message = _convert_message_to_dict(expanded_message)
        checks.append(
            _self_check_result(
                name="model_message_uses_openai_chat_protocol",
                passed=_is_openai_chat_image_message(openai_message),
                detail={
                    "keys": sorted(openai_message.keys()),
                    "role": openai_message.get("role"),
                    "content_types": [
                        item.get("type")
                        for item in openai_message.get("content", [])
                        if isinstance(item, dict)
                    ],
                },
            )
        )

        archive = archive_messages(
            temp_dir,
            "self-check-thread",
            [
                human_message,
                HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]),
                AIMessage(content="ok"),
            ],
            summary="summary",
            reason="self-check",
        )
        archived_text = archive.messages_path.read_text(encoding="utf-8")
        checks.append(
            _self_check_result(
                name="compression_archive_keeps_image_data_urls",
                passed="data:image/" in archived_text and "ai_terminal_image_attachments" in archived_text,
                detail={
                    "messages_path": str(archive.messages_path),
                    "summary_path": str(archive.summary_path),
                },
            )
        )
        recall_list = read_compression_archive_tool(temp_dir, thread_id="self-check-thread", mode="list")
        recall_summary = read_compression_archive_tool(temp_dir, thread_id="self-check-thread", mode="summary")
        recall_messages = read_compression_archive_tool(
            temp_dir,
            thread_id="self-check-thread",
            mode="messages",
            line_count=2,
        )
        recall_search = read_compression_archive_tool(
            temp_dir,
            thread_id="self-check-thread",
            mode="search",
            pattern="inspect attached screenshot",
        )
        denied_cross_thread = False
        denied_cross_thread_error = ""
        try:
            read_compression_archive_tool(
                temp_dir,
                thread_id="other-thread",
                mode="summary",
                archive_path=str(archive.archive_dir),
            )
        except Exception as error:
            denied_cross_thread = "当前线程" in str(error) or "compressions" in str(error)
            denied_cross_thread_error = str(error)
        checks.append(
            _self_check_result(
                name="compression_archive_recall_is_bounded",
                passed=(
                    bool(recall_list.get("ok"))
                    and recall_list.get("archive_count") == 1
                    and bool(recall_summary.get("ok"))
                    and any(line.get("text") == "summary" for line in recall_summary.get("lines", []))
                    and bool(recall_messages.get("ok"))
                    and len(recall_messages.get("messages", [])) == 2
                    and bool(recall_search.get("ok"))
                    and recall_search.get("match_count") == 1
                    and denied_cross_thread
                ),
                detail={
                    "list_archive_count": recall_list.get("archive_count"),
                    "summary_lines": recall_summary.get("lines"),
                    "message_count": len(recall_messages.get("messages", [])),
                    "search_match_count": recall_search.get("match_count"),
                    "cross_thread_error": denied_cross_thread_error,
                },
            )
        )

        raw_data_url = redact_image_data_urls({"image": "data:image/png;base64,AAAA"})
        checks.append(
            _self_check_result(
                name="data_url_kept_raw",
                passed=raw_data_url["image"] == "data:image/png;base64,AAAA",
                detail=raw_data_url,
            )
        )

        checks.append(_check_terminal_prompt_strategy())
        checks.append(_check_plan_generation_validation_hints())
        checks.append(_check_terminal_export_and_plan_creation_boundaries())
        checks.append(_check_ai_confirmation_wait_lock_is_atomic())
        checks.append(_check_terminal_context_suffix_contract())
        checks.append(_check_terminal_context_updates_from_quality_review())
        checks.extend(_check_session_listing(human_message))
        checks.extend(_check_terminal_command_flow(storage_root, human_message))
        checks.extend(_check_terminal_input_widgets(attachment))
        checks.append(_check_terminal_streaming_output())
        checks.append(_check_terminal_streaming_interrupt_drains_safely())
        checks.append(_check_terminal_structured_event_stream())
        checks.append(_check_ai_ask_once_emits_jsonl_ready_events())
        checks.append(_check_terminal_busy_confirmation_route())
        checks.append(_check_ai_mode_manual_confirmation_dialog())
        checks.append(_check_ai_active_turn_input_classifier_routes_feedback())
        checks.append(_check_ai_ask_once_confirmation_times_out())
        checks.append(_check_terminal_tool_progress_output())
        checks.append(_check_terminal_work_plan_events())
        checks.append(_check_terminal_file_change_followup_events())
        checks.append(_check_terminal_plan_run_progress_output())
        checks.append(_check_missing_ai_config_is_user_facing(temp_dir))
        checks.append(_check_terminal_error_formatting(storage_root))

    return {
        "ok": all(check["passed"] for check in checks),
        "check": "ai_terminal_state",
        "project_root": str(resolved_project_root),
        "checks": checks,
    }


def _check_terminal_prompt_strategy() -> dict[str, Any]:
    from ai_automate_contro.ai.prompts.terminal import build_system_prompt

    prompt = build_system_prompt()
    required_fragments = [
        "开工前判断：",
        "目标、范围、目标 plan/URL/文件、输入数据、输出要求、登录权限和验收标准",
        "能通过当前上下文、handbook、plan、output 或只读工具确认的事情",
        "必须在执行前一次性问清楚",
        "只问关键缺口",
        "当前自动化浏览器停在哪一步、已有证据、缺口和用户需要在该浏览器里完成的动作",
        "可以调用 `import_plan_resource_file` 复制到当前 plan 包 `resources/`",
        "不要因为路径位于 plan 包外而拒绝、改写或强制记录审批字段",
        "浏览器本地页面优先使用 `{{resources_file_url}}`",
        "不要硬编码本机绝对 `file://` URL",
        "`write` 手册固定在 `handbook/actions/io/write.md`",
        "页面里已经存在的表格、列表、文本块或同类元素",
        "优先用 `extract.table`、`extract.all_texts`、`extract.text` 或 `script.evaluate` 做确定性提取",
        "`write.type=text` 可以直接写字符串数组",
        "最终交付物写到 Downloads、桌面、绝对路径或其他本机路径",
        "调用 export_local_file 写入或复制过去",
        "不要让用户手动复制",
        "写最终 plan.json 前必须先跑通流程证据",
        "第一步用 inspect_web_page 获取入口页面证据",
        "open_browser.headed=true",
        "让用户在同一个 Playwright 浏览器窗口里完成操作",
        "不要让用户去自己浏览器打开页面",
        "用户提供的截图或 HTML 只能作为辅助证据",
        "没有 `wait.type=timeout`",
        "`extract.type=aria_snapshot`",
        "`mode` 只能是 `default` 或 `ai`",
        "必须先调用 validate_plan",
        "validate_plan 只检查结构，不等于质量复查",
        "必须再调用 review_plan_quality",
        "用户原始需求、探测/探索证据摘要和用户要求的最终本机输出路径",
        "review_plan_quality 返回 fail",
        "强制运行门禁",
        "run_plan 会拒绝没有通过最新质量复查或复查后被修改过的 plan",
        "validate_plan -> review_plan_quality -> 修复直到通过 -> run_plan",
        "工作计划：",
        "复杂、多步骤、会创建/修改/运行/debug plan",
        "执行前必须先调用 update_work_plan",
        "简单问答、短状态查询、单个只读命令",
        "同一时间最多一个步骤是 in_progress",
        "处理复杂任务时同时保持产品、用户和架构视角",
        "执行循环：",
        "明确目标和验收标准 -> 收集最小必要证据 -> 做最小范围修改或运行 -> 验证结果",
        "不确定字段、selector、命令、配置、产物路径或运行状态",
        "用 handbook、只读工具、真实运行或输出产物确认",
        "触及执行器、动作组件、工具 schema、质量门禁、AI 终端上下文或共享解析逻辑",
        "扩大到相关 self-check 和代表性 plan 验证",
        "长会话或上下文不足时",
        "未覆盖测试和残余风险",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    section_order = [
        "你的职责：",
        "边界：",
        "开工前判断：",
        "执行循环：",
        "项目约定：",
        "网页 plan 创建规则：",
        "工具使用：",
        "回答要求：",
    ]
    positions = {section: prompt.find(section) for section in section_order}
    order_ok = all(position >= 0 for position in positions.values()) and list(positions.values()) == sorted(positions.values())
    dynamic_fragments = [
        "current_plan_path:",
        "current_debug_workspace:",
        "latest_output_dir:",
        "latest_compression_summary_path:",
        ".keygen/ai-terminal-sessions/",
    ]
    dynamic_leakage = [fragment for fragment in dynamic_fragments if fragment in prompt]
    return _self_check_result(
        name="terminal_prompt_declares_startup_decision_policy",
        passed=not missing and order_ok and not dynamic_leakage,
        detail={
            "missing": missing,
            "section_positions": positions,
            "dynamic_leakage": dynamic_leakage,
        },
    )


def _check_plan_generation_validation_hints() -> dict[str, Any]:
    from ai_automate_contro.plans.validator import validate_plan_file

    with TemporaryDirectory(prefix="ai-terminal-plan-hints-") as raw_temp_dir:
        project_root = Path(raw_temp_dir)
        package_dir = project_root / "plans" / "guardrail"
        package_dir.mkdir(parents=True)
        (package_dir / "config.json").write_text("{}\n", encoding="utf-8")
        plan_path = package_dir / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "name": "guardrail",
                    "variables": {},
                    "steps": [
                        {"action": "open_browser", "name": "main"},
                        {
                            "action": "wait",
                            "type": "timeout",
                            "browser": "main",
                            "timeout": 2000,
                        },
                        {
                            "action": "extract",
                            "type": "aria_snapshot",
                            "browser": "main",
                            "selector": "body",
                            "mode": "interesting",
                            "save_as": "snapshot",
                        },
                        {
                            "action": "extract",
                            "type": "all_texts",
                            "browser": "main",
                            "save_as": "items",
                        },
                        {
                            "action": "assert",
                            "type": "text",
                            "browser": "main",
                            "selector": "body",
                            "expected": "error",
                            "mode": "not_contains",
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result = validate_plan_file(plan_path, project_root)

    messages = [issue.message for issue in result.errors]
    joined = "\n".join(messages)
    return _self_check_result(
        name="plan_generation_validation_hints_are_actionable",
        passed=(
            not result.ok
            and "wait.type：timeout" in joined
            and "type=time" in joined
            and "seconds" in joined
            and "aria_snapshot.mode" in joined
            and "mode=ai" in joined
            and "extract.all_texts 缺少必填字段：selector" in joined
            and "assert.text" not in joined
        ),
        detail={"messages": messages},
    )


def _check_terminal_export_and_plan_creation_boundaries() -> dict[str, Any]:
    from ai_automate_contro.ai.plan_tools import create_plan_package_tool
    from ai_automate_contro.ai.terminal_tools import export_local_file_tool

    with TemporaryDirectory(prefix="ai-terminal-boundaries-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        (project_root / "plans").mkdir(parents=True)
        (project_root / "test-plans").mkdir(parents=True)
        (project_root / "plan.config").write_text(
            json.dumps(
                {
                    "handbook_path": "handbook",
                    "plan_roots": ["plans", "test-plans"],
                    "default_ai_config_dir": "plans",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        external_dir = project_root.parent / f"{project_root.name}-downloads"
        external_target = external_dir / "AI账户.txt"
        try:
            export_result = export_local_file_tool(
                project_root,
                target_path=external_target,
                content="account-a\n",
            )
            project_export_denied = False
            project_export_error = ""
            try:
                export_local_file_tool(project_root, target_path=project_root / "src" / "bad.txt", content="bad")
            except Exception as error:
                project_export_denied = "项目外" in str(error)
                project_export_error = str(error)

            package_result = create_plan_package_tool(project_root, package_path="plans/new-demo", name="new demo")
            output_plan_denied = False
            output_plan_error = ""
            try:
                create_plan_package_tool(project_root, package_path="plans/new-demo/output/bad", name="bad")
            except Exception as error:
                output_plan_denied = "拒绝" in str(error) or "plan_roots" in str(error)
                output_plan_error = str(error)

            external_plan_denied = False
            external_plan_error = ""
            try:
                create_plan_package_tool(project_root, package_path=external_dir / "bad-plan", name="bad")
            except Exception as error:
                external_plan_denied = "项目根目录内" in str(error)
                external_plan_error = str(error)
        finally:
            if external_dir.exists():
                for path in sorted(external_dir.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                if external_dir.exists():
                    external_dir.rmdir()

    passed = (
        bool(export_result.get("ok"))
        and external_target.name == "AI账户.txt"
        and project_export_denied
        and bool(package_result.get("ok"))
        and output_plan_denied
        and external_plan_denied
    )
    return _self_check_result(
        name="terminal_export_and_plan_creation_boundaries",
        passed=passed,
        detail={
            "export_result": export_result,
            "project_export_error": project_export_error,
            "package_result": package_result,
            "output_plan_error": output_plan_error,
            "external_plan_error": external_plan_error,
        },
    )


def _check_ai_confirmation_wait_lock_is_atomic() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal._ai_confirmation_lock = threading.Lock()
    terminal._ai_confirmation = None
    terminal._ask_once_mode = False
    terminal._client_event_sink_local = threading.local()
    terminal._client_event_sink = lambda event: None
    result: dict[str, Any] = {}

    def first_waiter() -> None:
        try:
            result["accepted"] = AITerminal._wait_for_ai_confirmation(
                terminal,
                "第一个确认",
                wait_type="manual_confirm",
            )
        except Exception as error:
            result["first_error"] = str(error)

    thread = threading.Thread(target=first_waiter, daemon=True)
    thread.start()
    for _ in range(100):
        if terminal._ai_confirmation is not None:
            break
        time.sleep(0.01)

    duplicate_error = ""
    try:
        AITerminal._wait_for_ai_confirmation(terminal, "第二个确认", wait_type="manual_confirm")
    except Exception as error:
        duplicate_error = str(error)

    wait = terminal._ai_confirmation
    if wait is not None:
        wait.accepted = False
        wait.event.set()
    thread.join(timeout=1)

    passed = (
        "已有一个等待确认" in duplicate_error
        and result.get("accepted") is False
        and not thread.is_alive()
    )
    return _self_check_result(
        name="ai_confirmation_wait_lock_is_atomic",
        passed=passed,
        detail={
            "duplicate_error": duplicate_error,
            "first_result": result,
            "thread_alive": thread.is_alive(),
        },
    )


def _check_terminal_context_suffix_contract() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal_context import format_ai_terminal_context

    empty_context = format_ai_terminal_context({})
    state = {
        "ignored_dynamic_noise": "should not appear",
        "latest_compression_archive_dir": ".keygen/ai-terminal-sessions/thread/compressions/archive",
        "latest_output_dir": "plans/demo/output/run",
        "current_debug_workspace": "plans/demo/output/debug/run",
        "latest_compression_messages_path": ".keygen/ai-terminal-sessions/thread/compressions/archive/messages.jsonl",
        "current_plan_path": "plans/demo/plan.json",
        "latest_compression_summary_path": ".keygen/ai-terminal-sessions/thread/compressions/archive/summary.md",
        "latest_plan_quality_review_plan_path": "plans/demo/plan.json",
        "latest_plan_quality_review_signature": "abc123",
        "latest_plan_quality_review_ok": "true",
        "latest_plan_quality_review_severity": "warn",
        "latest_plan_quality_review_next_action": "run_plan_then_export_local_file",
        "work_plan_summary": "修复登录计划",
        "work_plan_items": [
            {"title": "读取失败证据", "status": "completed"},
            {"title": "注入调试步骤", "status": "in_progress"},
            {"title": "生成补丁", "status": "pending"},
        ],
    }
    context = format_ai_terminal_context(state)
    repeated_context = format_ai_terminal_context(dict(state))
    expected_order = [
        "- current_plan_path:",
        "- current_debug_workspace:",
        "- latest_output_dir:",
        "- latest_compression_summary_path:",
        "- latest_compression_messages_path:",
        "- latest_compression_archive_dir:",
        "- latest_plan_quality_review_plan_path:",
        "- latest_plan_quality_review_ok:",
        "- latest_plan_quality_review_severity:",
        "- latest_plan_quality_review_next_action:",
        "- latest_plan_quality_review_signature:",
    ]
    positions = {field: context.find(field) for field in expected_order}
    order_ok = all(position >= 0 for position in positions.values()) and list(positions.values()) == sorted(positions.values())
    ignored_unknown = "ignored_dynamic_noise" not in context and "should not appear" not in context
    guidance_ok = "优先使用这些上下文" in context and "先读取压缩摘要" in context
    work_plan_ok = (
        "当前可见工作计划" in context
        and "修复登录计划" in context
        and "[in_progress] 注入调试步骤" in context
    )
    quality_review_ok = (
        "latest_plan_quality_review_plan_path: plans/demo/plan.json" in context
        and "latest_plan_quality_review_ok: true" in context
        and "latest_plan_quality_review_severity: warn" in context
        and "latest_plan_quality_review_next_action: run_plan_then_export_local_file" in context
        and "latest_plan_quality_review_signature: <recorded>" in context
        and "abc123" not in context
    )
    plan_only_context = format_ai_terminal_context(
        {
            "work_plan_items": [{"title": "确认需求", "status": "in_progress"}],
            "work_plan_summary": "只有计划",
        }
    )
    return _self_check_result(
        name="terminal_context_suffix_is_stable_and_bounded",
        passed=(
            empty_context == ""
            and context == repeated_context
            and order_ok
            and ignored_unknown
            and guidance_ok
            and work_plan_ok
            and quality_review_ok
            and "只有计划" in plan_only_context
        ),
        detail={
            "empty_context": empty_context,
            "field_positions": positions,
            "ignored_unknown": ignored_unknown,
            "guidance_ok": guidance_ok,
            "work_plan_ok": work_plan_ok,
            "quality_review_ok": quality_review_ok,
            "plan_only_context": plan_only_context,
        },
    )


def _check_terminal_context_updates_from_quality_review() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal_context import context_update_from_tool_result
    from ai_automate_contro.ai.terminal_state import AITerminalStateMixin

    update = context_update_from_tool_result(
        "review_plan_quality",
        {"plan_path": "plans/demo/plan.json"},
        {
            "ok": True,
            "plan_path": "plans/demo/plan.json",
            "plan_signature": "signature-123",
            "severity": "warn",
            "next_action": "run_plan_then_export_local_file",
        },
    )
    failed_update = context_update_from_tool_result(
        "review_plan_quality",
        {"plan_path": "plans/demo/plan.json"},
        {
            "ok": False,
            "plan_path": "plans/demo/plan.json",
            "plan_signature": "signature-456",
            "severity": "fail",
            "next_action": "fix_plan",
        },
    )

    class _FakeGraph:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}

        def get_state(self, _config: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(values=self.values)

        def update_state(self, _config: dict[str, Any], update: dict[str, Any]) -> None:
            self.values.update(update)

    class _RuntimeContextTerminal(AITerminalStateMixin):
        def __init__(self) -> None:
            self.graph = _FakeGraph()
            self.graph_recursion_limit = 128
            self.thread_id = "quality-review-context"
            self._runtime_context_state: dict[str, str] = {}

    runtime_terminal = _RuntimeContextTerminal()
    runtime_terminal._update_context_state(update)
    runtime_context = runtime_terminal._context_state()

    current_plan_path = str(update.get("current_plan_path", "")).replace("\\", "/")
    review_plan_path = str(update.get("latest_plan_quality_review_plan_path", "")).replace("\\", "/")
    quality_keys_ok = (
        current_plan_path.endswith("plans/demo/plan.json")
        and review_plan_path.endswith("plans/demo/plan.json")
        and update.get("latest_plan_quality_review_signature") == "signature-123"
        and update.get("latest_plan_quality_review_ok") == "true"
        and update.get("latest_plan_quality_review_severity") == "warn"
        and update.get("latest_plan_quality_review_next_action") == "run_plan_then_export_local_file"
    )
    runtime_context_ok = (
        runtime_context.get("latest_plan_quality_review_ok") == "true"
        and runtime_context.get("latest_plan_quality_review_signature") == "signature-123"
    )
    failed_review_ok = (
        failed_update.get("latest_plan_quality_review_ok") == "false"
        and failed_update.get("latest_plan_quality_review_signature") == "signature-456"
        and failed_update.get("latest_plan_quality_review_next_action") == "fix_plan"
    )
    return _self_check_result(
        name="quality_review_updates_terminal_context",
        passed=quality_keys_ok and runtime_context_ok and failed_review_ok,
        detail={
            "update": update,
            "runtime_context": runtime_context,
            "failed_update": failed_update,
        },
    )


def _check_missing_ai_config_is_user_facing(temp_dir: Path) -> dict[str, Any]:
    from ai_automate_contro.ai.terminal_config import load_ai_terminal_config

    project_root = temp_dir / "missing-config-project"
    (project_root / "handbook").mkdir(parents=True, exist_ok=True)
    plans_dir = project_root / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "plan.config").write_text(
        json.dumps(
            {
                "handbook_path": "handbook",
                "plan_roots": ["plans"],
                "default_ai_config_dir": "plans",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (plans_dir / "config.json").write_text("{}", encoding="utf-8")
    try:
        load_ai_terminal_config(project_root)
    except Exception as error:
        return _self_check_result(
            name="terminal_missing_ai_config_is_user_facing",
            passed=isinstance(error, UserFacingError) and "AI 终端服务未配置" in str(error),
            detail={
                "error_type": type(error).__name__,
                "message": str(error),
            },
        )
    return _self_check_result(
        name="terminal_missing_ai_config_is_user_facing",
        passed=False,
        detail={"error": "missing config unexpectedly passed"},
    )


def _check_terminal_error_formatting(project_root: Path) -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal, check_ai_terminal_service

    formatted_usage = format_error_for_terminal("用法：/image <image-path>", project_root=project_root)
    formatted_unknown_command = format_error_for_terminal(
        "unknown AI terminal command: /attach",
        project_root=project_root,
    )
    formatted_no_run = format_error_for_terminal(ValueError("no active run"), project_root=project_root)
    formatted_user_error = format_error_for_terminal(
        UserFacingError(
            "AI 终端服务未配置：default",
            details=["配置文件：plans\\config.json"],
            fix="添加 ai_services.default。",
            verify=["python .\\main.py self-check env"],
        ),
        project_root=project_root,
    )
    external_ai_error_type = type("APIStatusError", (Exception,), {"__module__": "openai"})
    formatted_external_ai_error = format_error_for_terminal(
        external_ai_error_type("Error code: 503 - upstream unavailable"),
        project_root=project_root,
    )
    terminal = object.__new__(AITerminal)
    terminal.project_root = project_root
    terminal.config = SimpleNamespace(
        service_name="default",
        service_config={
            "base_url": "https://example.test/v1",
            "model": "demo-model",
            "api_key": "secret-test-key",
        },
    )
    terminal.model_name = "demo-model"
    terminal.events = []
    terminal._client_event_sink = terminal.events.append
    AITerminal._emit_error(terminal, external_ai_error_type("Error code: 502 - upstream bad gateway"))
    enriched_external_ai_error = terminal.events[-1].text if terminal.events else ""
    formatted_method_error = AITerminal.format_error_message(
        terminal,
        external_ai_error_type("Error code: 504 - upstream timeout"),
    )
    missing_service_check = check_ai_terminal_service(
        project_root / "missing-live-check-project",
        service="default",
        thread_id="self-check-missing-service",
    )
    outputs = {
        "usage": formatted_usage,
        "unknown_command": formatted_unknown_command,
        "no_run": formatted_no_run,
        "user_error": formatted_user_error,
        "external_ai_error": formatted_external_ai_error,
        "enriched_external_ai_error": enriched_external_ai_error,
        "formatted_method_error": formatted_method_error,
        "missing_service_check": json.dumps(missing_service_check, ensure_ascii=False),
    }
    passed = (
        "命令用法不正确" in formatted_usage
        and "未知 AI 会话命令：/attach" in formatted_unknown_command
        and "当前没有正在运行或等待的 plan" in formatted_no_run
        and "AI 终端服务未配置：default" in formatted_user_error
        and formatted_external_ai_error == "错误：Error code: 503 - upstream unavailable"
        and "service=default" in enriched_external_ai_error
        and "model=demo-model" in enriched_external_ai_error
        and "base_url=https://example.test/v1" in enriched_external_ai_error
        and "service=default" in formatted_method_error
        and "model=demo-model" in formatted_method_error
        and missing_service_check.get("ok") is False
        and missing_service_check.get("check") == "ai_terminal_service"
        and "AI 终端服务未配置" in str(missing_service_check.get("formatted_error", ""))
        and "secret-test-key" in enriched_external_ai_error
        and "secret-test-key" in formatted_method_error
        and "Traceback" not in "\n".join(outputs.values())
        and "self-check" not in formatted_external_ai_error
    )
    return _self_check_result(
        name="terminal_errors_are_user_facing",
        passed=passed,
        detail=outputs,
    )


def _check_session_listing(human_message: HumanMessage) -> list[dict[str, Any]]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    try:
        _put_checkpoint(
            checkpointer,
            thread_id="alpha",
            checkpoint_id="0001",
            messages=[HumanMessage(content="alpha user"), AIMessage(content="alpha assistant")],
            extra_values={"current_plan_path": "plans/minimal-browser-plan/plan.json"},
        )
        _put_checkpoint(
            checkpointer,
            thread_id="image-thread",
            checkpoint_id="0002",
            messages=[human_message, AIMessage(content="image response")],
            extra_values={"latest_compression_summary_path": ".keygen/summary.md"},
        )
        sessions = list_ai_terminal_sessions(checkpointer, limit=10)
        resolved_by_index = resolve_ai_terminal_session(checkpointer, "1")
        resolved_by_partial = resolve_ai_terminal_session(checkpointer, "image")
        image_summary = next((session for session in sessions if session.thread_id == "image-thread"), None)
        with tempfile.TemporaryDirectory(prefix="ai-terminal-index-self-check-") as raw_index_dir:
            index_root = Path(raw_index_dir)
            quality_context = {
                "latest_plan_quality_review_plan_path": "plans/minimal-browser-plan/plan.json",
                "latest_plan_quality_review_ok": "true",
                "latest_plan_quality_review_signature": "signature-123",
            }
            update_ai_terminal_session_index(index_root, checkpointer, "alpha", context_state=quality_context)
            update_ai_terminal_session_index(index_root, checkpointer, "alpha")
            indexed_sessions = list_ai_terminal_sessions(checkpointer, project_root=index_root, limit=10)
            indexed_resolved = resolve_ai_terminal_session(checkpointer, "alpha", project_root=index_root)
            indexed_alpha = next((session for session in indexed_sessions if session.thread_id == "alpha"), None)
            remove_ai_terminal_session_from_index(index_root, "alpha")
            index_exists_after_remove = session_index_path(index_root).exists()
            index_after_remove_payload = json.loads(session_index_path(index_root).read_text(encoding="utf-8"))
            index_after_remove_threads = [
                str(session.get("thread_id"))
                for session in index_after_remove_payload.get("sessions", [])
                if isinstance(session, dict)
            ]
            session_index_path(index_root).write_text(
                '{"version":1,"updated_at":"broken","sessions":[]}'
                '"latest_output_dir":"/tmp/stale"',
                encoding="utf-8",
            )
            recovered_sessions = list_ai_terminal_sessions(checkpointer, project_root=index_root, limit=10)
            recovered_threads = [session.thread_id for session in recovered_sessions]
        return [
            _self_check_result(
                name="session_listing_summarizes_latest_checkpoints",
                passed=len(sessions) == 2 and sessions[0].thread_id == "image-thread",
                detail={
                    "threads": [session.thread_id for session in sessions],
                    "message_counts": [session.message_count for session in sessions],
                },
            ),
            _self_check_result(
                name="session_resume_selectors",
                passed=resolved_by_index == "image-thread" and resolved_by_partial == "image-thread",
                detail={
                    "resolved_by_index": resolved_by_index,
                    "resolved_by_partial": resolved_by_partial,
                },
            ),
            _self_check_result(
                name="session_image_metadata_counted",
                passed=image_summary is not None and image_summary.image_count == 1,
                detail={
                    "image_count": image_summary.image_count if image_summary is not None else None,
                },
            ),
            _self_check_result(
                name="session_index_round_trip",
                passed=(
                    index_exists_after_remove
                    and indexed_resolved == "alpha"
                    and any(session.thread_id == "alpha" for session in indexed_sessions)
                    and indexed_alpha is not None
                    and indexed_alpha.context_state.get("latest_plan_quality_review_ok") == "true"
                    and indexed_alpha.context_state.get("latest_plan_quality_review_signature") == "signature-123"
                    and all(thread_id != "alpha" for thread_id in index_after_remove_threads)
                ),
                detail={
                    "index_path": str(session_index_path(index_root)),
                    "indexed_threads": [session.thread_id for session in indexed_sessions],
                    "indexed_context": indexed_alpha.context_state if indexed_alpha is not None else {},
                    "after_remove_threads": index_after_remove_threads,
                    "index_exists_after_remove": index_exists_after_remove,
                    "resolved": indexed_resolved,
                },
            ),
            _self_check_result(
                name="session_index_recovers_from_trailing_garbage",
                passed="alpha" in recovered_threads and "image-thread" in recovered_threads,
                detail={"threads": recovered_threads},
            ),
        ]
    finally:
        connection.close()


def _check_terminal_command_flow(project_root: Path, human_message: HumanMessage) -> list[dict[str, Any]]:
    from ai_automate_contro.ai.terminal import AITerminal, SLASH_COMMANDS

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    try:
        alpha_messages = [HumanMessage(content="alpha user"), AIMessage(content="alpha assistant")]
        image_messages = [human_message, AIMessage(content="image response")]
        _put_checkpoint(
            checkpointer,
            thread_id="alpha",
            checkpoint_id="0001",
            messages=alpha_messages,
            extra_values={"current_plan_path": "plans/minimal-browser-plan/plan.json"},
        )
        _put_checkpoint(
            checkpointer,
            thread_id="image-thread",
            checkpoint_id="0002",
            messages=image_messages,
            extra_values={"latest_output_dir": "test-plans/example/output/run"},
        )
        terminal = _FakeTerminal(
            project_root=project_root,
            checkpointer=checkpointer,
            messages_by_thread={
                "alpha": alpha_messages,
                "image-thread": image_messages,
                "flow-thread": [HumanMessage(content="flow user"), AIMessage(content="flow assistant")],
            },
        )

        terminal.do_status("")
        status_payload = json.loads(terminal.outputs[-1])
        status_ok = (
            status_payload["thread_id"] == "alpha"
            and status_payload["busy"] is False
            and status_payload["last_error"] == "previous model error"
            and status_payload["context_window"]["model_context_token_limit"] == 128_000
            and status_payload["context_window"]["graph_recursion_limit"] == 128
        )
        terminal._current_turn_text = "busy turn"
        busy_status_payload = terminal.status_payload()
        terminal._current_turn_text = None

        terminal.do_sessions("--json")
        sessions_payload = json.loads(terminal.outputs[-1])
        sessions_ok = len(sessions_payload) == 2 and sessions_payload[0]["thread_id"] == "image-thread"
        index_path = session_index_path(project_root)
        sessions_index_ok = index_path.exists()

        terminal.do_resume("1")
        resume_ok = (
            terminal.thread_id == "image-thread"
            and terminal._last_error == ""
            and terminal.outputs[-2] == "AI 会话线程：image-thread"
        )

        terminal.do_new("flow-thread")
        new_ok = terminal.thread_id == "flow-thread" and terminal.outputs[-1] == "AI 会话线程：flow-thread"

        slash_ok = AITerminal._handle_slash_command(terminal, "/status") is True
        slash_status_payload = json.loads(terminal.outputs[-1])
        slash_ok = slash_ok and slash_status_payload["thread_id"] == "flow-thread"

        backend_command_names = set(SLASH_COMMANDS)
        backend_command_text = "\n".join(f"/{name}" for name in sorted(backend_command_names))
        help_shortcuts_ok = "help" not in backend_command_names and "exit" not in backend_command_names
        terminal.do_plan("")
        plan_empty_text = terminal.outputs[-1]
        terminal.forwarded_messages: list[str] = []
        terminal._run_agent_turn = lambda line: terminal.forwarded_messages.append(str(line))
        terminal.handle_user_request = lambda line: AITerminal.handle_user_request(terminal, line)
        terminal._handle_slash_command = lambda line: AITerminal._handle_slash_command(terminal, line)
        plain_status_message_ok = AITerminal.handle_input(terminal, "status") is False and terminal.forwarded_messages[-1] == "status"
        mid_slash_message_ok = (
            AITerminal.handle_input(terminal, "普通文字 /status") is False
            and terminal.forwarded_messages[-1] == "普通文字 /status"
        )
        leading_space_message_ok = (
            AITerminal.handle_input(terminal, " /status") is False
            and terminal.forwarded_messages[-1] == " /status"
        )
        bad_slash_format = AITerminal.handle_input(terminal, "/键盘") is False
        bad_slash_error = terminal.errors[-1] if terminal.errors else ""
        slash_attach_unknown = AITerminal._handle_slash_command(terminal, "/attach list") is True
        slash_attach_error = terminal.errors[-1] if terminal.errors else ""
        slash_paste_unknown = AITerminal._handle_slash_command(terminal, "/paste-image") is True
        slash_paste_error = terminal.errors[-1] if terminal.errors else ""
        slash_run_context_unknown = AITerminal._handle_slash_command(terminal, "/run_context output/run") is True
        slash_run_context_error = terminal.errors[-1] if terminal.errors else ""
        slash_context_unknown = AITerminal._handle_slash_command(terminal, "/context") is True
        slash_context_error = terminal.errors[-1] if terminal.errors else ""
        removed_command_errors: dict[str, str] = {}
        removed_commands_unknown = True
        removed_command_expectations = {
            "/ai hello": "/ai",
            "/compress": "/compress",
            "/exit": "/exit",
            "/help": "/help",
            "/history": "/history",
            "/keyboard": "/keyboard",
            "/pending": "/pending",
        }
        for removed_command, expected_name in removed_command_expectations.items():
            handled = AITerminal._handle_slash_command(terminal, removed_command)
            removed_command_errors[removed_command] = terminal.errors[-1] if terminal.errors else ""
            removed_commands_unknown = (
                removed_commands_unknown
                and handled is True
                and f"未知 AI 会话命令：{expected_name}" in removed_command_errors[removed_command]
            )
        image_surface_ok = (
            "attach list" not in backend_command_text
            and "plan" in backend_command_names
            and "help" not in backend_command_names
            and "exit" not in backend_command_names
            and "ai" not in backend_command_names
            and "/todo" not in backend_command_text
            and "/back" not in backend_command_text
            and "/quit" not in backend_command_text
            and "/compact" not in backend_command_text
            and "/compress" not in backend_command_text
            and "/history" not in backend_command_text
            and "/keyboard" not in backend_command_text
            and "/pending" not in backend_command_text
            and "当前没有工作计划" in plan_empty_text
            and "attach remove" not in backend_command_text
            and "attach clear" not in backend_command_text
            and "/attach" not in backend_command_text
            and "/paste-image" not in backend_command_text
            and "paste_image" not in backend_command_text
            and "cancel" not in backend_command_text
            and "run_context" not in backend_command_text
            and "tools [name]" not in backend_command_text
            and "context" not in backend_command_text
            and plain_status_message_ok
            and mid_slash_message_ok
            and leading_space_message_ok
            and bad_slash_format
            and "命令名必须以英文字母开头" in bad_slash_error
            and slash_attach_unknown
            and "未知 AI 会话命令：/attach" in slash_attach_error
            and slash_paste_unknown
            and "未知 AI 会话命令：/paste-image" in slash_paste_error
            and slash_run_context_unknown
            and "未知 AI 会话命令：/run_context" in slash_run_context_error
            and slash_context_unknown
            and "未知 AI 会话命令：/context" in slash_context_error
            and removed_commands_unknown
        )

        busy_guard_ok, busy_guard_detail = _check_busy_command_guard()

        ask_once_guard_ok = False
        ask_once_error = ""
        terminal._has_interrupts = True
        try:
            AITerminal.ask_once(terminal, "continue")
        except Exception as error:
            ask_once_error = str(error)
            ask_once_guard_ok = "等待审批" in ask_once_error
        finally:
            terminal._has_interrupts = False

        return [
            _self_check_result(
                name="terminal_status_command_reports_context",
                passed=status_ok and busy_status_payload["busy"] is True,
                detail={
                    "thread_id": status_payload.get("thread_id"),
                    "context_window": status_payload.get("context_window"),
                    "last_error": status_payload.get("last_error"),
                    "busy_status": busy_status_payload.get("busy"),
                },
            ),
            _self_check_result(
                name="terminal_sessions_command_lists_checkpoints",
                passed=sessions_ok and sessions_index_ok,
                detail={
                    "threads": [session.get("thread_id") for session in sessions_payload],
                    "index_path": str(index_path),
                    "index_exists": sessions_index_ok,
                },
            ),
            _self_check_result(
                name="terminal_resume_and_new_commands_switch_threads",
                passed=resume_ok and new_ok,
                detail={
                    "thread_id": terminal.thread_id,
                    "resume_ok": resume_ok,
                    "new_ok": new_ok,
                },
            ),
            _self_check_result(
                name="terminal_slash_command_dispatch",
                passed=slash_ok,
                detail={
                    "thread_id": slash_status_payload.get("thread_id"),
                },
            ),
            _self_check_result(
                name="terminal_backend_keeps_ui_commands_out_of_session_commands",
                passed=help_shortcuts_ok and "Alt+V" not in backend_command_text,
                detail={
                    "help_shortcuts_ok": help_shortcuts_ok,
                    "backend_commands": sorted(backend_command_names),
                    "backend_mentions_keyboard": "/keyboard" in backend_command_text,
                    "backend_mentions_inline_paste": "Alt+V" in backend_command_text,
                },
            ),
            _self_check_result(
                name="terminal_image_command_surface_is_low_friction",
                passed=image_surface_ok,
                detail={
                    "backend_mentions_keyboard": "/keyboard" in backend_command_text,
                    "backend_mentions_plan": "plan" in backend_command_names,
                    "plan_empty_text": plan_empty_text,
                    "plain_status_messages": terminal.forwarded_messages,
                    "bad_slash_error": bad_slash_error,
                    "slash_attach_error": slash_attach_error,
                    "slash_paste_error": slash_paste_error,
                    "slash_run_context_error": slash_run_context_error,
                    "slash_context_error": slash_context_error,
                    "removed_command_errors": removed_command_errors,
                },
            ),
            _self_check_result(
                name="terminal_busy_command_guard",
                passed=busy_guard_ok,
                detail=busy_guard_detail,
            ),
            _self_check_result(
                name="terminal_ask_once_requires_clear_thread",
                passed=ask_once_guard_ok,
                detail={"error": ask_once_error},
            ),
        ]
    finally:
        connection.close()


def _check_terminal_input_widgets(attachment: Any) -> list[dict[str, Any]]:
    from ai_automate_contro.ai.terminal import (
        reconcile_image_placeholders,
        reconcile_pending_image_attachments,
    )

    first = attachment
    second = attachment
    placeholder_1 = image_attachment_placeholder(1)
    placeholder_2 = image_attachment_placeholder(2)
    reordered_text, reordered_attachments, reordered_required = reconcile_pending_image_attachments(
        f"{placeholder_2} 然后 {placeholder_1}",
        [first, second],
        [True, True],
        preserve_when_absent=False,
    )
    reorder_ok = (
        reordered_text == f"{placeholder_1} 然后 {placeholder_2}"
        and reordered_attachments == [second, first]
        and reordered_required == [True, True]
    )
    no_placeholder_text, no_placeholder_attachments = reconcile_image_placeholders(
        "plain request",
        [first],
        preserve_when_absent=True,
    )
    no_placeholder_ok = no_placeholder_text == "plain request" and no_placeholder_attachments == [first]
    submit_text, submit_attachments, submit_required = reconcile_pending_image_attachments(
        "plain request",
        [first, second],
        [True, False],
        preserve_when_absent=False,
    )
    submit_filter_ok = submit_text == "plain request" and submit_attachments == [second] and submit_required == [False]
    invalid_text, invalid_attachments, invalid_required = reconcile_pending_image_attachments(
        f"{placeholder_1} {placeholder_1} [图片 #99]",
        [first, second],
        [True, False],
        preserve_when_absent=False,
    )
    invalid_placeholder_ok = (
        invalid_text == f"{placeholder_1} {placeholder_1} [图片 #99]"
        and invalid_attachments == [first, second]
        and invalid_required == [True, False]
    )
    return [
        _self_check_result(
            name="terminal_image_attachment_placeholder_reconcile",
            passed=reorder_ok and no_placeholder_ok and submit_filter_ok and invalid_placeholder_ok,
            detail={
                "reordered_text": reordered_text,
                "reordered_count": len(reordered_attachments),
                "no_placeholder_attachments": len(no_placeholder_attachments),
                "submit_filter_attachments": len(submit_attachments),
                "invalid_text": invalid_text,
                "invalid_count": len(invalid_attachments),
            },
        )
    ]

def _formatted_text_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return "".join(str(fragment[1]) for fragment in value)
    except Exception:
        return str(value)


def _check_terminal_streaming_output() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    class FakeGraph:
        def stream(self, *_: Any, **__: Any) -> Any:
            yield ("values", {"messages": [HumanMessage(content="hello")]})
            yield (
                "messages",
                (
                    AIMessageChunk(content="流式"),
                    {"langgraph_node": "model"},
                ),
            )
            yield (
                "messages",
                (
                    AIMessageChunk(content="输出"),
                    {"langgraph_node": "model"},
                ),
            )
            yield (
                "values",
                {"messages": [HumanMessage(content="hello"), AIMessage(content="流式输出")]},
            )

        def get_state(self, *_: Any, **__: Any) -> Any:
            return SimpleNamespace(values={"messages": []})

    terminal = object.__new__(AITerminal)
    terminal.graph = FakeGraph()
    terminal.graph_recursion_limit = 128
    terminal.thread_id = "stream-check"
    terminal.chunks: list[str] = []
    terminal.indicator_events: list[str] = []
    terminal._graph_config = lambda: {"configurable": {"thread_id": terminal.thread_id}}
    terminal._stream_response_text = lambda text: terminal.chunks.append(text)
    terminal._stream_response_newline = lambda: terminal.chunks.append("\n")
    terminal._start_thinking_indicator = lambda: terminal.indicator_events.append("start") or "indicator"
    terminal._stop_thinking_indicator = lambda indicator: terminal.indicator_events.append(f"stop:{indicator}")

    final_state, streamed = AITerminal._invoke_graph_streaming(terminal, {"messages": []})
    rendered = "".join(terminal.chunks)
    return _self_check_result(
        name="terminal_agent_turn_streams_tokens",
        passed=(
            streamed
            and rendered == "流式输出\n"
            and len(final_state.get("messages", [])) == 2
            and terminal.indicator_events == ["start", "stop:indicator"]
        ),
        detail={
            "streamed": streamed,
            "rendered": rendered,
            "message_count": len(final_state.get("messages", [])),
            "indicator_events": terminal.indicator_events,
        },
    )


def _check_terminal_streaming_interrupt_drains_safely() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    class FakeGraph:
        def __init__(self) -> None:
            self.events_seen = 0

        def stream(self, *_: Any, **__: Any) -> Any:
            yield (
                "messages",
                (
                    AIMessageChunk(content="前半"),
                    {"langgraph_node": "model"},
                ),
            )
            self.events_seen += 1
            yield (
                "messages",
                (
                    AIMessageChunk(content="后半"),
                    {"langgraph_node": "model"},
                ),
            )
            self.events_seen += 1
            yield ("values", {"messages": [AIMessage(content="前半后半")]})
            self.events_seen += 1

        def get_state(self, *_: Any, **__: Any) -> Any:
            return SimpleNamespace(values={"messages": []})

    terminal = object.__new__(AITerminal)
    terminal.graph = FakeGraph()
    terminal.thread_id = "safe-interrupt-check"
    terminal.chunks: list[str] = []
    terminal.indicator_events: list[str] = []
    terminal._graph_config = lambda: {"configurable": {"thread_id": terminal.thread_id}}
    terminal._stream_response_text = lambda text: terminal.chunks.append(text)
    terminal._stream_response_newline = lambda: terminal.chunks.append("\n")
    terminal._start_thinking_indicator = lambda: terminal.indicator_events.append("start") or "indicator"
    terminal._stop_thinking_indicator = lambda indicator: terminal.indicator_events.append(f"stop:{indicator}")

    cancel_after_first_chunk = {"seen_first_chunk": False}

    def current_turn_cancelled() -> bool:
        if cancel_after_first_chunk["seen_first_chunk"]:
            return True
        cancel_after_first_chunk["seen_first_chunk"] = True
        return False

    terminal._current_agent_turn_cancelled = current_turn_cancelled
    final_state, streamed = AITerminal._invoke_graph_streaming(terminal, {"messages": []})
    rendered = "".join(terminal.chunks)
    return _self_check_result(
        name="terminal_safe_interrupt_drains_stream",
        passed=(
            streamed
            and rendered == "前半"
            and terminal.graph.events_seen == 3
            and len(final_state.get("messages", [])) == 1
        ),
        detail={
            "streamed": streamed,
            "rendered": rendered,
            "events_seen": terminal.graph.events_seen,
            "message_count": len(final_state.get("messages", [])),
        },
    )


def _check_terminal_structured_event_stream() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.project_root = Path(".").resolve()
    terminal.config = type("Config", (), {"service_name": "self-check"})()
    terminal.model_name = "fake-model"
    terminal.thread_id = "event-thread"
    terminal._pending_attachments = []
    terminal._last_error = ""
    terminal.events = []
    terminal.commands: list[str] = []
    terminal.handle_input = lambda line: terminal.commands.append(str(line)) or False
    terminal._current_interrupts = lambda: ()
    terminal._is_agent_busy = lambda: False
    terminal._context_state = lambda: {"current_plan_path": "plans/demo/plan.json"}
    terminal._client_event_sink = None

    AITerminal.run_event_turn(terminal, "创建 plan", terminal.events.append)

    with AITerminal.client_event_sink(terminal, terminal.events.append):
        AITerminal._emit_user_message(terminal, "用户消息")
        AITerminal._emit_assistant_message(terminal, "AI 正文")
        AITerminal._stream_response_text(terminal, "流式")
        AITerminal._stream_response_newline(terminal)
        AITerminal._start_thinking_indicator(terminal)
        AITerminal._print_tool_progress(terminal, "start", "inspect_web_page", {"url": "https://example.com"})
        AITerminal._print_tool_progress(
            terminal,
            "done",
            "inspect_web_page",
            {"url": "https://example.com"},
            {"ok": True, "resolved_url": "https://example.com"},
        )
        worker = threading.Thread(
            target=lambda: AITerminal._print_tool_progress(
                terminal,
                "start",
                "grep_project_text",
                {"pattern": "selector", "root_path": "handbook/actions"},
            )
        )
        worker.start()
        worker.join()

    kinds = [event.kind for event in terminal.events]
    user_message_suppressed = all(event.text != "用户消息" for event in terminal.events)
    context_events = [event for event in terminal.events if event.kind == "context_updated"]
    activity_texts = [event.text for event in terminal.events if event.kind == "activity"]
    passed = (
        terminal.commands == ["创建 plan"]
        and user_message_suppressed
        and kinds.count("assistant_delta") == 2
        and kinds.count("assistant_done") == 2
        and len(context_events) >= 2
        and context_events[0].data.get("thread_id") == "event-thread"
        and "status" in kinds
        and "tool_started" in kinds
        and "tool_finished" in kinds
        and "开始处理用户请求" in activity_texts
        and any("调用工具 inspect_web_page" == text for text in activity_texts)
        and any("调用工具 grep_project_text" == text for text in activity_texts)
        and any("工具完成 inspect_web_page" == text for text in activity_texts)
        and "本轮事件处理完成" in activity_texts
        and "exit_requested" not in kinds
    )
    return _self_check_result(
        name="terminal_structured_event_stream_for_textual_client",
        passed=passed,
        detail={
            "commands": terminal.commands,
            "kinds": kinds,
            "texts": [event.text for event in terminal.events],
        },
    )


def _check_ai_ask_once_emits_jsonl_ready_events() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.thread_id = "ask-events"
    terminal.model_name = "fake-model"
    terminal.checkpoint_path = Path(".keygen") / "ai-terminal-checkpoints.sqlite"
    terminal._ask_once_mode = False
    terminal._pending_attachments = []
    terminal._pending_attachment_placeholder_required = []
    terminal._client_event_sink_local = __import__("threading").local()
    terminal._client_event_sink = None
    terminal._last_error = ""
    terminal._is_agent_busy = lambda: False
    terminal._current_interrupts = lambda: ()
    terminal._prepare_input_attachments = lambda text: (text, [])
    terminal._sync_current_session_index = lambda: None
    terminal._context_state = lambda: {"current_plan_path": "plans/demo/plan.json"}
    terminal.client_status_snapshot = lambda: {
        "thread_id": terminal.thread_id,
        "busy": False,
        "pending_approval": False,
        "context_state": terminal._context_state(),
        "last_error": terminal._last_error,
    }
    terminal._invoke_agent_text = lambda text, attachments: {
        "messages": [HumanMessage(content=text), AIMessage(content="完成")]
    }

    events = []
    result = AITerminal.ask_once(terminal, "创建 plan", event_sink=events.append)
    kinds = [event.kind for event in events]
    passed = (
        result.get("ok") is True
        and result.get("assistant_message") == "完成"
        and kinds[:2] == ["context_updated", "activity"]
        and events[1].text == "开始处理脚本化 AI 请求"
    )
    return _self_check_result(
        name="ai_ask_once_emits_script_events",
        passed=passed,
        detail={
            "result": result,
            "events": [{"kind": event.kind, "text": event.text, "data": event.data} for event in events],
        },
    )


def _check_terminal_busy_confirmation_route() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal, AIConfirmationWait

    terminal = object.__new__(AITerminal)
    terminal._current_turn_text = "等待用户确认"
    terminal._current_turn_id = 1
    terminal._cancelled_turn_ids = set()
    terminal._turn_lock = __import__("threading").Lock()
    terminal._ai_confirmation_lock = __import__("threading").Lock()
    terminal._ai_confirmation = AIConfirmationWait(prompt="请确认浏览器状态。", wait_type="manual_confirm")

    confirmation_allowed = AITerminal.can_handle_input_during_turn(terminal, "可以继续") is True
    status_allowed = AITerminal.can_handle_input_during_turn(terminal, "/status") is True

    with terminal._ai_confirmation_lock:
        terminal._ai_confirmation = None
    plain_blocked = AITerminal.can_handle_input_during_turn(terminal, "普通消息") is False
    help_blocked = AITerminal.can_handle_input_during_turn(terminal, "/help") is False
    new_blocked = AITerminal.can_handle_input_during_turn(terminal, "/new thread") is False
    passed = confirmation_allowed and status_allowed and plain_blocked and help_blocked and new_blocked
    return _self_check_result(
        name="terminal_busy_turn_accepts_manual_confirmation_input",
        passed=passed,
        detail={
            "confirmation_allowed": confirmation_allowed,
            "status_allowed": status_allowed,
            "plain_blocked": plain_blocked,
            "help_blocked": help_blocked,
            "new_blocked": new_blocked,
        },
    )


def _check_ai_mode_manual_confirmation_dialog() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import (
        AITerminal,
        classify_ai_confirmation_reply,
    )

    terminal = object.__new__(AITerminal)
    terminal.events = []
    terminal._client_event_sink = terminal.events.append
    terminal.project_root = Path(".").resolve()
    terminal.model = SimpleNamespace(invoke=lambda messages: AIMessage(content='{"decision":"approve"}'))
    terminal._ai_confirmation_lock = __import__("threading").Lock()
    terminal._ai_confirmation = None
    terminal._ask_once_mode = False

    result: dict[str, Any] = {}

    def wait_for_confirmation() -> None:
        result["accepted"] = AITerminal._wait_for_ai_confirmation(
            terminal,
            "请确认页面状态。",
            wait_type="manual_confirm",
        )

    thread = __import__("threading").Thread(target=wait_for_confirmation)
    thread.start()
    for _ in range(100):
        if AITerminal._current_ai_confirmation(terminal) is not None:
            break
        __import__("time").sleep(0.01)
    waiting_ok = AITerminal._current_ai_confirmation(terminal) is not None
    AITerminal.handle_input(terminal, "页面看到了，可以继续导入")
    thread.join(timeout=2)
    continued_ok = result.get("accepted") is True and AITerminal._current_ai_confirmation(terminal) is None
    classifier_ok = (
        classify_ai_confirmation_reply("停止") == "reject"
        and classify_ai_confirmation_reply("继续") == "approve"
        and classify_ai_confirmation_reply("可以，继续") == "unclear"
        and classify_ai_confirmation_reply("页面没问题，你接着弄") == "unclear"
        and classify_ai_confirmation_reply("账户密码没有填写上呢") == "unclear"
        and classify_ai_confirmation_reply("exit") == "unclear"
        and classify_ai_confirmation_reply("我看一下") == "unclear"
    )
    model_classifier_ok = AITerminal._classify_ai_confirmation_reply(
        terminal,
        "页面没问题，你接着弄",
        SimpleNamespace(wait_type="manual_confirm", prompt="确认页面"),
    ) == "approve"
    return _self_check_result(
        name="ai_mode_manual_confirmation_uses_dialog",
        passed=waiting_ok and continued_ok and classifier_ok and model_classifier_ok,
        detail={
            "waiting_ok": waiting_ok,
            "accepted": result.get("accepted"),
            "classifier_ok": classifier_ok,
            "model_classifier_ok": model_classifier_ok,
            "events": [
                {"kind": event.kind, "text": event.text}
                for event in terminal.events
            ],
        },
    )


def _check_ai_active_turn_input_classifier_routes_feedback() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import (
        AITerminal,
        AIConfirmationWait,
        classify_ai_confirmation_reply,
    )

    responses = iter(
        [
            AIMessage(content='{"intent":"feedback_or_correction"}'),
            AIMessage(content='{"intent":"confirm_current_wait"}'),
            AIMessage(content='{"decision":"unclear"}'),
            AIMessage(content='{"intent":"feedback_or_correction"}'),
            AIMessage(content='{"decision":"unclear"}'),
        ]
    )
    terminal = object.__new__(AITerminal)
    terminal.model = SimpleNamespace(invoke=lambda messages: next(responses))
    terminal._ai_confirmation_lock = threading.Lock()
    terminal._ai_confirmation = AIConfirmationWait(prompt="请确认浏览器状态。", wait_type="manual_confirm")

    feedback_intent = AITerminal.classify_active_turn_input(terminal, "账户密码没有填写上呢")
    confirm_intent = AITerminal.classify_active_turn_input(terminal, "继续")
    unclear_decision = AITerminal.classify_wait_confirmation_reply(
        terminal,
        "账户密码没有填写上呢",
        prompt="请确认浏览器状态。",
        wait_type="manual_confirm",
    )
    natural_language_intent = AITerminal.classify_active_turn_input(terminal, "可以继续，账户密码还是没有填写上")
    natural_language_decision = AITerminal.classify_wait_confirmation_reply(
        terminal,
        "页面没问题，你接着弄",
        prompt="请确认浏览器状态。",
        wait_type="manual_confirm",
    )
    completed_login_intent = AITerminal.classify_active_turn_input(terminal, "已经登录进去了")
    completed_login_decision = AITerminal.classify_wait_confirmation_reply(
        terminal,
        "已经登录进去了",
        prompt="请填写验证码并登录后台。",
        wait_type="manual_confirm",
    )
    captured_classifier_messages: list[Any] = []

    def capture_contextual_classifier(messages: Any) -> AIMessage:
        captured_classifier_messages.append(messages)
        return AIMessage(content='{"intent":"confirm_current_wait"}')

    terminal.model = SimpleNamespace(invoke=capture_contextual_classifier)
    terminal._context_state = lambda: {
        "current_plan_path": "plans/explore-ai-account-management/plan.json",
        "latest_output_dir": "plans/explore-ai-account-management/output/latest",
        "work_plan_summary": "登录后台并提取 AI 账户名称",
    }
    contextual_intent = AITerminal.classify_active_turn_input(
        terminal,
        "现在就是你要求的那个状态",
        context={
            "client": {"status": "等待人工确认", "queued_count": 0},
            "active_wait": {"wait_type": "manual_confirm", "prompt": "请填写验证码并登录后台。"},
        },
    )
    classifier_context_text = str(captured_classifier_messages[-1][1][1]) if captured_classifier_messages else ""
    fallback_feedback = classify_ai_confirmation_reply("账户密码没有填写上呢")
    fallback_simple_continue = classify_ai_confirmation_reply("继续")
    fallback_mixed_continue = classify_ai_confirmation_reply("可以，继续")
    fallback_rich_sentence = classify_ai_confirmation_reply("页面没问题，你接着弄")
    fallback_problem_sentence = classify_ai_confirmation_reply("有问题，不对，账户密码没有填")
    passed = (
        feedback_intent == "feedback_or_correction"
        and confirm_intent == "confirm_current_wait"
        and unclear_decision == "unclear"
        and natural_language_intent == "feedback_or_correction"
        and natural_language_decision == "approve"
        and completed_login_intent == "confirm_current_wait"
        and completed_login_decision == "approve"
        and contextual_intent == "confirm_current_wait"
        and "等待上下文" in classifier_context_text
        and "plans/explore-ai-account-management/plan.json" in classifier_context_text
        and "请确认浏览器状态" in classifier_context_text
        and "queued_count" in classifier_context_text
        and fallback_feedback == "unclear"
        and fallback_simple_continue == "approve"
        and fallback_mixed_continue == "unclear"
        and fallback_rich_sentence == "unclear"
        and fallback_problem_sentence == "unclear"
    )
    return _self_check_result(
        name="ai_active_turn_input_classifier_routes_feedback",
        passed=passed,
        detail={
            "feedback_intent": feedback_intent,
            "confirm_intent": confirm_intent,
            "unclear_decision": unclear_decision,
            "natural_language_intent": natural_language_intent,
            "natural_language_decision": natural_language_decision,
            "completed_login_intent": completed_login_intent,
            "completed_login_decision": completed_login_decision,
            "contextual_intent": contextual_intent,
            "classifier_context_text": classifier_context_text,
            "fallback_feedback": fallback_feedback,
            "fallback_simple_continue": fallback_simple_continue,
            "fallback_mixed_continue": fallback_mixed_continue,
            "fallback_rich_sentence": fallback_rich_sentence,
            "fallback_problem_sentence": fallback_problem_sentence,
        },
    )


def _check_ai_ask_once_confirmation_times_out() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.events = []
    terminal._client_event_sink = terminal.events.append
    terminal.project_root = Path(".").resolve()
    terminal._ai_confirmation_lock = __import__("threading").Lock()
    terminal._ai_confirmation = None
    terminal._ask_once_mode = True

    started = time.monotonic()
    error = ""
    try:
        AITerminal._wait_for_ai_confirmation(
            terminal,
            "请在当前浏览器输入验证码。",
            wait_type="manual_confirm",
        )
    except Exception as exc:
        error = str(exc)
    elapsed = time.monotonic() - started
    return _self_check_result(
        name="ai_ask_once_manual_confirmation_returns_quickly",
        passed=(
            "脚本化 ai ask 不会等待人工操作" in error
            and "不能在进程结束后保留可继续接管的浏览器" in error
            and elapsed < 5
            and AITerminal._current_ai_confirmation(terminal) is None
        ),
        detail={
            "elapsed": round(elapsed, 3),
            "error": error,
            "events": [
                {"kind": event.kind, "text": event.text}
                for event in terminal.events
            ],
        },
    )


def _check_terminal_tool_progress_output() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.events = []
    terminal._client_event_sink = terminal.events.append

    AITerminal._print_tool_progress(
        terminal,
        "start",
        "inspect_web_page",
        {
            "url": "https://example.com/login",
            "headed": True,
            "_manual_confirmation_handler": object(),
            "_run_event_handler": object(),
        },
    )
    AITerminal._print_tool_progress(
        terminal,
        "done",
        "inspect_web_page",
        {"url": "https://example.com/login", "headed": True},
        {
            "ok": True,
            "resolved_url": "https://example.com/login",
            "page": {
                "title": "登录页面",
                "final_url": "https://example.com/login",
                "auth": {
                    "login_fields_detected": True,
                    "challenge_detected": True,
                },
            },
        },
    )
    AITerminal._print_tool_progress(
        terminal,
        "done",
        "grep_project_text",
        {"pattern": "工具进度", "root_path": ".", "file_glob": "*.md"},
        {"ok": True, "match_count": 0, "truncated": False},
    )
    AITerminal._print_tool_progress(
        terminal,
        "done",
        "run_plan",
        {"plan_path": "plans/demo/plan.json"},
        {"ok": False, "error": "示例失败原因"},
    )
    started_events = [event for event in terminal.events if event.kind == "tool_started"]
    finished_events = [event for event in terminal.events if event.kind == "tool_finished"]
    activity_events = [event for event in terminal.events if event.kind == "activity"]
    texts = "\n".join(event.text for event in terminal.events)
    return _self_check_result(
        name="terminal_tool_progress_events",
        passed=(
            len(started_events) == 1
            and len(finished_events) == 3
            and len(activity_events) == 4
            and activity_events[0].text == "调用工具 inspect_web_page"
            and activity_events[-1].data.get("phase") == "failed"
            and started_events[0].title == "inspect_web_page"
            and started_events[0].data.get("arguments", {}).get("url") == "https://example.com/login"
            and "_manual_confirmation_handler" not in texts
            and "_run_event_handler" not in texts
            and finished_events[0].title == "inspect_web_page"
            and finished_events[0].data.get("ok") is True
            and finished_events[0].data.get("phase") == "done"
            and "title=登录页面" in finished_events[0].text
            and "发现登录字段/验证信号" in finished_events[0].text
            and finished_events[1].title == "grep_project_text"
            and finished_events[1].text == "matches=0"
            and finished_events[2].title == "run_plan"
            and finished_events[2].data.get("ok") is False
            and finished_events[2].data.get("phase") == "failed"
            and finished_events[2].text == "status=failed error=示例失败原因"
        ),
        detail={
            "events": [
                {"kind": event.kind, "title": event.title, "text": event.text, "data": event.data}
                for event in terminal.events
            ]
        },
    )


def _check_terminal_work_plan_events() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.events = []
    terminal.context_updates = []
    terminal.synced = 0
    terminal._client_event_sink = terminal.events.append
    terminal._update_context_state = lambda update: terminal.context_updates.append(update)
    terminal._sync_current_session_index = lambda: setattr(terminal, "synced", terminal.synced + 1)

    result = {
        "ok": True,
        "summary": "创建真实网站 plan",
        "items": [
            {"title": "探测入口页面", "status": "completed"},
            {"title": "运行可见浏览器探索", "status": "in_progress"},
            {"title": "写入最终 plan", "status": "pending"},
        ],
        "total": 3,
        "completed": 1,
        "active": "运行可见浏览器探索",
    }
    AITerminal._after_tool_call(terminal, "update_work_plan", {"summary": "创建真实网站 plan"}, result)

    tool_events = [event for event in terminal.events if event.kind in {"tool_started", "tool_finished"}]
    plan_events = [event for event in terminal.events if event.kind == "work_plan_updated"]
    activity_events = [event for event in terminal.events if event.kind == "activity"]
    passed = (
        not tool_events
        and len(plan_events) == 1
        and len(activity_events) == 1
        and activity_events[0].text == "更新工作计划"
        and activity_events[0].data.get("category") == "plan"
        and plan_events[0].data.get("summary") == "创建真实网站 plan"
        and plan_events[0].data.get("items", [])[1].get("status") == "in_progress"
        and "当前工作计划：1/3 完成" in plan_events[0].text
        and terminal.context_updates
        and terminal.context_updates[-1]["work_plan_items"][1]["title"] == "运行可见浏览器探索"
        and terminal.synced == 1
    )
    return _self_check_result(
        name="terminal_work_plan_updates_are_structured_events",
        passed=passed,
        detail={
            "events": [
                {"kind": event.kind, "title": event.title, "text": event.text, "data": event.data}
                for event in terminal.events
            ],
            "context_updates": terminal.context_updates,
            "synced": terminal.synced,
        },
    )


def _check_terminal_file_change_followup_events() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    with TemporaryDirectory(prefix="ai-terminal-file-events-") as raw_temp_dir:
        temp_dir = Path(raw_temp_dir)
        patch_path = temp_dir / "patch.diff"
        patch_path.write_text(
            "\n".join(
                [
                    "diff --git a/plan.json b/plan.json",
                    "--- a/plan.json",
                    "+++ b/plan.json",
                    "@@ -1 +1 @@",
                    "-old",
                    "+new",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        terminal = object.__new__(AITerminal)
        terminal.events = []
        terminal._client_event_sink = terminal.events.append
        AITerminal._emit_tool_followup_events(
            terminal,
            "write_plan_package_file",
            {"plan_path": "plans/demo/plan.json", "relative_path": "docs/notes.md", "mode": "overwrite"},
            {
                "ok": True,
                "plan_path": "plans/demo/plan.json",
                "path": str(temp_dir / "plans" / "demo" / "docs" / "notes.md"),
                "relative_path": "docs/notes.md",
                "mode": "overwrite",
                "bytes": 42,
            },
        )
        AITerminal._emit_tool_followup_events(
            terminal,
            "export_local_file",
            {
                "target_path": str(temp_dir / "Downloads" / "AI账户.txt"),
                "plan_path": "plans/demo/plan.json",
                "source_output_path": "text/AI账户.txt",
                "mode": "overwrite",
            },
            {
                "ok": True,
                "path": str(temp_dir / "Downloads" / "AI账户.txt"),
                "target_path": str(temp_dir / "Downloads" / "AI账户.txt"),
                "source_path": str(temp_dir / "plans" / "demo" / "output" / "text" / "AI账户.txt"),
                "mode": "overwrite",
                "bytes": 128,
            },
        )
        AITerminal._emit_tool_followup_events(
            terminal,
            "generate_debug_patch",
            {"workspace": "workspace"},
            {
                "ok": True,
                "patch_path": str(patch_path),
                "patch_size": patch_path.stat().st_size,
                "result": {
                    "workspace_root": str(temp_dir),
                    "patch_path": str(patch_path),
                    "changed_files": ["plan.json"],
                    "applied": False,
                },
            },
        )
        AITerminal._emit_tool_followup_events(
            terminal,
            "run_plan",
            {"plan_path": "plans/demo/plan.json"},
            {"ok": True, "status": "passed", "output_dir": str(temp_dir / "output" / "run")},
        )
    file_events = [event for event in terminal.events if event.kind == "file_changed"]
    diff_events = [event for event in terminal.events if event.kind == "diff"]
    artifact_events = [event for event in terminal.events if event.kind == "artifact"]
    activity_events = [event for event in terminal.events if event.kind == "activity"]
    texts = "\n".join(event.text for event in terminal.events)
    return _self_check_result(
        name="terminal_file_change_diff_and_artifact_events",
        passed=(
            len(file_events) == 2
            and file_events[0].data.get("relative_path") == "docs/notes.md"
            and file_events[0].data.get("bytes") == 42
            and file_events[1].title == "export_local_file"
            and file_events[1].data.get("path", "").endswith("AI账户.txt")
            and file_events[1].data.get("bytes") == 128
            and len(diff_events) == 1
            and "diff --git" in diff_events[0].text
            and diff_events[0].data.get("changed_files") == ["plan.json"]
            and len(artifact_events) == 2
            and len(activity_events) == 5
            and {event.data.get("source_kind") for event in activity_events} == {"file_changed", "diff", "artifact"}
            and any(event.data.get("artifact_type") == "patch" for event in artifact_events)
            and any(event.data.get("artifact_type") == "output_dir" for event in artifact_events)
            and "文件 写入" in texts
            and "AI账户.txt" in texts
            and "输出目录" in texts
        ),
        detail={
            "events": [
                {"kind": event.kind, "title": event.title, "text": event.text, "data": event.data}
                for event in terminal.events
            ]
        },
    )


def _check_terminal_plan_run_progress_output() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.events = []
    terminal._client_event_sink = terminal.events.append

    AITerminal._handle_plan_run_event(
        terminal,
        "run_plan",
        {
            "level": "INFO",
            "message": "plan started",
            "fields": {"run_name": "login-smoke", "plan_path": "plans/demo/plan.json"},
        },
    )
    AITerminal._handle_plan_run_event(
        terminal,
        "run_plan",
        {
            "level": "INFO",
            "message": "step 1 start",
            "fields": {
                "step": 1,
                "action": "open_browser",
                "step_name": "open_browser",
                "step_summary": "name=main, headed=True",
            },
        },
    )
    AITerminal._handle_plan_run_event(
        terminal,
        "run_plan",
        {
            "level": "INFO",
            "message": "browser opened",
            "fields": {"browser": "main", "headed": True},
        },
    )
    AITerminal._handle_plan_run_event(
        terminal,
        "run_plan",
        {
            "level": "INFO",
            "message": "waiting for manual confirmation",
            "fields": {"prompt": "请完成登录"},
        },
    )
    AITerminal._handle_plan_run_event(
        terminal,
        "run_plan",
        {
            "level": "ERROR",
            "message": "step 2 failed",
            "fields": {
                "step": 2,
                "action": "element",
                "step_name": "fill account",
                "step_summary": "browser=main, type=fill, selector=#account",
                "error": "Timeout 15000ms exceeded",
            },
        },
    )
    events = list(terminal.events)
    plan_events = [event for event in events if event.kind == "plan_progress"]
    activity_events = [event for event in events if event.kind == "activity"]
    texts = "\n".join(event.text for event in plan_events)
    passed = (
        len(plan_events) == 5
        and len(activity_events) == 5
        and all(event.data.get("source_kind") == "plan_progress" for event in activity_events)
        and activity_events[-1].data.get("phase") == "failed"
        and "plan 开始" in texts
        and "步骤 1 开始" in texts
        and "浏览器已打开" in texts
        and "等待人工确认" in texts
        and "当前 Playwright 浏览器" in texts
        and "步骤 2 失败" in texts
        and "Timeout 15000ms exceeded" in texts
    )
    return _self_check_result(
        name="terminal_plan_run_progress_events",
        passed=passed,
        detail={
            "events": [
                {"kind": event.kind, "title": event.title, "text": event.text}
                for event in events
            ]
        },
    )



class _FakeTerminal(AITerminalCommandsMixin):
    def __init__(
        self,
        *,
        project_root: Path,
        checkpointer: SqliteSaver,
        messages_by_thread: dict[str, list[Any]],
    ) -> None:
        self.project_root = project_root
        self.config = SimpleNamespace(
            service_name="default",
            service_config={"model": "fake-model", "api_key": "test-api-key"},
        )
        self.model_name = "fake-model"
        self.graph_recursion_limit = 128
        self.thread_id = "alpha"
        self.checkpoint_path = project_root / ".keygen" / "ai-terminal-checkpoints.sqlite"
        self.checkpointer = checkpointer
        self._messages_by_thread = messages_by_thread
        self._current_turn_text = None
        self._current_turn_id = 1
        self._cancelled_turn_ids: set[int] = set()
        self._last_error = "previous model error"
        self._approval_resume_active = False
        self._has_interrupts = False
        self._pending_attachments: list[Any] = []
        self._pending_attachment_placeholder_required: list[bool] = []
        self.outputs: list[str] = []
        self.errors: list[str] = []

    def _emit_system_output(self, value: Any) -> None:
        self.outputs.append(str(value))

    def _emit_error(self, value: Any) -> None:
        self.errors.append(format_error_for_terminal(value, project_root=self.project_root))

    def _clear_pending_attachments(self) -> None:
        self._pending_attachments.clear()
        self._pending_attachment_placeholder_required.clear()

    def status_payload(self) -> dict[str, Any]:
        self.do_status("")
        return json.loads(self.outputs[-1])

    def _current_messages(self) -> list[Any]:
        return list(self._messages_by_thread.get(self.thread_id, []))

    def _current_interrupts(self) -> tuple[Any, ...]:
        if self._has_interrupts:
            return (object(),)
        return ()

    def _context_state(self) -> dict[str, Any]:
        return {"current_plan_path": "plans/minimal-browser-plan/plan.json"}

    def _work_plan_state(self) -> dict[str, Any]:
        return {"items": [], "summary": ""}

    def _compress_current_thread(self, *, reason: str = "manual") -> dict[str, Any]:
        return {
            "ok": True,
            "compressed": False,
            "reason": reason,
            "thread_id": self.thread_id,
        }

    def _sync_current_session_index(self) -> None:
        update_ai_terminal_session_index(self.project_root, self.checkpointer, self.thread_id)

    def _is_agent_busy(self) -> bool:
        return self._current_turn_text is not None

    def _cancel_agent_turn(self) -> bool:
        if self._current_turn_text is None:
            return False
        self._cancelled_turn_ids.add(self._current_turn_id)
        self._current_turn_text = None
        return True


def _check_busy_command_guard() -> tuple[bool, dict[str, Any]]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.errors = []
    terminal.forwarded_lines = []
    terminal._busy = True
    terminal._is_agent_busy = lambda: terminal._busy
    terminal._emit_error = lambda value: terminal.errors.append(format_error_for_terminal(value, project_root=Path.cwd()))
    terminal.handle_user_request = lambda line: terminal.forwarded_lines.append(str(line))
    terminal.do_status = lambda arg: terminal.forwarded_lines.append("/status")

    plain_text_while_busy = AITerminal.handle_input(terminal, "new blocked-thread")
    blocked_stop = AITerminal.handle_input(terminal, "/new blocked-thread")
    blocked_error = terminal.errors[-1] if terminal.errors else ""
    allowed_status = AITerminal.handle_input(terminal, "/status")

    allowed = {
        "status": AITerminal._command_allowed_while_busy(terminal, "status"),
        "/status": AITerminal._command_allowed_while_busy(terminal, "/status"),
        "/plan": AITerminal._command_allowed_while_busy(terminal, "/plan"),
        "/new": AITerminal._command_allowed_while_busy(terminal, "/new blocked-thread"),
        "/exit": AITerminal._command_allowed_while_busy(terminal, "/exit"),
    }
    passed = (
        plain_text_while_busy is False
        and blocked_stop is False
        and allowed_status is False
        and "等待当前回复完成" in blocked_error
        and terminal.forwarded_lines == ["/status"]
        and not allowed["status"]
        and allowed["/status"]
        and allowed["/plan"]
        and not allowed["/new"]
        and not allowed["/exit"]
    )
    return passed, {
        "blocked_error": blocked_error,
        "forwarded_lines": terminal.forwarded_lines,
        "allowed": allowed,
    }


def _put_checkpoint(
    checkpointer: SqliteSaver,
    *,
    thread_id: str,
    checkpoint_id: str,
    messages: list[Any],
    extra_values: dict[str, Any] | None = None,
) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["ts"] = f"2026-05-10T00:00:0{checkpoint_id[-1]}+00:00"
    checkpoint["channel_values"] = {"messages": messages, **(extra_values or {})}
    checkpointer.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        checkpoint,
        {"source": "self-check", "step": 1, "writes": {}},
        {},
    )


def _write_1x1_png(path: Path) -> None:
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6360000002000100ffff03000006000557bfab440000000049454e44ae426082"
        )
    )


def _is_openai_chat_image_message(message: dict[str, Any]) -> bool:
    if set(message) != {"content", "role"}:
        return False
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list) or len(content) != 2:
        return False
    text_part, image_part = content
    if not isinstance(text_part, dict) or set(text_part) != {"type", "text"}:
        return False
    if text_part.get("type") != "text" or not isinstance(text_part.get("text"), str):
        return False
    if not isinstance(image_part, dict) or set(image_part) != {"type", "image_url"}:
        return False
    if image_part.get("type") != "image_url":
        return False
    image_url = image_part.get("image_url")
    if not isinstance(image_url, dict) or set(image_url) != {"url"}:
        return False
    url = image_url.get("url")
    return isinstance(url, str) and url.startswith("data:image/")


def _self_check_result(*, name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "detail": detail or {},
    }
