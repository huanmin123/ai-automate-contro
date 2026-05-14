from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from ai_automate_contro.ai import terminal_tools
from ai_automate_contro.ai.compression_recall import read_compression_archive_tool
from ai_automate_contro.ai.file_search import grep_project_text_tool, read_project_file_slice_tool
from ai_automate_contro.ai.plan_tools import (
    create_plan_package_tool,
    list_plan_packages_tool,
    read_plan_package_tool,
    validate_plan_tool,
    write_plan_package_file_tool,
)
from ai_automate_contro.ai.tool_schemas import (
    AnalyzeLatestRunFailureArgs,
    ApplyDebugPatchAfterApprovalArgs,
    CreateDebugWorkspaceArgs,
    CreatePlanPackageArgs,
    FindDebugWorkspaceArgs,
    GenerateDebugPatchArgs,
    GrepProjectTextArgs,
    InjectDebugStepsArgs,
    InspectWebPageArgs,
    ListDebugWorkspacesArgs,
    ListOutputArtifactsArgs,
    ListPlanPackagesArgs,
    PatchDebugWorkspaceJsonArgs,
    PrepareFailureDebugWorkspaceArgs,
    ProposeDebugFixArgs,
    ReadCompressionArchiveArgs,
    ReadDebugWorkspaceArgs,
    ReadLatestRunReportArgs,
    ReadLatestRunStateArgs,
    ReadOutputArtifactArgs,
    ReadPlanPackageArgs,
    ReadProjectFileSliceArgs,
    ReadRunEventsArgs,
    ReadRunLogArgs,
    RunDebugPlanArgs,
    RunPlanArgs,
    ValidateDebugPlanArgs,
    ValidatePlanArgs,
    WriteDebugWorkspaceFileArgs,
    WritePlanPackageFileArgs,
)


@dataclass(frozen=True)
class ToolSpec:
    handler: Callable[..., dict[str, Any]]
    args_schema: type[BaseModel]
    description: str
    requires_project_root: bool = False
    protected: bool = False


