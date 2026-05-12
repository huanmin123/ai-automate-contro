from __future__ import annotations

import json
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

        redacted = redact_image_data_urls({"image": "data:image/png;base64,AAAA"})
        checks.append(
            _self_check_result(
                name="legacy_data_url_redaction",
                passed=redacted["image"].startswith("<redacted image data URL"),
                detail=redacted,
            )
        )

        checks.extend(_check_session_listing(human_message))
        checks.extend(_check_terminal_command_flow(storage_root, human_message))
        checks.extend(_check_terminal_input_widgets(attachment))
        checks.append(_check_terminal_markdown_rendering())
        checks.append(_check_terminal_streaming_output())
        checks.append(_check_terminal_user_message_echo())
        checks.append(_check_terminal_multiline_input_formatting())
        checks.extend(_check_unified_terminal_mode_switch(storage_root))
        checks.append(_check_missing_ai_config_is_user_facing(temp_dir))
        checks.append(_check_terminal_error_formatting(storage_root))

    return {
        "ok": all(check["passed"] for check in checks),
        "check": "ai_terminal_state",
        "project_root": str(resolved_project_root),
        "checks": checks,
    }


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
    formatted_usage = format_error_for_terminal("用法：history [limit]", project_root=project_root)
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
        terminal.do_cancel("")
        cancel_output = terminal.outputs[-1]
        cancel_ok = cancel_output == "取消：已清理残留的 AI 等待状态。" and terminal._current_turn_text is None

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
        plain_question_help = AITerminal.onecmd(terminal, "?") is False and terminal.outputs[-1].startswith("AI 终端命令：")
        slash_attach_unknown = AITerminal._handle_slash_command(terminal, "/attach list") is True
        slash_attach_error = terminal.errors[-1] if terminal.errors else ""
        slash_paste_unknown = AITerminal._handle_slash_command(terminal, "/paste-image") is True
        slash_paste_error = terminal.errors[-1] if terminal.errors else ""
        image_surface_ok = (
            "attach list" not in help_text
            and "attach remove" not in help_text
            and "attach clear" not in help_text
            and "/attach" not in help_text
            and "/paste-image" not in help_text
            and "paste_image" not in help_text
            and plain_question_help
            and slash_attach_unknown
            and "未知 AI 终端命令：/attach" in slash_attach_error
            and slash_paste_unknown
            and "未知 AI 终端命令：/paste-image" in slash_paste_error
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
                name="terminal_cancel_command_clears_stale_turn_state",
                passed=cancel_ok,
                detail={
                    "cancel_output": cancel_output,
                    "current_turn_text": terminal._current_turn_text,
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
                name="terminal_image_command_surface_is_low_friction",
                passed=image_surface_ok,
                detail={
                    "help_mentions_alt_v": "Alt+V" in help_text,
                    "slash_attach_error": slash_attach_error,
                    "slash_paste_error": slash_paste_error,
                },
            ),
            _self_check_result(
                name="terminal_render_command_switches_display_layer",
                passed=render_status_ok and render_markdown_ok and render_plain_ok and "render [markdown|plain]" in help_text,
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
    from prompt_toolkit.document import Document

    from ai_automate_contro.ai.terminal import (
        IMAGE_PLACEHOLDER_STYLE,
        ImagePlaceholderLexer,
        SlashCommandCompleter,
        _is_slash_completion_context,
        reconcile_image_placeholders,
        reconcile_pending_image_attachments,
        remove_image_placeholder_near_cursor,
        select_completion_candidate,
        snap_cursor_out_of_image_placeholder,
        style_image_placeholders,
    )

    completions_for_slash = list(SlashCommandCompleter().get_completions(Document("/"), None))
    completions_for_prefix = list(SlashCommandCompleter().get_completions(Document("/s"), None))
    slash_completion_ok = (
        any(completion.text == "/status" for completion in completions_for_slash)
        and any(completion.text == "/sessions" for completion in completions_for_prefix)
        and all(completion.text.startswith("/s") for completion in completions_for_prefix)
        and _is_slash_completion_context("/", 1)
        and _is_slash_completion_context("/s", 2)
        and not _is_slash_completion_context("text /", 6)
        and not _is_slash_completion_context("/status now", 11)
    )

    placeholder_1 = image_attachment_placeholder(1)
    placeholder_2 = image_attachment_placeholder(2)
    styled = style_image_placeholders(f"看 {placeholder_1} 这里")
    lexer_line = ImagePlaceholderLexer().lex_document(Document(f"看 {placeholder_1} 这里"))(0)
    style_ok = (
        (IMAGE_PLACEHOLDER_STYLE, placeholder_1) in styled
        and (IMAGE_PLACEHOLDER_STYLE, placeholder_1) in lexer_line
    )

    first = attachment
    second = attachment
    buffer = SimpleNamespace(text=f"{placeholder_1} 然后 {placeholder_2}", cursor_position=len(placeholder_1))
    attachments = [first, second]
    deleted = remove_image_placeholder_near_cursor(buffer, attachments, prefer_before=True)
    delete_ok = (
        deleted
        and buffer.text == f" 然后 {placeholder_1}"
        and buffer.cursor_position == 0
        and attachments == [second]
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
    snap_text = f"前面 {placeholder_1} 后面"
    snap_start = snap_text.index(placeholder_1)
    snap_end = snap_start + len(placeholder_1)
    snap_ok = (
        snap_cursor_out_of_image_placeholder(snap_text, snap_start + 2, previous_cursor=snap_start) == snap_end
        and snap_cursor_out_of_image_placeholder(snap_text, snap_end - 2, previous_cursor=snap_end) == snap_start
        and snap_cursor_out_of_image_placeholder(snap_text, snap_start - 1, previous_cursor=snap_start - 2) == snap_start - 1
    )

    class FakeCompletionState:
        def __init__(self) -> None:
            self.completions = ["one", "two"]
            self.complete_index = None

        @property
        def current_completion(self) -> str | None:
            if self.complete_index is None:
                return None
            return self.completions[self.complete_index]

    completion_state = FakeCompletionState()
    completion_buffer = SimpleNamespace(
        complete_state=completion_state,
        go_to_completion=lambda index: setattr(completion_state, "complete_index", index),
        complete_previous=lambda: setattr(completion_state, "complete_index", max(0, completion_state.complete_index - 1)),
        complete_next=lambda: setattr(
            completion_state,
            "complete_index",
            min(len(completion_state.completions) - 1, completion_state.complete_index + 1),
        ),
    )
    completion_ok = (
        select_completion_candidate(completion_buffer, previous=False)
        and completion_state.complete_index == 0
        and select_completion_candidate(completion_buffer, previous=False)
        and completion_state.complete_index == 1
        and select_completion_candidate(completion_buffer, previous=True)
        and completion_state.complete_index == 0
    )

    return [
        _self_check_result(
            name="terminal_slash_completion_suggests_commands",
            passed=slash_completion_ok and completion_ok,
            detail={
                "slash": [completion.text for completion in completions_for_slash],
                "prefix": [completion.text for completion in completions_for_prefix],
                "completion_index": completion_state.complete_index,
            },
        ),
        _self_check_result(
            name="terminal_image_placeholder_is_highlighted",
            passed=style_ok,
            detail={"styled": styled, "lexer_line": lexer_line},
        ),
        _self_check_result(
            name="terminal_image_placeholder_deletes_as_unit",
            passed=delete_ok and no_placeholder_ok and submit_filter_ok,
            detail={
                "deleted": deleted,
                "text": buffer.text,
                "attachments": len(attachments),
                "no_placeholder_attachments": len(no_placeholder_attachments),
                "submit_filter_attachments": len(submit_attachments),
            },
        ),
        _self_check_result(
            name="terminal_image_placeholder_cursor_skips_body",
            passed=snap_ok,
            detail={"text": snap_text, "start": snap_start, "end": snap_end},
        ),
    ]


def _check_terminal_markdown_rendering() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal
    from ai_automate_contro.ai.terminal_markdown import normalize_response_render_mode, render_markdown_to_ansi

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
        AITerminal._print_assistant_message(terminal, markdown_text)
    finally:
        terminal_module.terminal_supports_rich_markdown = original_supports_markdown
        builtins.print = original_print

    captured_text = "".join(captured)
    terminal.response_render_mode = "plain"
    plain_should_not_render = AITerminal._should_render_final_markdown(terminal) is False
    passed = (
        normalize_response_render_mode("md") == "markdown"
        and normalize_response_render_mode("raw") == "plain"
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
        and captured_text.startswith("AI>\n")
        and markdown_text not in captured_text
        and plain_should_not_render
    )
    return _self_check_result(
        name="terminal_markdown_rendering_is_display_only",
        passed=passed,
        detail={
            "rendered_chars": len(rendered),
            "captured_prefix": captured_text[:80],
            "mode_md": normalize_response_render_mode("md"),
            "mode_raw": normalize_response_render_mode("raw"),
            "plain_should_not_render": plain_should_not_render,
        },
    )


def _check_terminal_streaming_output() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal, format_user_terminal_message

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
            and rendered == "AI> 流式输出\n"
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


def _check_terminal_user_message_echo() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import AITerminal, format_user_terminal_message

    terminal = object.__new__(AITerminal)
    terminal.outputs: list[str] = []
    terminal.poutput = lambda value: terminal.outputs.append(str(value))
    placeholder = image_attachment_placeholder(1)
    AITerminal._print_user_message(terminal, f"第一行\n{placeholder} 第二行")
    expected = f"你> 第一行\n... {placeholder} 第二行"
    return _self_check_result(
        name="terminal_user_message_echo",
        passed=terminal.outputs == [expected],
        detail={
            "outputs": terminal.outputs,
            "formatted": format_user_terminal_message(f"第一行\n{placeholder} 第二行"),
        },
    )


def _check_terminal_multiline_input_formatting() -> dict[str, Any]:
    from ai_automate_contro.ai.terminal import format_user_terminal_message

    formatted = format_user_terminal_message("第一行\n第二行\n第三行")
    return _self_check_result(
        name="terminal_multiline_input_formatting",
        passed=formatted == "第一行\n... 第二行\n... 第三行",
        detail={"formatted": formatted},
    )


def _check_unified_terminal_mode_switch(project_root: Path) -> list[dict[str, Any]]:
    from prompt_toolkit.document import Document

    from ai_automate_contro.app.management_terminal import (
        ManagementTerminal,
        PlanCommandCompleter,
        _is_plan_completion_context,
        _repair_piped_stdin_text,
    )

    terminal = ManagementTerminal(project_root)
    terminal.outputs = []
    terminal.poutput = lambda value: terminal.outputs.append(str(value))
    lazy_ok = terminal.mode == "plan" and terminal._ai_terminal is None and terminal.prompt == "plan> "

    fake_ai = SimpleNamespace(
        lines=[],
        closed=False,
        onecmd=lambda line: fake_ai.lines.append(line),
        close=lambda: setattr(fake_ai, "closed", True),
    )
    terminal._ai_terminal = fake_ai
    terminal.onecmd("ai")
    entered_ok = terminal.mode == "ai" and terminal.prompt == "ai> "
    terminal.onecmd("status")
    forwarded_ok = fake_ai.lines == ["status"]
    terminal.onecmd("exit")
    returned_ok = terminal.mode == "plan" and terminal.prompt == "plan> "
    terminal.outputs = []
    terminal.onecmd("/help")
    slash_help_ok = terminal.outputs and "命令：" in terminal.outputs[-1]
    plan_completions = list(PlanCommandCompleter().get_completions(Document("/"), None))
    plan_prefix_completions = list(PlanCommandCompleter().get_completions(Document("/s"), None))
    plan_slash_completion_ok = (
        any(completion.text == "/status" for completion in plan_completions)
        and any(completion.text == "/status" for completion in plan_prefix_completions)
        and _is_plan_completion_context("/", 1)
        and _is_plan_completion_context("/s", 2)
        and not _is_plan_completion_context("text /", 6)
        and not _is_plan_completion_context("/status now", 11)
    )
    surrogate_text = "ai 测试".encode("utf-8").decode("ascii", errors="surrogateescape")
    stdin_repair_ok = _repair_piped_stdin_text(surrogate_text, encoding="ascii") == "ai 测试"
    terminal.close()
    closed_ok = fake_ai.closed

    return [
        _self_check_result(
            name="unified_terminal_lazy_ai_mode",
            passed=(
                lazy_ok
                and entered_ok
                and forwarded_ok
                and returned_ok
                and slash_help_ok
                and plan_slash_completion_ok
                and stdin_repair_ok
                and closed_ok
            ),
            detail={
                "lazy_ok": lazy_ok,
                "entered_ok": entered_ok,
                "forwarded_lines": fake_ai.lines,
                "returned_mode": terminal.mode,
                "slash_help_ok": slash_help_ok,
                "plan_slash_completions": [completion.text for completion in plan_completions],
                "plan_prefix_completions": [completion.text for completion in plan_prefix_completions],
                "stdin_repair_ok": stdin_repair_ok,
                "closed": fake_ai.closed,
            },
        )
    ]


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

    def poutput(self, value: Any) -> None:
        self.outputs.append(str(value))

    def perror(self, value: Any) -> None:
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
    terminal.perror = lambda value: terminal.errors.append(format_error_for_terminal(value, project_root=Path.cwd()))
    terminal.default = lambda line: terminal.forwarded_lines.append(str(line))
    terminal.do_status = lambda arg: terminal.forwarded_lines.append("/status")

    blocked_stop = AITerminal.onecmd(terminal, "new blocked-thread")
    blocked_error = terminal.errors[-1] if terminal.errors else ""
    allowed_status = AITerminal.onecmd(terminal, "/status")

    allowed = {
        "status": AITerminal._command_allowed_while_busy(terminal, "status"),
        "/status": AITerminal._command_allowed_while_busy(terminal, "/status"),
        "help": AITerminal._command_allowed_while_busy(terminal, "help"),
        "new": AITerminal._command_allowed_while_busy(terminal, "new blocked-thread"),
        "exit": AITerminal._command_allowed_while_busy(terminal, "exit"),
    }
    passed = (
        blocked_stop is False
        and allowed_status is False
        and "等待当前回复完成" in blocked_error
        and terminal.forwarded_lines == ["/status"]
        and allowed["status"]
        and allowed["/status"]
        and allowed["help"]
        and not allowed["new"]
        and not allowed["exit"]
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
