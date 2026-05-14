from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from collections.abc import AsyncIterator
from tempfile import TemporaryDirectory

from ai_automate_contro.client.backend import AITerminalBackend, FakeAgentBackend, _management_payload
from ai_automate_contro.client.management import ClientManagementController
from ai_automate_contro.client.events import ClientEvent
from ai_automate_contro.client.textual_app import AICTextualApp, CommandPalette, Composer, MessageBlock


def self_check_textual_client(project_root: str | Path) -> dict[str, Any]:
    return asyncio.run(_self_check_textual_client_async(Path(project_root).resolve()))


async def _self_check_textual_client_async(project_root: Path) -> dict[str, Any]:
    backend = FakeAgentBackend(response="你好，我在。\n\n- 可以创建 plan\n- 可以运行 plan")
    app = AICTextualApp(backend)
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.query_one("#composer", Composer)
        composer.focus()
        composer.text = "工具测试\n第二行"
        app._sync_composer_height()
        initial_height = int(composer.styles.height.value)
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
        composer.text = "工具测试\n第二行"
        await pilot.press("enter")
        composer.text = "第二条排队消息"
        await pilot.press("enter")
        composer.text = "审批 错误"
        await pilot.press("enter")
        await pilot.pause(0.2)
        messages = list(app.query(MessageBlock))
        message_texts = [message.text for message in messages]
        user_messages = [message for message in messages if message.has_class("user")]
        assistant_messages = [message for message in messages if message.has_class("assistant")]
        tool_messages = [message for message in messages if message.has_class("tool")]
        error_messages = [message for message in messages if message.has_class("error")]
        status_text = str(app.query_one("#status").content)

    user_ok = len(user_messages) == 3 and user_messages[0].text == "工具测试\n第二行"
    assistant_ok = len(assistant_messages) == 3 and all("你好，我在。" in message.text for message in assistant_messages)
    tool_ok = len(tool_messages) >= 2 and any("inspect_web_page" in message.text for message in tool_messages)
    approval_ok = any("[等待审批]" in message.text for message in tool_messages)
    error_ok = len(error_messages) == 1 and "模拟错误" in error_messages[0].text
    queue_ok = [message.text for message in user_messages] == ["工具测试\n第二行", "第二条排队消息", "审批 错误"]
    resize_ok = initial_height == 2 and 1 <= wide_height <= narrow_height <= 6
    no_legacy_prompt_ok = all(
        "AI>" not in text and "你>" not in text and "plan>" not in text and "ai>" not in text
        for text in message_texts
    )
    status_ok = status_text in {"就绪", "正在处理"}
    active_confirmation_result = await _check_active_confirmation_input()
    command_palette_result = await _check_textual_command_palette_and_local_commands()
    clipboard_paste_result = await _check_textual_clipboard_image_paste()
    management_result = await _check_textual_management_commands()
    slash_routing_result = _check_textual_slash_command_routing(project_root)
    return {
        "ok": (
            user_ok
            and assistant_ok
            and tool_ok
            and approval_ok
            and error_ok
            and queue_ok
            and resize_ok
            and no_legacy_prompt_ok
            and status_ok
            and active_confirmation_result["passed"]
            and command_palette_result["passed"]
            and clipboard_paste_result["passed"]
            and management_result["passed"]
            and slash_routing_result["passed"]
        ),
        "check": "textual_client",
        "project_root": str(project_root),
        "checks": [
            {
                "name": "textual_fake_backend_chat_flow",
                "passed": user_ok and assistant_ok,
                "detail": {"messages": message_texts},
            },
            {
                "name": "textual_client_renders_tool_progress",
                "passed": tool_ok,
                "detail": {"tool_messages": [message.text for message in tool_messages]},
            },
            {
                "name": "textual_client_renders_approval_and_errors",
                "passed": approval_ok and error_ok,
                "detail": {
                    "tool_messages": [message.text for message in tool_messages],
                    "error_messages": [message.text for message in error_messages],
                },
            },
            {
                "name": "textual_client_queues_multiple_messages",
                "passed": queue_ok,
                "detail": {"user_messages": [message.text for message in user_messages]},
            },
            {
                "name": "textual_client_composer_height_tracks_resize",
                "passed": resize_ok,
                "detail": {
                    "initial_height": initial_height,
                    "wide_height": wide_height,
                    "narrow_height": narrow_height,
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
            active_confirmation_result,
            command_palette_result,
            clipboard_paste_result,
            management_result,
            slash_routing_result,
        ],
    }


class ConfirmationBackend:
    def __init__(self) -> None:
        self.confirmation: asyncio.Future[str] | None = None
        self.handled_inputs: list[str] = []

    async def stream(self, message: str) -> AsyncIterator[ClientEvent]:
        self.confirmation = asyncio.get_running_loop().create_future()
        yield ClientEvent("approval_requested", text=f"等待确认：{message}")
        accepted = await self.confirmation
        yield ClientEvent("terminal_output", text=f"确认输入：{accepted}")
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
        tool_messages = [message.text for message in messages if message.has_class("tool")]
        assistant_messages = [message.text for message in messages if message.has_class("assistant")]
    passed = (
        backend.handled_inputs == ["可以继续"]
        and user_messages == ["需要人工确认的任务", "可以继续"]
        and any("确认输入：可以继续" in text for text in tool_messages)
        and assistant_messages == ["继续执行"]
    )
    return {
        "name": "textual_client_routes_confirmation_to_active_turn",
        "passed": passed,
        "detail": {
            "handled_inputs": backend.handled_inputs,
            "user_messages": user_messages,
            "tool_messages": tool_messages,
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
            composer.text = "/export"
            await pilot.press("enter")
            await pilot.pause(0.05)
            messages = list(app.query(MessageBlock))
            tool_messages = [message.text for message in messages if message.has_class("tool")]
            exports = sorted((project_root / ".keygen" / "client-exports").glob("transcript-*.md"))
            export_text = exports[-1].read_text(encoding="utf-8") if exports else ""

    passed = (
        "sessions" in palette_names
        and completed_text == "/sessions "
        and details_completed_text == "/details "
        and details_enabled
        and any("工具细节显示：开启" in message for message in tool_messages)
        and any("tool done: inspect_web_page\n" in message and "x" * 500 in message for message in tool_messages)
        and bool(exports)
        and "## Tool" in export_text
        and "工具细节显示：开启" in export_text
    )
    return {
        "name": "textual_client_supports_command_palette_details_and_export",
        "passed": passed,
        "detail": {
            "palette_names": palette_names,
            "completed_text": completed_text,
            "details_completed_text": details_completed_text,
            "details_enabled": details_enabled,
            "tool_messages": tool_messages,
            "exports": [str(path) for path in exports],
        },
    }


class ClipboardImageBackend(FakeAgentBackend):
    def __init__(self) -> None:
        super().__init__(response="clipboard ok")
        self.attach_calls = 0

    async def attach_clipboard_images(self) -> list[str]:
        self.attach_calls += 1
        return ["[图片 #1]"]


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
        app = AICTextualApp(backend)
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
            tool_messages = [message.text for message in messages if message.has_class("tool")]
            error_messages = [message.text for message in messages if message.has_class("error")]

    joined = "\n".join(tool_messages)
    passed = (
        not error_messages
        and "textual-management-demo" in joined
        and "当前 plan：" in joined
        and "textual-debug" in joined
        and "debug point" in joined
        and '"applied": true' in joined
        and "计划校验通过" in joined
        and "计划运行结果 passed" in joined
        and "management ok" in joined
        and "run.log" in joined
    )
    return {
        "name": "textual_client_restores_management_commands",
        "passed": passed,
        "detail": {
            "tool_messages": tool_messages,
            "error_messages": error_messages,
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


async def _wait_until_idle(app: AICTextualApp, pilot: Any, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if not app._busy and not app._queue:
            await pilot.pause(0.05)
            return
        await pilot.pause(0.05)