AI_TERMINAL_TOOL_SPECS: dict[str, ToolSpec] = {
    "analyze_latest_run_failure": ToolSpec(
        terminal_tools.analyze_latest_run_failure_tool,
        AnalyzeLatestRunFailureArgs,
        "分析最近一次失败运行的证据，包括日志、事件、截图、HTML、页面状态和 DOM 摘要。",
    ),
    "apply_debug_patch_after_approval": ToolSpec(
        terminal_tools.apply_debug_patch_after_approval_tool,
        ApplyDebugPatchAfterApprovalArgs,
        "在用户明确批准后，把 patch.diff 应用回原始 plan 包。",
        protected=True,
    ),
    "create_debug_workspace": ToolSpec(
        terminal_tools.create_debug_workspace_tool,
        CreateDebugWorkspaceArgs,
        "为 plan 包创建隔离的 output/debug 调试工作区。",
        requires_project_root=True,
    ),
    "create_plan_package": ToolSpec(
        create_plan_package_tool,
        CreatePlanPackageArgs,
        "创建新的 plan 包模板。",
        requires_project_root=True,
    ),
    "write_plan_package_file": ToolSpec(
        write_plan_package_file_tool,
        WritePlanPackageFileArgs,
        "创建 plan 时写入受控文件：plan.json、config.json、docs/**、resources/** 或 sub-plans/*-plan.json。",
        requires_project_root=True,
    ),
    "find_debug_workspace": ToolSpec(
        terminal_tools.find_debug_workspace_tool,
        FindDebugWorkspaceArgs,
        "按名称、后缀或最近一次查找调试工作区。",
    ),
    "generate_debug_patch": ToolSpec(
        terminal_tools.generate_debug_patch_tool,
        GenerateDebugPatchArgs,
        "比较 source-copy/ 和 injected-plan/ 生成 patch.diff；返回补丁元数据，不返回完整正文。",
    ),
    "grep_project_text": ToolSpec(
        grep_project_text_tool,
        GrepProjectTextArgs,
        "用 ripgrep 渐进式搜索项目文本，再按需读取文件片段。",
        requires_project_root=True,
    ),
    "inject_debug_steps": ToolSpec(
        terminal_tools.inject_debug_steps_tool,
        InjectDebugStepsArgs,
        "向 injected-plan/ 注入诊断步骤。",
    ),
    "inspect_web_page": ToolSpec(
        terminal_tools.inspect_web_page_tool,
        InspectWebPageArgs,
        "用一次性 Playwright 页面打开 URL 或本地 HTML，返回受限 DOM、表单、按钮、链接、表格、登录和验证证据；真实流程或需要用户操作时改用 open_browser.headed=true 探索 plan。",
        requires_project_root=True,
    ),
    "list_debug_workspaces": ToolSpec(
        terminal_tools.list_debug_workspaces_tool,
        ListDebugWorkspacesArgs,
        "列出某个 plan 包的调试工作区。",
    ),
    "list_output_artifacts": ToolSpec(
        terminal_tools.list_output_artifacts_tool,
        ListOutputArtifactsArgs,
        "列出当前 plan 包 output/ 目录下的文件。",
    ),
    "list_plan_packages": ToolSpec(
        list_plan_packages_tool,
        ListPlanPackagesArgs,
        "按当前运行根的 plan_roots 列出可用 plan 包。",
        requires_project_root=True,
    ),
    "patch_debug_workspace_json": ToolSpec(
        terminal_tools.patch_debug_workspace_json_tool,
        PatchDebugWorkspaceJsonArgs,
        "对 injected-plan/ 下的 JSON 文件执行最小 JSON 路径修改。",
    ),
    "prepare_failure_debug_workspace": ToolSpec(
        terminal_tools.prepare_failure_debug_workspace_tool,
        PrepareFailureDebugWorkspaceArgs,
        "基于失败运行证据创建调试工作区，并在失败步骤前注入诊断。",
        requires_project_root=True,
    ),
    "propose_debug_fix": ToolSpec(
        terminal_tools.propose_debug_fix_tool,
        ProposeDebugFixArgs,
        "在调试工作区内生成保守的干净修复候选。",
        requires_project_root=True,
    ),
    "read_debug_workspace": ToolSpec(
        terminal_tools.read_debug_workspace_tool,
        ReadDebugWorkspaceArgs,
        "读取调试工作区结构和文本文件元数据，不加载完整 notes、report 或 patch 正文。",
    ),
    "read_latest_run_report": ToolSpec(
        terminal_tools.read_latest_run_report_tool,
        ReadLatestRunReportArgs,
        "读取最近运行输出中的 report.md。",
    ),
    "read_latest_run_state": ToolSpec(
        terminal_tools.read_latest_run_state_tool,
        ReadLatestRunStateArgs,
        "读取最近运行输出中的 state.json。",
    ),
    "read_output_artifact": ToolSpec(
        terminal_tools.read_output_artifact_tool,
        ReadOutputArtifactArgs,
        "在 grep 或列表定位后，读取 output/ 下某个产物的受限片段。",
    ),
    "read_plan_package": ToolSpec(
        read_plan_package_tool,
        ReadPlanPackageArgs,
        "读取 plan 包结构和元数据，不加载完整文档或资源正文。",
        requires_project_root=True,
    ),
    "read_project_file_slice": ToolSpec(
        read_project_file_slice_tool,
        ReadProjectFileSliceArgs,
        "在 grep 或列表定位后，读取某个项目文件的受限行片段。",
        requires_project_root=True,
    ),
    "read_compression_archive": ToolSpec(
        read_compression_archive_tool,
        ReadCompressionArchiveArgs,
        "受限读取当前 AI 终端线程的压缩归档：列出归档、读取摘要、搜索或读取 messages.jsonl 小片段。",
        requires_project_root=True,
    ),
    "read_run_events": ToolSpec(
        terminal_tools.read_run_events_tool,
        ReadRunEventsArgs,
        "读取运行输出中的 events.jsonl。",
    ),
    "read_run_log": ToolSpec(
        terminal_tools.read_run_log_tool,
        ReadRunLogArgs,
        "读取运行输出中的 run.log。",
    ),
    "run_debug_plan": ToolSpec(
        terminal_tools.run_debug_plan_tool,
        RunDebugPlanArgs,
        "运行调试工作区内的 injected-plan/plan.json。",
        requires_project_root=True,
    ),
    "run_plan": ToolSpec(
        terminal_tools.run_plan_tool,
        RunPlanArgs,
        "运行 plan 包。",
        requires_project_root=True,
    ),
    "validate_debug_plan": ToolSpec(
        terminal_tools.validate_debug_plan_tool,
        ValidateDebugPlanArgs,
        "校验调试工作区内的 injected-plan/plan.json。",
        requires_project_root=True,
    ),
    "validate_plan": ToolSpec(
        validate_plan_tool,
        ValidatePlanArgs,
        "只校验 plan 包，不运行。",
        requires_project_root=True,
    ),
    "write_debug_workspace_file": ToolSpec(
        terminal_tools.write_debug_workspace_file_tool,
        WriteDebugWorkspaceFileArgs,
        "只写入 injected-plan/、notes.md 或 report.md 中允许的文件。",
    ),
}

