from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from collections.abc import AsyncIterator
from tempfile import TemporaryDirectory

from textual.events import Paste

import ai_automate_contro.client.backend as backend_module
from ai_automate_contro.client.backend import AITerminalBackend, FakeAgentBackend
from ai_automate_contro.client.backend import CONFIRM_CURRENT_WAIT, FEEDBACK_OR_CORRECTION
from ai_automate_contro.client.events import ClientEvent
from ai_automate_contro.client.textual_app import (
    AICTextualApp,
    ApprovalBlock,
    COMMAND_PALETTE_VISIBLE_ROWS,
    COMPOSER_MAX_LINES,
    COMPOSER_MIN_LINES,
    CommandPalette,
    Composer,
    MessageBlock,
    MetaBlock,
    PendingQueuePanel,
    THINKING_IDLE_TICKS,
    THINKING_TICK_SECONDS,
    ToolBlock,
    WorkPlanPanel,
    ActivityBlock,
    _format_approval_text,
    _format_transcript_markdown,
    _is_newline_key_event,
    _move_composer_cursor_to_end,
)


def self_check_textual_client(project_root: str | Path) -> dict[str, Any]:
    return asyncio.run(_self_check_textual_client_async(Path(project_root).resolve()))


async def _self_check_textual_client_async(project_root: Path) -> dict[str, Any]:
    legacy_surface_result = _check_no_legacy_interactive_surface(project_root)
    backend = FakeAgentBackend(response="你好，我在。\n\n- 可以创建 plan\n- 可以运行 plan")
    app = AICTextualApp(backend)
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "工具测试\n第二行"
        app._sync_composer_height()
        initial_height = int(composer.styles.height.value)
        composer.text = "续行\\"
        _move_composer_cursor_to_end(composer)
        await pilot.press("enter")
        line_continuation_text = composer.text
        composer.text = "第一行"
        _move_composer_cursor_to_end(composer)
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        composer.clear()
        composer.text = (
            "这是一个很长的中文输入，用来检查宽度变化时 composer 高度会按终端单元宽度重新计算，"
            "并且不会越过最大高度。窗口变窄以后，这段中文应该自然增加可视行数。"
        )
        app._sync_composer_height()
        wide_height = int(composer.styles.height.value)
        await pilot.resize_terminal(36, 20)
        await pilot.pause(0.05)
        app._sync_composer_height()
        narrow_height = int(composer.styles.height.value)
        css = AICTextualApp.CSS
        composer.text = "工具测试\n第二行"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        composer.text = "第二条排队消息"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        composer.text = "审批 错误"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        composer.text = "计划任务"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        plan_panel = app.query_one("#work_plan_panel", WorkPlanPanel)
        plan_panel_visible = bool(plan_panel.display)
        plan_panel_text = str(plan_panel.render())
        composer.text = "/plan"
        await pilot.press("enter")
        await pilot.pause(0.2)
        messages = list(app.query(MessageBlock))
        message_texts = [message.text for message in messages]
        user_messages = [message for message in messages if message.has_class("user")]
        assistant_messages = [message for message in messages if message.has_class("assistant")]
        tool_messages = [message for message in messages if message.has_class("tool")]
        approval_messages = [message for message in messages if message.has_class("approval")]
        error_messages = [message for message in messages if message.has_class("error")]
        summary_messages = [message for message in messages if message.has_class("summary")]
        activity_messages = [message for message in messages if message.has_class("activity")]
        work_plan_query_messages = [
            message.text
            for message in messages
            if message.has_class("meta") and "计划 1/3" in message.text and "检查工具输出" in message.text
        ]
        status_text = str(app.query_one("#status").content)
        tool_block_count = len(app.query(ToolBlock))
        tool_done_class_ok = any(block.has_class("tool-done") for block in app.query(ToolBlock))

    expected_user_messages = ["第一行", "工具测试\n第二行", "第二条排队消息", "审批 错误", "计划任务"]
    user_ok = [message.text for message in user_messages] == expected_user_messages
    assistant_ok = len(assistant_messages) == 5 and all("你好，我在。" in message.text for message in assistant_messages)
    tool_ok = (
        len(tool_messages) >= 1
        and any("工具 完成 inspect_web_page" in message.text for message in tool_messages)
        and not any("工具 运行中 inspect_web_page" in message.text for message in tool_messages)
        and all("\n" not in message.text for message in tool_messages)
        and tool_block_count == 1
        and tool_done_class_ok
    )
    approval_ok = len(approval_messages) == 1 and any("需要你确认" in message.text for message in approval_messages)
    error_ok = len(error_messages) == 1 and error_messages[0].text.startswith("error\n") and "模拟错误" in error_messages[0].text
    summary_ok = (
        len(summary_messages) >= 2
        and any("本轮结果" in message.text and "工具：完成 inspect_web_page" in message.text for message in summary_messages)
        and any("错误" in message.text and "模拟错误" in message.text for message in summary_messages)
        and any("进度：更新工作计划" in message.text and "下一步：按可见计划继续推进。" in message.text for message in summary_messages)
    )
    activity_ok = (
        len(activity_messages) == 1
        and any("计划" in message.text and "更新工作计划" in message.text for message in activity_messages)
        and not any("inspect_web_page" in message.text for message in activity_messages)
        and all(isinstance(message, ActivityBlock) for message in activity_messages)
    )
    queue_ok = [message.text for message in user_messages] == expected_user_messages
    work_plan_ok = (
        plan_panel_visible
        and "计划 1/3" in plan_panel_text
        and "检查工具输出" in plan_panel_text
        and bool(work_plan_query_messages)
    )
    multiline_shortcut_ok = line_continuation_text == "续行\n"
    modified_enter_newline_ok = (
        _is_newline_key_event(SimpleNamespace(key="shift+enter", aliases=[]))
        and _is_newline_key_event(SimpleNamespace(key="alt+enter", aliases=[]))
        and _is_newline_key_event(SimpleNamespace(key="enter", aliases=["option+enter"]))
        and not _is_newline_key_event(SimpleNamespace(key="enter", aliases=[]))
    )
    enter_send_ok = any(message.text == "第一行" for message in user_messages)
    resize_ok = initial_height == COMPOSER_MIN_LINES and COMPOSER_MIN_LINES <= wide_height <= narrow_height <= COMPOSER_MAX_LINES
    no_legacy_prompt_ok = all(
        "AI>" not in text and "你>" not in text and "plan>" not in text and "ai>" not in text
        for text in message_texts
    )
    status_ok = status_text.startswith("就绪") or status_text.startswith("正在处理")
    composer_style_ok = (
        COMPOSER_MIN_LINES == 4
        and initial_height == 4
        and "#composer .text-area--cursor" in css
        and "background: #ffd166" in css
        and "min-height: 7" in css
        and "background: #2d3035" in css
    )
    chrome_result = _check_textual_agent_chrome()
    thinking_result = await _check_textual_thinking_indicator()
    markdown_result = _check_textual_markdown_does_not_emit_terminal_hyperlinks()
    approval_guidance_result = _check_textual_approval_guidance_is_not_duplicated()
    transcript_export_result = _check_textual_transcript_export_keeps_raw_text()
    duplicate_tool_result = await _check_textual_duplicate_tool_transcript_records()
    interrupt_result = await _check_textual_escape_interrupts_without_queue()
    queued_batch_result = await _check_textual_busy_messages_stay_queued_until_batch_consumed()
    intervention_result = await _check_textual_escape_promotes_queue_to_intervention()
    stuck_intervention_result = await _check_textual_escape_intervention_survives_stuck_turn()
    interrupted_markdown_result = await _check_textual_interrupted_assistant_markdown_is_finalized()
    backend_exception_result = await _check_textual_backend_stream_exception_renders_error()
    active_confirmation_result = await _check_active_confirmation_input()
    natural_completion_confirmation_result = await _check_active_confirmation_natural_completion_input()
    idle_active_wait_result = await _check_idle_active_wait_routes_to_confirmation()
    delayed_confirmation_echo_result = await _check_confirmation_input_echoes_before_backend_returns()
    active_feedback_intervention_result = await _check_active_confirmation_feedback_becomes_intervention()
    natural_language_feedback_result = await _check_natural_language_continue_becomes_feedback()
    command_palette_result = await _check_textual_command_palette_and_local_commands()
    clipboard_text_paste_result = await _check_textual_clipboard_text_paste_once()
    clipboard_paste_result = await _check_textual_clipboard_image_paste()
    busy_clipboard_paste_result = await _check_textual_busy_clipboard_image_paste_is_deferred()
    pending_approval_status_result = await _check_textual_pending_approval_status_survives_idle()
    backend_interrupt_result = await _check_ai_terminal_backend_interrupt_forks_stuck_worker(project_root)
    backend_confirmation_feedback_result = await _check_backend_confirmation_feedback_not_swallowed(project_root)
    activity_noise_result = await _check_textual_activity_stream_stays_high_level()
    snapshot_result = await _check_textual_ui_snapshot_layout()
    slash_routing_result = _check_textual_slash_command_routing(project_root)
    return {
        "ok": (
            user_ok
            and assistant_ok
            and tool_ok
            and approval_ok
            and error_ok
            and summary_ok
            and activity_ok
            and queue_ok
            and work_plan_ok
            and multiline_shortcut_ok
            and modified_enter_newline_ok
            and enter_send_ok
            and resize_ok
            and no_legacy_prompt_ok
            and status_ok
            and composer_style_ok
            and chrome_result["passed"]
            and thinking_result["passed"]
            and markdown_result["passed"]
            and approval_guidance_result["passed"]
            and transcript_export_result["passed"]
            and duplicate_tool_result["passed"]
            and interrupt_result["passed"]
            and queued_batch_result["passed"]
            and intervention_result["passed"]
            and stuck_intervention_result["passed"]
            and interrupted_markdown_result["passed"]
            and backend_exception_result["passed"]
            and active_confirmation_result["passed"]
            and natural_completion_confirmation_result["passed"]
            and idle_active_wait_result["passed"]
            and delayed_confirmation_echo_result["passed"]
            and active_feedback_intervention_result["passed"]
            and natural_language_feedback_result["passed"]
            and command_palette_result["passed"]
            and clipboard_text_paste_result["passed"]
            and clipboard_paste_result["passed"]
            and busy_clipboard_paste_result["passed"]
            and pending_approval_status_result["passed"]
            and backend_interrupt_result["passed"]
            and backend_confirmation_feedback_result["passed"]
            and activity_noise_result["passed"]
            and snapshot_result["passed"]
            and slash_routing_result["passed"]
            and legacy_surface_result["passed"]
        ),
        "check": "textual_client",
        "project_root": str(project_root),
        "checks": [
            {
                "name": "textual_fake_backend_chat_flow",
                "passed": user_ok and assistant_ok,
                "detail": {"messages": message_texts, "tool_block_count": tool_block_count},
            },
            {
                "name": "textual_client_renders_tool_progress",
                "passed": tool_ok,
                "detail": {
                    "tool_messages": [message.text for message in tool_messages],
                    "tool_block_count": tool_block_count,
                },
            },
            {
                "name": "textual_client_renders_approval_and_errors",
                "passed": approval_ok and error_ok,
                "detail": {
                    "tool_messages": [message.text for message in tool_messages],
                    "approval_messages": [message.text for message in approval_messages],
                    "error_messages": [message.text for message in error_messages],
                },
            },
            {
                "name": "textual_client_summarizes_turn_results",
                "passed": summary_ok,
                "detail": {"summary_messages": [message.text for message in summary_messages]},
            },
            {
                "name": "textual_client_renders_activity_stream",
                "passed": activity_ok,
                "detail": {"activity_messages": [message.text for message in activity_messages]},
            },
            {
                "name": "textual_client_queues_multiple_messages",
                "passed": queue_ok,
                "detail": {"user_messages": [message.text for message in user_messages]},
            },
            {
                "name": "textual_client_renders_and_queries_work_plan",
                "passed": work_plan_ok,
                "detail": {
                    "panel_visible": plan_panel_visible,
                    "panel_text": plan_panel_text,
                    "query_messages": work_plan_query_messages,
                },
            },
            {
                "name": "textual_client_composer_height_tracks_resize",
                "passed": resize_ok,
                "detail": {
                    "initial_height": initial_height,
                    "wide_height": wide_height,
                    "narrow_height": narrow_height,
                    "min_lines": COMPOSER_MIN_LINES,
                    "max_lines": COMPOSER_MAX_LINES,
                },
            },
            {
                "name": "textual_client_supports_line_continuation_newline",
                "passed": multiline_shortcut_ok and modified_enter_newline_ok and enter_send_ok,
                "detail": {
                    "line_continuation_text": line_continuation_text,
                    "modified_enter_newline": modified_enter_newline_ok,
                    "enter_sent_message": enter_send_ok,
                },
            },
            {
                "name": "textual_client_does_not_emit_legacy_prompt_prefixes",
                "passed": no_legacy_prompt_ok,
                "detail": {"messages": message_texts},
            },
            {
                "name": "textual_client_status_recovers",
                "passed": status_ok,
                "detail": {"status": status_text},
            },
            {
                "name": "textual_client_composer_is_large_and_cursor_visible",
                "passed": composer_style_ok,
                "detail": {
                    "min_lines": COMPOSER_MIN_LINES,
                    "initial_height": initial_height,
                    "has_cursor_css": "#composer .text-area--cursor" in css,
                    "has_cursor_color": "background: #ffd166" in css,
                    "has_large_row": "min-height: 7" in css,
                    "has_composer_background": "background: #2d3035" in css,
                },
            },
            chrome_result,
            thinking_result,
            markdown_result,
            approval_guidance_result,
            transcript_export_result,
            duplicate_tool_result,
            interrupt_result,
            queued_batch_result,
            intervention_result,
            stuck_intervention_result,
            interrupted_markdown_result,
            backend_exception_result,
            active_confirmation_result,
            natural_completion_confirmation_result,
            idle_active_wait_result,
            delayed_confirmation_echo_result,
            active_feedback_intervention_result,
            natural_language_feedback_result,
            command_palette_result,
            clipboard_text_paste_result,
            clipboard_paste_result,
            busy_clipboard_paste_result,
            pending_approval_status_result,
            backend_interrupt_result,
            backend_confirmation_feedback_result,
            activity_noise_result,
            snapshot_result,
            slash_routing_result,
            legacy_surface_result,
        ],
    }


class PausingBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        yield ClientEvent("status", text="正在思考")
        await asyncio.sleep(THINKING_TICK_SECONDS * (THINKING_IDLE_TICKS + 1))
        yield ClientEvent("assistant_delta", text="第一段")
        await asyncio.sleep(THINKING_TICK_SECONDS * (THINKING_IDLE_TICKS + 8))
        yield ClientEvent("assistant_delta", text="第二段")
        yield ClientEvent("assistant_done")


async def _check_textual_thinking_indicator() -> dict[str, Any]:
    backend = PausingBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "慢回复"
        await pilot.press("enter")
        await pilot.pause(THINKING_TICK_SECONDS * 1.5)
        early_status = str(app.query_one("#status").content)
        await pilot.pause(THINKING_TICK_SECONDS * (THINKING_IDLE_TICKS + 3))
        waiting_status = str(app.query_one("#status").content)
        await _wait_until_idle(app, pilot)
        final_status = str(app.query_one("#status").content)
        assistant_messages = [
            message.text
            for message in app.query(MessageBlock)
            if message.has_class("assistant")
        ]
    passed = (
        "正在思考" in early_status
        and "." in early_status
        and "正在思考" in waiting_status
        and final_status.startswith("就绪")
        and "正在思考" not in final_status
        and assistant_messages == ["第一段第二段"]
    )
    return {
        "name": "textual_client_animates_thinking_and_clears_on_done",
        "passed": passed,
        "detail": {
            "early_status": early_status,
            "waiting_status": waiting_status,
            "final_status": final_status,
            "assistant_messages": assistant_messages,
        },
    }


def _check_textual_markdown_does_not_emit_terminal_hyperlinks() -> dict[str, Any]:
    block = MessageBlock("https://example.com\n\n[link](https://example.com)", role="assistant")
    renderable = block._renderable()
    hyperlinks = getattr(renderable, "hyperlinks", None)
    streaming_block = MessageBlock("", role="assistant", streaming=True)
    streaming_block.text = "https://example.com\n\n[link](https://example.com)"
    streaming_renderable_type = type(streaming_block._renderable()).__name__
    streaming_block.streaming = False
    finalized_hyperlinks = getattr(streaming_block._renderable(), "hyperlinks", None)
    passed = hyperlinks is False and streaming_renderable_type == "Text" and finalized_hyperlinks is False
    return {
        "name": "textual_client_disables_terminal_hyperlinks_in_assistant_markdown",
        "passed": passed,
        "detail": {
            "hyperlinks": hyperlinks,
            "streaming_renderable_type": streaming_renderable_type,
            "finalized_hyperlinks": finalized_hyperlinks,
        },
    }


def _check_textual_approval_guidance_is_not_duplicated() -> dict[str, Any]:
    message = _format_approval_text(
        "请在当前已经打开的 Playwright 浏览器窗口完成操作；完成后回到这里输入“继续”，要停止就输入“停止”。"
    )
    passed = message.count("请在当前已经打开的 Playwright 浏览器窗口完成操作") == 1
    return {
        "name": "textual_client_deduplicates_browser_handoff_approval_guidance",
        "passed": passed,
        "detail": {"message": message},
    }


