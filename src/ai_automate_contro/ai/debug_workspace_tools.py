from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_automate_contro.debug.workspace import (
    apply_debug_patch,
    find_debug_workspace,
    generate_debug_patch,
)
from ai_automate_contro.ai.debug_workspace_io import (
    debug_relative_path,
    read_debug_manifest,
    read_debug_plan_tree,
    read_text_preserve_newlines,
    resolve_debug_write_path,
    write_text_preserve_newlines,
)
from ai_automate_contro.ai.json_patch import (
    apply_json_patch_operations,
    normalize_json_patch_operation,
)
from ai_automate_contro.ai.json_text_patch import serialize_json_patch_result
from ai_automate_contro.ai.plan_tools import (
    list_package_files,
    read_json_file_overview,
    read_package_docs,
    read_plan_file_overview,
    read_sub_plans,
    validate_plan_tool,
)


def generate_debug_patch_tool(workspace: str | Path) -> dict[str, Any]:
    result = generate_debug_patch(workspace)
    patch_size = result.patch_path.stat().st_size if result.patch_path.exists() else 0
    return {
        "ok": True,
        "result": result.to_dict(),
        "patch_path": str(result.patch_path),
        "patch_size": patch_size,
        "next_actions": [
            "先用 grep_project_text 搜索 patch.diff 中的目标变更。",
            "再用 read_project_file_slice 只读取必要的 patch 行段。",
        ],
    }


def apply_debug_patch_after_approval_tool(workspace: str | Path, *, approved: bool = False) -> dict[str, Any]:
    result = apply_debug_patch(workspace, yes=approved)
    return {
        "ok": True,
        "result": result.to_dict(),
    }


def find_debug_workspace_tool(plan_path: str | Path, *, name: str | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "workspace": find_debug_workspace(plan_path, name),
    }


def read_debug_workspace_tool(workspace: str | Path) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    source_copy_dir = Path(manifest["source_copy_dir"]).resolve()
    injected_plan_dir = Path(manifest["injected_plan_dir"]).resolve()
    return {
        "ok": True,
        "manifest": manifest,
        "source": read_debug_plan_tree(
            source_copy_dir,
            read_json_file_overview=read_json_file_overview,
            read_plan_file_overview=read_plan_file_overview,
            read_package_docs=read_package_docs,
            read_sub_plans=read_sub_plans,
            list_package_files=list_package_files,
        ),
        "injected": read_debug_plan_tree(
            injected_plan_dir,
            read_json_file_overview=read_json_file_overview,
            read_plan_file_overview=read_plan_file_overview,
            read_package_docs=read_package_docs,
            read_sub_plans=read_sub_plans,
            list_package_files=list_package_files,
        ),
        "text_files": {
            "notes": debug_text_metadata(Path(manifest["notes_path"]).resolve()),
            "report": debug_text_metadata(Path(manifest["report_path"]).resolve()),
            "patch": debug_text_metadata(Path(manifest["patch_path"]).resolve()),
        },
        "next_actions": [
            "先用 grep_project_text 在 workspace 中定位相关 notes、report 或 patch 行。",
            "再用 read_project_file_slice 读取需要的小范围行段。",
        ],
    }


def debug_text_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size": 0,
        }
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
    }


def write_debug_workspace_file_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    content: str | None = None,
    json_value: Any | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    target_path = resolve_debug_write_path(
        manifest,
        root=root,
        relative_path=relative_path,
    )
    if content is None and json_value is None:
        raise ValueError("write_debug_workspace_file 需要 content 或 json_value。")
    if content is not None and json_value is not None:
        raise ValueError("write_debug_workspace_file 的 content 和 json_value 只能提供一个。")
    if mode not in {"overwrite", "append"}:
        raise ValueError("mode 必须是 overwrite 或 append。")
    if mode == "append" and root == "injected-plan":
        raise ValueError("append 模式只允许用于 notes 和 report。")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if json_value is not None:
        serialized = json.dumps(json_value, ensure_ascii=False, indent=2) + "\n"
    else:
        serialized = content or ""
    if mode == "append":
        with target_path.open("a", encoding="utf-8") as file:
            file.write(serialized)
    else:
        target_path.write_text(serialized, encoding="utf-8")

    return {
        "ok": True,
        "path": str(target_path),
        "relative_path": debug_relative_path(manifest, target_path),
        "mode": mode,
        "size": target_path.stat().st_size,
    }


def patch_debug_workspace_json_tool(
    workspace: str | Path,
    *,
    root: str = "injected-plan",
    relative_path: str = "plan.json",
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace_root = Path(workspace).resolve()
    manifest = read_debug_manifest(workspace_root)
    target_path = resolve_debug_write_path(
        manifest,
        root=root,
        relative_path=relative_path,
    )
    if root.strip().lower() != "injected-plan":
        raise ValueError("patch_debug_workspace_json 只能修改 injected-plan/ 下的文件。")
    if target_path.suffix.lower() != ".json":
        raise ValueError("patch_debug_workspace_json 的目标文件必须是 .json。")
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"debug JSON 文件不存在：{target_path}")
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations 必须是非空数组。")

    original_text = read_text_preserve_newlines(target_path)
    try:
        document = json.loads(original_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"目标文件不是有效 JSON：{error.msg}") from error

    normalized_operations = [normalize_json_patch_operation(operation) for operation in operations]
    updated_document = apply_json_patch_operations(document, normalized_operations)
    updated_text, strategy = serialize_json_patch_result(
        original_text,
        updated_document,
        normalized_operations,
    )
    write_text_preserve_newlines(target_path, updated_text)

    return {
        "ok": True,
        "path": str(target_path),
        "relative_path": debug_relative_path(manifest, target_path),
        "operations": len(normalized_operations),
        "write_strategy": strategy,
        "size": target_path.stat().st_size,
    }


def validate_debug_plan_tool(project_root: str | Path, *, workspace: str | Path) -> dict[str, Any]:
    manifest = read_debug_manifest(Path(workspace).resolve())
    return validate_plan_tool(project_root, Path(manifest["injected_plan_dir"]) / "plan.json")


def run_debug_plan_tool(
    project_root: str | Path,
    *,
    workspace: str | Path,
    run_plan: Any,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
    _manual_confirmation_handler: Any | None = None,
    _inspection_confirmation_handler: Any | None = None,
) -> dict[str, Any]:
    manifest = read_debug_manifest(Path(workspace).resolve())
    injected_plan_path = Path(manifest["injected_plan_dir"]) / "plan.json"
    return run_plan(
        project_root,
        injected_plan_path,
        run_name=run_name,
        variable_overrides=variable_overrides,
        _manual_confirmation_handler=_manual_confirmation_handler,
        _inspection_confirmation_handler=_inspection_confirmation_handler,
    )
