from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import tensorflow as tf  # noqa: E402

from .constants import INPUT_SIZE, MODEL_FILE, MODEL_NAME, MODEL_SHA256, NUM_CLASSES  # noqa: E402,F401


@dataclass(frozen=True)
class ComponentSpec:
    name: str  # display/component name
    submodel: str  # nested model layer name inside the ensemble
    feature_layer: str  # last spatial feature map used for Grad-CAM
    logits_layer: str  # Dense(7) before Activation('softmax')


COMPONENTS: tuple[ComponentSpec, ...] = (
    ComponentSpec("AlexNet", "model_1", "activation_5", "dense_2"),
    ComponentSpec("ResNet", "model_3", "activation_29", "dense_1"),
    ComponentSpec("DenseNet", "model_4", "activation_91", "dense_2"),
)


class ModelUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_keras_model(path: Path) -> tf.keras.Model:
    return tf.keras.models.load_model(path, compile=False)


@dataclass
class LoadedEnsemble:
    model: tf.keras.Model
    sha256: str
    xai_models: dict[str, tf.keras.Model]


def load_ensemble(models_dir: Path, verify_sha: bool = True) -> LoadedEnsemble:
    path = models_dir / MODEL_FILE
    if not path.is_file():
        raise ModelUnavailable("MODEL_FILE_MISSING", "model file not found")
    digest = sha256_file(path)
    if verify_sha and digest != MODEL_SHA256:
        raise ModelUnavailable("MODEL_CHECKSUM_MISMATCH", "model checksum does not match the audited file")
    model = load_keras_model(path)
    if tuple(model.input_shape) != (None, INPUT_SIZE, INPUT_SIZE, 3) or tuple(model.output_shape) != (
        None,
        NUM_CLASSES,
    ):
        raise ModelUnavailable("MODEL_BAD_SHAPE", "unexpected model input/output shape")
    return LoadedEnsemble(model=model, sha256=digest, xai_models=build_xai_models(model))


def build_xai_models(ensemble: tf.keras.Model) -> dict[str, tf.keras.Model]:
    result = {}
    for spec in COMPONENTS:
        sub = ensemble.get_layer(spec.submodel)
        result[spec.name] = tf.keras.Model(
            inputs=sub.input,
            outputs=[sub.get_layer(spec.feature_layer).output, sub.get_layer(spec.logits_layer).output],
            name=f"xai_{spec.name.lower()}",
        )
    return result
