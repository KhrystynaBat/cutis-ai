from __future__ import annotations

import uuid
from datetime import datetime

from app.db.models import AnalysisStatus, ExplanationStatus, XaiMethod, XaiStatus

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


class ExplanationClassification(ApiModel):
    result: str
    heatmaps: str


class ExplanationFeature(ApiModel):
    label: str
    value: str


class ExplanationDescription(ApiModel):
    intro: str
    features: list[ExplanationFeature]


class ExplanationAssessment(ApiModel):
    intro: str
    differential: list[str]


class ExplanationOut(ApiModel):
    status: ExplanationStatus
    error_code: str | None = None
    error_message: str | None = None
    model: str | None = None
    classification: ExplanationClassification | None = None
    discrepancy: str | None = None  # empty when the photo matches the class
    description: ExplanationDescription | None = None
    assessment: ExplanationAssessment | None = None
    recommendations: str | None = None
    conclusion: str | None = None


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
    explanation: ExplanationOut | None = None  # doctor-only views


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
