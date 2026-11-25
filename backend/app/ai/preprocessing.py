from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .constants import INPUT_SIZE

PREPROCESSING_VERSION = "ham10000-bgr128-cubic-std-v1"
STD_EPSILON = 1e-7
PARAMS_PATH = Path(__file__).with_name("preprocessing.json")


class ImageDecodeError(ValueError):
    pass


class NormalizationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizationParams:
    mean: np.ndarray  # shape (3,), BGR order, float64
    std: np.ndarray  # shape (3,), BGR order, float64
    version: str

    @classmethod
    def from_file(cls, path: Path = PARAMS_PATH) -> NormalizationParams:
        if not path.is_file():
            raise NormalizationUnavailable(f"normalization file not found: {path.name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("preprocessing_version") != PREPROCESSING_VERSION:
            raise NormalizationUnavailable("preprocessing version mismatch")
        mean = np.asarray(data["mean_bgr"], dtype=np.float64)
        std = np.asarray(data["std_bgr"], dtype=np.float64)
        if mean.shape != (3,) or std.shape != (3,) or not np.all(std > 0):
            raise NormalizationUnavailable("invalid normalization parameters")
        return cls(mean=mean, std=std, version=data["preprocessing_version"])


@lru_cache(maxsize=1)
def load_params() -> NormalizationParams:
    return NormalizationParams.from_file()


def decode_bgr(data: bytes) -> np.ndarray:
    buf = np.frombuffer(data, dtype=np.uint8)
    if buf.size == 0:
        raise ImageDecodeError("empty file")
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None or img.ndim != 3 or img.shape[2] != 3:
        raise ImageDecodeError("cannot decode image")
    return img


def resize_bgr(img_bgr: np.ndarray) -> np.ndarray:
    return cv2.resize(img_bgr, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_CUBIC)


def standardize(x: np.ndarray, params: NormalizationParams) -> np.ndarray:
    return ((x.astype(np.float64) - params.mean) / (params.std + STD_EPSILON)).astype(np.float32)


def preprocess_bgr(img_bgr: np.ndarray, params: NormalizationParams | None = None) -> np.ndarray:
    params = params or load_params()
    return standardize(resize_bgr(img_bgr), params)[np.newaxis, ...]


def preprocess_bytes(data: bytes, params: NormalizationParams | None = None) -> tuple[np.ndarray, np.ndarray]:
    img_bgr = decode_bgr(data)
    return preprocess_bgr(img_bgr, params), cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