def _check_textual_transcript_export_keeps_raw_text() -> dict[str, Any]:
    export_text = _format_transcript_markdown(
        [
            ("user", "账户名 huanmin\n密码hu123456.\napi_key=sk-secret12345678"),
            ("assistant", "收到。"),
        ]
    )
    passed = "hu123456" in export_text and "sk-secret12345678" in export_text and "[REDACTED]" not in export_text
    return {
        "name": "textual_client_export_keeps_raw_inline_text",
        "passed": passed,
        "detail": {"export_text": export_text},
    }


async def _check_textual_duplicate_tool_transcript_records() -> dict[str, Any]:
    app = AICTextualApp(FakeAgentBackend(response=""))
    async with app.run_test(size=(90, 24)) as pilot:
        await app._handle_client_event(ClientEvent("tool_started", title="inspect_web_page", text="same args"))
        await app._handle_client_event(ClientEvent("tool_started", title="inspect_web_page", text="same args"))
        await app._handle_client_event(ClientEvent("tool_finished", title="inspect_web_page", text="first result"))
        await app._handle_client_event(ClientEvent("tool_finished", title="inspect_web_page", text="second result"))
        await pilot.pause(0.05)
        compact_tool_records = [text for role, text in app._transcript_records if role == "tool"]
        compact_tool_blocks = [block.text for block in app.query(ToolBlock)]
        app._show_tool_details = True
        app._rerender_tool_blocks()
        detailed_tool_records = [text for role, text in app._transcript_records if role == "tool"]
        detailed_tool_blocks = [block.text for block in app.query(ToolBlock)]
        export_text = _format_transcript_markdown(app._transcript_records)
    passed = (
        compact_tool_records == [
            "工具 完成 inspect_web_page first result",
            "工具 完成 inspect_web_page second result",
        ]
        and compact_tool_blocks == compact_tool_records
        and len(detailed_tool_records) == 2
        and detailed_tool_blocks == detailed_tool_records
        and "first result" in detailed_tool_records[0]
        and "second result" in detailed_tool_records[1]
        and detailed_tool_records[0] != detailed_tool_records[1]
        and export_text.count("## Tool") == 1
        and "first result" in export_text
        and "second result" in export_text
    )
    return {
        "name": "textual_client_keeps_duplicate_tool_transcript_records_distinct",
        "passed": passed,
        "detail": {
            "compact_tool_records": compact_tool_records,
            "compact_tool_blocks": compact_tool_blocks,
            "detailed_tool_records": detailed_tool_records,
            "detailed_tool_blocks": detailed_tool_blocks,
            "export_text": export_text,
        },
    }


class InterruptibleBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.messages: list[str] = []
        self.interrupt_calls = 0
        self._interrupt_event: asyncio.Event | None = None

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.messages.append(message)
        if len(self.messages) == 1:
            self._interrupt_event = asyncio.Event()
            yield ClientEvent("status", text="正在思考")
            while not self._interrupt_event.is_set():
                await asyncio.sleep(0.01)
            yield ClientEvent("assistant_done")
            return
        yield ClientEvent("assistant_delta", text=f"收到：{message}")
        yield ClientEvent("assistant_done")

    async def interrupt(self) -> ClientEvent:
        self.interrupt_calls += 1
        if self._interrupt_event is not None:
            self._interrupt_event.set()
        return ClientEvent("interrupted", text="已中断当前 AI 回复。")


class NonCooperativeInterruptBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.messages: list[str] = []
        self.interrupt_calls = 0
        self._first_turn_started = asyncio.Event()
        self._release_first_turn = asyncio.Event()

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.messages.append(message)
        if len(self.messages) == 1:
            self._first_turn_started.set()
            yield ClientEvent("status", text="正在思考")
            await self._release_first_turn.wait()
            yield ClientEvent("assistant_delta", text="迟到的旧回复")
            yield ClientEvent("assistant_done")
            return
        yield ClientEvent("assistant_delta", text=f"介入已处理：{message}")
        yield ClientEvent("assistant_done")

    async def interrupt(self) -> ClientEvent:
        self.interrupt_calls += 1
        return ClientEvent("interrupted", text="已中断当前 AI 回复。")


async def _check_textual_escape_interrupts_without_queue() -> dict[str, Any]:
    backend = InterruptibleBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "第一条慢消息"
        await pilot.press("enter")
        await pilot.pause(0.05)
        await pilot.press("escape")
        await _wait_until_idle(app, pilot)
        messages = list(app.query(MessageBlock))
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        status_text = str(app.query_one("#status").content)

    passed = (
        backend.messages == ["第一条慢消息"]
        and backend.interrupt_calls == 1
        and assistant_messages == []
        and any("已中断当前 AI 回复" in message for message in meta_messages)
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_escape_interrupts_active_turn_without_queue",
        "passed": passed,
        "detail": {
            "messages": backend.messages,
            "interrupt_calls": backend.interrupt_calls,
            "assistant_messages": assistant_messages,
            "meta_messages": meta_messages,
            "status": status_text,
        },
    }


class QueueBatchBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.messages: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.messages.append(message)
        if len(self.messages) == 1:
            self.started.set()
            yield ClientEvent("status", text="正在思考")
            await self.release.wait()
            yield ClientEvent("assistant_delta", text="第一条完成")
            yield ClientEvent("assistant_done")
            return
        yield ClientEvent("assistant_delta", text=f"批量收到：{message}")
        yield ClientEvent("assistant_done")


async def _check_textual_busy_messages_stay_queued_until_batch_consumed() -> dict[str, Any]:
    backend = QueueBatchBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 26)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "第一条慢消息"
        await pilot.press("enter")
        for _ in range(100):
            if backend.started.is_set():
                break
            await pilot.pause(0.01)
        composer.text = "排队一"
        await pilot.press("enter")
        composer.text = "排队二"
        await pilot.press("enter")
        await pilot.pause(0.05)
        queued_before_release = list(app._queue)
        queue_panel = app.query_one("#pending_queue_panel", PendingQueuePanel)
        queue_panel_visible_before = bool(queue_panel.display)
        queue_panel_text_before = str(queue_panel.render())
        messages_before_release = list(app.query(MessageBlock))
        user_before_release = [message.text for message in messages_before_release if message.has_class("user")]
        backend.release.set()
        await _wait_until_idle(app, pilot)
        queue_panel_visible_after = bool(queue_panel.display)
        messages_after = list(app.query(MessageBlock))
        user_after = [message.text for message in messages_after if message.has_class("user")]
        assistant_after = [message.text for message in messages_after if message.has_class("assistant")]
        status_text = str(app.query_one("#status").content)

    expected_batch = "排队一\n\n排队二"
    passed = (
        queued_before_release == ["排队一", "排队二"]
        and queue_panel_visible_before
        and "待处理 2 条" in queue_panel_text_before
        and "排队一" in queue_panel_text_before
        and "排队二" in queue_panel_text_before
        and backend.messages == ["第一条慢消息", expected_batch]
        and user_before_release == ["第一条慢消息"]
        and user_after == ["第一条慢消息", expected_batch]
        and any(f"批量收到：{expected_batch}" == message for message in assistant_after)
        and not queue_panel_visible_after
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_keeps_busy_messages_in_queue_panel_until_batched_consumption",
        "passed": passed,
        "detail": {
            "queued_before_release": queued_before_release,
            "queue_panel_visible_before": queue_panel_visible_before,
            "queue_panel_text_before": queue_panel_text_before,
            "backend_messages": backend.messages,
            "user_before_release": user_before_release,
            "user_after": user_after,
            "assistant_after": assistant_after,
            "queue_panel_visible_after": queue_panel_visible_after,
            "status": status_text,
        },
    }


async def _check_textual_escape_promotes_queue_to_intervention() -> dict[str, Any]:
    backend = InterruptibleBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 26)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "第一条慢消息"
        await pilot.press("enter")
        await pilot.pause(0.05)
        composer.text = "第一条介入"
        await pilot.press("enter")
        composer.text = "第二条介入"
        await pilot.press("enter")
        queued_before_escape = list(app._queue)
        await pilot.press("escape")
        await _wait_until_idle(app, pilot)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        queue_panel_visible = bool(app.query_one("#pending_queue_panel", PendingQueuePanel).display)
        status_text = str(app.query_one("#status").content)

    expected_intervention = "第一条介入\n\n第二条介入"
    passed = (
        queued_before_escape == ["第一条介入", "第二条介入"]
        and backend.messages == ["第一条慢消息", expected_intervention]
        and backend.interrupt_calls == 1
        and user_messages == ["第一条慢消息", expected_intervention]
        and assistant_messages == [f"收到：{expected_intervention}"]
        and any("已介入排队消息 2 条" in message for message in meta_messages)
        and not queue_panel_visible
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_escape_promotes_queued_messages_to_intervention",
        "passed": passed,
        "detail": {
            "queued_before_escape": queued_before_escape,
            "backend_messages": backend.messages,
            "interrupt_calls": backend.interrupt_calls,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "meta_messages": meta_messages,
            "queue_panel_visible": queue_panel_visible,
            "status": status_text,
        },
    }


