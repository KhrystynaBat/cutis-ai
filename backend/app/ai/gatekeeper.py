from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .preprocessing import decode_bgr

logger = logging.getLogger("dermalab.ai")

CONFIG_PATH = Path(__file__).with_name("gatekeeper.json")


@dataclass(frozen=True)
class GateConfig:
    model_name: str
    model_file: str
    sha256: str
    input_size: tuple[int, int]
    threshold: float


@lru_cache(maxsize=1)
def load_config(path: Path = CONFIG_PATH) -> GateConfig:
    d = json.loads(path.read_text(encoding="utf-8"))
    return GateConfig(
        model_name=d["model_name"],
        model_file=d["model_file"],
        sha256=d["sha256"],
        input_size=(int(d["input_size"][0]), int(d["input_size"][1])),
        threshold=float(d["threshold"]),
    )


@dataclass(frozen=True)
class GateResult:
    score: float  # probability that the photo is dermoscopic
    passed: bool
    model_sha256: str


class GateModel(Protocol):
    model_sha256: str
    threshold: float

    def predict(self, image_bytes: bytes) -> float: ...


def preprocess(image_bytes: bytes, size: tuple[int, int] | None = None) -> np.ndarray:
    import tensorflow as tf

    size = size or load_config().input_size
    rgb = cv2.cvtColor(decode_bgr(image_bytes), cv2.COLOR_BGR2RGB)  # decode_bgr applies EXIF orientation
    resized = tf.image.resize(rgb, size, antialias=True)
    return tf.cast(tf.clip_by_value(resized, 0, 255), tf.uint8).numpy()[np.newaxis, ...]


class GateUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class KerasGate:
    def __init__(self, models_dir: Path):
        import tensorflow as tf

        from .loader import sha256_file

        cfg = load_config()
        path = models_dir / cfg.model_file
        if not path.is_file():
            raise GateUnavailable("GATE_FILE_MISSING", "filter model file not found")
        digest = sha256_file(path)
        if digest != cfg.sha256:
            raise GateUnavailable("GATE_CHECKSUM_MISMATCH", "filter model checksum does not match")
        self.model = tf.keras.models.load_model(path, compile=False)
        if tuple(self.model.input_shape) != (None, *cfg.input_size, 3) or tuple(self.model.output_shape) != (None, 1):
            raise GateUnavailable("GATE_BAD_SHAPE", "unexpected filter model input/output shape")
        self.model_sha256 = digest
        self.threshold = cfg.threshold
        self.size = cfg.input_size

    def predict(self, image_bytes: bytes) -> float:
        batch = preprocess(image_bytes, self.size)
        return float(self.model(batch, training=False).numpy().ravel()[0])


class GateService:
    def __init__(self, model: GateModel | None = None, *, state: str | None = None):
        self.model = model
        self.state = state or ("ready" if model is not None else "unavailable")
        self.reason_code: str | None = None
        self._lock = threading.Lock()

    @classmethod
    def loading(cls) -> GateService:
        return cls(None, state="loading")

    def load(self, models_dir: Path) -> None:
        try:
            self.model = KerasGate(models_dir)
        except Exception as e:  # noqa: BLE001 - the filter is optional
            self.reason_code = getattr(e, "code", "GATE_LOAD_FAILED")
            self.state = "unavailable"
            logger.warning("image filter unavailable: %s (%s)", self.reason_code, e.__class__.__name__)
        else:
            self.state = "ready"
            logger.info("image filter ready")

    def check(self, image_bytes: bytes) -> GateResult | None:
        model = self.model
        if model is None:
            if self.state != "loading":
                logger.warning("image filter skipped: unavailable")
            return None
        try:
            with self._lock:
                score = model.predict(image_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning("image filter failed: %s", e.__class__.__name__)
            return None
        if not np.isfinite(score):
            logger.warning("image filter failed: non-finite score")
            return None
        return GateResult(score=score, passed=score >= model.threshold, model_sha256=model.model_sha256)


def from_settings(settings: Any) -> GateService:
    return GateService.loading() if settings.ai_enabled else GateService(None)
