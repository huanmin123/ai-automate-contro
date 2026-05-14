from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
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
from ai_automate_contro.ai.terminal_commands import format_keyboard_shortcuts_for_terminal
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
            [human_message, AIMessage(content="ok")],
            summary="summary",
            reason="self-check",
        )
        archived_text = archive.messages_path.read_text(encoding="utf-8")
        checks.append(
            _self_check_result(
                name="compression_archive_redacts_image_data_urls",
                passed="data:image/" not in archived_text and "ai_terminal_image_attachments" in archived_text,
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

        redacted = redact_image_data_urls({"image": "data:image/png;base64,AAAA"})
        checks.append(
            _self_check_result(
                name="data_url_redaction",
                passed=redacted["image"].startswith("<redacted image data URL"),
                detail=redacted,
            )
        )

        checks.append(_check_terminal_prompt_strategy())
        checks.append(_check_terminal_context_suffix_contract())
        checks.extend(_check_session_listing(human_message))
        checks.extend(_check_terminal_command_flow(storage_root, human_message))
        checks.extend(_check_terminal_input_widgets(attachment))
        checks.append(_check_terminal_markdown_rendering())
        checks.append(_check_terminal_streaming_output())
        checks.append(_check_terminal_streaming_interrupt_drains_safely())
        checks.append(_check_terminal_structured_event_stream())
        checks.append(_check_terminal_busy_confirmation_route())
        checks.append(_check_ai_mode_manual_confirmation_dialog())
        checks.append(_check_terminal_tool_progress_output())
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
        "浏览器本地页面优先使用 {{resources_file_url}}",
        "不要硬编码本机绝对 file URL",
        "写最终 plan.json 前必须先跑通流程证据",
        "第一步用 inspect_web_page 获取入口页面证据",
        "open_browser.headed=true",
        "让用户在同一个 Playwright 浏览器窗口里完成操作",
        "不要让用户去自己浏览器打开页面",
        "用户提供的截图或 HTML 只能作为辅助证据",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    section_order = [
        "你的职责：",
        "边界：",
        "开工前判断：",
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
    ]
    positions = {field: context.find(field) for field in expected_order}
    order_ok = all(position >= 0 for position in positions.values()) and list(positions.values()) == sorted(positions.values())
    ignored_unknown = "ignored_dynamic_noise" not in context and "should not appear" not in context
    guidance_ok = "优先使用这些上下文" in context and "先读取压缩摘要" in context
    return _self_check_result(
        name="terminal_context_suffix_is_stable_and_bounded",
        passed=empty_context == "" and context == repeated_context and order_ok and ignored_unknown and guidance_ok,
        detail={
            "empty_context": empty_context,
            "field_positions": positions,
            "ignored_unknown": ignored_unknown,
            "guidance_ok": guidance_ok,
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
    formatted_usage = format_error_for_terminal("用法：/history [limit]", project_root=project_root)
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
    outputs = {
        "usage": formatted_usage,
        "unknown_command": formatted_unknown_command,
        "no_run": formatted_no_run,
        "user_error": formatted_user_error,
        "external_ai_error": formatted_external_ai_error,
    }
    passed = (
        "命令用法不正确" in formatted_usage
        and "未知 AI 终端命令：/attach" in formatted_unknown_command
        and "当前没有正在运行或等待的 plan" in formatted_no_run
        and "AI 终端服务未配置：default" in formatted_user_error
        and formatted_external_ai_error == "错误：Error code: 503 - upstream unavailable"
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
            update_ai_terminal_session_index(index_root, checkpointer, "alpha")
            indexed_sessions = list_ai_terminal_sessions(checkpointer, project_root=index_root, limit=10)
            indexed_resolved = resolve_ai_terminal_session(checkpointer, "alpha", project_root=index_root)
            remove_ai_terminal_session_from_index(index_root, "alpha")
            index_exists_after_remove = session_index_path(index_root).exists()
            index_after_remove_payload = json.loads(session_index_path(index_root).read_text(encoding="utf-8"))
            index_after_remove_threads = [
                str(session.get("thread_id"))
                for session in index_after_remove_payload.get("sessions", [])
                if isinstance(session, dict)
            ]
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
                    and all(thread_id != "alpha" for thread_id in index_after_remove_threads)
                ),
                detail={
                    "index_path": str(session_index_path(index_root)),
                    "indexed_threads": [session.thread_id for session in indexed_sessions],
                    "after_remove_threads": index_after_remove_threads,
                    "index_exists_after_remove": index_exists_after_remove,
                    "resolved": indexed_resolved,
                },
            ),
        ]
    finally:
        connection.close()


def _check_terminal_command_flow(project_root: Path, human_message: HumanMessage) -> list[dict[str, Any]]:
    from ai_automate_contro.ai.terminal import AITerminal

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
            and terminal.outputs[-2] == "AI 终端线程：image-thread"
        )

        terminal.do_new("flow-thread")
        new_ok = terminal.thread_id == "flow-thread" and terminal.outputs[-1] == "AI 终端线程：flow-thread"

        slash_ok = AITerminal._handle_slash_command(terminal, "/status") is True
        slash_status_payload = json.loads(terminal.outputs[-1])
        slash_ok = slash_ok and slash_status_payload["thread_id"] == "flow-thread"
        keyboard_command_ok = (
            AITerminal._handle_slash_command(terminal, "/keyboard") is True
            and "AI 终端键盘快捷键：" in terminal.outputs[-1]
        )
        mac_keyboard_text = format_keyboard_shortcuts_for_terminal("Darwin")
        windows_keyboard_text = format_keyboard_shortcuts_for_terminal("Windows")
        keyboard_platform_ok = (
            "Enter" in mac_keyboard_text
            and "Control+J" in mac_keyboard_text
            and "Control+Q / Control+C" in mac_keyboard_text
            and "Textual 客户端" in mac_keyboard_text
            and "Windows" not in mac_keyboard_text
            and "Ctrl+J" in windows_keyboard_text
            and "Ctrl+Q / Ctrl+C" in windows_keyboard_text
            and "Control+Q" not in windows_keyboard_text
        )

        terminal.do_help("")
        help_text = terminal.outputs[-1]
        terminal.do_render("")
        render_status_ok = terminal.outputs[-1] == "AI 回复显示方式：plain"
        terminal.do_render("markdown")
        render_markdown_ok = (
            terminal.response_render_mode == "markdown"
            and terminal.outputs[-1] == "AI 回复显示方式：markdown"
        )
        terminal.do_render("plain")
        render_plain_ok = (
            terminal.response_render_mode == "plain"
            and terminal.outputs[-1] == "AI 回复显示方式：plain"
        )
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
        image_surface_ok = (
            "attach list" not in help_text
            and "attach remove" not in help_text
            and "attach clear" not in help_text
            and "/attach" not in help_text
            and "/paste-image" not in help_text
            and "paste_image" not in help_text
            and "cancel" not in help_text
            and "run_context" not in help_text
            and "tools [name]" not in help_text
            and "context" not in help_text
            and "  status" not in help_text
            and plain_status_message_ok
            and mid_slash_message_ok
            and leading_space_message_ok
            and bad_slash_format
            and "命令名必须以英文字母开头" in bad_slash_error
            and slash_attach_unknown
            and "未知 AI 终端命令：/attach" in slash_attach_error
            and slash_paste_unknown
            and "未知 AI 终端命令：/paste-image" in slash_paste_error
            and slash_run_context_unknown
            and "未知 AI 终端命令：/run_context" in slash_run_context_error
            and slash_context_unknown
            and "未知 AI 终端命令：/context" in slash_context_error
        )

        busy_guard_ok, busy_guard_detail = _check_busy_command_guard()

        terminal.do_compress("flow-check")
        compress_payload = json.loads(terminal.outputs[-1])
        compress_ok = compress_payload == {
            "ok": True,
            "compressed": False,
            "reason": "flow-check",
            "thread_id": "flow-thread",
        }
        ask_once_guard_ok = False
        ask_once_error = ""
        terminal._has_interrupts = True
        try:
            AITerminal.ask_once(terminal, "continue")
        except Exception as error:
            ask_once_error = str(error)
            ask_once_guard_ok = "pending approval" in ask_once_error or "等待审批" in ask_once_error
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
                name="terminal_keyboard_command_describes_shortcuts",
                passed=keyboard_command_ok and keyboard_platform_ok and "keyboard" in help_text and "Alt+V" not in help_text,
                detail={
                    "keyboard_command_ok": keyboard_command_ok,
                    "mac_mentions_control": "Control+Q / Control+C" in mac_keyboard_text,
                    "windows_mentions_ctrl": "Ctrl+Q / Ctrl+C" in windows_keyboard_text,
                    "help_mentions_keyboard": "keyboard" in help_text,
                    "help_mentions_inline_paste": "Alt+V" in help_text,
                },
            ),
            _self_check_result(
                name="terminal_image_command_surface_is_low_friction",
                passed=image_surface_ok,
                detail={
                    "help_mentions_keyboard": "keyboard" in help_text,
                    "plain_status_messages": terminal.forwarded_messages,
                    "bad_slash_error": bad_slash_error,
                    "slash_attach_error": slash_attach_error,
                    "slash_paste_error": slash_paste_error,
                    "slash_run_context_error": slash_run_context_error,
                    "slash_context_error": slash_context_error,
                },
            ),
            _self_check_result(
                name="terminal_render_command_switches_display_layer",
                passed=render_status_ok and render_markdown_ok and render_plain_ok and "/render [markdown|plain]" in help_text,
                detail={
                    "render_status_ok": render_status_ok,
                    "render_markdown_ok": render_markdown_ok,
                    "render_plain_ok": render_plain_ok,
                    "mode": terminal.response_render_mode,
                },
            ),
            _self_check_result(
                name="terminal_busy_command_guard",
                passed=busy_guard_ok,
                detail=busy_guard_detail,
            ),
            _self_check_result(
                name="terminal_compress_command_uses_current_thread",
                passed=compress_ok,
                detail=compress_payload,
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


def _check_terminal_markdown_rendering() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal
    from ai_automate_contro.ai.terminal_markdown import (
        normalize_response_render_mode,
        render_markdown_to_ansi,
        terminal_supports_rich_markdown,
    )

    markdown_text = "# 标题\n\n**重点**\n\n```python\nprint('ok')\n```"
    rendered = render_markdown_to_ansi(markdown_text, width=80)

    terminal = object.__new__(AITerminal)
    terminal.response_render_mode = "markdown"
    captured: list[str] = []
    import builtins

    original_print = builtins.print
    import ai_automate_contro.ai.terminal as terminal_module

    original_supports_markdown = terminal_module.terminal_supports_rich_markdown
    try:
        terminal_module.terminal_supports_rich_markdown = lambda: True
        builtins.print = lambda *args, **kwargs: captured.append(
            "".join(str(arg) for arg in args) + ("" if kwargs.get("end") == "" else "\n")
        )
        AITerminal._emit_assistant_message(terminal, markdown_text)
    finally:
        terminal_module.terminal_supports_rich_markdown = original_supports_markdown
        builtins.print = original_print

    captured_text = "".join(captured)
    plain_fallback_captured: list[str] = []
    try:
        terminal.response_render_mode = "markdown"
        terminal_module.terminal_supports_rich_markdown = lambda: False
        builtins.print = lambda *args, **kwargs: plain_fallback_captured.append(
            "".join(str(arg) for arg in args) + ("" if kwargs.get("end") == "" else "\n")
        )
        AITerminal._emit_assistant_message(terminal, markdown_text)
    finally:
        terminal_module.terminal_supports_rich_markdown = original_supports_markdown
        builtins.print = original_print
    plain_fallback_text = "".join(plain_fallback_captured)

    import io

    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    env_keys = ["NO_COLOR", "TERM", "CLICOLOR", "CLICOLOR_FORCE"]
    original_env = {key: os.environ.get(key) for key in env_keys}
    try:
        os.environ["NO_COLOR"] = "1"
        os.environ["TERM"] = "xterm-256color"
        os.environ.pop("CLICOLOR", None)
        os.environ.pop("CLICOLOR_FORCE", None)
        no_color_disables_markdown = terminal_supports_rich_markdown(FakeTTY()) is False
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    terminal.response_render_mode = "plain"
    plain_should_not_render = AITerminal._should_render_final_markdown(terminal) is False
    old_ai_prefix = "› " + "AI"
    plain_fallback_ok = (
        plain_fallback_text == f"{markdown_text}\n"
        and "\x1b[" not in plain_fallback_text
        and old_ai_prefix not in plain_fallback_text
    )
    passed = (
        normalize_response_render_mode("md") == "markdown"
        and normalize_response_render_mode("raw") == "plain"
        and no_color_disables_markdown
        and "标题" in rendered
        and "重点" in rendered
        and "print" in rendered
        and "\x1b[48;" not in rendered
        and "\x1b[40m" not in rendered
        and "\x1b[47m" not in rendered
        and "\x1b[100m" not in rendered
        and "\x1b[107m" not in rendered
        and "\x1b[7m" not in rendered
        and "\x1b[27m" not in rendered
        and old_ai_prefix not in captured_text
        and "标题" in captured_text
        and markdown_text not in captured_text
        and plain_should_not_render
        and plain_fallback_ok
    )
    return _self_check_result(
        name="terminal_markdown_rendering_is_display_only",
        passed=passed,
        detail={
            "rendered_chars": len(rendered),
            "captured_prefix": captured_text[:80],
            "plain_fallback_prefix": plain_fallback_text[:80],
            "plain_fallback_ok": plain_fallback_ok,
            "no_color_disables_markdown": no_color_disables_markdown,
            "mode_md": normalize_response_render_mode("md"),
            "mode_raw": normalize_response_render_mode("raw"),
            "plain_should_not_render": plain_should_not_render,
        },
    )


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
    terminal.response_render_mode = "plain"
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
    terminal.response_render_mode = "plain"
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
            and rendered == "前半\n"
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
    terminal.response_render_mode = "markdown"
    terminal.events = []
    terminal.commands: list[str] = []
    terminal.handle_input = lambda line: terminal.commands.append(str(line)) or (str(line).strip() == "/exit")
    terminal._client_event_sink = None

    AITerminal.run_client_turn(terminal, "创建 plan", terminal.events.append)
    first_turn_mode_restored = terminal.response_render_mode == "markdown"

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

    AITerminal.run_client_turn(terminal, "/exit", terminal.events.append)

    kinds = [event.kind for event in terminal.events]
    user_message_suppressed = all(event.text != "用户消息" for event in terminal.events)
    passed = (
        terminal.commands == ["创建 plan", "/exit"]
        and first_turn_mode_restored
        and user_message_suppressed
        and kinds.count("assistant_delta") == 2
        and kinds.count("assistant_done") == 2
        and "status" in kinds
        and "tool_started" in kinds
        and "tool_finished" in kinds
        and "exit_requested" in kinds
    )
    return _self_check_result(
        name="terminal_structured_event_stream_for_textual_client",
        passed=passed,
        detail={
            "commands": terminal.commands,
            "kinds": kinds,
            "texts": [event.text for event in terminal.events],
            "mode_restored": first_turn_mode_restored,
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
    help_allowed = AITerminal.can_handle_input_during_turn(terminal, "/help") is True
    new_blocked = AITerminal.can_handle_input_during_turn(terminal, "/new thread") is False
    passed = confirmation_allowed and status_allowed and plain_blocked and help_allowed and new_blocked
    return _self_check_result(
        name="terminal_busy_turn_accepts_manual_confirmation_input",
        passed=passed,
        detail={
            "confirmation_allowed": confirmation_allowed,
            "status_allowed": status_allowed,
            "plain_blocked": plain_blocked,
            "help_allowed": help_allowed,
            "new_blocked": new_blocked,
        },
    )


def _check_ai_mode_manual_confirmation_dialog() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import (
        AITerminal,
        classify_ai_confirmation_reply,
    )

    terminal = object.__new__(AITerminal)
    terminal.outputs: list[str] = []
    terminal._emit_terminal_output = lambda value: terminal.outputs.append(str(value))
    terminal.project_root = Path(".").resolve()
    terminal.model = SimpleNamespace(invoke=lambda messages: AIMessage(content='{"decision":"approve"}'))
    terminal._ai_confirmation_lock = __import__("threading").Lock()
    terminal._ai_confirmation = None

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
        classify_ai_confirmation_reply("别继续了，取消") == "reject"
        and classify_ai_confirmation_reply("可以，继续") == "approve"
        and classify_ai_confirmation_reply("页面没问题，你接着弄") == "approve"
        and classify_ai_confirmation_reply("exit") == "reject"
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
            "outputs": terminal.outputs,
        },
    )


def _check_terminal_tool_progress_output() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal

    terminal = object.__new__(AITerminal)
    terminal.outputs: list[str] = []
    terminal._emit_terminal_output = lambda value: terminal.outputs.append(str(value))

    AITerminal._print_tool_progress(
        terminal,
        "start",
        "inspect_web_page",
        {"url": "https://example.com/login", "headed": True, "_manual_confirmation_handler": object()},
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
    output = "\n".join(terminal.outputs)
    return _self_check_result(
        name="terminal_tool_progress_output",
        passed=(
            "调用工具 inspect_web_page" in output
            and "url=https://example.com/login" in output
            and "_manual_confirmation_handler" not in output
            and "工具 inspect_web_page 完成" in output
            and "title=登录页面" in output
            and "发现登录字段/验证信号" in output
            and "工具 grep_project_text 完成：matches=0" in output
            and "工具 run_plan 失败：status=failed，error=示例失败原因" in output
        ),
        detail={"outputs": terminal.outputs},
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
            service_config={"model": "fake-model", "api_key": "fake-key"},
        )
        self.model_name = "fake-model"
        self.graph_recursion_limit = 128
        self.thread_id = "alpha"
        self.response_render_mode = "plain"
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

    def _emit_terminal_output(self, value: Any) -> None:
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

    def _context_state(self) -> dict[str, str]:
        return {"current_plan_path": "plans/minimal-browser-plan/plan.json"}

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
        "help": AITerminal._command_allowed_while_busy(terminal, "help"),
        "/help": AITerminal._command_allowed_while_busy(terminal, "/help"),
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
        and not allowed["help"]
        and allowed["/help"]
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