async def _check_textual_escape_intervention_survives_stuck_turn() -> dict[str, Any]:
    backend = NonCooperativeInterruptBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 26)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "第一条会卡住"
        await pilot.press("enter")
        for _ in range(100):
            if backend._first_turn_started.is_set():
                break
            await pilot.pause(0.01)
        composer.text = "这是更重要的介入消息"
        await pilot.press("enter")
        await pilot.press("escape")
        for _ in range(100):
            if len(backend.messages) >= 2 and not app._queue:
                break
            await pilot.pause(0.02)
        status_after_intervention = str(app.query_one("#status").content)
        messages = list(app.query(MessageBlock))
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        busy_after_intervention = app._busy
        backend._release_first_turn.set()
        await pilot.pause(0.1)
        messages_after_release = list(app.query(MessageBlock))
        assistant_after_release = [message.text for message in messages_after_release if message.has_class("assistant")]

    passed = (
        backend.messages == ["第一条会卡住", "这是更重要的介入消息"]
        and backend.interrupt_calls == 1
        and assistant_messages == ["介入已处理：这是更重要的介入消息"]
        and assistant_after_release == assistant_messages
        and any("已介入排队消息 1 条" in message for message in meta_messages)
        and not busy_after_intervention
        and status_after_intervention.startswith("就绪")
    )
    return {
        "name": "textual_client_escape_intervention_survives_stuck_turn",
        "passed": passed,
        "detail": {
            "backend_messages": backend.messages,
            "interrupt_calls": backend.interrupt_calls,
            "assistant_messages": assistant_messages,
            "assistant_after_release": assistant_after_release,
            "meta_messages": meta_messages,
            "status_after_intervention": status_after_intervention,
            "busy_after_intervention": busy_after_intervention,
        },
    }


class MarkdownInterruptBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.messages: list[str] = []
        self.interrupt_calls = 0
        self.started = asyncio.Event()
        self.interrupted = asyncio.Event()

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.messages.append(message)
        yield ClientEvent("assistant_delta", text="部分 **Markdown** [link](https://example.com)")
        self.started.set()
        await self.interrupted.wait()
        yield ClientEvent("assistant_done")

    async def interrupt(self) -> ClientEvent:
        self.interrupt_calls += 1
        self.interrupted.set()
        return ClientEvent("interrupted", text="已中断当前 AI 回复。")


async def _check_textual_interrupted_assistant_markdown_is_finalized() -> dict[str, Any]:
    backend = MarkdownInterruptBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "会被中断的 Markdown"
        await pilot.press("enter")
        for _ in range(100):
            if backend.started.is_set():
                break
            await pilot.pause(0.01)
        await pilot.pause(0.05)
        await pilot.press("escape")
        await _wait_until_idle(app, pilot)
        assistant_blocks = [message for message in app.query(MessageBlock) if message.has_class("assistant")]
        assistant_streaming = [bool(getattr(message, "streaming", False)) for message in assistant_blocks]
        renderable_types = [type(message._renderable()).__name__ for message in assistant_blocks]
        meta_messages = [message.text for message in app.query(MessageBlock) if message.has_class("meta")]

    passed = (
        backend.interrupt_calls == 1
        and assistant_blocks
        and assistant_streaming == [False]
        and renderable_types == ["Markdown"]
        and any("已中断当前 AI 回复" in message for message in meta_messages)
    )
    return {
        "name": "textual_client_finalizes_interrupted_assistant_markdown",
        "passed": passed,
        "detail": {
            "interrupt_calls": backend.interrupt_calls,
            "assistant_texts": [message.text for message in assistant_blocks],
            "assistant_streaming": assistant_streaming,
            "renderable_types": renderable_types,
            "meta_messages": meta_messages,
        },
    }


class FailingStreamBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.messages: list[str] = []

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.messages.append(message)
        yield ClientEvent("assistant_delta", text="出错前 **内容**")
        raise RuntimeError("boom")


async def _check_textual_backend_stream_exception_renders_error() -> dict[str, Any]:
    backend = FailingStreamBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "触发后端异常"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        messages = list(app.query(MessageBlock))
        assistant_blocks = [message for message in messages if message.has_class("assistant")]
        error_messages = [message.text for message in messages if message.has_class("error")]
        assistant_streaming = [bool(getattr(message, "streaming", False)) for message in assistant_blocks]
        status_text = str(app.query_one("#status").content)

    passed = (
        backend.messages == ["触发后端异常"]
        and assistant_streaming == [False]
        and any("boom" in message for message in error_messages)
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_backend_stream_exception_renders_error",
        "passed": passed,
        "detail": {
            "backend_messages": backend.messages,
            "assistant_texts": [message.text for message in assistant_blocks],
            "assistant_streaming": assistant_streaming,
            "error_messages": error_messages,
            "status": status_text,
        },
    }


def _check_textual_agent_chrome() -> dict[str, Any]:
    css = AICTextualApp.CSS
    forbidden_light_fragments = [
        "background: #ffffff",
        "background: #f3f4f6",
        "background: #fff5f5",
        "background: #eef6ff",
    ]
    passed = (
        "#top_bar" not in css
        and "#brand" not in css
        and "#top_status" not in css
        and "#composer_row" in css
        and "padding: 1 0 0 0" in css
        and "padding: 0 0 1 0" in css
        and ".tool-running" in css
        and ".tool-done" in css
        and ".tool-failed" in css
        and ".tool {\n        color: #b8b2a7;\n        background: #101214;" in css
        and "border-left: tall #4e5560" not in css
        and ".tool {\n        color: #b8b2a7;\n        background: #101214;\n        height: 1;" in css
        and ".tool-details" in css
        and "background: #101214" in css
        and not any(fragment in css for fragment in forbidden_light_fragments)
    )
    return {
        "name": "textual_client_uses_agent_tui_chrome",
        "passed": passed,
        "detail": {
            "has_top_bar_css": "#top_bar" in css,
            "has_compact_page_padding": "padding: 1 0 0 0" in css and "padding: 0 0 1 0" in css,
            "has_tool_phase_css": all(fragment in css for fragment in (".tool-running", ".tool-done", ".tool-failed")),
            "tool_is_compact": "border-left: tall #4e5560" not in css and "height: 1;" in css,
        },
    }


class ConfirmationBackend:
    def __init__(self) -> None:
        self.confirmation: asyncio.Future[str] | None = None
        self.handled_inputs: list[str] = []
        self.submit_started = asyncio.Event()
        self.submit_release = asyncio.Event()
        self.delay_submit = False
        self.feedback_inputs: set[str] = set()
        self.classified_inputs: list[tuple[str, str]] = []
        self.classified_contexts: list[dict[str, Any]] = []
        self.interrupt_calls = 0
        self._interrupted = False

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        if self._interrupted:
            yield ClientEvent("assistant_delta", text=f"反馈已处理：{message}")
            yield ClientEvent("assistant_done")
            return
        self.confirmation = asyncio.get_running_loop().create_future()
        yield ClientEvent(
            "approval_requested",
            text=f"等待确认：{message}",
            data={"approval_kind": "active_wait", "wait_type": "manual_confirm", "wait_prompt": message},
        )
        accepted = await self.confirmation
        yield ClientEvent("system_output", text=f"确认输入：{accepted}")
        yield ClientEvent("assistant_delta", text="继续执行")
        yield ClientEvent("assistant_done")

    async def submit_during_turn(self, message: str) -> bool:
        if self.confirmation is None or self.confirmation.done():
            return False
        self.submit_started.set()
        if self.delay_submit:
            await self.submit_release.wait()
        self.handled_inputs.append(message)
        self.confirmation.set_result(message)
        return True

    async def confirm_active_wait(self, message: str) -> AsyncIterator[ClientEvent]:
        handled = await self.submit_during_turn(message)
        if not handled:
            yield ClientEvent("error", text="没有可确认的等待。")

    async def classify_active_turn_input(self, message: str, *, context: dict[str, Any] | None = None) -> str:
        intent = FEEDBACK_OR_CORRECTION if message in self.feedback_inputs else CONFIRM_CURRENT_WAIT
        self.classified_inputs.append((message, intent))
        self.classified_contexts.append(dict(context or {}))
        return intent

    async def interrupt(self) -> ClientEvent:
        self.interrupt_calls += 1
        self._interrupted = True
        if self.confirmation is not None and not self.confirmation.done():
            self.confirmation.cancel()
        return ClientEvent("interrupted", text="已中断当前等待。")

    async def attach_clipboard_images(self) -> list[str]:
        return []

    async def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": "confirmation",
            "busy": self.confirmation is not None and not self.confirmation.done(),
            "pending_approval": self.confirmation is not None and not self.confirmation.done(),
            "pending_approval_kind": "active_wait" if self.confirmation is not None and not self.confirmation.done() else "",
            "active_wait": {
                "wait_type": "manual_confirm",
                "prompt": "需要人工确认的任务",
            }
            if self.confirmation is not None and not self.confirmation.done()
            else {},
            "context_state": {
                "current_plan_path": "plans/context-demo/plan.json",
                "latest_output_dir": "plans/context-demo/output/latest",
                "work_plan_summary": "测试人工确认上下文",
            },
        }

    async def close(self) -> None:
        if self.confirmation is not None and not self.confirmation.done():
            self.confirmation.cancel()


