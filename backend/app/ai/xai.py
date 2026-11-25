from __future__ import annotations

import numpy as np
import tensorflow as tf

from .overlay import overlay_png, upsample
from .types import METHODS, CamResult, XaiError

__all__ = [
    "METHODS",
    "CamResult",
    "XaiError",
    "compute_cams",
    "feature_gradients",
    "gradcam_pp_weights",
    "gradcam_weights",
    "overlay_png",
    "upsample",
    "weighted_map",
]


def feature_gradients(xai_model: tf.keras.Model, x: np.ndarray, class_index: int) -> tuple[np.ndarray, np.ndarray]:
    x_t = tf.convert_to_tensor(x, dtype=tf.float32)
    with tf.GradientTape() as tape:
        feats, logits = xai_model(x_t, training=False)
        score = logits[:, class_index]
    grads = tape.gradient(score, feats)
    if grads is None:
        raise XaiError("XAI_NO_GRADIENT", "gradient path not available")
    return feats[0].numpy().astype(np.float64), grads[0].numpy().astype(np.float64)


def gradcam_weights(grads: np.ndarray) -> np.ndarray:
    return grads.mean(axis=(0, 1))


def gradcam_pp_weights(feats: np.ndarray, grads: np.ndarray) -> np.ndarray:
    g2, g3 = grads**2, grads**3
    sum_a = feats.sum(axis=(0, 1), keepdims=True)
    denom = 2.0 * g2 + sum_a * g3
    alphas = g2 / np.where(denom != 0.0, denom, 1.0)
    return (alphas * np.maximum(grads, 0.0)).sum(axis=(0, 1))


def weighted_map(feats: np.ndarray, weights: np.ndarray) -> np.ndarray:
    cam = np.maximum((feats * weights).sum(axis=-1), 0.0)
    if not np.all(np.isfinite(cam)):
        raise XaiError("XAI_NAN", "non-finite values in saliency map")
    peak = cam.max()
    if peak <= 0.0:
        raise XaiError("XAI_ZERO_GRADIENT", "saliency map is identically zero")
    return (cam / peak).astype(np.float32)


def compute_cams(
    xai_model: tf.keras.Model, component: str, layer_name: str, x: np.ndarray, class_index: int
) -> dict[str, CamResult | XaiError]:
    out: dict[str, CamResult | XaiError] = {}
    try:
        feats, grads = feature_gradients(xai_model, x, class_index)
        if not np.all(np.isfinite(grads)):
            raise XaiError("XAI_NAN", "non-finite gradients")
        if not np.any(grads):
            raise XaiError("XAI_ZERO_GRADIENT", "gradients are identically zero")
    except XaiError as e:
        return {m: e for m in METHODS}
    for method, w in (
        ("gradcam", lambda: gradcam_weights(grads)),
        ("gradcam_pp", lambda: gradcam_pp_weights(feats, grads)),
    ):
        try:
            out[method] = CamResult(method, component, layer_name, weighted_map(feats, w()))
        except XaiError as e:
            out[method] = e
    return out
