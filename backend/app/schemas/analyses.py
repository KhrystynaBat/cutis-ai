from __future__ import annotations

import uuid
from datetime import datetime

from app.db.models import AnalysisStatus, XaiMethod, XaiStatus

from .common import ApiModel


class ClassLabel(ApiModel):
    code: str
    label_uk: str


class ClassScore(ClassLabel):
    score: float


class XaiArtifactOut(ApiModel):
    id: uuid.UUID
    method: XaiMethod
    component: str
    layer_name: str
    grid_size: int | None
    status: XaiStatus
    error_code: str | None
    reason: str | None  # why the map is unavailable, user-facing
    url: str | None


class AnalysisOut(ApiModel):
    id: uuid.UUID
    case_id: uuid.UUID
    image_id: uuid.UUID
    status: AnalysisStatus
    model: str
    model_version: str | None  # short SHA-256 of the audited weights file
    preprocessing_version: str
    predicted_class: ClassLabel | None
    score: float | None
    scores: list[ClassScore]  # all 7 classes, highest first
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    xai: list[XaiArtifactOut]
    image_gate_overridden: bool = False


class AiStatusOut(ApiModel):
    status: str  # ready | loading | unavailable
    code: str | None
    message: str
    model: str
    model_version: str | None
    preprocessing_version: str
    components: list[str]
    xai_methods: list[str]
    max_concurrent_analyses: int
    pending_analyses: int
    gate_status: str = "unavailable"  # image filter: ready | loading | unavailable


class AiResultRef(ApiModel):
    code: str
    label_uk: str
    score: float
