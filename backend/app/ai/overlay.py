from __future__ import annotations

import cv2
import numpy as np

from .types import XaiError


def upsample(cam: np.ndarray, width: int, height: int) -> np.ndarray:
    return np.clip(cv2.resize(cam, (width, height), interpolation=cv2.INTER_LINEAR), 0.0, 1.0)


def fit_display(image_rgb: np.ndarray, max_side: int) -> np.ndarray:
    h, w = image_rgb.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1.0:
        return image_rgb
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return cv2.resize(image_rgb, size, interpolation=cv2.INTER_AREA)


def overlay_png(image_rgb: np.ndarray, cam: np.ndarray, alpha: float = 0.45) -> bytes:
    h, w = image_rgb.shape[:2]
    heat = cv2.applyColorMap((upsample(cam, w, h) * 255).astype(np.uint8), cv2.COLORMAP_JET)  # BGR
    base_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    blended = cv2.addWeighted(heat, alpha, base_bgr, 1.0 - alpha, 0.0)
    ok, buf = cv2.imencode(".png", blended)
    if not ok:
        raise XaiError("XAI_ENCODE", "cannot encode overlay")
    return buf.tobytes()
