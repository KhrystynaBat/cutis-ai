from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import cv2

from app.ai.preprocessing import ImageDecodeError, decode_bgr
from app.core.errors import ApiError

MIN_SIDE = 64
MAX_SIDE = 10_000

_FORMATS = {
    "jpeg": ("image/jpeg", ".jpg"),
    "png": ("image/png", ".png"),
    "webp": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    sha256: str


def sniff_format(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image(data: bytes, max_bytes: int) -> ValidatedImage:
    if not data:
        raise ApiError(422, "FILE_EMPTY", "Файл порожній")
    if len(data) > max_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", f"Файл завеликий: максимум {max_bytes // (1024 * 1024)} МБ")
    fmt = sniff_format(data)
    if fmt is None:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "Підтримуються лише зображення JPG, PNG або WebP")
    try:
        img = decode_bgr(data)
    except (ImageDecodeError, cv2.error):
        raise ApiError(422, "IMAGE_DECODE_FAILED", "Не вдалося прочитати зображення: файл пошкоджений") from None
    height, width = img.shape[:2]
    if min(width, height) < MIN_SIDE:
        raise ApiError(422, "IMAGE_TOO_SMALL", f"Зображення замале: щонайменше {MIN_SIDE}×{MIN_SIDE} пікселів")
    if max(width, height) > MAX_SIDE:
        raise ApiError(422, "IMAGE_TOO_LARGE", f"Зображення завелике: не більше {MAX_SIDE} пікселів по стороні")
    mime, ext = _FORMATS[fmt]
    return ValidatedImage(data, mime, ext, width, height, hashlib.sha256(data).hexdigest())


_UNSAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)


def sanitize_filename(name: str | None, extension: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _UNSAFE.sub("_", base).strip(" ._")[:120]
    return base or f"photo{extension}"
