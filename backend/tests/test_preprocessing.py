import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.ai.preprocessing import (
    PREPROCESSING_VERSION,
    STD_EPSILON,
    ImageDecodeError,
    NormalizationParams,
    decode_bgr,
    preprocess_bgr,
    preprocess_bytes,
)

PARAMS = NormalizationParams(
    mean=np.array([150.0, 140.0, 190.0]), std=np.array([40.0, 45.0, 50.0]), version=PREPROCESSING_VERSION
)


def _photo(h: int = 300, w: int = 400) -> np.ndarray:
    rng = np.random.default_rng(42)
    img = np.zeros((h, w, 3), np.uint8)
    img[..., 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]  # R ramps horizontally
    img[..., 1] = np.linspace(0, 255, h, dtype=np.uint8)[:, None]  # G ramps vertically
    img[..., 2] = rng.integers(0, 256, (h, w), dtype=np.uint8)
    img[: h // 3, : w // 4] = (220, 30, 30)
    return img


def _encode(rgb: np.ndarray, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format=fmt, **kw)
    return buf.getvalue()


def _reference(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    img = cv2.resize(img, (128, 128), interpolation=cv2.INTER_CUBIC)
    return ((img.astype(np.float64) - PARAMS.mean) / (PARAMS.std + STD_EPSILON)).astype(np.float32)[None]


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_backend_matches_training_pipeline(tmp_path, fmt):
    data = _encode(_photo(), fmt, **({"quality": 92} if fmt == "JPEG" else {}))
    path = tmp_path / f"img.{fmt.lower()}"
    path.write_bytes(data)
    x, rgb = preprocess_bytes(data, PARAMS)
    assert x.shape == (1, 128, 128, 3) and x.dtype == np.float32
    assert np.abs(x - _reference(path)).max() < 1e-4
    assert rgb.shape == (300, 400, 3)


def test_rgb_without_conversion_differs():
    rgb = _photo()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    assert np.abs(preprocess_bgr(bgr, PARAMS) - preprocess_bgr(rgb, PARAMS)).max() > 0.5


def test_model_receives_bgr_display_copy_is_rgb():
    rgb = _photo()
    _, display = preprocess_bytes(_encode(rgb, "PNG"), PARAMS)
    assert np.array_equal(display, rgb)
    assert np.array_equal(decode_bgr(_encode(rgb, "PNG")), rgb[..., ::-1])


def test_png_alpha_dropped_and_grayscale_expanded():
    rgba = np.dstack([_photo(), np.full((300, 400), 128, np.uint8)])
    assert decode_bgr(_encode(rgba, "PNG")).shape == (300, 400, 3)
    gray = decode_bgr(_encode(_photo()[..., 0], "PNG"))
    assert gray.shape == (300, 400, 3) and np.array_equal(gray[..., 0], gray[..., 2])


def test_exif_orientation_applied_like_imread(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW on display
    data = _encode(_photo(), "JPEG", quality=95, exif=exif.tobytes())
    path = tmp_path / "rot.jpg"
    path.write_bytes(data)
    img = decode_bgr(data)
    assert img.shape == (400, 300, 3)  # rotated
    assert np.array_equal(img, cv2.imread(str(path), cv2.IMREAD_COLOR))


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n broken"])
def test_invalid_bytes_rejected(data):
    with pytest.raises(ImageDecodeError):
        decode_bgr(data)


def test_params_file_missing_raises(tmp_path):
    from app.ai.preprocessing import NormalizationUnavailable

    with pytest.raises(NormalizationUnavailable):
        NormalizationParams.from_file(tmp_path / "missing.json")
