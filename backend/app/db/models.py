from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAt, Timestamps, UUIDPk


class Role(enum.StrEnum):
    ADMIN = "Admin"
    DOCTOR = "Doctor"
    LAB_SPECIALIST = "LabSpecialist"


class CaseStatus(enum.StrEnum):
    OPEN = "Open"
    FOLLOW_UP_PLANNED = "FollowUpPlanned"
    REFERRED = "Referred"
    CLOSED = "Closed"


class CaseDecision(enum.StrEnum):
    CLOSE = "Close"
    FOLLOW_UP = "FollowUp"
    REFER = "Refer"


class AnalysisStatus(enum.StrEnum):
    QUEUED = "Queued"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


class XaiMethod(enum.StrEnum):
    GRADCAM = "gradcam"
    GRADCAM_PP = "gradcam_pp"


class XaiStatus(enum.StrEnum):
    COMPLETED = "Completed"
    FAILED = "Failed"


class ReferralStatus(enum.StrEnum):
    SENT = "Sent"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"


class EmailStatus(enum.StrEnum):
    PENDING = "Pending"
    LOGGED = "Logged"
    SENT = "Sent"
    FAILED = "Failed"


class TokenPurpose(enum.StrEnum):
    INVITATION = "Invitation"
    PASSWORD_RESET = "PasswordReset"  # noqa: S105 (enum label, not a secret)


class Sex(enum.StrEnum):
    FEMALE = "Female"
    MALE = "Male"


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


def _fk(target: str, **kw: Any) -> Any:
    return ForeignKey(target, ondelete="RESTRICT", **kw)


UUIDType = UUID(as_uuid=True)
TZ = DateTime(timezone=True)


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role = 'Admin' OR (first_name IS NOT NULL AND last_name IS NOT NULL)", name="staff_has_name"),
    )

    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))  # по батькові
    phone: Mapped[str | None] = mapped_column(String(32))
    birth_date: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[Sex | None] = mapped_column(_enum(Sex, "sex"))
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    password_hash: Mapped[str | None] = mapped_column(String(255))  # null until invitation accepted
    role: Mapped[Role] = mapped_column(_enum(Role, "role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    deactivated_at: Mapped[datetime | None] = mapped_column(TZ)
    last_login_at: Mapped[datetime | None] = mapped_column(TZ)


class Patient(UUIDPk, Timestamps, Base):
    __tablename__ = "patients"

    doctor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))  # по батькові
    date_of_birth: Mapped[date] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Case(UUIDPk, Timestamps, Base):
    __tablename__ = "cases"
    __table_args__ = (
        # a planned follow-up always has a date
        CheckConstraint("status <> 'FollowUpPlanned' OR follow_up_date IS NOT NULL", name="follow_up_has_date"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("patients.id"), index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    examined_at: Mapped[date] = mapped_column(Date)
    body_location: Mapped[str] = mapped_column(String(200))
    clinical_description: Mapped[str] = mapped_column(Text)
    doctor_assessment: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[CaseDecision | None] = mapped_column(_enum(CaseDecision, "case_decision"))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    follow_up_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CaseStatus] = mapped_column(
        _enum(CaseStatus, "case_status"), default=CaseStatus.OPEN, server_default=CaseStatus.OPEN.value, index=True
    )


class CaseImage(UUIDPk, Base):
    __tablename__ = "case_images"

    case_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("cases.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    gate_score: Mapped[float | None] = mapped_column(Float)
    gate_passed: Mapped[bool | None] = mapped_column(Boolean)
    gate_model_sha256: Mapped[str | None] = mapped_column(String(64))
    gate_confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("users.id"))
    gate_confirmed_at: Mapped[datetime | None] = mapped_column(TZ)


class AiAnalysis(UUIDPk, CreatedAt, Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index(
            "uq_ai_analyses_one_active_per_case",
            "case_id",
            unique=True,
            postgresql_where=text("status IN ('Queued', 'Running')"),
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("cases.id"), index=True)
    image_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("case_images.id"))
    status: Mapped[AnalysisStatus] = mapped_column(_enum(AnalysisStatus, "analysis_status"))
    model_name: Mapped[str] = mapped_column(String(64))
    model_sha256: Mapped[str | None] = mapped_column(String(64))
    preprocessing_version: Mapped[str] = mapped_column(String(64))
    predicted_class_code: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(Float)
    scores_json: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message_safe: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    completed_at: Mapped[datetime | None] = mapped_column(TZ)


class XaiArtifact(UUIDPk, CreatedAt, Base):
    __tablename__ = "xai_artifacts"
    __table_args__ = (UniqueConstraint("analysis_id", "method", "component_name", name="uq_xai_artifacts_map"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("ai_analyses.id"), index=True)
    method: Mapped[XaiMethod] = mapped_column(_enum(XaiMethod, "xai_method"))
    component_name: Mapped[str] = mapped_column(String(32))
    layer_name: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(255))  # null when Failed: no picture
    status: Mapped[XaiStatus] = mapped_column(_enum(XaiStatus, "xai_status"))
    error_code: Mapped[str | None] = mapped_column(String(64))


class Referral(UUIDPk, CreatedAt, Base):
    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint("status <> 'Completed' OR completed_at IS NOT NULL", name="completed_has_date"),
        CheckConstraint("(status = 'Sent') = (assigned_lab_specialist_id IS NULL)", name="assignment_matches_status"),
        CheckConstraint("(assigned_lab_specialist_id IS NULL) = (assigned_at IS NULL)", name="assignment_has_time"),
        Index(
            "uq_referrals_one_active_per_case",
            "case_id",
            unique=True,
            postgresql_where=text("status IN ('Sent', 'InProgress')"),
        ),
    )

    referral_number: Mapped[str] = mapped_column(String(32), unique=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("cases.id"), index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("ai_analyses.id"))
    status: Mapped[ReferralStatus] = mapped_column(
        _enum(ReferralStatus, "referral_status"), default=ReferralStatus.SENT, index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    assigned_lab_specialist_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("users.id"), index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(TZ)
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    completed_at: Mapped[datetime | None] = mapped_column(TZ)


class LabResult(UUIDPk, Timestamps, Base):
    __tablename__ = "lab_results"
    __table_args__ = (
        CheckConstraint(
            "NOT is_approved OR (lab_accession_number IS NOT NULL AND histopathology_diagnosis IS NOT NULL"
            " AND histopathology_description IS NOT NULL AND examined_at IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_is_complete",
        ),
    )

    referral_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("referrals.id"), unique=True)
    lab_specialist_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"))
    lab_accession_number: Mapped[str | None] = mapped_column(String(64), unique=True)
    histopathology_diagnosis: Mapped[str | None] = mapped_column(Text)
    histopathology_description: Mapped[str | None] = mapped_column(Text)
    examined_at: Mapped[date | None] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(Text)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    approved_at: Mapped[datetime | None] = mapped_column(TZ)
    pdf_storage_key: Mapped[str | None] = mapped_column(String(255))


