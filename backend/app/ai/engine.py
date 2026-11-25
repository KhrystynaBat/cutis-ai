from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .constants import MODEL_NAME
from .inference import analyze
from .loader import load_ensemble
from .preprocessing import PREPROCESSING_VERSION, load_params
from .types import AnalysisOutput


class EnsembleEngine:
    def __init__(self, models_dir: Path):
        self.params = load_params()
        self.ensemble = load_ensemble(models_dir)
        self.model_name = MODEL_NAME
        self.model_sha256 = self.ensemble.sha256
        self.preprocessing_version = PREPROCESSING_VERSION

    def analyze(self, image_bytes: bytes) -> AnalysisOutput:
        return analyze(self.ensemble, image_bytes, self.params)

    def warmup(self) -> None:
        img = np.random.default_rng(0).integers(0, 256, (128, 128, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".png", img)
        if ok:
            self.analyze(buf.tobytes())
