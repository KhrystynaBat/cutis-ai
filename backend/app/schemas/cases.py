from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field, field_validator

from app.core.clock import today_local
from app.db.models import CaseDecision, CaseStatus, ReferralStatus

from .analyses import AiResultRef
from .common import ApiModel
from .patients import PatientRef


def _required_text(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Поле не може бути порожнім")
    return v


def _not_future(v: date) -> date:
    if v > today_local():
        raise ValueError("Дата огляду не може бути в майбутньому")
    return v


class CaseCreate(ApiModel):
    patient_id: uuid.UUID
    examined_at: date
    body_location: str = Field(min_length=1, max_length=200)
    clinical_description: str = Field(min_length=1, max_length=5000)

    _text = field_validator("body_location", "clinical_description")(_required_text)
    _date = field_validator("examined_at")(_not_future)


class CaseUpdate(ApiModel):
    examined_at: date | None = None
    body_location: str | None = Field(default=None, min_length=1, max_length=200)
    clinical_description: str | None = Field(default=None, min_length=1, max_length=5000)

    @field_validator("body_location", "clinical_description")
    @classmethod
    def _text(cls, v: str | None) -> str | None:
        return None if v is None else _required_text(v)

    @field_validator("examined_at")
    @classmethod
    def _date(cls, v: date | None) -> date | None:
        return None if v is None else _not_future(v)


class CaseImageOut(ApiModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    byte_size: int
    uploaded_at: datetime
    url: str
    gate_overridden: bool = False


class ImageCheckOut(ApiModel):
    passed: bool
    score: float | None


class ReferralRef(ApiModel):
    id: uuid.UUID
    referral_number: str
    status: ReferralStatus
    created_at: datetime


class ReferralBrief(ReferralRef):
    reason: str
    analysis_id: uuid.UUID | None


class CaseSummary(ApiModel):
    id: uuid.UUID
    patient: PatientRef
    examined_at: date
    body_location: str
    status: CaseStatus
    has_image: bool
    ai_result: AiResultRef | None = None  # latest completed analysis
    referral: ReferralRef | None = None  # latest referral
    created_at: datetime


class CaseOut(CaseSummary):
    clinical_description: str
    doctor_assessment: str | None
    follow_up_date: date | None
    follow_up_note: str | None
    updated_at: datetime
    image: CaseImageOut | None
    is_editable: bool
    decision: CaseDecision | None
    referral: ReferralBrief | None = None
    available_actions: list[str]


class AssessmentUpdate(ApiModel):
    doctor_assessment: str | None = Field(default=None, max_length=5000)
    decision: CaseDecision | None = None
    follow_up_date: date | None = None
    follow_up_note: str | None = Field(default=None, max_length=2000)
    referral_reason: str | None = Field(default=None, max_length=2000)


class DashboardOut(ApiModel):
    patients: int
    active_cases: int
    pending_referrals: int
    ready_results: int
    recent_cases: list[CaseSummary]