class IdleActiveWaitBackend:
    def __init__(self) -> None:
        self.pending = True
        self.stream_messages: list[str] = []
        self.confirm_messages: list[str] = []
        self.classified_contexts: list[dict[str, Any]] = []
        self.interrupt_calls = 0

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.stream_messages.append(message)
        yield ClientEvent("assistant_delta", text=f"普通流收到：{message}")
        yield ClientEvent("assistant_done")

    async def submit_during_turn(self, message: str) -> bool:
        return False

    async def confirm_active_wait(self, message: str) -> AsyncIterator[ClientEvent]:
        self.confirm_messages.append(message)
        self.pending = False
        yield ClientEvent("system_output", text=f"确认输入：{message}")

    async def classify_active_turn_input(self, message: str, *, context: dict[str, Any] | None = None) -> str:
        self.classified_contexts.append(dict(context or {}))
        return CONFIRM_CURRENT_WAIT

    async def interrupt(self) -> ClientEvent:
        self.interrupt_calls += 1
        self.pending = False
        return ClientEvent("interrupted", text="已中断 idle 等待。")

    async def attach_clipboard_images(self) -> list[str]:
        return []

    async def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": "idle-active-wait",
            "busy": False,
            "pending_approval": self.pending,
            "pending_approval_kind": "active_wait" if self.pending else "",
            "active_wait": {"wait_type": "manual_confirm", "prompt": "idle 等待确认"} if self.pending else {},
            "context_state": {},
        }

    async def close(self) -> None:
        return None


async def _check_active_confirmation_input() -> dict[str, Any]:
    backend = ConfirmationBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        await pilot.pause(0.05)
        composer.text = "继续"
        await pilot.press("enter")
        await pilot.pause(0.1)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        approval_messages = [message.text for message in messages if message.has_class("approval")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
    passed = (
        backend.handled_inputs == ["继续"]
        and user_messages == ["需要人工确认的任务", "继续"]
        and any("确认输入：继续" in text for text in meta_messages)
        and any("等待确认：需要人工确认的任务" in text for text in approval_messages)
        and assistant_messages == ["继续执行"]
    )
    return {
        "name": "textual_client_routes_confirmation_to_active_turn",
        "passed": passed,
        "detail": {
            "handled_inputs": backend.handled_inputs,
            "user_messages": user_messages,
            "meta_messages": meta_messages,
            "approval_messages": approval_messages,
            "assistant_messages": assistant_messages,
        },
    }


async def _check_idle_active_wait_routes_to_confirmation() -> dict[str, Any]:
    backend = IdleActiveWaitBackend()
    app = AICTextualApp(backend)
    debug_default_ok = ("AIC_TEXTUAL_INPUT_DEBUG" in os.environ) or not app._input_debug_enabled
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.05)
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "继续"
        await pilot.press("enter")
        await pilot.pause(0.1)
        confirm_messages = list(backend.confirm_messages)
        stream_messages = list(backend.stream_messages)
        classified_contexts = list(backend.classified_contexts)
        meta_messages = [message.text for message in app.query(MessageBlock) if message.has_class("meta")]

    escape_backend = IdleActiveWaitBackend()
    escape_app = AICTextualApp(escape_backend)
    async with escape_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.05)
        await pilot.press("escape")
        await pilot.pause(0.1)
        escape_confirm_messages = list(escape_backend.confirm_messages)
        escape_stream_messages = list(escape_backend.stream_messages)
        escape_meta_messages = [
            message.text for message in escape_app.query(MessageBlock) if message.has_class("meta")
        ]

    passed = (
        debug_default_ok
        and confirm_messages == ["继续"]
        and stream_messages == []
        and bool(classified_contexts)
        and any("确认输入：继续" in message for message in meta_messages)
        and escape_confirm_messages == ["停止"]
        and escape_stream_messages == []
        and any("Esc 已请求停止当前等待" in message for message in escape_meta_messages)
    )
    return {
        "name": "textual_client_routes_idle_active_wait_to_confirmation",
        "passed": passed,
        "detail": {
            "debug_default_ok": debug_default_ok,
            "confirm_messages": confirm_messages,
            "stream_messages": stream_messages,
            "classified_contexts": classified_contexts,
            "meta_messages": meta_messages,
            "escape_confirm_messages": escape_confirm_messages,
            "escape_stream_messages": escape_stream_messages,
            "escape_meta_messages": escape_meta_messages,
        },
    }


async def _check_active_confirmation_natural_completion_input() -> dict[str, Any]:
    backend = ConfirmationBackend()
    completion = "已经登录进去了"
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        await pilot.pause(0.05)
        composer.text = completion
        await pilot.press("enter")
        await pilot.pause(0.1)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        classified_context = backend.classified_contexts[0] if backend.classified_contexts else {}
        active_wait_context = classified_context.get("active_wait") if isinstance(classified_context, dict) else {}
        state_context = classified_context.get("context_state") if isinstance(classified_context, dict) else {}
    passed = (
        backend.classified_inputs == [(completion, CONFIRM_CURRENT_WAIT)]
        and backend.handled_inputs == [completion]
        and backend.interrupt_calls == 0
        and user_messages == ["需要人工确认的任务", completion]
        and any(f"确认输入：{completion}" in text for text in meta_messages)
        and assistant_messages == ["继续执行"]
        and isinstance(active_wait_context, dict)
        and active_wait_context.get("wait_type") == "manual_confirm"
        and "需要人工确认的任务" in str(active_wait_context.get("prompt", ""))
        and isinstance(state_context, dict)
        and state_context.get("current_plan_path") == "plans/context-demo/plan.json"
    )
    return {
        "name": "textual_client_treats_natural_completion_as_confirmation",
        "passed": passed,
        "detail": {
            "classified_inputs": backend.classified_inputs,
            "handled_inputs": backend.handled_inputs,
            "interrupt_calls": backend.interrupt_calls,
            "user_messages": user_messages,
            "meta_messages": meta_messages,
            "assistant_messages": assistant_messages,
            "classified_context": classified_context,
        },
    }


async def _check_confirmation_input_echoes_before_backend_returns() -> dict[str, Any]:
    backend = ConfirmationBackend()
    backend.delay_submit = True
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        for _ in range(100):
            if bool(app._backend_status.get("pending_approval")):
                break
            await pilot.pause(0.01)
        composer.text = "继续"
        await pilot.press("enter")
        await pilot.pause(0.05)
        user_before_release = [message.text for message in app.query(MessageBlock) if message.has_class("user")]
        status_before_release = str(app.query_one("#status").content)
        submit_started_before_release = backend.submit_started.is_set()
        handled_before_release = list(backend.handled_inputs)
        backend.submit_release.set()
        await _wait_until_idle(app, pilot)
        user_after_release = [message.text for message in app.query(MessageBlock) if message.has_class("user")]
        meta_after_release = [message.text for message in app.query(MessageBlock) if message.has_class("meta")]

    passed = (
        submit_started_before_release
        and handled_before_release == []
        and user_before_release == ["需要人工确认的任务", "继续"]
        and "已收到输入" in status_before_release
        and backend.handled_inputs == ["继续"]
        and user_after_release == ["需要人工确认的任务", "继续"]
        and any("确认输入：继续" in message for message in meta_after_release)
    )
    return {
        "name": "textual_client_echoes_confirmation_input_before_backend_returns",
        "passed": passed,
        "detail": {
            "submit_started_before_release": submit_started_before_release,
            "handled_before_release": handled_before_release,
            "user_before_release": user_before_release,
            "status_before_release": status_before_release,
            "handled_after_release": backend.handled_inputs,
            "user_after_release": user_after_release,
            "meta_after_release": meta_after_release,
        },
    }


async def _check_active_confirmation_feedback_becomes_intervention() -> dict[str, Any]:
    backend = ConfirmationBackend()
    feedback = "账户密码没有填写上呢"
    backend.feedback_inputs.add(feedback)
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 26)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        for _ in range(100):
            if bool(app._backend_status.get("pending_approval")):
                break
            await pilot.pause(0.01)
        composer.text = feedback
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        queue_panel_visible = bool(app.query_one("#pending_queue_panel", PendingQueuePanel).display)
        status_text = str(app.query_one("#status").content)

    passed = (
        backend.classified_inputs == [(feedback, FEEDBACK_OR_CORRECTION)]
        and backend.handled_inputs == []
        and backend.interrupt_calls == 1
        and user_messages == ["需要人工确认的任务", feedback]
        and assistant_messages == [f"反馈已处理：{feedback}"]
        and any("已中断当前等待" in message for message in meta_messages)
        and not queue_panel_visible
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_routes_wait_feedback_to_intervention_not_confirmation",
        "passed": passed,
        "detail": {
            "classified_inputs": backend.classified_inputs,
            "handled_inputs": backend.handled_inputs,
            "interrupt_calls": backend.interrupt_calls,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "meta_messages": meta_messages,
            "queue_panel_visible": queue_panel_visible,
            "status": status_text,
        },
    }


