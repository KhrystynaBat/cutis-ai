from __future__ import annotations

import numpy as np

from .constants import CLASS_CODES, NUM_CLASSES
from .loader import COMPONENTS, LoadedEnsemble
from .preprocessing import NormalizationParams, preprocess_bytes
from .types import AnalysisOutput, InferenceError, Prediction
from .xai import compute_cams

__all__ = ["AnalysisOutput", "InferenceError", "Prediction", "analyze", "predict_tensor"]


def predict_tensor(ens: LoadedEnsemble, x: np.ndarray) -> Prediction:
    probs = ens.model(x, training=False).numpy()
    if probs.shape != (1, NUM_CLASSES):
        raise InferenceError("AI_BAD_OUTPUT", "unexpected output shape")
    if not np.all(np.isfinite(probs)):
        raise InferenceError("AI_NAN", "non-finite model output")
    if abs(float(probs.sum()) - 1.0) > 1e-3:
        raise InferenceError("AI_BAD_OUTPUT", "output is not a probability distribution")
    p = probs[0]
    idx = int(p.argmax())
    return Prediction(idx, CLASS_CODES[idx], float(p[idx]), {c: float(v) for c, v in zip(CLASS_CODES, p, strict=True)})


def analyze(
    ens: LoadedEnsemble, image_bytes: bytes, params: NormalizationParams | None = None, with_xai: bool = True
) -> AnalysisOutput:
    x, image_rgb = preprocess_bytes(image_bytes, params)
    out = AnalysisOutput(prediction=predict_tensor(ens, x), image_rgb=image_rgb)
    if with_xai:
        for spec in COMPONENTS:
            cams = compute_cams(ens.xai_models[spec.name], spec.name, spec.feature_layer, x, out.prediction.class_index)
            for method, res in cams.items():
                out.cams[(spec.name, method)] = res
    return out