AI_TERMINAL_TOOLS = {
    name: spec.handler
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
TOOL_ARGS_SCHEMAS = {
    name: spec.args_schema
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
TOOL_DESCRIPTIONS = {
    name: spec.description
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
}
PROJECT_ROOT_TOOLS = {
    name
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
    if spec.requires_project_root
}
PROTECTED_AI_TERMINAL_TOOLS = {
    name
    for name, spec in AI_TERMINAL_TOOL_SPECS.items()
    if spec.protected
}


def call_ai_terminal_tool(
    tool_name: str,
    project_root: str | Path,
    arguments: dict[str, Any] | None = None,
    *,
    allow_protected: bool = False,
) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOL_SPECS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOL_SPECS))
        raise ValueError(f"不支持的 AI 终端工具：{tool_name}。支持的工具：{supported}")
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    if spec.protected and not allow_protected:
        raise ValueError(
            f"工具 {tool_name} 是受保护工具，只能通过 AI 终端人工审批流程执行。"
        )
    raw_arguments = dict(arguments or {})
    injected_arguments: dict[str, Any] = {}
    if tool_name in {"run_plan", "run_debug_plan"}:
        for key in ("_manual_confirmation_handler", "_inspection_confirmation_handler"):
            if key in raw_arguments:
                injected_arguments[key] = raw_arguments.pop(key)
    tool_arguments = _validate_ai_terminal_tool_arguments(tool_name, raw_arguments)
    tool_arguments.update(injected_arguments)
    if spec.requires_project_root:
        return spec.handler(project_root, **tool_arguments)
    return spec.handler(**tool_arguments)


def list_ai_terminal_tools() -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    return {
        "ok": True,
        "tools": [
            {
                "name": name,
                "description": spec.description,
                "requires_project_root": spec.requires_project_root,
                "protected": spec.protected,
                "args": list(spec.args_schema.model_fields),
            }
            for name, spec in sorted(AI_TERMINAL_TOOL_SPECS.items())
        ],
    }


def describe_ai_terminal_tool(tool_name: str) -> dict[str, Any]:
    _ensure_ai_terminal_tool_registry_consistent()
    if tool_name not in AI_TERMINAL_TOOL_SPECS:
        supported = ", ".join(sorted(AI_TERMINAL_TOOL_SPECS))
        raise ValueError(f"不支持的 AI 终端工具：{tool_name}。支持的工具：{supported}")
    spec = AI_TERMINAL_TOOL_SPECS[tool_name]
    return {
        "ok": True,
        "name": tool_name,
        "description": spec.description,
        "requires_project_root": spec.requires_project_root,
        "protected": spec.protected,
        "args_schema": spec.args_schema.model_json_schema(),
    }


def check_ai_terminal_tool_registry() -> dict[str, Any]:
    tool_names = set(AI_TERMINAL_TOOL_SPECS)
    schema_names = set(TOOL_ARGS_SCHEMAS)
    description_names = set(TOOL_DESCRIPTIONS)
    project_root_names = set(PROJECT_ROOT_TOOLS)
    protected_names = set(PROTECTED_AI_TERMINAL_TOOLS)
    missing_schemas = sorted(tool_names - schema_names)
    extra_schemas = sorted(schema_names - tool_names)
    missing_descriptions = sorted(tool_names - description_names)
    extra_descriptions = sorted(description_names - tool_names)
    invalid_project_root_tools = sorted(project_root_names - tool_names)
    invalid_protected_tools = sorted(protected_names - tool_names)
    invalid_specs = sorted(
        name
        for name, spec in AI_TERMINAL_TOOL_SPECS.items()
        if not callable(spec.handler) or not spec.description or not issubclass(spec.args_schema, BaseModel)
    )
    errors = []
    if missing_schemas:
        errors.append(f"缺少 Pydantic 参数 schema：{', '.join(missing_schemas)}")
    if extra_schemas:
        errors.append(f"存在未注册工具对应的参数 schema：{', '.join(extra_schemas)}")
    if missing_descriptions:
        errors.append(f"缺少工具描述：{', '.join(missing_descriptions)}")
    if extra_descriptions:
        errors.append(f"存在未注册工具对应的描述：{', '.join(extra_descriptions)}")
    if invalid_project_root_tools:
        errors.append(f"PROJECT_ROOT_TOOLS 包含未知工具：{', '.join(invalid_project_root_tools)}")
    if invalid_protected_tools:
        errors.append(f"PROTECTED_AI_TERMINAL_TOOLS 包含未知工具：{', '.join(invalid_protected_tools)}")
    if invalid_specs:
        errors.append(f"工具定义不正确：{', '.join(invalid_specs)}")
    return {
        "ok": not errors,
        "registered_tools": len(tool_names),
        "schemas": len(schema_names),
        "descriptions": len(description_names),
        "project_root_tools": len(project_root_names),
        "protected_tools": len(protected_names),
        "missing_schemas": missing_schemas,
        "extra_schemas": extra_schemas,
        "missing_descriptions": missing_descriptions,
        "extra_descriptions": extra_descriptions,
        "invalid_project_root_tools": invalid_project_root_tools,
        "invalid_protected_tools": invalid_protected_tools,
        "invalid_specs": invalid_specs,
        "errors": errors,
    }


def _ensure_ai_terminal_tool_registry_consistent() -> None:
    result = check_ai_terminal_tool_registry()
    if not result["ok"]:
        raise RuntimeError("AI 终端工具注册表不一致：" + "；".join(result["errors"]))


def _validate_ai_terminal_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = AI_TERMINAL_TOOL_SPECS.get(tool_name)
    if spec is None:
        raise ValueError(f"AI 终端工具缺少参数 schema：{tool_name}")
    return spec.args_schema.model_validate(arguments).model_dump()
