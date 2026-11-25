from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .constants import MODEL_NAME
from .preprocessing import PREPROCESSING_VERSION

METHODS = ("gradcam", "gradcam_pp")


class XaiError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class InferenceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class CamResult:
    method: str
    component: str
    layer_name: str
    cam: np.ndarray


@dataclass
class Prediction:
    class_index: int
    class_code: str
    score: float
    scores: dict[str, float]
    model_name: str = MODEL_NAME
    preprocessing_version: str = PREPROCESSING_VERSION


@dataclass
class AnalysisOutput:
    prediction: Prediction
    image_rgb: np.ndarray
    cams: dict[tuple[str, str], CamResult | XaiError] = field(default_factory=dict)  # (component, method)
