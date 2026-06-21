from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.types import Interrupt

from ai_automate_contro.ai.session_compression import (
    MANUAL_COMPRESS_KEEP_MESSAGES,
    archive_messages,
    count_ai_terminal_tokens,
)
from ai_automate_contro.ai.session_store import CONTEXT_STATE_KEYS, update_ai_terminal_session_index
from ai_automate_contro.ai.terminal_context import context_update_from_tool_result
from ai_automate_contro.ai.terminal_context import work_plan_update_from_tool_result
from ai_automate_contro.ai.terminal_events import AITerminalEvent
from ai_automate_contro.ai.terminal_message_utils import (
    extract_interrupts,
    interrupt_action_requests,
    message_content_to_text,
)
from ai_automate_contro.ai.work_plan import format_work_plan_for_terminal


MAX_CLIENT_DIFF_CHARS = 12000


class AITerminalStateMixin:
    def _last_assistant_message(self, messages: list[BaseMessage]) -> str:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            if message.tool_calls:
                continue
            content = message_content_to_text(message.content).strip()
            if content:
                return content
        return ""

    def _latest_user_approved(self) -> bool:
        return self._approval_resume_active

    def _graph_config(self) -> dict[str, Any]:
        return {
            "recursion_limit": self.graph_recursion_limit,
            "configurable": {
                "thread_id": self.thread_id,
            },
        }

    def _current_messages(self) -> list[BaseMessage]:
        state = self.graph.get_state(self._graph_config())
        messages = state.values.get("messages", [])
        if isinstance(messages, list):
            return messages
        return []

    def _context_state(self) -> dict[str, Any]:
        values = self.graph.get_state(self._graph_config()).values
        result: dict[str, Any] = {}
        for key in (
            "current_plan_path",
            "current_debug_workspace",
            "latest_output_dir",
            "latest_compression_archive_dir",
            "latest_compression_messages_path",
            "latest_compression_summary_path",
            "latest_compression_token_count",
            "latest_compression_message_count",
            "latest_plan_quality_review_plan_path",
            "latest_plan_quality_review_signature",
            "latest_plan_quality_review_ok",
            "latest_plan_quality_review_severity",
            "latest_plan_quality_review_next_action",
            "latest_web_inspection_requested_url",
            "latest_web_inspection_resolved_url",
            "latest_web_inspection_final_url",
            "latest_web_inspection_title",
        ):
            value = values.get(key)
            if isinstance(value, str) and value:
                result[key] = value
        work_plan_items = values.get("work_plan_items")
        if isinstance(work_plan_items, list):
            result["work_plan_items"] = work_plan_items
        work_plan_summary = values.get("work_plan_summary")
        if isinstance(work_plan_summary, str) and work_plan_summary:
            result["work_plan_summary"] = work_plan_summary
        runtime_context = getattr(self, "_runtime_context_state", {})
        if isinstance(runtime_context, dict):
            result.update(
                {
                    str(key): str(value)
                    for key, value in runtime_context.items()
                    if key in CONTEXT_STATE_KEYS and value
                }
            )
        return result

    def _update_context_state(self, update: dict[str, Any]) -> None:
        runtime_update = {
            str(key): str(value)
            for key, value in update.items()
            if key in CONTEXT_STATE_KEYS and isinstance(value, str) and value
        }
        if runtime_update:
            runtime_context = getattr(self, "_runtime_context_state", None)
            if not isinstance(runtime_context, dict):
                runtime_context = {}
                self._runtime_context_state = runtime_context
            runtime_context.update(runtime_update)
        self.graph.update_state(self._graph_config(), update)

    def _before_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> None:
        if tool_name == "update_work_plan":
            return
        self._print_tool_progress("start", tool_name, arguments)

    def _after_tool_call(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        work_plan_update = work_plan_update_from_tool_result(tool_name, result)
        if work_plan_update:
            self._update_context_state(work_plan_update)
            self._sync_current_session_index()
            self._emit_work_plan_updated(work_plan_update["work_plan_items"], work_plan_update.get("work_plan_summary", ""))
            return
        self._print_tool_progress("done", tool_name, arguments, result)
        self._emit_tool_followup_events(tool_name, arguments, result)
        update = context_update_from_tool_result(tool_name, arguments, result)
        if update:
            self._update_context_state(update)
            self._sync_current_session_index()

    def _work_plan_state(self) -> dict[str, Any]:
        values = self.graph.get_state(self._graph_config()).values
        items = values.get("work_plan_items")
        summary = values.get("work_plan_summary")
        return {
            "items": items if isinstance(items, list) else [],
            "summary": summary if isinstance(summary, str) else "",
        }

    def _emit_work_plan_updated(self, items: list[dict[str, str]], summary: str = "") -> None:
        text = format_work_plan_for_terminal(items, summary=summary)
        self._emit_activity(
            "更新工作计划",
            category="plan",
            phase="done",
            source_kind="work_plan_updated",
        )
        self._emit_event(
            AITerminalEvent(
                "work_plan_updated",
                title="工作计划",
                text=text,
                data={"items": items, "summary": summary},
            )
        )

    def _emit_tool_followup_events(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        for event in _tool_followup_events(tool_name, arguments, result):
            activity = _activity_from_terminal_event(event)
            if activity is not None:
                self._emit_event(activity)
            self._emit_event(event)

    def _handle_plan_run_event(self, tool_name: str, event: dict[str, Any]) -> None:
        text = _format_plan_run_event(event)
        if not text:
            return
        self._emit_activity(
            text,
            category="run",
            phase=_activity_phase_from_text(text),
            source_kind="plan_progress",
            tool_name=tool_name,
        )
        self._emit_event(
            AITerminalEvent(
                "plan_progress",
                title=tool_name,
                text=text,
                data={"tool_name": tool_name, "event": _client_safe_data(event)},
            )
        )

    def _print_tool_progress(
        self,
        phase: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> None:
        if phase == "start":
            detail = _tool_argument_summary(tool_name, arguments)
            self._emit_activity(
                f"调用工具 {tool_name}",
                category="tool",
                phase="start",
                source_kind="tool_started",
                tool_name=tool_name,
            )
            self._emit_event(
                AITerminalEvent(
                    "tool_started",
                    title=tool_name,
                    text=detail,
                    data={"tool_name": tool_name, "arguments": _client_safe_data(arguments)},
                )
            )
            return
        ok = not isinstance(result, dict) or bool(result.get("ok", True))
        detail = _tool_result_summary(tool_name, result or {})
        self._emit_activity(
            f"{'工具完成' if ok else '工具失败'} {tool_name}",
            category="tool",
            phase="done" if ok else "failed",
            source_kind="tool_finished",
            tool_name=tool_name,
        )
        self._emit_event(
            AITerminalEvent(
                "tool_finished",
                title=tool_name,
                text=detail,
                data={
                    "tool_name": tool_name,
                    "arguments": _client_safe_data(arguments),
                    "result": _client_safe_data(result or {}),
                    "ok": ok,
                    "phase": "done" if ok else "failed",
                },
            )
        )

    def _sync_current_session_index(self) -> None:
        update_ai_terminal_session_index(
            self.project_root,
            self.checkpointer,
            self.thread_id,
            context_state=self._context_state(),
        )

    def _current_interrupts(self) -> tuple[Interrupt, ...]:
        return self.graph.get_state(self._graph_config()).interrupts

    def _print_pending_interrupt(self, final_state: Any) -> bool:
        interrupts = extract_interrupts(final_state) or self._current_interrupts()
        if not interrupts:
            return False
        self._print_interrupts(interrupts)
        return True

    def _print_interrupts(self, interrupts: tuple[Interrupt, ...] | list[Interrupt]) -> None:
        requests = interrupt_action_requests(interrupts)
        self._emit_activity("等待用户确认", category="run", phase="start", source_kind="approval_requested")
        if not requests:
            self._emit_event(
                AITerminalEvent(
                    "approval_requested",
                    text="AI 正在等待人工输入。\n输入 /approve 继续，或输入 /reject <原因> 停止本次工具调用。",
                    data={"approval_kind": "tool_approval"},
                )
            )
            return
        chunks = ["AI 请求执行受保护工具。"]
        for index, request in enumerate(requests, start=1):
            name = request.get("name", "<未知>")
            raw_args = request.get("args", {})
            args = _client_safe_data(raw_args) if isinstance(raw_args, dict) else {}
            description = request.get("description", "")
            chunks.append(f"{index}. 工具：{name}")
            if description:
                chunks.append(str(description))
            chunks.append(json.dumps(args, ensure_ascii=False, indent=2))
        chunks.append("输入 /approve 批准执行，或输入 /reject <原因> 拒绝并继续会话。")
        self._emit_event(
            AITerminalEvent(
                "approval_requested",
                text="\n".join(chunks),
                data={"approval_kind": "tool_approval"},
            )
        )

    def _checkpoint_count(self) -> int:
        return sum(1 for _ in self.checkpointer.list({"configurable": {"thread_id": self.thread_id}}))

    def _compress_current_thread(self, *, reason: str = "manual") -> dict[str, Any]:
        messages = self._current_messages()
        token_count = count_ai_terminal_tokens(messages)
        if not messages:
            return {
                "ok": True,
                "compressed": False,
                "reason": "no messages in current thread",
                "thread_id": self.thread_id,
            }
        result = self.summary_middleware.compress_messages(
            messages,
            reason=reason,
            keep_messages=MANUAL_COMPRESS_KEEP_MESSAGES,
        )
        if result is None:
            summary = "Manual archive created, but the thread is too small to replace with a compressed summary."
            archive = archive_messages(
                self.project_root,
                self.thread_id,
                messages,
                summary=summary,
                reason=reason,
            )
            self._update_context_state(archive.state_update())
            self._sync_current_session_index()
            self._emit_activity(
                "上下文已压缩归档",
                category="context",
                phase="done",
                source_kind="compress",
                archive_dir=str(archive.archive_dir),
                summary_path=str(archive.summary_path),
            )
            return {
                "ok": True,
                "compressed": False,
                "reason": "not enough messages to compress safely",
                "thread_id": self.thread_id,
                "message_count": len(messages),
                "token_count": token_count,
                "archive_dir": str(archive.archive_dir),
                "messages_path": str(archive.messages_path),
                "summary_path": str(archive.summary_path),
            }

        self.graph.update_state(self._graph_config(), result.state_update())
        self._sync_current_session_index()
        self._emit_activity(
            "上下文已压缩归档",
            category="context",
            phase="done",
            source_kind="compress",
            archive_dir=str(result.archive.archive_dir),
            summary_path=str(result.archive.summary_path),
        )
        return {
            "ok": True,
            "compressed": True,
            "thread_id": self.thread_id,
            "message_count": len(messages),
            "token_count": token_count,
            "summarized_messages": len(result.messages_to_summarize),
            "preserved_messages": len(result.preserved_messages),
            "archive_dir": str(result.archive.archive_dir),
            "messages_path": str(result.archive.messages_path),
            "summary_path": str(result.archive.summary_path),
        }

    def _close_checkpoint_connection(self) -> None:
        connection = getattr(self, "_checkpoint_connection", None)
        if connection is None:
            return
        connection.close()
        self._checkpoint_connection = None

    def _emit_activity(self, text: str, *, category: str, phase: str, **data: Any) -> None:
        payload = {"category": category, "phase": phase}
        payload.update({key: value for key, value in data.items() if value is not None and value != ""})
        self._emit_event(AITerminalEvent("activity", text=text, data=payload))


def _tool_argument_summary(tool_name: str, arguments: dict[str, Any]) -> str:
    if not arguments:
        return ""
    fields_by_tool = {
        "inspect_web_page": ("url", "headed"),
        "grep_project_text": ("pattern", "root_path", "file_glob"),
        "read_project_file_slice": ("path", "start_line", "line_count"),
        "read_plan_package": ("plan_path",),
        "create_plan_package": ("package_path", "name"),
        "export_local_file": ("target_path", "source_output_path", "mode"),
        "write_plan_package_file": ("plan_path", "relative_path", "mode"),
        "validate_plan": ("plan_path",),
        "review_plan_quality": ("plan_path", "planned_output_path"),
        "run_plan": ("plan_path", "run_name"),
        "read_latest_run_state": ("plan_path",),
        "read_latest_run_report": ("plan_path",),
        "analyze_latest_run_failure": ("plan_path", "output_dir"),
        "read_run_log": ("plan_path", "output_dir", "lines"),
        "read_run_events": ("plan_path", "output_dir", "lines"),
        "list_output_artifacts": ("plan_path", "filter_text", "limit"),
        "read_output_artifact": ("plan_path", "relative_path", "max_bytes"),
        "create_debug_workspace": ("plan_path", "name"),
        "list_debug_workspaces": ("plan_path",),
        "find_debug_workspace": ("plan_path", "name"),
        "read_debug_workspace": ("workspace",),
        "prepare_failure_debug_workspace": ("plan_path", "output_dir", "name"),
        "inject_debug_steps": ("workspace", "presets", "position", "step"),
        "write_debug_workspace_file": ("workspace", "root", "relative_path", "mode"),
        "patch_debug_workspace_json": ("workspace", "root", "relative_path"),
        "propose_debug_fix": ("workspace", "apply", "run_after_apply"),
        "validate_debug_plan": ("workspace",),
        "run_debug_plan": ("workspace", "run_name"),
        "generate_debug_patch": ("workspace",),
        "apply_debug_patch_after_approval": ("workspace",),
        "read_compression_archive": ("mode", "archive_path", "pattern"),
        "update_work_plan": ("summary",),
        "list_plan_packages": ("filter_text",),
    }
    fields = fields_by_tool.get(tool_name, tuple(arguments)[:3])
    parts = []
    for key in fields:
        if key not in arguments:
            continue
        value = arguments.get(key)
        if key.startswith("_") or callable(value):
            continue
        text = _compact_tool_value(value)
        if text:
            parts.append(f"{key}={text}")
    return "(" + ", ".join(parts) + ")" if parts else ""


def _tool_result_summary(tool_name: str, result: dict[str, Any]) -> str:
    if not result:
        return ""
    summary_parts: list[str] = []
    if tool_name == "inspect_web_page":
        page = result.get("page") if isinstance(result.get("page"), dict) else {}
        title = page.get("title") or ""
        final_url = page.get("final_url") or result.get("resolved_url") or ""
        auth = page.get("auth") if isinstance(page.get("auth"), dict) else {}
        signals = []
        if auth.get("login_fields_detected"):
            signals.append("登录字段")
        if auth.get("challenge_detected"):
            signals.append("验证信号")
        if title:
            summary_parts.append(f"title={_compact_tool_value(title)}")
        if final_url:
            summary_parts.append(f"url={_compact_tool_value(final_url)}")
        if signals:
            summary_parts.append("发现" + "/".join(signals))
    elif tool_name == "grep_project_text":
        if result.get("ok") is False:
            summary_parts.append(f"error={_compact_tool_value(result.get('error', '搜索失败'), limit=120)}")
            suggested_paths = result.get("suggested_paths")
            if isinstance(suggested_paths, list) and suggested_paths:
                summary_parts.append(f"suggest={_compact_tool_value(suggested_paths[0])}")
        else:
            summary_parts.append(f"matches={result.get('match_count', 0)}")
        if result.get("truncated"):
            summary_parts.append("已截断")
    elif tool_name == "read_project_file_slice":
        summary_parts.append(f"lines={result.get('line_count', 0)}")
        if result.get("relative_path"):
            summary_parts.append(f"path={_compact_tool_value(result.get('relative_path'))}")
    elif tool_name in {"run_plan", "run_debug_plan"}:
        status = result.get("status") or ("passed" if result.get("ok") else "failed")
        summary_parts.append(f"status={status}")
        if result.get("output_dir"):
            summary_parts.append(f"output={_compact_path(result.get('output_dir'))}")
        if result.get("error"):
            summary_parts.append(f"error={_compact_tool_value(result.get('error'), limit=120)}")
    elif tool_name in {"validate_plan", "validate_debug_plan"}:
        summary_parts.append("通过" if result.get("ok") else "未通过")
    elif tool_name == "review_plan_quality":
        summary_parts.append("通过" if result.get("ok") else "未通过")
        if result.get("severity"):
            summary_parts.append(f"severity={result.get('severity')}")
        if result.get("issue_count") is not None:
            summary_parts.append(f"issues={result.get('issue_count', 0)}")
        if result.get("next_action"):
            summary_parts.append(f"next={_compact_tool_value(result.get('next_action'))}")
    elif tool_name == "list_plan_packages":
        plans = result.get("plans") if isinstance(result.get("plans"), list) else []
        summary_parts.append(f"plans={len(plans)}")
    elif tool_name == "list_output_artifacts":
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        summary_parts.append(f"artifacts={len(artifacts)}")
    elif tool_name == "read_output_artifact":
        if result.get("relative_path"):
            summary_parts.append(f"path={_compact_tool_value(result.get('relative_path'))}")
        if result.get("content") is not None:
            line_count = result.get("non_empty_line_count", result.get("line_count", 0))
            prefix = "lines" if result.get("content_complete", True) else "lines>="
            summary_parts.append(f"{prefix}{line_count}")
        if result.get("truncated"):
            summary_parts.append("已截断")
    elif tool_name == "update_work_plan":
        summary_parts.append(f"items={result.get('total', 0)}")
        if result.get("active"):
            summary_parts.append(f"active={_compact_tool_value(result.get('active'))}")
    elif tool_name == "export_local_file":
        if result.get("path") or result.get("target_path"):
            summary_parts.append(f"path={_compact_path(result.get('path') or result.get('target_path'))}")
        if result.get("source_path"):
            summary_parts.append(f"source={_compact_path(result.get('source_path'))}")
    elif tool_name in {"create_plan_package", "write_plan_package_file", "read_plan_package"}:
        if result.get("plan_path"):
            summary_parts.append(f"plan={_compact_path(result.get('plan_path'))}")
        elif isinstance(result.get("summary"), dict) and result["summary"].get("path"):
            summary_parts.append(f"plan={_compact_path(result['summary'].get('path'))}")
    elif "workspace" in result:
        summary_parts.append(f"workspace={_compact_path(result.get('workspace'))}")
    elif "path" in result:
        summary_parts.append(f"path={_compact_path(result.get('path'))}")
    elif "relative_path" in result:
        summary_parts.append(f"path={_compact_tool_value(result.get('relative_path'))}")
    elif result.get("error"):
        summary_parts.append(f"error={_compact_tool_value(result.get('error'), limit=120)}")
    if not summary_parts and "ok" in result:
        summary_parts.append("ok=true" if result.get("ok") else "ok=false")
    return " ".join(summary_parts) if summary_parts else ""


def _tool_followup_events(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[AITerminalEvent]:
    if not isinstance(result, dict) or result.get("ok") is False:
        return []
    safe_arguments = _client_safe_data(arguments)
    safe_result = _client_safe_data(result)
    events: list[AITerminalEvent] = []
    file_events = _file_change_events_from_tool_result(tool_name, safe_arguments, safe_result)
    events.extend(file_events)
    diff_event = _diff_event_from_tool_result(tool_name, safe_arguments, safe_result)
    if diff_event is not None:
        events.append(diff_event)
    artifact_event = _artifact_event_from_tool_result(tool_name, safe_arguments, safe_result)
    if artifact_event is not None:
        events.append(artifact_event)
    return events


def _activity_from_terminal_event(event: AITerminalEvent) -> AITerminalEvent | None:
    if event.kind == "file_changed":
        return AITerminalEvent(
            "activity",
            text=event.text or "文件变更",
            data={
                "category": "file",
                "phase": "done",
                "source_kind": event.kind,
                "tool_name": event.data.get("tool_name") or event.title,
            },
        )
    if event.kind == "diff":
        return AITerminalEvent(
            "activity",
            text="生成 diff",
            data={
                "category": "file",
                "phase": "done",
                "source_kind": event.kind,
                "tool_name": event.data.get("tool_name") or event.title,
            },
        )
    if event.kind == "artifact":
        return AITerminalEvent(
            "activity",
            text=event.text or "产物更新",
            data={
                "category": "run",
                "phase": "done",
                "source_kind": event.kind,
                "tool_name": event.data.get("tool_name") or event.title,
            },
        )
    return None


def _activity_phase_from_text(text: str) -> str:
    lowered = str(text or "").lower()
    if "失败" in lowered or "error" in lowered:
        return "failed"
    if "完成" in lowered or "结束" in lowered or "finished" in lowered:
        return "done"
    return "start"


def _file_change_events_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[AITerminalEvent]:
    events: list[AITerminalEvent] = []
    if tool_name == "create_plan_package":
        plan_path = result.get("plan_path")
        if plan_path:
            events.append(
                _file_change_event(
                    tool_name,
                    action="created",
                    path=plan_path,
                    relative_path=_path_name(plan_path),
                    detail="plan package",
                    result=result,
                )
            )
    elif tool_name == "write_plan_package_file":
        mode = str(result.get("mode") or arguments.get("mode") or "overwrite")
        events.append(
            _file_change_event(
                tool_name,
                action="appended" if mode == "append" else "updated",
                path=result.get("path"),
                relative_path=result.get("relative_path"),
                bytes_count=result.get("bytes"),
                detail=f"mode={mode}",
                result=result,
            )
        )
    elif tool_name == "export_local_file":
        mode = str(result.get("mode") or arguments.get("mode") or "overwrite")
        events.append(
            _file_change_event(
                tool_name,
                action="appended" if mode == "append" else "updated",
                path=result.get("path") or result.get("target_path"),
                relative_path=result.get("target_path") or result.get("path"),
                bytes_count=result.get("bytes"),
                detail=f"mode={mode}",
                result=result,
            )
        )
    elif tool_name in {"write_debug_workspace_file", "patch_debug_workspace_json"}:
        mode = str(result.get("mode") or "patch")
        detail_parts = []
        if tool_name == "patch_debug_workspace_json":
            detail_parts.append(f"operations={result.get('operations', 0)}")
            if result.get("write_strategy"):
                detail_parts.append(f"strategy={result.get('write_strategy')}")
        elif mode:
            detail_parts.append(f"mode={mode}")
        events.append(
            _file_change_event(
                tool_name,
                action="patched" if tool_name == "patch_debug_workspace_json" else ("appended" if mode == "append" else "updated"),
                path=result.get("path"),
                relative_path=result.get("relative_path"),
                bytes_count=result.get("size"),
                detail=" ".join(detail_parts),
                result=result,
            )
        )
    elif tool_name == "inject_debug_steps":
        nested = result.get("result") if isinstance(result.get("result"), dict) else {}
        if nested.get("plan_path"):
            events.append(
                _file_change_event(
                    tool_name,
                    action="updated",
                    path=nested.get("plan_path"),
                    relative_path=_path_name(nested.get("plan_path")),
                    detail=f"injected_steps={len(nested.get('injected_steps') or [])}",
                    result=result,
                )
            )
    elif tool_name == "prepare_failure_debug_workspace":
        injection = result.get("injection") if isinstance(result.get("injection"), dict) else {}
        if injection.get("plan_path"):
            events.append(
                _file_change_event(
                    tool_name,
                    action="updated",
                    path=injection.get("plan_path"),
                    relative_path=_path_name(injection.get("plan_path")),
                    detail=f"injected_steps={len(injection.get('injected_steps') or [])}",
                    result=result,
                )
            )
    elif tool_name == "propose_debug_fix" and result.get("applied"):
        patch_result = result.get("patch_result") if isinstance(result.get("patch_result"), dict) else {}
        if patch_result.get("path"):
            events.append(
                _file_change_event(
                    tool_name,
                    action="patched",
                    path=patch_result.get("path"),
                    relative_path=patch_result.get("relative_path"),
                    bytes_count=patch_result.get("size"),
                    detail=f"operations={patch_result.get('operations', 0)}",
                    result=result,
                )
            )
    elif tool_name == "apply_debug_patch_after_approval":
        patch_result = _debug_patch_result_payload(result)
        changed_files = patch_result.get("changed_files") if isinstance(patch_result.get("changed_files"), list) else []
        for relative_path in changed_files:
            events.append(
                _file_change_event(
                    tool_name,
                    action="applied",
                    path=relative_path,
                    relative_path=str(relative_path),
                    detail="debug patch",
                    result=result,
                )
            )
    return [event for event in events if event.data.get("path") or event.data.get("relative_path")]


def _file_change_event(
    tool_name: str,
    *,
    action: str,
    path: Any,
    relative_path: Any = "",
    bytes_count: Any = None,
    detail: str = "",
    result: dict[str, Any] | None = None,
) -> AITerminalEvent:
    data = {
        "tool_name": tool_name,
        "action": action,
        "path": str(path or ""),
        "relative_path": str(relative_path or ""),
        "bytes": bytes_count,
        "detail": detail,
    }
    if result is not None:
        data["result"] = result
    text = _format_file_change_event_text(data)
    return AITerminalEvent("file_changed", title=tool_name, text=text, data=data)


def _diff_event_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> AITerminalEvent | None:
    if tool_name not in {"generate_debug_patch", "propose_debug_fix"}:
        return None
    patch_payload = result.get("patch") if tool_name == "propose_debug_fix" and isinstance(result.get("patch"), dict) else result
    patch_result = _debug_patch_result_payload(patch_payload)
    patch_path = patch_payload.get("patch_path") or patch_result.get("patch_path")
    if not patch_path:
        return None
    diff_text, truncated = _read_patch_excerpt(patch_path)
    changed_files = patch_result.get("changed_files") if isinstance(patch_result.get("changed_files"), list) else []
    data = {
        "tool_name": tool_name,
        "patch_path": str(patch_path),
        "changed_files": changed_files,
        "truncated": truncated,
        "applied": bool(patch_result.get("applied")),
    }
    summary = _format_diff_event_header(data)
    text = f"{summary}\n{diff_text}" if diff_text else summary
    return AITerminalEvent("diff", title=tool_name, text=text, data=data)


def _artifact_event_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> AITerminalEvent | None:
    if tool_name in {"run_plan", "run_debug_plan"} and result.get("output_dir"):
        data = {
            "tool_name": tool_name,
            "artifact_type": "output_dir",
            "path": str(result.get("output_dir")),
            "status": result.get("status") or ("passed" if result.get("ok") else "failed"),
        }
        return AITerminalEvent("artifact", title=tool_name, text=_format_artifact_event_text(data), data=data)
    if tool_name == "generate_debug_patch":
        patch_result = _debug_patch_result_payload(result)
        patch_path = result.get("patch_path") or patch_result.get("patch_path")
        if patch_path:
            data = {
                "tool_name": tool_name,
                "artifact_type": "patch",
                "path": str(patch_path),
                "bytes": result.get("patch_size"),
                "changed_files": patch_result.get("changed_files") or [],
            }
            return AITerminalEvent("artifact", title=tool_name, text=_format_artifact_event_text(data), data=data)
    return None


def _debug_patch_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    nested = result.get("result")
    if isinstance(nested, dict):
        return nested
    return result


def _read_patch_excerpt(path: Any) -> tuple[str, bool]:
    try:
        patch_path = Path(str(path)).expanduser()
        text = patch_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", False
    if len(text) <= MAX_CLIENT_DIFF_CHARS:
        return text.rstrip(), False
    return text[:MAX_CLIENT_DIFF_CHARS].rstrip() + "\n... diff truncated ...", True


def _format_file_change_event_text(data: dict[str, Any]) -> str:
    label = {
        "created": "创建",
        "updated": "写入",
        "appended": "追加",
        "patched": "修改",
        "applied": "应用",
    }.get(str(data.get("action") or ""), "变更")
    path = data.get("relative_path") or data.get("path") or "<unknown>"
    parts = [f"文件 {label}", _compact_path(path)]
    if data.get("bytes") not in {None, ""}:
        parts.append(f"{data.get('bytes')} bytes")
    if data.get("detail"):
        parts.append(str(data.get("detail")))
    return " · ".join(str(part) for part in parts if str(part or "").strip())


def _format_diff_event_header(data: dict[str, Any]) -> str:
    changed_files = data.get("changed_files") if isinstance(data.get("changed_files"), list) else []
    patch_path = _compact_path(data.get("patch_path"))
    parts = ["diff"]
    if patch_path:
        parts.append(patch_path)
    if changed_files:
        parts.append("files=" + ", ".join(str(item) for item in changed_files[:6]))
        if len(changed_files) > 6:
            parts.append("...")
    if data.get("truncated"):
        parts.append("truncated")
    return " · ".join(parts)


def _format_artifact_event_text(data: dict[str, Any]) -> str:
    label = {
        "output_dir": "输出目录",
        "patch": "补丁文件",
    }.get(str(data.get("artifact_type") or ""), "产物")
    parts = [label, _compact_path(data.get("path"))]
    if data.get("status"):
        parts.append(f"status={data.get('status')}")
    if data.get("bytes") not in {None, ""}:
        parts.append(f"{data.get('bytes')} bytes")
    changed_files = data.get("changed_files") if isinstance(data.get("changed_files"), list) else []
    if changed_files:
        parts.append(f"files={len(changed_files)}")
    return " · ".join(str(part) for part in parts if str(part or "").strip())


def _path_name(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        return Path(text).name
    except Exception:
        return text


def _compact_tool_value(value: Any, *, limit: int = 80) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        text = "[" + ", ".join(_compact_tool_value(item, limit=24) for item in list(value)[:4]) + "]"
        if len(value) > 4:
            text += "..."
    elif isinstance(value, dict):
        text = "{...}"
    else:
        text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _compact_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        parts = path.parts
        if len(parts) >= 3:
            return str(Path(*parts[-3:]))
    except Exception:
        pass
    return _compact_tool_value(text)


def _client_safe_data(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_") or callable(item):
                continue
            safe_item = _client_safe_data(item)
            if safe_item is not None:
                result[str(key)] = safe_item
        return result
    if isinstance(value, (list, tuple)):
        return [
            safe_item
            for item in value
            if (safe_item := _client_safe_data(item)) is not None
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _format_plan_run_event(event: dict[str, Any]) -> str:
    message = str(event.get("message") or "").strip()
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    level = str(event.get("level") or "").strip().upper()
    if not message:
        return ""
    if message == "plan started":
        run_name = _compact_tool_value(fields.get("run_name"), limit=72)
        plan_path = _compact_path(fields.get("plan_path"))
        parts = ["plan 开始"]
        if run_name:
            parts.append(run_name)
        if plan_path:
            parts.append(f"plan={plan_path}")
        return " · ".join(parts)
    if message == "plan finished":
        run_name = _compact_tool_value(fields.get("run_name"), limit=72)
        return f"plan 结束 · {run_name}" if run_name else "plan 结束"
    if message.startswith("step "):
        return _format_step_run_event(message, fields, level)
    if message == "browser opened":
        browser = _compact_tool_value(fields.get("browser"), limit=48)
        headed = fields.get("headed")
        suffix = " · headed" if headed is True else ""
        return f"浏览器已打开 · {browser}{suffix}" if browser else f"浏览器已打开{suffix}"
    if message == "browser closed":
        browser = _compact_tool_value(fields.get("browser"), limit=48)
        return f"浏览器已关闭 · {browser}" if browser else "浏览器已关闭"
    if message in {"new page opened", "page switched", "page closed"}:
        page = _compact_tool_value(fields.get("page"), limit=48)
        browser = _compact_tool_value(fields.get("browser"), limit=48)
        labels = {
            "new page opened": "页面已打开",
            "page switched": "页面已切换",
            "page closed": "页面已关闭",
        }
        return _join_progress_parts(labels[message], browser, page)
    if message == "dialog captured":
        dialog_type = _compact_tool_value(fields.get("dialog_type"), limit=32)
        dialog_message = _compact_tool_value(fields.get("dialog_message"), limit=96)
        return _join_progress_parts("页面弹窗", dialog_type, dialog_message)
    if message == "waiting for manual confirmation":
        prompt = _compact_tool_value(fields.get("prompt"), limit=120)
        return _join_progress_parts("等待人工确认", prompt, "请在当前 Playwright 浏览器完成操作后回来继续")
    if message == "manual confirmation accepted":
        return "人工确认已继续"
    if message == "waiting for post-run inspection confirmation":
        prompt = _compact_tool_value(fields.get("prompt"), limit=120)
        return _join_progress_parts("等待运行后检查", prompt)
    if level in {"ERROR", "WARNING"}:
        detail = _compact_tool_value(fields.get("error"), limit=120)
        label = "运行错误" if level == "ERROR" else "运行警告"
        return _join_progress_parts(label, message, detail)
    return ""


def _format_step_run_event(message: str, fields: dict[str, Any], level: str) -> str:
    step = _compact_tool_value(fields.get("step"), limit=16)
    action = _compact_tool_value(fields.get("action"), limit=36)
    step_name = _compact_tool_value(fields.get("step_name"), limit=64)
    summary = _compact_tool_value(fields.get("step_summary"), limit=120)
    error = _compact_tool_value(fields.get("error"), limit=120)
    if message.endswith(" start"):
        return _join_progress_parts(f"步骤 {step} 开始", action, step_name, summary)
    if message.endswith(" finished"):
        return _join_progress_parts(f"步骤 {step} 完成", action, step_name, summary)
    if message.endswith(" failed") or level == "ERROR":
        return _join_progress_parts(f"步骤 {step} 失败", action, step_name, summary, error)
    return ""


def _join_progress_parts(*parts: Any) -> str:
    values = [str(part).strip() for part in parts if str(part or "").strip()]
    return " · ".join(values)
