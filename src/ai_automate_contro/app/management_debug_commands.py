from __future__ import annotations

import json
from pathlib import Path

from ai_automate_contro.ai.terminal_tool_registry import call_ai_terminal_tool
from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    create_debug_workspace,
    find_debug_workspace,
    generate_debug_patch,
    inject_debug_steps,
    list_debug_workspaces,
)


class DebugCommandsMixin:
    def do_debug(self, arg: str) -> None:
        """管理调试工作区：debug prepare [name] | debug create [name] | debug list | debug fix [--apply] [workspace] | debug inject <preset[,preset...]> [workspace] | debug patch [workspace] | debug apply --yes [workspace]"""
        usage = (
            "用法：debug prepare [name] | debug create [name] | debug list | debug fix [--apply] [workspace] | "
            "debug inject <preset[,preset...]> [workspace] | debug patch [workspace] | debug apply --yes [workspace]"
        )
        parts = arg.split(maxsplit=2)
        if not parts:
            self.perror(usage)
            return
        command = parts[0]
        name = parts[1].strip() if len(parts) > 1 else None
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(error)
            return
        if command == "prepare":
            self._debug_prepare(plan_path, name)
            return
        if command == "fix":
            self._debug_fix(plan_path, name, parts)
            return
        if command == "create":
            self._debug_create(plan_path, name)
            return
        if command == "list":
            self._debug_list(plan_path)
            return
        if command == "inject":
            self._debug_inject(plan_path, name, parts)
            return
        if command == "patch":
            self._debug_patch(plan_path, name)
            return
        if command == "apply":
            self._debug_apply(plan_path, name, parts)
            return
        self.perror(usage)

    def _debug_prepare(self, plan_path: Path, name: str | None) -> None:
        try:
            result = call_ai_terminal_tool(
                "prepare_failure_debug_workspace",
                self.project_root,
                {
                    "plan_path": str(plan_path),
                    "name": name,
                },
            )
        except Exception as error:
            self.perror(error)
            return
        summary = {
            "ok": result.get("ok"),
            "workspace": result.get("workspace"),
            "injection": result.get("injection"),
            "validation": result.get("validation"),
            "recommended_next_actions": result.get("recommended_next_actions"),
        }
        self.poutput(json.dumps(summary, ensure_ascii=False, indent=2))

    def _debug_fix(self, plan_path: Path, name: str | None, parts: list[str]) -> None:
        apply_candidate = name == "--apply"
        workspace_name = parts[2].strip() if apply_candidate and len(parts) > 2 else name
        try:
            workspace = find_debug_workspace(plan_path, workspace_name)
            result = call_ai_terminal_tool(
                "propose_debug_fix",
                self.project_root,
                {
                    "workspace": workspace["root"],
                    "apply": apply_candidate,
                },
            )
        except Exception as error:
            self.perror(error)
            return
        self.poutput(json.dumps(result, ensure_ascii=False, indent=2))

    def _debug_create(self, plan_path: Path, name: str | None) -> None:
        try:
            workspace = create_debug_workspace(plan_path, self.project_root, name=name)
        except Exception as error:
            self.perror(error)
            return
        self.poutput(json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2))

    def _debug_list(self, plan_path: Path) -> None:
        workspaces = list_debug_workspaces(plan_path)
        if not workspaces:
            self.poutput("调试工作区：<无>")
            return
        for workspace in workspaces:
            self.poutput(f"{workspace.get('name')} | {workspace.get('root')}")

    def _debug_inject(self, plan_path: Path, name: str | None, parts: list[str]) -> None:
        if not name:
            self.perror("用法：debug inject <preset[,preset...]> [workspace]")
            return
        workspace_name = parts[2].strip() if len(parts) > 2 else None
        try:
            workspace = find_debug_workspace(plan_path, workspace_name)
            result = inject_debug_steps(
                workspace["root"],
                presets=[preset.strip() for preset in name.split(",") if preset.strip()],
            )
        except Exception as error:
            self.perror(error)
            return
        self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    def _debug_patch(self, plan_path: Path, workspace_name: str | None) -> None:
        try:
            workspace = find_debug_workspace(plan_path, workspace_name)
            result = generate_debug_patch(workspace["root"])
        except Exception as error:
            self.perror(error)
            return
        self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        patch_text = Path(result.patch_path).read_text(encoding="utf-8")
        if patch_text:
            self.poutput(patch_text)

    def _debug_apply(self, plan_path: Path, name: str | None, parts: list[str]) -> None:
        if name != "--yes":
            self.perror("用法：debug apply --yes [workspace]")
            return
        workspace_name = parts[2].strip() if len(parts) > 2 else None
        try:
            workspace = find_debug_workspace(plan_path, workspace_name)
            result = apply_debug_patch(workspace["root"], yes=True)
        except Exception as error:
            self.perror(error)
            return
        self.poutput(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
