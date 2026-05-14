from __future__ import annotations

import base64
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_automate_contro.ai.session_compression import session_root
from ai_automate_contro.support.paths import path_from_text


MAX_IMAGE_ATTACHMENTS = 5
MAX_IMAGE_ATTACHMENT_BYTES = 20 * 1024 * 1024
IMAGE_ATTACHMENTS_METADATA_KEY = "ai_terminal_image_attachments"
SUPPORTED_IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@dataclass(frozen=True)
class ImageAttachment:
    original_path: str
    stored_path: Path
    file_name: str
    mime_type: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "original_path": self.original_path,
            "stored_path": str(self.stored_path),
        }


def attach_image_file(
    project_root: Path,
    thread_id: str,
    image_path: str | Path,
    *,
    pending_count: int = 0,
) -> ImageAttachment:
    _ensure_capacity(pending_count, adding=1)
    source = resolve_image_path(project_root, image_path)
    mime_type = image_mime_type(source)
    size_bytes = validate_image_file(source)
    stored_path = _copy_to_session_attachments(project_root, thread_id, source)
    return ImageAttachment(
        original_path=str(source),
        stored_path=stored_path,
        file_name=source.name,
        mime_type=mime_type,
        size_bytes=size_bytes,
    )


def attach_clipboard_images(
    project_root: Path,
    thread_id: str,
    *,
    pending_count: int = 0,
) -> list[ImageAttachment]:
    try:
        from PIL import ImageGrab
    except Exception as error:
        raise RuntimeError(
            "剪贴板图片粘贴需要 Pillow。请先安装项目依赖："
            "python -m pip install -e ."
        ) from error

    clipboard = ImageGrab.grabclipboard()
    if clipboard is None:
        raise ValueError("剪贴板中没有图片或图片文件路径。")

    if isinstance(clipboard, list):
        image_paths = [Path(item) for item in clipboard if _looks_like_supported_image(Path(item))]
        if not image_paths:
            raise ValueError("剪贴板文件列表中没有支持的图片。")
        _ensure_capacity(pending_count, adding=len(image_paths))
        attachments: list[ImageAttachment] = []
        for image_path in image_paths:
            attachment = attach_image_file(
                project_root,
                thread_id,
                image_path,
                pending_count=pending_count + len(attachments),
            )
            attachments.append(attachment)
        return attachments

    save = getattr(clipboard, "save", None)
    if not callable(save):
        raise ValueError("剪贴板内容不是支持的图片。")

    _ensure_capacity(pending_count, adding=1)
    stored_path = _session_attachments_dir(project_root, thread_id) / _stored_file_name("clipboard", ".png")
    clipboard.save(stored_path, "PNG")
    size_bytes = validate_image_file(stored_path)
    return [
        ImageAttachment(
            original_path="clipboard",
            stored_path=stored_path,
            file_name=stored_path.name,
            mime_type="image/png",
            size_bytes=size_bytes,
        )
    ]


def build_human_message_content(text: str, attachments: list[ImageAttachment]) -> str:
    if not attachments:
        return text
    placeholders = image_attachment_placeholders(attachments)
    if all(placeholder in text for placeholder in placeholders):
        return text
    missing_placeholders = [placeholder for placeholder in placeholders if placeholder not in text]
    placeholder_text = " ".join(missing_placeholders)
    if any(placeholder in text for placeholder in placeholders):
        return f"{text} {placeholder_text}".strip()
    if not text.strip():
        return placeholder_text
    return f"{placeholder_text} {text}".strip()


def build_human_message_additional_kwargs(attachments: list[ImageAttachment]) -> dict[str, Any]:
    if not attachments:
        return {}
    return {IMAGE_ATTACHMENTS_METADATA_KEY: [attachment.to_dict() for attachment in attachments]}


def expand_message_image_attachments_for_model(message: Any) -> Any:
    additional_kwargs = getattr(message, "additional_kwargs", {})
    if not isinstance(additional_kwargs, dict):
        return message
    raw_attachments = additional_kwargs.get(IMAGE_ATTACHMENTS_METADATA_KEY)
    if not isinstance(raw_attachments, list) or not raw_attachments:
        return message

    text = _message_content_text(getattr(message, "content", ""))
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for raw_attachment in raw_attachments:
        attachment = image_attachment_from_metadata(raw_attachment)
        content.append({"type": "image_url", "image_url": {"url": image_attachment_data_url(attachment)}})

    model_copy = getattr(message, "model_copy", None)
    if callable(model_copy):
        return model_copy(update={"content": content, "additional_kwargs": {}})
    copy = getattr(message, "copy", None)
    if callable(copy):
        return copy(update={"content": content, "additional_kwargs": {}})
    return message


