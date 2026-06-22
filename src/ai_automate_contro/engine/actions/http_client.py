from __future__ import annotations

import base64
import json
import mimetypes
import ssl
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    HTTPHandler,
    Request,
    build_opener,
)

from ai_automate_contro.support.paths import is_absolute_path_text, path_from_text


HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
BODY_FIELDS = ("json", "body", "body_path", "form", "multipart")
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MAX_BODY_BYTES = 262_144
MAX_BODY_BYTES_CAP = 1_048_576


def request(executor: Any, step: dict[str, Any]) -> None:
    method = str(step["method"]).upper()
    if method not in HTTP_METHODS:
        raise ValueError(f"http.method 不支持：{method}")
    _validate_body_runtime(method, step)

    started_at = time.perf_counter()
    url = _build_url(str(step["url"]), step.get("query"))
    headers = _build_headers(step)
    data = _build_body(executor, step, headers)
    timeout = max(0.001, float(step.get("timeout_ms", DEFAULT_TIMEOUT_MS)) / 1000)
    request_obj = Request(url, data=data, headers=headers, method=method)
    opener = _build_opener(step)

    try:
        with opener.open(request_obj, timeout=timeout) as response:
            status = int(response.status)
            final_url = str(response.url)
            response_headers = dict(response.headers.items())
            body_bytes = response.read()
    except HTTPError as error:
        status = int(error.code)
        final_url = str(error.url)
        response_headers = dict(error.headers.items())
        body_bytes = error.read()

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    body_path = ""
    if "response_body_path" in step:
        output_path = executor._resolve_output_path(step["response_body_path"], category="http")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body_bytes)
        body_path = str(output_path)

    include_headers = bool(step.get("include_headers", True))
    include_body = bool(step.get("include_body", "response_body_path" not in step))
    payload: dict[str, Any] = {
        "url": url,
        "final_url": final_url,
        "method": method,
        "status": status,
        "ok": 200 <= status < 400,
        "headers": _normalize_headers(response_headers) if include_headers else {},
        "body_path": body_path,
        "elapsed_ms": elapsed_ms,
    }
    if include_body:
        payload["body"] = _decode_response_body(step, response_headers, body_bytes)

    expected = step.get("expect_status")
    if expected is not None and status not in _expected_statuses(expected):
        raise AssertionError(f"HTTP status assertion failed. expected={expected}, actual={status}")

    if "save_as" in step:
        executor.state.variables[str(step["save_as"])] = payload

    executor.state.logger.log(
        "info",
        "http request finished",
        method=method,
        url=url,
        status=status,
        ok=payload["ok"],
        elapsed_ms=elapsed_ms,
        save_as=step.get("save_as", ""),
        body_path=body_path,
    )


def _validate_body_runtime(method: str, step: dict[str, Any]) -> None:
    body_fields = [field for field in BODY_FIELDS if field in step]
    if len(body_fields) > 1:
        raise ValueError(f"http.request 只能同时使用一种 body 字段，当前包含：{', '.join(body_fields)}")
    if method in {"GET", "HEAD"} and body_fields and not bool(step.get("allow_body", False)):
        raise ValueError(f"{method} 默认不允许请求体；确需发送时请显式设置 allow_body=true。")


def _build_url(raw_url: str, query: Any) -> str:
    parts = urlsplit(raw_url)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("http.url 只支持 http:// 或 https://。")
    if query in (None, ""):
        return raw_url
    if not isinstance(query, dict):
        raise ValueError("http.query 必须是对象。")
    existing_query = parts.query
    extra_query = urlencode(query, doseq=True)
    merged_query = "&".join(part for part in (existing_query, extra_query) if part)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, merged_query, parts.fragment))


def _build_headers(step: dict[str, Any]) -> dict[str, str]:
    raw_headers = step.get("headers", {})
    if raw_headers in (None, ""):
        raw_headers = {}
    if not isinstance(raw_headers, dict):
        raise ValueError("http.headers 必须是对象。")
    headers = {str(key): str(value) for key, value in raw_headers.items()}
    auth = step.get("auth")
    if auth is not None:
        _apply_auth(headers, auth)
    return headers


def _apply_auth(headers: dict[str, str], auth: Any) -> None:
    if not isinstance(auth, dict):
        raise ValueError("http.auth 必须是对象。")
    auth_type = str(auth.get("type", "")).lower()
    if auth_type == "basic":
        username = str(auth.get("username", ""))
        password = str(auth.get("password", ""))
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers.setdefault("Authorization", f"Basic {token}")
        return
    if auth_type == "bearer":
        token = str(auth.get("token", ""))
        headers.setdefault("Authorization", f"Bearer {token}")
        return
    raise ValueError(f"http.auth.type 不支持：{auth_type}")


