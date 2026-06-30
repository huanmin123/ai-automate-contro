from __future__ import annotations

import json
import os
import time
import threading
from contextlib import nullcontext
from pathlib import Path
from typing import Any, ContextManager, BinaryIO


_PROCESS_DESKTOP_MUTEX = threading.Lock()
_VALID_SCOPES = {"project", "plan_package"}
_VALID_CONFLICT_POLICIES = {"fail", "wait"}


class DesktopRunMutexError(RuntimeError):
    pass


def desktop_run_mutex_context(
    *,
    project_root: Path,
    plan_dir: Path,
    output_dir: Path,
    run_name: str,
    plan_config: dict[str, Any] | None,
    logger: Any | None = None,
) -> ContextManager[None]:
    config = resolve_desktop_run_mutex_config(plan_config)
    if not config["enabled"]:
        return nullcontext(None)
    lock_path = _desktop_mutex_lock_path(project_root, plan_dir, scope=str(config["scope"]))
    metadata = {
        "pid": os.getpid(),
        "run_name": run_name,
        "plan_dir": str(plan_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "scope": config["scope"],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    return DesktopRunMutex(
        lock_path=lock_path,
        metadata=metadata,
        on_conflict=str(config["on_conflict"]),
        wait_timeout_seconds=float(config["wait_timeout_seconds"]),
        stale_after_seconds=float(config["stale_after_seconds"]),
        logger=logger,
    )


def resolve_desktop_run_mutex_config(plan_config: dict[str, Any] | None) -> dict[str, Any]:
    config = plan_config if isinstance(plan_config, dict) else {}
    desktop = config.get("desktop") if isinstance(config.get("desktop"), dict) else {}
    raw = desktop.get("run_mutex") if isinstance(desktop.get("run_mutex"), dict) else {}
    scope = str(raw.get("scope", "project") or "project")
    if scope not in _VALID_SCOPES:
        scope = "project"
    on_conflict = str(raw.get("on_conflict", "fail") or "fail")
    if on_conflict not in _VALID_CONFLICT_POLICIES:
        on_conflict = "fail"
    return {
        "enabled": raw.get("enabled") if isinstance(raw.get("enabled"), bool) else True,
        "scope": scope,
        "on_conflict": on_conflict,
        "wait_timeout_seconds": max(0.0, _float_value(raw.get("wait_timeout_seconds", 0), default=0.0)),
        "stale_after_seconds": max(1.0, _float_value(raw.get("stale_after_seconds", 7200), default=7200.0)),
    }


class DesktopRunMutex:
    def __init__(
        self,
        *,
        lock_path: Path,
        metadata: dict[str, Any],
        on_conflict: str,
        wait_timeout_seconds: float,
        stale_after_seconds: float,
        logger: Any | None = None,
    ) -> None:
        self.lock_path = lock_path
        self.metadata = dict(metadata)
        self.on_conflict = on_conflict
        self.wait_timeout_seconds = wait_timeout_seconds
        self.stale_after_seconds = stale_after_seconds
        self.logger = logger
        self._file: BinaryIO | None = None
        self._process_lock_acquired = False
        self._file_lock_acquired = False

    def __enter__(self) -> None:
        self.acquire()
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()
        return None

    def acquire(self) -> None:
        deadline = time.monotonic() + self.wait_timeout_seconds
        while True:
            try:
                self._try_acquire_once()
            except DesktopRunMutexError as error:
                if self.on_conflict != "wait" or time.monotonic() >= deadline:
                    raise error
                time.sleep(0.2)
                continue
            if self.logger is not None:
                self.logger.log("info", "desktop run mutex acquired", lock_path=str(self.lock_path))
            return

    def release(self) -> None:
        if self._file_lock_acquired and self._file is not None:
            try:
                _unlock_file(self._file)
            finally:
                self._file_lock_acquired = False
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None
        if self._process_lock_acquired:
            self._process_lock_acquired = False
            _PROCESS_DESKTOP_MUTEX.release()
        if self.logger is not None:
            self.logger.log("info", "desktop run mutex released", lock_path=str(self.lock_path))

    def _try_acquire_once(self) -> None:
        if not _PROCESS_DESKTOP_MUTEX.acquire(blocking=False):
            raise self._conflict_error(owner={"source": "same_process"})
        self._process_lock_acquired = True
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.lock_path.open("a+b")
            _ensure_lock_file_byte(self._file)
            _lock_file(self._file)
            self._file_lock_acquired = True
            self._write_metadata()
        except DesktopRunMutexError as error:
            owner = _read_lock_owner(self.lock_path)
            self.release()
            raise self._conflict_error(owner=owner, cause=error) from error
        except Exception as error:
            owner = _read_lock_owner(self.lock_path)
            self.release()
            raise self._conflict_error(owner=owner, cause=error) from error

    def _write_metadata(self) -> None:
        if self._file is None:
            return
        payload = {
            **self.metadata,
            "lock_path": str(self.lock_path),
            "stale_after_seconds": self.stale_after_seconds,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._file.seek(0)
        self._file.truncate()
        self._file.write(raw)
        self._file.flush()

    def _conflict_error(self, *, owner: Any, cause: Exception | None = None) -> DesktopRunMutexError:
        detail = owner if owner else {"lock_path": str(self.lock_path)}
        if cause is not None:
            detail = {"owner": detail, "error": str(cause), "error_type": type(cause).__name__}
        return DesktopRunMutexError(
            "已有 desktop plan 正在控制当前项目桌面资源；"
            f"请等待上一轮结束后重试。lock_path={self.lock_path} owner={detail}"
        )


def _desktop_mutex_lock_path(project_root: Path, plan_dir: Path, *, scope: str) -> Path:
    runtime_dir = project_root.resolve() / ".keygen" / "runtime"
    if scope == "plan_package":
        token = _safe_lock_token(str(plan_dir.resolve()))
        return runtime_dir / f"desktop-run-{token}.lock"
    return runtime_dir / "desktop-run-project.lock"


def _safe_lock_token(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def _ensure_lock_file_byte(file: BinaryIO) -> None:
    file.seek(0, os.SEEK_END)
    if file.tell() == 0:
        file.write(b"\0")
        file.flush()
    file.seek(0)


def _lock_file(file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise DesktopRunMutexError(str(error)) from error
        return
    import fcntl

    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise DesktopRunMutexError(str(error)) from error


def _unlock_file(file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _read_lock_owner(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