async def _check_natural_language_continue_becomes_feedback() -> dict[str, Any]:
    backend = ConfirmationBackend()
    feedback = "可以继续，账户密码还是没有填写上"
    backend.feedback_inputs.add(feedback)
    app = AICTextualApp(backend)
    async with app.run_test(size=(90, 26)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        for _ in range(100):
            if bool(app._backend_status.get("pending_approval")):
                break
            await pilot.pause(0.01)
        composer.text = feedback
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        error_messages = [message.text for message in messages if message.has_class("error")]

    passed = (
        backend.classified_inputs == [(feedback, FEEDBACK_OR_CORRECTION)]
        and backend.handled_inputs == []
        and backend.interrupt_calls == 1
        and user_messages == ["需要人工确认的任务", feedback]
        and assistant_messages == [f"反馈已处理：{feedback}"]
        and any("已中断当前等待" in message for message in meta_messages)
        and not error_messages
    )
    return {
        "name": "textual_client_treats_natural_language_continue_as_feedback",
        "passed": passed,
        "detail": {
            "classified_inputs": backend.classified_inputs,
            "handled_inputs": backend.handled_inputs,
            "interrupt_calls": backend.interrupt_calls,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "meta_messages": meta_messages,
            "error_messages": error_messages,
        },
    }


async def _check_textual_command_palette_and_local_commands() -> dict[str, Any]:
    with TemporaryDirectory(prefix="textual-local-command-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        backend = FakeAgentBackend(response="local command check")
        app = AICTextualApp(backend, project_root=project_root)
        async with app.run_test(size=(90, 24)) as pilot:
            composer = app.query_one("#composer", Composer)
            composer.focus()
            composer.text = "/s"
            app._sync_command_palette()
            await pilot.pause(0.05)
            palette = app.query_one("#command_palette", CommandPalette)
            palette_names = [command.name for command in palette.commands]
            composer.text = "/se"
            app._sync_command_palette()
            await pilot.pause(0.05)
            session_palette_names = [command.name for command in palette.commands]
            composer.text = "/copy-"
            app._sync_command_palette()
            await pilot.pause(0.05)
            hyphen_palette_names = [command.name for command in palette.commands]
            composer.text = "/copy_"
            app._sync_command_palette()
            await pilot.pause(0.05)
            underscore_palette_names = [command.name for command in palette.commands]
            composer.text = "/"
            app._sync_command_palette()
            slash_palette_total = len(palette.commands)
            slash_palette_names = [command.name for command in palette.commands]
            app._backend_status["pending_approval"] = True
            app._backend_status["pending_approval_kind"] = "tool_approval"
            app._sync_command_palette()
            approval_palette_names = [command.name for command in palette.commands]
            app._backend_status["pending_approval"] = False
            app._backend_status["pending_approval_kind"] = ""
            app._sync_command_palette()
            for _ in range(COMMAND_PALETTE_VISIBLE_ROWS):
                await pilot.press("down")
            await pilot.pause(0.05)
            palette_visible_names = [command.name for command in palette.visible_commands()]
            palette_selected = palette.selected_command()
            palette_selected_name = palette_selected.name if palette_selected is not None else ""
            palette_scroll_offset = palette.palette_offset
            palette_selection_visible = palette_selected_name in palette_visible_names
            composer.text = "/se"
            app._sync_command_palette()
            await pilot.press("down")
            await pilot.press("up")
            await pilot.press("tab")
            completed_text = composer.text
            composer.text = "/details"
            details_visible_in_palette = "details" in slash_palette_names
            await pilot.press("enter")
            await pilot.pause(0.05)
            details_enabled = app._show_tool_details
            await app._handle_client_event(
                ClientEvent(
                    "tool_finished",
                    title="inspect_web_page",
                    text="x" * 520,
                )
            )
            await app._handle_client_event(ClientEvent("assistant_delta", text="local command check"))
            await app._handle_client_event(ClientEvent("assistant_done"))
            composer.text = "/export"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/copy-last"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/export ."
            await pilot.press("enter")
            await pilot.pause(0.05)
            messages = list(app.query(MessageBlock))
            tool_messages = [message.text for message in messages if message.has_class("tool")]
            meta_messages = [message.text for message in messages if message.has_class("meta")]
            error_messages = [message.text for message in messages if message.has_class("error")]
            exports = sorted((project_root / ".keygen" / "client-exports").glob("transcript-*.md"))
            export_text = exports[-1].read_text(encoding="utf-8") if exports else ""
            last_assistant_path = project_root / ".keygen" / "client-exports" / "last-assistant.md"
            last_assistant_text = last_assistant_path.read_text(encoding="utf-8") if last_assistant_path.exists() else ""
            composer.text = "/clear"
            await pilot.press("enter")
            await pilot.pause(0.05)
            cleared_message_count = len(list(app.query(MessageBlock)))

    passed = (
        "status" in palette_names
        and "sessions" in session_palette_names
        and "copy-last" in hyphen_palette_names
        and "copy-last" not in underscore_palette_names
        and slash_palette_total > COMMAND_PALETTE_VISIBLE_ROWS
        and palette_scroll_offset > 0
        and palette_selection_visible
        and completed_text == "/sessions "
        and not details_visible_in_palette
        and details_enabled
        and not any(
            name in slash_palette_names
            for name in (
                "ai",
                "approve",
                "back",
                "check",
                "close",
                "compact",
                "continue",
                "debug",
                "details",
                "list",
                "logs",
                "output",
                "pending",
                "quit",
                "reject",
                "report",
                "run",
                "stop",
                "todo",
                "use",
                "validate",
            )
        )
        and {"approve", "reject"}.issubset(set(approval_palette_names))
        and any("工具细节显示：开启" in message for message in meta_messages)
        and not any("AI 服务可用" in message for message in meta_messages)
        and any("状态：" in message and "thread=fake" in message for message in meta_messages)
        and any("工具 完成 inspect_web_page\n" in message and "x" * 500 in message for message in tool_messages)
        and bool(exports)
        and "## Meta" in export_text
        and "工具细节显示：开启" in export_text
        and any("Is a directory" in message or "目录" in message for message in error_messages)
        and last_assistant_text == "local command check\n"
        and cleared_message_count == 0
    )
    return {
        "name": "textual_client_supports_command_palette_details_and_export",
        "passed": passed,
        "detail": {
            "palette_names": palette_names,
            "session_palette_names": session_palette_names,
            "hyphen_palette_names": hyphen_palette_names,
            "underscore_palette_names": underscore_palette_names,
            "slash_palette_total": slash_palette_total,
            "slash_palette_names": slash_palette_names,
            "approval_palette_names": approval_palette_names,
            "palette_visible_names": palette_visible_names,
            "palette_selected_name": palette_selected_name,
            "palette_scroll_offset": palette_scroll_offset,
            "completed_text": completed_text,
            "details_visible_in_palette": details_visible_in_palette,
            "details_enabled": details_enabled,
            "tool_messages": tool_messages,
            "meta_messages": meta_messages,
            "error_messages": error_messages,
            "exports": [str(path) for path in exports],
            "last_assistant_text": last_assistant_text,
            "cleared_message_count": cleared_message_count,
        },
    }


class ClipboardImageBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="clipboard ok")
        self.attach_calls = 0

    async def attach_clipboard_images(self) -> list[str]:
        self.attach_calls += 1
        return ["[图片 #1]"]


class ClipboardTextOnlyBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="clipboard text ok")
        self.attach_calls = 0

    async def attach_clipboard_images(self) -> list[str]:
        self.attach_calls += 1
        return []


async def _check_textual_clipboard_text_paste_once() -> dict[str, Any]:
    backend = ClipboardTextOnlyBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "前缀"
        _move_composer_cursor_to_end(composer)
        app.copy_to_clipboard("粘贴文本")
        composer.post_message(Paste("粘贴文本"))
        await pilot.pause(0.1)
        await pilot.press("ctrl+v")
        await pilot.pause(0.1)
        pasted_text = composer.text
    passed = backend.attach_calls == 1 and pasted_text == "前缀粘贴文本"
    return {
        "name": "textual_client_pastes_text_once_when_native_paste_and_ctrl_v_overlap",
        "passed": passed,
        "detail": {
            "attach_calls": backend.attach_calls,
            "pasted_text": pasted_text,
        },
    }


