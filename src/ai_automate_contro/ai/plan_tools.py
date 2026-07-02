from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ai_automate_contro.app.runtime_config import plan_roots_for_project
from ai_automate_contro.engine.executor import execute_plan
from ai_automate_contro.plans.loader import detect_document_type, load_plan
from ai_automate_contro.plans.packages import (
    create_plan_package,
    default_plan_package_dir,
    discover_plan_packages,
    plan_matches_filter,
    summarize_plan,
)
from ai_automate_contro.plans.validator import ValidationIssue, validate_plan_file
from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


MAX_PACKAGE_DOCS = 20
MAX_SUB_PLANS = 50
MAX_PACKAGE_FILE_LIST = 200
MAX_PLAN_STEP_OUTLINE = 80
ALLOWED_PLAN_PACKAGE_WRITE_ROOTS = {"docs", "resources"}
FORBIDDEN_PLAN_PACKAGE_WRITE_PARTS = {
    ".git",
    ".keygen",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "output",
}
FORBIDDEN_PLAN_PACKAGE_CREATE_PARTS = {*FORBIDDEN_PLAN_PACKAGE_WRITE_PARTS, "profiles"}


def list_plan_packages_tool(project_root: str | Path, *, filter_text: str = "") -> dict[str, Any]:
    root = Path(project_root).resolve()
    normalized_filter = filter_text.lower().strip()
    plan_paths = discover_plan_packages(root)
    if normalized_filter:
        plan_paths = [
            plan_path
            for plan_path in plan_paths
            if plan_matches_filter(plan_path, root, normalized_filter)
        ]
    return {
        "ok": True,
        "plans": [summarize_plan(plan_path, root) for plan_path in plan_paths],
    }


def read_plan_package_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent
    docs = read_package_docs(package_dir)
    sub_plans = read_sub_plans(package_dir)
    resources = list_package_files(package_dir / "resources", package_dir)
    return {
        "ok": True,
        "summary": summarize_plan(resolved_plan_path, root),
        "plan": read_plan_file_overview(resolved_plan_path, package_dir),
        "config": read_json_file_overview(package_dir / "config.json", package_dir),
        "docs": docs,
        "sub_plans": sub_plans,
        "resources": resources,
        "next_actions": [
            "先用 grep_project_text 定位相关 plan、docs、resource 或 config 行。",
            "编辑前再用 read_project_file_slice 读取必要的小范围行段。",
        ],
    }


