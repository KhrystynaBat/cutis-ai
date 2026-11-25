from pathlib import Path

import numpy as np
import pytest
import tensorflow as tf

from app.ai.xai import (
    CamResult,
    XaiError,
    compute_cams,
    gradcam_pp_weights,
    gradcam_weights,
    overlay_png,
    upsample,
    weighted_map,
)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def _toy_model(zero_dense: bool = False) -> tf.keras.Model:
    tf.keras.utils.set_random_seed(1)
    inp = tf.keras.Input((16, 16, 3))
    feats = tf.keras.layers.Conv2D(4, 3, padding="same", activation="relu", name="feats")(inp)
    pooled = tf.keras.layers.GlobalAveragePooling2D()(feats)
    dense = tf.keras.layers.Dense(3, name="logits", kernel_initializer="zeros" if zero_dense else "glorot_uniform")
    logits = dense(pooled)
    return tf.keras.Model(inp, [feats, logits])


def test_gradcam_weights_are_spatial_mean():
    g = np.arange(2 * 2 * 3, dtype=np.float64).reshape(2, 2, 3)
    assert np.allclose(gradcam_weights(g), g.mean(axis=(0, 1)))


def test_gradcam_pp_linear_head_equals_positive_gradcam_direction():
    feats = np.random.default_rng(0).random((3, 3, 2))
    grads = np.stack([np.full((3, 3), 0.5), np.full((3, 3), -0.5)], axis=-1)
    w = gradcam_pp_weights(feats, grads)
    assert w[0] > 0 and w[1] == 0


def test_zero_denominator_is_stabilised():
    w = gradcam_pp_weights(np.zeros((2, 2, 1)), np.zeros((2, 2, 1)))
    assert np.all(np.isfinite(w)) and np.all(w == 0)


def test_weighted_map_normalised_and_errors():
    cam = weighted_map(np.ones((2, 2, 1)) * np.array([[[1.0], [2.0]], [[3.0], [4.0]]]), np.array([1.0]))
    assert cam.max() == 1.0 and cam.min() >= 0
    with pytest.raises(XaiError) as e:
        weighted_map(np.ones((2, 2, 1)), np.array([-1.0]))
    assert e.value.code == "XAI_ZERO_GRADIENT"
    with pytest.raises(XaiError) as e:
        weighted_map(np.full((2, 2, 1), np.nan), np.array([1.0]))
    assert e.value.code == "XAI_NAN"


def test_compute_cams_toy_model_deterministic():
    m = _toy_model()
    x = np.random.default_rng(3).standard_normal((1, 16, 16, 3)).astype(np.float32)
    a, b = compute_cams(m, "toy", "feats", x, 1), compute_cams(m, "toy", "feats", x, 1)
    for method in ("gradcam", "gradcam_pp"):
        assert isinstance(a[method], CamResult)
        assert a[method].cam.shape == (16, 16)
        assert np.array_equal(a[method].cam, b[method].cam)


def test_compute_cams_zero_gradient_reports_code():
    res = compute_cams(_toy_model(zero_dense=True), "toy", "feats", np.ones((1, 16, 16, 3), np.float32), 0)
    assert all(isinstance(r, XaiError) and r.code == "XAI_ZERO_GRADIENT" for r in res.values())


def test_upsample_geometry_no_shift():
    cam = np.zeros((4, 4), np.float32)
    cam[0, 0] = 1.0  # top-left cell
    up = upsample(cam, 400, 200)
    assert up.shape == (200, 400)
    ys, xs = np.unravel_index(up.argmax(), up.shape)
    assert ys < 50 and xs < 100  # stays in the top-left quarter-cell region
    assert up[150:, 300:].max() == 0


def test_overlay_png_roundtrip():
    import cv2

    png = overlay_png(np.zeros((50, 70, 3), np.uint8), np.ones((4, 4), np.float32))
    assert cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR).shape == (50, 70, 3)


@pytest.mark.skipif(not (MODELS_DIR / "ensemble_best.h5").is_file(), reason="model weights not available")
def test_real_components_produce_nonzero_maps():
    from app.ai.loader import COMPONENTS, load_ensemble

    ens = load_ensemble(MODELS_DIR)
    x = np.random.default_rng(0).standard_normal((1, 128, 128, 3)).astype(np.float32)
    cls = int(ens.model(x, training=False).numpy().argmax())
    expected_res = {"AlexNet": (8, 8), "ResNet": (5, 5), "DenseNet": (4, 4)}
    for spec in COMPONENTS:
        res = compute_cams(ens.xai_models[spec.name], spec.name, spec.feature_layer, x, cls)
        for r in res.values():
            assert isinstance(r, CamResult), r
            assert r.cam.shape == expected_res[spec.name] and r.cam.max() == 1.0