class Notification(UUIDPk, CreatedAt, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "referral_id", name="uq_notifications_user_type_referral"),
        Index("ix_notifications_user_unread", "user_id", postgresql_where=text("NOT is_read")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    referral_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("referrals.id"))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    read_at: Mapped[datetime | None] = mapped_column(TZ)


class EmailOutbox(UUIDPk, CreatedAt, Base):
    __tablename__ = "email_outbox"
    __table_args__ = (UniqueConstraint("referral_id", "template_key", name="uq_email_outbox_referral_template"),)

    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("patients.id"))
    referral_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("referrals.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_email: Mapped[str] = mapped_column(String(254))
    template_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[EmailStatus] = mapped_column(_enum(EmailStatus, "email_status"), default=EmailStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error_safe: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(TZ)


class AuditEvent(UUIDPk, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, _fk("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class UserToken(UUIDPk, CreatedAt, Base):
    __tablename__ = "user_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    purpose: Mapped[TokenPurpose] = mapped_column(_enum(TokenPurpose, "token_purpose"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    used_at: Mapped[datetime | None] = mapped_column(TZ)


class UserSession(UUIDPk, CreatedAt, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, _fk("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    last_seen_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(TZ)


class LoginChallenge(UUIDPk, CreatedAt, Base):
    __tablename__ = "login_challenges"

    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_nonce_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    used_at: Mapped[datetime | None] = mapped_column(TZ)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class EmailChangeRequest(UUIDPk, CreatedAt, Base):
    __tablename__ = "email_change_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    new_email: Mapped[str] = mapped_column(String(254))  # lower-case
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    confirmed_at: Mapped[datetime | None] = mapped_column(TZ)
    cancelled_at: Mapped[datetime | None] = mapped_column(TZ)