def create_plan_package_tool(
    project_root: str | Path,
    package_path: str | Path | None = None,
    *,
    automation_type: str,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    if not package_path and not name:
        raise ValueError("create_plan_package 需要 package_path 或 name。")
    if package_path:
        raw_package_path = path_from_text(package_path)
        if raw_package_path.is_absolute():
            resolved_package_path = raw_package_path.resolve()
        else:
            resolved_package_path = (root / raw_package_path).resolve()
    else:
        resolved_package_path = default_plan_package_dir(root, name=name or "").resolve()
    _validate_create_plan_package_path(resolved_package_path, root)
    package_dir = create_plan_package(
        resolved_package_path,
        project_root=root,
        automation_type=automation_type,
        name=name,
        force=force,
    )
    return {
        "ok": True,
        "package_dir": str(package_dir),
        "plan_path": str(package_dir / "plan.json"),
        "summary": summarize_plan(package_dir / "plan.json", root),
    }


def write_plan_package_file_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    relative_path: str | Path,
    content: str | None = None,
    json_value: Any = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent.resolve()
    if not is_relative_to(package_dir, root):
        raise ValueError("plan 包必须位于项目根目录内。")
    if not resolved_plan_path.exists():
        raise FileNotFoundError(f"plan 包入口不存在：{resolved_plan_path}")

    raw_relative_path = path_from_text(relative_path)
    if is_absolute_path_text(relative_path):
        raise ValueError("relative_path 必须是相对于 plan 包的路径。")
    normalized_relative_path = Path(*raw_relative_path.parts)
    _validate_plan_package_write_path(normalized_relative_path)

    write_mode = mode.strip().lower()
    if write_mode not in {"overwrite", "append"}:
        raise ValueError("mode 必须是 overwrite 或 append。")
    if content is not None and json_value is not None:
        raise ValueError("content 和 json_value 只能提供一个。")
    if content is None and json_value is None:
        raise ValueError("write_plan_package_file 需要 content 或 json_value。")
    if json_value is not None and write_mode == "append":
        raise ValueError("json_value 只支持 overwrite 模式。")

    target_path = (package_dir / normalized_relative_path).resolve()
    if not is_relative_to(target_path, package_dir):
        raise ValueError("目标路径必须位于 plan 包内。")

    if json_value is not None:
        if target_path.suffix.lower() != ".json":
            raise ValueError("json_value 只能写入 JSON 文件。")
        serialized = json.dumps(json_value, ensure_ascii=False, indent=2) + "\n"
    else:
        serialized = str(content)
        if target_path.suffix.lower() == ".json":
            try:
                parsed_json = json.loads(serialized)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON 文件内容格式不正确：{error}") from error

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if write_mode == "append":
        target_path.write_text(
            (target_path.read_text(encoding="utf-8") if target_path.exists() else "") + serialized,
            encoding="utf-8",
        )
    else:
        target_path.write_text(serialized, encoding="utf-8")

    stat = target_path.stat()
    return {
        "ok": True,
        "plan_path": str(resolved_plan_path),
        "package_dir": str(package_dir),
        "path": str(target_path),
        "relative_path": str(normalized_relative_path),
        "mode": write_mode,
        "bytes": stat.st_size,
    }


def import_plan_resource_file_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    source_path: str | Path,
    relative_path: str | Path = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_plan_path = resolve_plan_path(plan_path)
    package_dir = resolved_plan_path.parent.resolve()
    if not is_relative_to(package_dir, root):
        raise ValueError("plan 包必须位于项目根目录内。")
    if not resolved_plan_path.exists():
        raise FileNotFoundError(f"plan 包入口不存在：{resolved_plan_path}")

    raw_source_path = path_from_text(source_path).expanduser()
    resolved_source_path = raw_source_path.resolve() if raw_source_path.is_absolute() else (root / raw_source_path).resolve()
    if not resolved_source_path.exists() or not resolved_source_path.is_file():
        raise FileNotFoundError(f"源文件不存在：{resolved_source_path}")

    normalized_relative_path = _normalize_resource_import_path(relative_path, resolved_source_path.name)
    target_path = (package_dir / normalized_relative_path).resolve()
    resources_dir = (package_dir / "resources").resolve()
    if not is_relative_to(target_path, resources_dir):
        raise ValueError("导入资源只能写入当前 plan 包 resources/ 下。")
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"目标资源已存在：{target_path}。需要覆盖时设置 overwrite=true。")
    if target_path.exists() and target_path.is_dir():
        raise ValueError(f"目标资源是目录，不能覆盖：{target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resolved_source_path, target_path)
    stat = target_path.stat()
    return {
        "ok": True,
        "plan_path": str(resolved_plan_path),
        "package_dir": str(package_dir),
        "source_path": str(resolved_source_path),
        "path": str(target_path),
        "relative_path": normalized_relative_path.as_posix(),
        "bytes": stat.st_size,
    }


def validate_plan_tool(project_root: str | Path, plan_path: str | Path) -> dict[str, Any]:
    result = validate_plan_file(plan_path, project_root)
    return {
        "ok": result.ok,
        "plan_path": str(result.plan_path),
        "errors": [issue_to_dict(error) for error in result.errors],
    }


def run_plan_tool(
    project_root: str | Path,
    plan_path: str | Path,
    *,
    run_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
    latest_state_reader: Any | None = None,
    manual_confirmation_handler: Any | None = None,
    inspection_confirmation_handler: Any | None = None,
    run_event_handler: Any | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    document = load_plan(plan_path)
    document_type = detect_document_type(document)
    if document_type != "plan":
        raise ValueError("只能运行 plan 文档。请确认文件是 plan 包入口 plan.json。")
    try:
        result = execute_plan(
            document,
            root,
            plan_path=plan_path,
            run_name=run_name,
            variable_overrides=variable_overrides or {},
            manual_confirmation_handler=manual_confirmation_handler,
            inspection_confirmation_handler=inspection_confirmation_handler,
            run_event_handler=run_event_handler,
            log_echo=run_event_handler is None,
        )
    except Exception as error:
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(error),
        }
        if latest_state_reader is not None:
            payload["latest_state"] = latest_state_reader(plan_path)
        return payload
    return {
        "ok": result.status == "passed",
        "result": result.to_dict(),
    }


def resolve_plan_path(raw_plan_path: str | Path) -> Path:
    plan_path = path_from_text(raw_plan_path).resolve()
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"
    return plan_path


def _validate_plan_package_write_path(relative_path: Path) -> None:
    parts = relative_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("relative_path 必须是 plan 包内的干净路径。")
    if parts[0] == "profiles":
        raise ValueError("拒绝写入 profiles/ 浏览器状态目录。")
    if any(part in FORBIDDEN_PLAN_PACKAGE_WRITE_PARTS for part in parts):
        raise ValueError("拒绝写入 output、缓存、checkpoint、git 或 pycache 路径。")
    if relative_path.name.endswith((".pyc", ".pyo")) or ".egg-info" in parts:
        raise ValueError("拒绝写入 pyc、pyo 或 egg-info 路径。")
    if parts == ("plan.json",) or parts == ("config.json",):
        return
    if parts[0] == "sub-plans" and len(parts) == 2 and relative_path.name.endswith("-plan.json"):
        return
    if parts[0] in ALLOWED_PLAN_PACKAGE_WRITE_ROOTS and len(parts) >= 2:
        return
    raise ValueError("允许写入的目标只有 plan.json、config.json、docs/**、resources/** 或 sub-plans/*-plan.json。")


def _normalize_resource_import_path(relative_path: str | Path, fallback_name: str) -> Path:
    raw_path_text = str(relative_path or "").strip()
    raw_path = path_from_text(raw_path_text) if raw_path_text else Path(fallback_name)
    if is_absolute_path_text(raw_path):
        raise ValueError("relative_path 必须是 resources/ 下的相对路径。")
    parts = raw_path.parts
    if not parts:
        raise ValueError("relative_path 不能为空。")
    if parts[0] == "resources":
        parts = parts[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("relative_path 必须是 resources/ 下的干净文件路径。")
    if any(part in FORBIDDEN_PLAN_PACKAGE_WRITE_PARTS for part in parts):
        raise ValueError("拒绝导入到 output、缓存、checkpoint、git 或 pycache 路径。")
    target = Path("resources", *parts)
    if target.name.endswith((".pyc", ".pyo")) or ".egg-info" in target.parts:
        raise ValueError("拒绝导入 pyc、pyo 或 egg-info 文件。")
    return target


def _validate_no_plain_secret_literals(relative_path: Path, value: Any) -> None:
    return


def _requires_secret_literal_guard(relative_path: Path) -> bool:
    parts = relative_path.parts
    if parts == ("plan.json",) or parts == ("config.json",):
        return True
    if parts and parts[0] in {"resources", "sub-plans"}:
        return True
    return False


def _collect_plain_secret_literals(value: Any, *, path: str, findings: list[str]) -> None:
    return


def _is_password_fill_step(value: dict[str, Any]) -> bool:
    if str(value.get("action") or "") != "element" or str(value.get("type") or "") != "fill":
        return False
    fields = " ".join(
        str(value.get(key) or "")
        for key in ("selector", "role", "name", "label", "placeholder", "test_id")
    ).lower()
    return any(token in fields for token in ("password", "passwd", "pwd", "密码", "口令"))


def _is_plain_secret_literal(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or "{{" in text or "}}" in text:
        return False
    return True


def _validate_text_has_no_plain_secret_literals(text: str) -> None:
    return


def _validate_create_plan_package_path(package_dir: Path, project_root: Path) -> None:
    if not is_relative_to(package_dir, project_root):
        raise ValueError("create_plan_package 只能在当前项目根目录内创建 plan 包。")
    plan_roots = tuple(root.resolve() for root in plan_roots_for_project(project_root))
    if not any(is_relative_to(package_dir, plan_root) for plan_root in plan_roots):
        allowed = ", ".join(str(root) for root in plan_roots)
        raise ValueError(f"create_plan_package 只能写入 plan.config.plan_roots：{allowed}")
    relative_parts = package_dir.relative_to(project_root).parts
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        raise ValueError("package_path 必须是干净的 plan 包路径。")
    if any(part in FORBIDDEN_PLAN_PACKAGE_CREATE_PARTS for part in relative_parts):
        raise ValueError("拒绝在 output、profiles、缓存、checkpoint、git 或 pycache 路径创建 plan 包。")
    if package_dir.name.endswith((".pyc", ".pyo")) or ".egg-info" in relative_parts:
        raise ValueError("拒绝在 pyc、pyo 或 egg-info 路径创建 plan 包。")


def issue_to_dict(issue: ValidationIssue) -> dict[str, str]:
    return {
        "location": issue.location,
        "message": issue.message,
        "formatted": issue.format(),
    }


def read_package_docs(package_dir: Path) -> list[dict[str, Any]]:
    docs_dir = package_dir / "docs"
    docs: list[dict[str, Any]] = []
    if not docs_dir.exists():
        return docs
    for path in sorted(docs_dir.rglob("*.md"), key=lambda item: str(item).lower())[:MAX_PACKAGE_DOCS]:
        stat = path.stat()
        docs.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return docs


def read_sub_plans(package_dir: Path) -> list[dict[str, Any]]:
    sub_plans_dir = package_dir / "sub-plans"
    sub_plans: list[dict[str, Any]] = []
    if not sub_plans_dir.exists():
        return sub_plans
    for path in sorted(sub_plans_dir.glob("*-plan.json"), key=lambda item: str(item).lower())[:MAX_SUB_PLANS]:
        sub_plans.append(read_plan_file_overview(path, package_dir))
    return sub_plans


def list_package_files(root: Path, package_dir: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower())[:MAX_PACKAGE_FILE_LIST]:
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(package_dir)),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return files


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_plan_file_overview(path: Path, package_dir: Path) -> dict[str, Any]:
    overview = read_json_file_overview(path, package_dir)
    if not overview["exists"]:
        return overview
    document = read_json_if_exists(path)
    if not isinstance(document, dict):
        overview["document_type"] = "unknown"
        return overview
    try:
        overview["document_type"] = detect_document_type(document)
    except ValueError:
        overview["document_type"] = "unknown"
    steps = document.get("steps")
    if not isinstance(steps, list):
        steps = []
    variables = document.get("variables")
    if not isinstance(variables, dict):
        variables = {}
    tags = document.get("tags")
    if not isinstance(tags, list):
        tags = []
    overview.update(
        {
            "name": document.get("name") or path.parent.name,
            "automation_type": document.get("automation_type") or "",
            "tags": [str(tag) for tag in tags],
            "variables": sorted(str(key) for key in variables.keys()),
            "step_count": len(steps),
            "steps_preview": summarize_plan_steps(steps),
            "steps_truncated": len(steps) > MAX_PLAN_STEP_OUTLINE,
        }
    )
    return overview


def read_json_file_overview(path: Path, package_dir: Path) -> dict[str, Any]:
    resolved_path = path.resolve()
    payload: dict[str, Any] = {
        "path": str(resolved_path),
        "relative_path": str(path.relative_to(package_dir)) if is_relative_to(resolved_path, package_dir.resolve()) else str(path),
        "exists": path.exists(),
        "size": 0,
        "modified_at": None,
        "top_level_keys": [],
    }
    if not path.exists():
        return payload
    stat = path.stat()
    payload["size"] = stat.st_size
    payload["modified_at"] = stat.st_mtime
    document = read_json_if_exists(path)
    if isinstance(document, dict):
        payload["top_level_keys"] = sorted(str(key) for key in document.keys())
    return payload


def summarize_plan_steps(steps: list[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, step in enumerate(steps[:MAX_PLAN_STEP_OUTLINE], start=1):
        if not isinstance(step, dict):
            summaries.append({"step_number": index, "type": type(step).__name__})
            continue
        summary: dict[str, Any] = {
            "step_number": index,
            "action": step.get("action"),
            "type": step.get("type"),
            "name": step.get("name"),
            "keys": sorted(str(key) for key in step.keys()),
        }
        if step.get("action") == "run_sub_plan":
            summary["path"] = step.get("path")
        summaries.append({key: value for key, value in summary.items() if value not in (None, "", [])})
    return summaries


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