async def _check_textual_clipboard_image_paste() -> dict[str, Any]:
    backend = ClipboardImageBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "请看"
        await pilot.press("ctrl+v")
        await pilot.pause(0.1)
        pasted_text = composer.text
        status_text = str(app.query_one("#status").content)
    passed = backend.attach_calls == 1 and "[图片 #1]" in pasted_text and status_text.startswith("已添加图片")
    return {
        "name": "textual_client_pastes_clipboard_images_into_composer",
        "passed": passed,
        "detail": {
            "attach_calls": backend.attach_calls,
            "pasted_text": pasted_text,
            "status": status_text,
        },
    }


class BusyClipboardImageBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.attach_calls = 0
        self.started: asyncio.Event | None = None
        self.release: asyncio.Event | None = None

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.started.set()
        yield ClientEvent("status", text="正在思考")
        await self.release.wait()
        yield ClientEvent("assistant_delta", text="完成")
        yield ClientEvent("assistant_done")

    async def attach_clipboard_images(self) -> list[str]:
        self.attach_calls += 1
        return ["[图片 #1]"]


async def _check_textual_busy_clipboard_image_paste_is_deferred() -> dict[str, Any]:
    backend = BusyClipboardImageBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "慢消息"
        await pilot.press("enter")
        for _ in range(100):
            if backend.started is not None and backend.started.is_set():
                break
            await pilot.pause(0.01)
        await pilot.press("ctrl+v")
        await pilot.pause(0.05)
        text_after_busy_paste = composer.text
        status_after_busy_paste = str(app.query_one("#status").content)
        meta_messages = [message.text for message in app.query(MessageBlock) if message.has_class("meta")]
        if backend.release is not None:
            backend.release.set()
        await _wait_until_idle(app, pilot)
    passed = (
        backend.attach_calls == 0
        and "[图片 #1]" not in text_after_busy_paste
        and "图片请在当前回复结束后粘贴" in status_after_busy_paste
        and any("图片请在回复结束后再粘贴" in message for message in meta_messages)
    )
    return {
        "name": "textual_client_defers_image_paste_while_busy",
        "passed": passed,
        "detail": {
            "attach_calls": backend.attach_calls,
            "composer_text": text_after_busy_paste,
            "status": status_after_busy_paste,
            "meta_messages": meta_messages,
        },
    }


class PendingApprovalEndingBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="")
        self.pending_approval = False

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.pending_approval = True
        yield ClientEvent("approval_requested", text="等待用户确认。", data={"approval_kind": "tool_approval"})

    async def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": "approval-ending",
            "busy": False,
            "pending_approval": self.pending_approval,
            "pending_approval_kind": "tool_approval" if self.pending_approval else "",
            "context_state": {},
        }


async def _check_textual_pending_approval_status_survives_idle() -> dict[str, Any]:
    backend = PendingApprovalEndingBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要审批"
        await pilot.press("enter")
        await _wait_until_idle(app, pilot)
        status_text = str(app.query_one("#status").content)
        approval_messages = [message.text for message in app.query(MessageBlock) if message.has_class("approval")]
        pending_approval = bool(app._backend_status.get("pending_approval"))
    passed = (
        pending_approval
        and "等待人工确认" in status_text
        and any("等待用户确认" in message for message in approval_messages)
    )
    return {
        "name": "textual_client_keeps_pending_approval_status_after_turn_idle",
        "passed": passed,
        "detail": {
            "status": status_text,
            "approval_messages": approval_messages,
            "pending_approval": pending_approval,
        },
    }


async def _check_ai_terminal_backend_interrupt_forks_stuck_worker(project_root: Path) -> dict[str, Any]:
    import ai_automate_contro.ai.terminal as terminal_module

    class FakeGraph:
        def __init__(self) -> None:
            self.updated_states: list[dict[str, Any]] = []

        def get_state(self, config: dict[str, Any]) -> Any:
            return SimpleNamespace(
                values={
                    "messages": ["stable-before-interrupt"],
                    "current_plan_path": "plans/demo/plan.json",
                }
            )

        def update_state(self, config: dict[str, Any], values: dict[str, Any]) -> None:
            self.updated_states.append(dict(values))

    class FakeTerminal:
        created: list["FakeTerminal"] = []
        slow_started = threading.Event()
        slow_release = threading.Event()

        def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
            self.project_root = project_root
            self.service = service
            self.thread_id = thread_id
            self.graph = FakeGraph()
            self.closed = False
            FakeTerminal.created.append(self)

        def _graph_config(self) -> dict[str, Any]:
            return {"configurable": {"thread_id": self.thread_id}}

        def run_event_turn(self, message: str, sink: Any) -> None:
            if message == "slow":
                FakeTerminal.slow_started.set()
                sink(SimpleNamespace(kind="status", text="正在思考", title="", data={}))
                FakeTerminal.slow_release.wait(timeout=2)
                sink(SimpleNamespace(kind="assistant_delta", text="迟到的旧回复", title="", data={}))
                sink(SimpleNamespace(kind="assistant_done", text="", title="", data={}))
                return
            sink(SimpleNamespace(kind="assistant_delta", text=f"介入 thread={self.thread_id}", title="", data={}))
            sink(SimpleNamespace(kind="assistant_done", text="", title="", data={}))

        def _cancel_agent_turn(self) -> bool:
            return True

        def can_handle_input_during_turn(self, message: str) -> bool:
            return False

        def handle_input(self, message: str) -> None:
            return None

        def attach_clipboard_images(self) -> list[str]:
            return []

        def client_status_snapshot(self) -> dict[str, Any]:
            return {"thread_id": self.thread_id, "service": self.service, "pending_approval": False}

        def _update_context_state(self, update: dict[str, Any]) -> None:
            return None

        def _sync_current_session_index(self) -> None:
            return None

        def format_error_message(self, error: BaseException) -> str:
            return str(error)

        def close(self) -> None:
            self.closed = True

    original_terminal = terminal_module.AITerminal
    original_grace = backend_module.INTERRUPT_GRACE_SECONDS
    terminal_module.AITerminal = FakeTerminal
    backend_module.INTERRUPT_GRACE_SECONDS = 0.01
    try:
        backend = AITerminalBackend(project_root, thread_id="self-check")
        slow_events: list[ClientEvent] = []

        async def collect_slow() -> None:
            async for event in backend.stream("slow"):
                slow_events.append(event)

        slow_task = asyncio.create_task(collect_slow())
        await asyncio.to_thread(FakeTerminal.slow_started.wait, 1)
        interrupt_event = await backend.interrupt()
        intervention_events = [event async for event in backend.stream("intervene")]
        FakeTerminal.slow_release.set()
        await asyncio.wait_for(slow_task, timeout=1)
        created_threads = [terminal.thread_id for terminal in FakeTerminal.created]
        fork_terminal = FakeTerminal.created[-1] if FakeTerminal.created else None
        fork_seeded = bool(fork_terminal and fork_terminal.graph.updated_states)
        assistant_messages = [event.text for event in intervention_events if event.kind == "assistant_delta"]
        passed = (
            interrupt_event.kind == "interrupted"
            and created_threads[:2] == ["self-check", "self-check-intervention-1"]
            and backend.thread_id == "self-check-intervention-1"
            and fork_seeded
            and assistant_messages == ["介入 thread=self-check-intervention-1"]
        )
        return {
            "name": "ai_terminal_backend_interrupt_forks_stuck_worker_checkpoint",
            "passed": passed,
            "detail": {
                "interrupt_event": {"kind": interrupt_event.kind, "text": interrupt_event.text},
                "created_threads": created_threads,
                "backend_thread": backend.thread_id,
                "fork_seeded": fork_seeded,
                "slow_events": [{"kind": event.kind, "text": event.text} for event in slow_events],
                "intervention_events": [{"kind": event.kind, "text": event.text} for event in intervention_events],
            },
        }
    except Exception as error:
        return {
            "name": "ai_terminal_backend_interrupt_forks_stuck_worker_checkpoint",
            "passed": False,
            "detail": {"error": str(error)},
        }
    finally:
        FakeTerminal.slow_release.set()
        terminal_module.AITerminal = original_terminal
        backend_module.INTERRUPT_GRACE_SECONDS = original_grace