def expand_messages_image_attachments_for_model(messages: list[Any]) -> list[Any]:
    return [expand_message_image_attachments_for_model(message) for message in messages]


def image_attachment_from_metadata(value: Any) -> ImageAttachment:
    if not isinstance(value, dict):
        raise ValueError("图片附件 metadata 必须是对象。")
    stored_path = Path(str(value.get("stored_path") or "")).resolve()
    file_name = str(value.get("file_name") or stored_path.name)
    mime_type = str(value.get("mime_type") or image_mime_type(stored_path))
    size_bytes = int(value.get("size_bytes") or validate_image_file(stored_path))
    original_path = str(value.get("original_path") or stored_path)
    if not stored_path.exists() or not stored_path.is_file():
        raise FileNotFoundError(f"图片附件文件不存在：{stored_path}")
    return ImageAttachment(
        original_path=original_path,
        stored_path=stored_path,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
    )


def image_attachment_data_url(attachment: ImageAttachment) -> str:
    encoded = base64.b64encode(attachment.stored_path.read_bytes()).decode("ascii")
    return f"data:{attachment.mime_type};base64,{encoded}"


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                if item.get("text"):
                    chunks.append(str(item["text"]))
                elif item.get("content"):
                    chunks.append(str(item["content"]))
        return "\n".join(chunks)
    return str(content)


def format_pending_attachments(attachments: list[ImageAttachment]) -> str:
    if not attachments:
        return "图片：无"
    lines = [
        f"图片：{' '.join(image_attachment_placeholders(attachments))} "
        f"({len(attachments)}/{MAX_IMAGE_ATTACHMENTS}，会随下一条消息发送)"
    ]
    for index, attachment in enumerate(attachments, start=1):
        lines.append(
            f"{image_attachment_placeholder(index)} {attachment.file_name} "
            f"({attachment.mime_type}, {_format_bytes(attachment.size_bytes)})"
        )
    return "\n".join(lines)


def image_attachment_placeholder(index: int) -> str:
    return f"[图片 #{index}]"


def image_attachment_placeholders(attachments: list[ImageAttachment]) -> list[str]:
    return [image_attachment_placeholder(index) for index, _ in enumerate(attachments, start=1)]


def resolve_image_path(project_root: Path, image_path: str | Path) -> Path:
    raw_path = path_from_text(image_path)
    if raw_path.is_absolute():
        resolved = raw_path.resolve()
    else:
        resolved = (project_root / raw_path).resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"图片文件不存在：{resolved}")
    return resolved


def image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_MIME_BY_SUFFIX:
        return SUPPORTED_IMAGE_MIME_BY_SUFFIX[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and guessed.startswith("image/"):
        return guessed
    supported = ", ".join(sorted(SUPPORTED_IMAGE_MIME_BY_SUFFIX))
    raise ValueError(f"不支持的图片类型：{path.suffix or '<无>'}。支持类型：{supported}")


def validate_image_file(path: Path) -> int:
    mime_type = image_mime_type(path)
    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise ValueError(f"图片文件为空：{path}")
    if size_bytes > MAX_IMAGE_ATTACHMENT_BYTES:
        raise ValueError(
            f"图片文件过大：{size_bytes} 字节。"
            f"最大允许 {MAX_IMAGE_ATTACHMENT_BYTES} 字节。"
        )
    if not mime_type.startswith("image/"):
        raise ValueError(f"不支持的图片 MIME 类型：{mime_type}")
    return size_bytes


def _copy_to_session_attachments(project_root: Path, thread_id: str, source: Path) -> Path:
    stored_path = _session_attachments_dir(project_root, thread_id) / _stored_file_name(source.stem, source.suffix)
    shutil.copy2(source, stored_path)
    return stored_path


def _session_attachments_dir(project_root: Path, thread_id: str) -> Path:
    attachments_dir = session_root(project_root, thread_id) / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    return attachments_dir


def _stored_file_name(stem: str, suffix: str) -> str:
    safe_stem = "".join(char if char.isalnum() or char in "._-" else "-" for char in stem).strip(".-")
    if not safe_stem:
        safe_stem = "image"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid4().hex[:8]}-{safe_stem}{suffix.lower()}"


def _ensure_capacity(pending_count: int, *, adding: int) -> None:
    if pending_count + adding > MAX_IMAGE_ATTACHMENTS:
        raise ValueError(f"最多只能附加 {MAX_IMAGE_ATTACHMENTS} 张图片")


def _looks_like_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_IMAGE_MIME_BY_SUFFIX and path.exists() and path.is_file()


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
