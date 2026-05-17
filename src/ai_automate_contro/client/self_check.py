from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from collections.abc import AsyncIterator
from tempfile import TemporaryDirectory

from textual.events import Paste

from ai_automate_contro.client.backend import AITerminalBackend, FakeAgentBackend, _management_payload
from ai_automate_contro.client.management import ClientManagementController
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
    THINKING_IDLE_TICKS,
    THINKING_TICK_SECONDS,
    ToolBlock,
    WorkPlanPanel,
    ActivityBlock,
    _format_approval_text,
    _format_transcript_markdown,
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
        composer.text = "第二条排队消息"
        await pilot.press("enter")
        composer.text = "审批 错误"
        await pilot.press("enter")
        composer.text = "计划任务"
        await pilot.press("enter")
        await pilot.pause(0.05)
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
        top_status_text = str(app.query_one("#top_status").content)
        brand_text = str(app.query_one("#brand").content)
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
    chrome_result = _check_textual_agent_chrome(brand_text=brand_text, top_status_text=top_status_text)
    thinking_result = await _check_textual_thinking_indicator()
    markdown_result = _check_textual_markdown_does_not_emit_terminal_hyperlinks()
    approval_guidance_result = _check_textual_approval_guidance_is_not_duplicated()
    transcript_export_result = _check_textual_transcript_export_keeps_raw_text()
    interrupt_result = await _check_textual_escape_interrupts_without_queue()
    intervention_result = await _check_textual_escape_promotes_queue_to_intervention()
    stuck_intervention_result = await _check_textual_escape_intervention_survives_stuck_turn()
    active_confirmation_result = await _check_active_confirmation_input()
    command_palette_result = await _check_textual_command_palette_and_local_commands()
    clipboard_text_paste_result = await _check_textual_clipboard_text_paste_once()
    clipboard_paste_result = await _check_textual_clipboard_image_paste()
    management_result = await _check_textual_management_commands()
    management_confirmation_result = await _check_textual_management_confirmation_natural_language()
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
            and interrupt_result["passed"]
            and intervention_result["passed"]
            and stuck_intervention_result["passed"]
            and active_confirmation_result["passed"]
            and command_palette_result["passed"]
            and clipboard_text_paste_result["passed"]
            and clipboard_paste_result["passed"]
            and management_result["passed"]
            and management_confirmation_result["passed"]
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
                "passed": multiline_shortcut_ok and enter_send_ok,
                "detail": {
                    "line_continuation_text": line_continuation_text,
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
                "detail": {"status": status_text, "top_status": top_status_text},
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
            interrupt_result,
            intervention_result,
            stuck_intervention_result,
            active_confirmation_result,
            command_palette_result,
            clipboard_text_paste_result,
            clipboard_paste_result,
            management_result,
            management_confirmation_result,
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
        early_top_status = str(app.query_one("#top_status").content)
        await pilot.pause(THINKING_TICK_SECONDS * (THINKING_IDLE_TICKS + 3))
        waiting_status = str(app.query_one("#status").content)
        waiting_top_status = str(app.query_one("#top_status").content)
        await _wait_until_idle(app, pilot)
        final_status = str(app.query_one("#status").content)
        final_top_status = str(app.query_one("#top_status").content)
        assistant_messages = [
            message.text
            for message in app.query(MessageBlock)
            if message.has_class("assistant")
        ]
    passed = (
        "正在思考" in early_status
        and "." in early_status
        and "正在思考" in waiting_status
        and "正在思考" not in early_top_status
        and "正在思考" not in waiting_top_status
        and "正在思考" not in final_top_status
        and final_status.startswith("就绪")
        and "正在思考" not in final_status
        and assistant_messages == ["第一段第二段"]
    )
    return {
        "name": "textual_client_animates_thinking_and_clears_on_done",
        "passed": passed,
        "detail": {
            "early_status": early_status,
            "early_top_status": early_top_status,
            "waiting_status": waiting_status,
            "waiting_top_status": waiting_top_status,
            "final_status": final_status,
            "final_top_status": final_top_status,
            "assistant_messages": assistant_messages,
        },
    }


def _check_textual_markdown_does_not_emit_terminal_hyperlinks() -> dict[str, Any]:
    block = MessageBlock("https://example.com\n\n[link](https://example.com)", role="assistant")
    renderable = block._renderable()
    hyperlinks = getattr(renderable, "hyperlinks", None)
    passed = hyperlinks is False
    return {
        "name": "textual_client_disables_terminal_hyperlinks_in_assistant_markdown",
        "passed": passed,
        "detail": {"hyperlinks": hyperlinks},
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
        status_text = str(app.query_one("#status").content)

    expected_intervention = "第一条介入\n\n第二条介入"
    passed = (
        queued_before_escape == ["第一条介入", "第二条介入"]
        and backend.messages == ["第一条慢消息", expected_intervention]
        and backend.interrupt_calls == 1
        and user_messages == ["第一条慢消息", "第一条介入", "第二条介入"]
        and assistant_messages == [f"收到：{expected_intervention}"]
        and any("已介入排队消息 2 条" in message for message in meta_messages)
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


def _check_textual_agent_chrome(*, brand_text: str, top_status_text: str) -> dict[str, Any]:
    css = AICTextualApp.CSS
    forbidden_light_fragments = [
        "background: #ffffff",
        "background: #f3f4f6",
        "background: #fff5f5",
        "background: #eef6ff",
    ]
    passed = (
        brand_text == "AIC"
        and bool(top_status_text.strip())
        and "#top_bar" in css
        and "#composer_row" in css
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
            "brand": brand_text,
            "top_status": top_status_text,
            "has_top_bar_css": "#top_bar" in css,
            "has_tool_phase_css": all(fragment in css for fragment in (".tool-running", ".tool-done", ".tool-failed")),
            "tool_is_compact": "border-left: tall #4e5560" not in css and "height: 1;" in css,
        },
    }


class ConfirmationBackend:
    def __init__(self) -> None:
        self.confirmation: asyncio.Future[str] | None = None
        self.handled_inputs: list[str] = []

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.confirmation = asyncio.get_running_loop().create_future()
        yield ClientEvent("approval_requested", text=f"等待确认：{message}")
        accepted = await self.confirmation
        yield ClientEvent("system_output", text=f"确认输入：{accepted}")
        yield ClientEvent("assistant_delta", text="继续执行")
        yield ClientEvent("assistant_done")

    async def submit_during_turn(self, message: str) -> bool:
        if self.confirmation is None or self.confirmation.done():
            return False
        self.handled_inputs.append(message)
        self.confirmation.set_result(message)
        return True

    async def attach_clipboard_images(self) -> list[str]:
        return []

    async def status_snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": "confirmation",
            "busy": self.confirmation is not None and not self.confirmation.done(),
            "pending_approval": self.confirmation is not None and not self.confirmation.done(),
            "context_state": {},
            "management": {},
        }

    async def close(self) -> None:
        if self.confirmation is not None and not self.confirmation.done():
            self.confirmation.cancel()


async def _check_active_confirmation_input() -> dict[str, Any]:
    backend = ConfirmationBackend()
    app = AICTextualApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "需要人工确认的任务"
        await pilot.press("enter")
        await pilot.pause(0.05)
        composer.text = "可以继续"
        await pilot.press("enter")
        await pilot.pause(0.1)
        messages = list(app.query(MessageBlock))
        user_messages = [message.text for message in messages if message.has_class("user")]
        meta_messages = [message.text for message in messages if message.has_class("meta")]
        approval_messages = [message.text for message in messages if message.has_class("approval")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
    passed = (
        backend.handled_inputs == ["可以继续"]
        and user_messages == ["需要人工确认的任务", "可以继续"]
        and any("确认输入：可以继续" in text for text in meta_messages)
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
            composer.text = "/"
            app._sync_command_palette()
            slash_palette_total = len(palette.commands)
            for _ in range(COMMAND_PALETTE_VISIBLE_ROWS + 3):
                await pilot.press("down")
            palette_visible_names = [command.name for command in palette.visible_commands()]
            palette_selected = palette.selected_command()
            palette_selected_name = palette_selected.name if palette_selected is not None else ""
            palette_scroll_offset = palette.palette_offset
            palette_selection_visible = palette_selected_name in palette_visible_names
            composer.text = "/s"
            app._sync_command_palette()
            await pilot.press("down")
            await pilot.press("up")
            await pilot.press("tab")
            completed_text = composer.text
            composer.text = "/det"
            app._sync_command_palette()
            await pilot.press("enter")
            details_completed_text = composer.text
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
            composer.text = "/check"
            await pilot.press("enter")
            await pilot.pause(0.05)
            messages = list(app.query(MessageBlock))
            tool_messages = [message.text for message in messages if message.has_class("tool")]
            meta_messages = [message.text for message in messages if message.has_class("meta")]
            exports = sorted((project_root / ".keygen" / "client-exports").glob("transcript-*.md"))
            export_text = exports[-1].read_text(encoding="utf-8") if exports else ""
            last_assistant_path = project_root / ".keygen" / "client-exports" / "last-assistant.md"
            last_assistant_text = last_assistant_path.read_text(encoding="utf-8") if last_assistant_path.exists() else ""
            composer.text = "/clear"
            await pilot.press("enter")
            await pilot.pause(0.05)
            cleared_message_count = len(list(app.query(MessageBlock)))

    passed = (
        "sessions" in palette_names
        and slash_palette_total > COMMAND_PALETTE_VISIBLE_ROWS
        and palette_scroll_offset > 0
        and palette_selection_visible
        and completed_text == "/sessions "
        and details_completed_text == "/details "
        and details_enabled
        and any("工具细节显示：开启" in message for message in meta_messages)
        and any("AI 服务可用" in message for message in meta_messages)
        and any("工具 完成 inspect_web_page\n" in message and "x" * 500 in message for message in tool_messages)
        and bool(exports)
        and "## Meta" in export_text
        and "工具细节显示：开启" in export_text
        and last_assistant_text == "local command check\n"
        and cleared_message_count == 0
    )
    return {
        "name": "textual_client_supports_command_palette_details_and_export",
        "passed": passed,
        "detail": {
            "palette_names": palette_names,
            "slash_palette_total": slash_palette_total,
            "palette_visible_names": palette_visible_names,
            "palette_selected_name": palette_selected_name,
            "palette_scroll_offset": palette_scroll_offset,
            "completed_text": completed_text,
            "details_completed_text": details_completed_text,
            "details_enabled": details_enabled,
            "tool_messages": tool_messages,
            "meta_messages": meta_messages,
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


async def _check_textual_management_commands() -> dict[str, Any]:
    with TemporaryDirectory(prefix="textual-management-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        plan_dir = project_root / "plans" / "demo"
        plan_dir.mkdir(parents=True)
        (project_root / "handbook").mkdir()
        (project_root / "plan.config").write_text(
            json.dumps(
                {
                    "handbook_path": "handbook",
                    "plan_roots": ["plans"],
                    "default_ai_config_dir": "plans",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (project_root / "plans" / "config.json").write_text("{}\n", encoding="utf-8")
        (plan_dir / "config.json").write_text("{}\n", encoding="utf-8")
        (plan_dir / "plan.json").write_text(
            json.dumps(
                {
                    "name": "textual-management-demo",
                    "variables": {},
                    "steps": [
                        {
                            "action": "print",
                            "message": "management ok",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        backend = AITerminalBackend(project_root)
        app = AICTextualApp(backend, project_root=project_root)
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", Composer)
            composer.focus()
            for command in (
                "/list",
                "/use plans/demo",
                "/debug create textual-debug",
                "/debug list",
                '/debug inject print textual-debug --message "debug point"',
                "/debug patch textual-debug",
                "/debug apply --yes textual-debug",
                "/current",
                "/validate",
                "/run textual-management-smoke",
                "/status --short",
                "/logs 10",
                "/artifacts 20",
            ):
                composer.text = command
                await pilot.press("enter")
                await pilot.pause(0.2)
            await _wait_until_idle(app, pilot)
            messages = list(app.query(MessageBlock))
            meta_messages = [message.text for message in messages if message.has_class("meta")]
            plan_messages = [message.text for message in messages if message.has_class("plan")]
            file_messages = [message.text for message in messages if message.has_class("file")]
            diff_messages = [message.text for message in messages if message.has_class("diff")]
            summary_messages = [message.text for message in messages if message.has_class("summary")]
            approval_messages = [message.text for message in messages if message.has_class("approval")]
            error_messages = [message.text for message in messages if message.has_class("error")]
            status_text = str(app.query_one("#status").content)

    joined = "\n".join(meta_messages + plan_messages + approval_messages)
    passed = (
        not error_messages
        and "textual-management-demo" in joined
        and "当前 plan：" in joined
        and "textual-debug" in joined
        and "debug point" in joined
        and '"applied": true' in joined
        and any("files=plan.json" in message and "+      \"message\": \"debug point\"" in message for message in diff_messages)
        and any("文件 应用" in message and "plan.json" in message for message in file_messages)
        and any("本轮结果" in message and "Diff：" in message and "plan.json" in message for message in summary_messages)
        and any("本轮结果" in message and "Plan：" in message and "plan 结束" in message for message in summary_messages)
        and "计划校验通过" in joined
        and "计划运行结果 passed" in joined
        and "management ok" in joined
        and "plan 开始" in joined
        and "步骤 1 开始" in joined
        and "plan 结束" in joined
        and "run.log" in joined
        and "plan plans/demo/plan.json" in status_text
    )
    return {
        "name": "textual_client_restores_management_commands",
        "passed": passed,
        "detail": {
            "meta_messages": meta_messages,
            "plan_messages": plan_messages,
            "file_messages": file_messages,
            "diff_messages": diff_messages,
            "summary_messages": summary_messages,
            "approval_messages": approval_messages,
            "error_messages": error_messages,
            "status": status_text,
        },
    }


async def _check_textual_management_confirmation_natural_language() -> dict[str, Any]:
    with TemporaryDirectory(prefix="textual-management-confirm-self-check-") as raw_temp_dir:
        project_root = Path(raw_temp_dir).resolve()
        plan_dir = project_root / "plans" / "confirm"
        plan_dir.mkdir(parents=True)
        (project_root / "handbook").mkdir()
        (project_root / "plan.config").write_text(
            json.dumps(
                {
                    "handbook_path": "handbook",
                    "plan_roots": ["plans"],
                    "default_ai_config_dir": "plans",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (project_root / "plans" / "config.json").write_text("{}\n", encoding="utf-8")
        (plan_dir / "config.json").write_text("{}\n", encoding="utf-8")
        (plan_dir / "plan.json").write_text(
            json.dumps(
                {
                    "name": "textual-management-confirm",
                    "variables": {},
                    "steps": [
                        {"action": "print", "message": "before confirm"},
                        {"action": "manual_confirm", "prompt": "请确认后继续。"},
                        {"action": "print", "message": "after confirm"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        backend = AITerminalBackend(project_root)
        app = AICTextualApp(backend, project_root=project_root)
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", Composer)
            composer.focus()
            for command in ("/use plans/confirm", "/run confirm-natural-language"):
                composer.text = command
                await pilot.press("enter")
                await pilot.pause(0.2)
            composer.text = "继续"
            await pilot.press("enter")
            await _wait_until_idle(app, pilot)
            messages = list(app.query(MessageBlock))
            user_messages = [message.text for message in messages if message.has_class("user")]
            meta_messages = [message.text for message in messages if message.has_class("meta")]
            plan_messages = [message.text for message in messages if message.has_class("plan")]
            approval_messages = [message.text for message in messages if message.has_class("approval")]
            summary_messages = [message.text for message in messages if message.has_class("summary")]
            error_messages = [message.text for message in messages if message.has_class("error")]
            status_text = str(app.query_one("#status").content)

    joined = "\n".join(meta_messages + plan_messages + approval_messages)
    passed = (
        not error_messages
        and user_messages[-1:] == ["继续"]
        and any("请确认后继续" in message and "直接回复“继续”" in message for message in approval_messages)
        and "人工确认已继续" in joined
        and "步骤 3 完成" in joined
        and "plan 结束 · confirm-natural-language" in joined
        and "计划运行结果 passed" in joined
        and "run passed" in status_text
        and any(
            "plan 结束 · confirm-natural-language" in message and "等待确认：" not in message
            for message in summary_messages
        )
    )
    return {
        "name": "textual_client_management_wait_accepts_natural_language_confirmation",
        "passed": passed,
        "detail": {
            "user_messages": user_messages,
            "meta_messages": meta_messages,
            "plan_messages": plan_messages,
            "approval_messages": approval_messages,
            "summary_messages": summary_messages,
            "error_messages": error_messages,
            "status": status_text,
        },
    }


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
        top_status_text = str(app.query_one("#top_status").content)
        plan_panel = app.query_one("#work_plan_panel", WorkPlanPanel)
        plan_panel_visible = bool(plan_panel.display)
        role_counts = {
            role: sum(1 for message in messages if message.has_class(role))
            for role in ("user", "assistant", "tool", "activity", "approval", "error", "summary", "meta")
        }
        activity_messages = [message.text for message in messages if message.has_class("activity")]
        summary_messages = [message.text for message in messages if message.has_class("summary")]
    required_svg_tokens = [
        "AIC",
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
        and "thread fake" in top_status_text
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
            "top_status": top_status_text,
            "plan_panel_visible": plan_panel_visible,
            "required_svg_tokens": {token: token in svg for token in required_svg_tokens},
            "forbidden_hits": [token for token in forbidden_tokens if token in svg],
        },
    }


def _check_textual_slash_command_routing(project_root: Path) -> dict[str, Any]:
    controller = ClientManagementController(project_root)
    cases = {
        "/list": _management_payload("/list", controller),
        "/debug list": _management_payload("/debug list", controller),
        "/sessions": _management_payload("/sessions", controller),
        "/approve": _management_payload("/approve", controller),
        "/ai hello": _management_payload("/ai hello", controller),
        "/compact": _management_payload("/compact", controller),
    }
    passed = (
        cases["/list"] == "/list"
        and cases["/debug list"] == "/debug list"
        and cases["/sessions"] is None
        and cases["/approve"] is None
        and cases["/ai hello"] is None
        and cases["/compact"] is None
    )
    return {
        "name": "textual_client_routes_only_management_slash_commands_to_management",
        "passed": passed,
        "detail": cases,
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
