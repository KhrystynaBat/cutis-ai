from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import Field, field_validator

from app.db.models import CaseStatus, ReferralStatus

from .analyses import AnalysisOut
from .cases import CaseImageOut
from .common import ApiModel
from .patients import PatientRef


class PersonRef(ApiModel):
    id: uuid.UUID
    first_name: str | None
    last_name: str | None
    middle_name: str | None = None
    phone: str | None = None  # the referring doctor's phone for the lab


class ReferralSummary(ApiModel):
    id: uuid.UUID
    referral_number: str
    status: ReferralStatus
    created_at: datetime
    patient: PatientRef
    doctor: PersonRef
    assignee: PersonRef | None
    case_id: uuid.UUID
    body_location: str
    lab_accession_number: str | None


class ReferralCase(ApiModel):
    id: uuid.UUID
    status: CaseStatus
    examined_at: date
    body_location: str
    clinical_description: str
    doctor_assessment: str | None
    image: CaseImageOut | None


class ReferralOut(ApiModel):
    id: uuid.UUID
    referral_number: str
    status: ReferralStatus
    reason: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    patient: PatientRef
    case: ReferralCase
    doctor: PersonRef
    assignee: PersonRef | None
    assigned_at: datetime | None
    analysis: AnalysisOut | None
    analysis_image_url: str | None
    lab_accession_number: str | None
    lab_result: LabResultOut | None


_ACCESSION = re.compile(r"^[\w][\w\-/.]*$")


def _blank_to_none(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


class LabResultIn(ApiModel):
    lab_accession_number: str | None = Field(default=None, max_length=64)
    histopathology_diagnosis: str | None = Field(default=None, max_length=2000)
    histopathology_description: str | None = Field(default=None, max_length=10000)
    examined_at: date | None = None
    comment: str | None = Field(default=None, max_length=2000)

    _blank = field_validator(
        "lab_accession_number", "histopathology_diagnosis", "histopathology_description", "comment", mode="before"
    )(_blank_to_none)

    @field_validator("lab_accession_number")
    @classmethod
    def _accession(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _ACCESSION.match(v):
            raise ValueError("Номер дослідження: лише літери, цифри та символи - / . без пробілів")
        return v.upper()


class LabResultOut(ApiModel):
    id: uuid.UUID
    lab_accession_number: str | None
    histopathology_diagnosis: str | None
    histopathology_description: str | None
    examined_at: date | None
    comment: str | None
    is_approved: bool
    approved_at: datetime | None
    lab_specialist: PersonRef
    updated_at: datetime
    pdf_url: str | None  # only for an approved result


class ReassignIn(ApiModel):
    lab_specialist_id: uuid.UUID


class NotificationReferral(ApiModel):
    id: uuid.UUID
    referral_number: str
    case_id: uuid.UUID


class NotificationOut(ApiModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
    read_at: datetime | None
    referral: NotificationReferral | None


class UnreadCount(ApiModel):
    unread: int


ReferralOut.model_rebuild()