def _build_body(executor: Any, step: dict[str, Any], headers: dict[str, str]) -> bytes | None:
    if "json" in step:
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(step["json"], ensure_ascii=False).encode("utf-8")
    if "body" in step:
        if "content_type" in step:
            headers.setdefault("Content-Type", str(step["content_type"]))
        return str(step["body"]).encode(str(step.get("encoding", "utf-8")))
    if "body_path" in step:
        path = _resolve_package_input_path(executor, str(step["body_path"]))
        if "content_type" in step:
            headers.setdefault("Content-Type", str(step["content_type"]))
        return path.read_bytes()
    if "form" in step:
        if not isinstance(step["form"], dict):
            raise ValueError("http.form 必须是对象。")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        return urlencode(step["form"], doseq=True).encode("utf-8")
    if "multipart" in step:
        content_type, body = _build_multipart_body(executor, step["multipart"])
        headers.setdefault("Content-Type", content_type)
        return body
    return None


def _build_multipart_body(executor: Any, multipart: Any) -> tuple[str, bytes]:
    if not isinstance(multipart, dict):
        raise ValueError("http.multipart 必须是对象。")
    boundary = f"----aic-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    fields = multipart.get("fields", {})
    if fields in (None, ""):
        fields = {}
    if not isinstance(fields, dict):
        raise ValueError("http.multipart.fields 必须是对象。")
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{_quote_header(str(name))}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    files = multipart.get("files", [])
    if not isinstance(files, list):
        raise ValueError("http.multipart.files 必须是数组。")
    for file_item in files:
        if not isinstance(file_item, dict):
            raise ValueError("http.multipart.files 每一项必须是对象。")
        field = str(file_item.get("field", "")).strip()
        raw_path = str(file_item.get("path", "")).strip()
        if not field or not raw_path:
            raise ValueError("http.multipart.files 每一项必须包含 field 和 path。")
        path = _resolve_package_input_path(executor, raw_path)
        filename = str(file_item.get("filename") or path.name)
        content_type = str(file_item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{_quote_header(field)}"; '
                    f'filename="{_quote_header(filename)}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def _resolve_package_input_path(executor: Any, raw_path: str) -> Path:
    if is_absolute_path_text(raw_path):
        resolved_path = path_from_text(raw_path).resolve()
    else:
        package_root = executor._package_root().resolve()
        resolved_path = (package_root / path_from_text(raw_path)).resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(f"输入文件不存在：{resolved_path}")
    return resolved_path


def _build_opener(step: dict[str, Any]) -> Any:
    handlers: list[Any] = []
    if bool(step.get("verify_tls", True)) is False:
        context = ssl._create_unverified_context()
        handlers.append(HTTPSHandler(context=context))
    else:
        handlers.append(HTTPSHandler())
    handlers.append(HTTPHandler())
    follow_redirects = bool(step.get("follow_redirects", True))
    if follow_redirects:
        handlers.append(_LimitedRedirectHandler(int(step.get("max_redirects", 10))))
    else:
        handlers.append(_NoRedirectHandler())
    return build_opener(*handlers)


class _LimitedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        self.max_redirects = max(0, max_redirects)
        self._count = 0

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        self._count += 1
        if self._count > self.max_redirects:
            raise RuntimeError(f"HTTP 重定向次数超过 max_redirects={self.max_redirects}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _decode_response_body(step: dict[str, Any], response_headers: dict[str, Any], body: bytes) -> Any:
    max_body_bytes = min(max(1, int(step.get("max_body_bytes", DEFAULT_MAX_BODY_BYTES))), MAX_BODY_BYTES_CAP)
    if len(body) > max_body_bytes:
        raise ValueError("响应体超过 max_body_bytes；请使用 response_body_path 保存大响应。")
    body_type = str(step.get("body_type") or _infer_body_type(response_headers)).lower()
    if body_type == "json":
        if not body:
            return None
        return json.loads(body.decode(_response_charset(response_headers), errors="replace"))
    if body_type == "bytes":
        return list(body)
    if body_type == "text":
        return body.decode(_response_charset(response_headers), errors="replace")
    raise ValueError(f"http.body_type 不支持：{body_type}")


def _infer_body_type(response_headers: dict[str, Any]) -> str:
    content_type = str(response_headers.get("Content-Type") or response_headers.get("content-type") or "").lower()
    if "json" in content_type:
        return "json"
    return "text"


def _response_charset(response_headers: dict[str, Any]) -> str:
    content_type = str(response_headers.get("Content-Type") or response_headers.get("content-type") or "")
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip() or "utf-8"
    return "utf-8"


def _expected_statuses(expected: Any) -> set[int]:
    if isinstance(expected, int):
        return {expected}
    if isinstance(expected, list):
        return {int(item) for item in expected}
    return {int(expected)}


def _normalize_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _quote_header(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

ACTION_HANDLERS = {
    "http": request,
}