async def _check_backend_confirmation_feedback_not_swallowed(project_root: Path) -> dict[str, Any]:
    from ai_automate_contro.ai import terminal as terminal_module

    class FakeTerminal:
        def __init__(self, project_root: Path, *, service: str = "default", thread_id: str = "default") -> None:
            self.project_root = project_root
            self.service = service
            self.thread_id = thread_id
            self.submitted: list[str] = []
            self.classified: list[tuple[str, str]] = []
            self._confirmation = object()

        def _current_ai_confirmation(self) -> object | None:
            return self._confirmation

        def can_handle_input_during_turn(self, message: str) -> bool:
            return self._confirmation is not None

        def classify_active_turn_input(
            self,
            message: str,
            *,
            prompt: str = "",
            wait_type: str = "",
            context: dict[str, Any] | None = None,
        ) -> str:
            intent = FEEDBACK_OR_CORRECTION if "没有填写" in message else CONFIRM_CURRENT_WAIT
            self.classified.append((message, intent))
            return intent

        def submit_ai_confirmation_reply(self, message: str) -> bool:
            self.submitted.append(message)
            self._confirmation = None
            return True

        def client_status_snapshot(self) -> dict[str, Any]:
            return {
                "thread_id": self.thread_id,
                "service": self.service,
                "pending_approval": self._confirmation is not None,
                "pending_approval_kind": "active_wait" if self._confirmation is not None else "",
            }

        def attach_clipboard_images(self) -> list[str]:
            return []

        def close(self) -> None:
            return None

    original_terminal = terminal_module.AITerminal
    terminal_module.AITerminal = FakeTerminal
    try:
        backend = AITerminalBackend(project_root, thread_id="confirmation-feedback")
        terminal = backend._require_terminal()
        feedback_handled = await backend.submit_during_turn("账户密码没有填写上呢")
        confirmation_still_pending = terminal._current_ai_confirmation() is not None
        confirm_handled = await backend.submit_during_turn("继续")
        passed = (
            feedback_handled is False
            and confirmation_still_pending
            and confirm_handled is True
            and terminal.classified == [
                ("账户密码没有填写上呢", FEEDBACK_OR_CORRECTION),
                ("继续", CONFIRM_CURRENT_WAIT),
            ]
            and terminal.submitted == ["继续"]
        )
        return {
            "name": "ai_terminal_backend_keeps_confirmation_feedback_for_intervention",
            "passed": passed,
            "detail": {
                "feedback_handled": feedback_handled,
                "confirmation_still_pending": confirmation_still_pending,
                "confirm_handled": confirm_handled,
                "classified": terminal.classified,
                "submitted": terminal.submitted,
            },
        }
    except Exception as error:
        return {
            "name": "ai_terminal_backend_keeps_confirmation_feedback_for_intervention",
            "passed": False,
            "detail": {"error": str(error)},
        }
    finally:
        terminal_module.AITerminal = original_terminal


async def _check_textual_activity_stream_stays_high_level() -> dict[str, Any]:
    app = AICTextualApp(FakeAgentBackend(response="活动降噪 ok"))
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "工具 计划"
        await pilot.press("enter")
        await pilot.pause(0.2)
        messages = list(app.query(MessageBlock))
        activity_messages = [message.text for message in messages if message.has_class("activity")]
        tool_messages = [message.text for message in messages if message.has_class("tool")]
        summary_messages = [message.text for message in messages if message.has_class("summary")]
    passed = (
        len(activity_messages) == 1
        and any("更新工作计划" in message for message in activity_messages)
        and not any("inspect_web_page" in message for message in activity_messages)
        and any("工具 完成 inspect_web_page" in message for message in tool_messages)
        and any("工具：完成 inspect_web_page" in message for message in summary_messages)
        and any("进度：更新工作计划" in message and "下一步：按可见计划继续推进。" in message for message in summary_messages)
    )
    return {
        "name": "textual_client_activity_stream_stays_high_level",
        "passed": passed,
        "detail": {
            "activity_messages": activity_messages,
            "tool_messages": tool_messages,
            "summary_messages": summary_messages,
        },
    }


async def _check_textual_ui_snapshot_layout() -> dict[str, Any]:
    backend = FakeAgentBackend(response="界面快照 ok")
    app = AICTextualApp(backend)
    async with app.run_test(size=(120, 44)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        for text in ("工具 计划", "审批 错误"):
            composer.text = text
            await pilot.press("enter")
            await pilot.pause(0.2)
        await pilot.pause(0.2)
        messages = list(app.query(MessageBlock))
        svg = app.export_screenshot()
        status_text = str(app.query_one("#status").content)
        plan_panel = app.query_one("#work_plan_panel", WorkPlanPanel)
        plan_panel_visible = bool(plan_panel.display)
        role_counts = {
            role: sum(1 for message in messages if message.has_class(role))
            for role in ("user", "assistant", "tool", "activity", "approval", "error", "summary", "meta")
        }
        activity_messages = [message.text for message in messages if message.has_class("activity")]
        summary_messages = [message.text for message in messages if message.has_class("summary")]
    required_svg_tokens = [
        "需要你确认",
        "error",
        "计划",
        "界面快照",
        "就绪",
    ]
    forbidden_tokens = ["AI&gt;", "你&gt;", "plan&gt;", "ai&gt;", "AI>", "你>", "plan>", "ai>"]
    passed = (
        len(svg) > 10_000
        and all(token in svg for token in required_svg_tokens)
        and not any(token in svg for token in forbidden_tokens)
        and role_counts["user"] == 2
        and role_counts["assistant"] == 2
        and role_counts["tool"] == 1
        and role_counts["activity"] == 1
        and role_counts["approval"] == 1
        and role_counts["error"] == 1
        and role_counts["summary"] >= 2
        and any("更新工作计划" in message for message in activity_messages)
        and not any("inspect_web_page" in message for message in activity_messages)
        and any("工具：完成 inspect_web_page" in message for message in summary_messages)
        and plan_panel_visible
        and status_text.startswith("就绪")
    )
    return {
        "name": "textual_client_ui_snapshot_layout",
        "passed": passed,
        "detail": {
            "svg_chars": len(svg),
            "role_counts": role_counts,
            "activity_messages": activity_messages,
            "summary_messages": summary_messages,
            "status": status_text,
            "plan_panel_visible": plan_panel_visible,
            "required_svg_tokens": {token: token in svg for token in required_svg_tokens},
            "forbidden_hits": [token for token in forbidden_tokens if token in svg],
        },
    }


def _check_textual_slash_command_routing(project_root: Path) -> dict[str, Any]:
    from ai_automate_contro.client.commands import client_command_suggestions

    slash_names = [command.name for command in client_command_suggestions("/")]
    forbidden = {"list", "use", "run", "continue", "close", "stop", "validate", "debug"}
    passed = not forbidden.intersection(slash_names)
    return {
        "name": "textual_client_has_no_plan_management_commands",
        "passed": passed,
        "detail": {
            "slash_names": slash_names,
            "forbidden_hits": sorted(forbidden.intersection(slash_names)),
        },
    }


def _check_no_legacy_interactive_surface(project_root: Path) -> dict[str, Any]:
    forbidden_files = [
        "src/ai_automate_contro/app/management_terminal.py",
        "src/ai_automate_contro/app/management_plan_commands.py",
        "src/ai_automate_contro/app/management_run_commands.py",
        "src/ai_automate_contro/app/management_debug_commands.py",
        "src/ai_automate_contro/app/management_output_commands.py",
        "src/ai_automate_contro/support/terminal_style.py",
        "src/ai_automate_contro/ai/terminal_markdown.py",
    ]
    forbidden_patterns = {
        "prompt_toolkit": ("src", "pyproject.toml", "scripts", "README.md", "docs", "handbook"),
        "terminal_output": ("src/ai_automate_contro/ai", "src/ai_automate_contro/client"),
        "_emit_terminal_output": ("src/ai_automate_contro/ai", "src/ai_automate_contro/client"),
        "response_render_mode": ("src", "docs", "README.md"),
        "terminal_render_mode": ("src", "docs", "README.md"),
        "/render": ("src", "docs", "README.md", "handbook"),
    }
    existing_forbidden_files = [
        relative_path
        for relative_path in forbidden_files
        if (project_root / relative_path).exists()
    ]
    pattern_hits: dict[str, list[str]] = {}
    for pattern, roots in forbidden_patterns.items():
        hits: list[str] = []
        for root in roots:
            root_path = project_root / root
            if not root_path.exists():
                continue
            if root_path.is_file():
                paths = [root_path]
            else:
                paths = [
                    path
                    for path in root_path.rglob("*")
                    if path.is_file()
                    and not _is_generated_or_self_check_file(path, project_root)
                    and path.suffix in {".py", ".md", ".toml", ".sh", ".ps1", ".txt"}
                ]
            for path in paths:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if pattern in text:
                    hits.append(str(path.relative_to(project_root)))
        if hits:
            pattern_hits[pattern] = sorted(set(hits))
    return {
        "name": "textual_client_has_no_legacy_interactive_surface",
        "passed": not existing_forbidden_files and not pattern_hits,
        "detail": {
            "forbidden_files": existing_forbidden_files,
            "pattern_hits": pattern_hits,
        },
    }


def _is_generated_or_self_check_file(path: Path, project_root: Path) -> bool:
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return True
    parts = set(relative.parts)
    return (
        "__pycache__" in parts
        or any(part.endswith(".egg-info") for part in relative.parts)
        or relative == Path("src/ai_automate_contro/client/self_check.py")
    )


async def _wait_until_idle(app: AICTextualApp, pilot: Any, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if not app._busy and not app._queue:
            await pilot.pause(0.05)
            return
        await pilot.pause(0.05)
