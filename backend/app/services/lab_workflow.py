from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import local_date, today_local
from app.core.errors import ApiError
from app.core.names import full_name
from app.db.models import Case, LabResult, Notification, Patient, Referral, ReferralStatus, Role, User
from app.email import outbox
from app.services import audit

NOTIFICATION_LAB_RESULT_READY = "lab_result_ready"

FIELDS = ("lab_accession_number", "histopathology_diagnosis", "histopathology_description", "examined_at", "comment")
REQUIRED = {
    "lab_accession_number": "номер лабораторного дослідження",
    "histopathology_diagnosis": "гістопатологічний висновок",
    "histopathology_description": "опис",
    "examined_at": "дата дослідження",
}


@dataclass
class LabInput:
    lab_accession_number: str | None = None
    histopathology_diagnosis: str | None = None
    histopathology_description: str | None = None
    examined_at: date | None = None
    comment: str | None = None


@dataclass
class Approval:
    result: LabResult
    created: bool


def lab_result_of(db: Session, referral_id: uuid.UUID) -> LabResult | None:
    return db.scalar(select(LabResult).where(LabResult.referral_id == referral_id))


def _completed() -> ApiError:
    return ApiError(409, "RESULT_APPROVED", "Результат уже затверджено: редагування заборонене")


def _name(u: User) -> str:
    return full_name(u)


def _assigned_to_other(db: Session, ref: Referral) -> ApiError:
    other = db.get(User, ref.assigned_lab_specialist_id)
    who = _name(other) if other else "—"
    return ApiError(409, "REFERRAL_ASSIGNED_TO_OTHER", f"Направлення опрацьовує інший лаборант: {who}")


def _require_assignee(db: Session, ref: Referral, user: User) -> None:
    if ref.status == ReferralStatus.COMPLETED:
        raise _completed()
    if ref.status == ReferralStatus.SENT:
        raise ApiError(409, "REFERRAL_NOT_STARTED", "Спершу візьміть направлення в роботу («Почати опрацювання»)")
    if ref.assigned_lab_specialist_id != user.id:
        raise _assigned_to_other(db, ref)


def _assign(ref: Referral, user_id: uuid.UUID) -> None:
    ref.assigned_lab_specialist_id = user_id
    ref.assigned_at = datetime.now(UTC)


def start(db: Session, ref: Referral, user: User) -> None:
    if ref.status == ReferralStatus.COMPLETED:
        raise ApiError(409, "REFERRAL_COMPLETED", "Направлення вже завершено")
    if ref.status == ReferralStatus.IN_PROGRESS:
        if ref.assigned_lab_specialist_id == user.id:
            return  # repeated click: already mine, nothing to do
        raise _assigned_to_other(db, ref)
    ref.status = ReferralStatus.IN_PROGRESS
    ref.started_at = datetime.now(UTC)
    _assign(ref, user.id)
    audit.record(db, "referral_started", "referral", ref.id, actor_id=user.id)


def active_lab_specialists(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == Role.LAB_SPECIALIST, User.is_active.is_(True), User.deactivated_at.is_(None))
            .order_by(User.last_name, User.first_name)
        )
    )


def reassign(db: Session, ref: Referral, user: User, target_id: uuid.UUID) -> None:
    _require_assignee(db, ref, user)
    if target_id == user.id:
        raise ApiError(422, "REASSIGN_TO_SELF", "Оберіть іншого лаборанта")
    target = db.get(User, target_id)
    if target is None or target.role != Role.LAB_SPECIALIST or not target.is_active or target.deactivated_at:
        raise ApiError(422, "LAB_SPECIALIST_UNAVAILABLE", "Цей лаборант недоступний (заблокований чи деактивований)")
    _assign(ref, target.id)
    audit.record(
        db,
        "referral_reassigned",
        "referral",
        ref.id,
        actor_id=user.id,
        metadata={"from": str(user.id), "to": str(target.id)},
    )


def _back_to_queue(ref: Referral) -> None:
    ref.status = ReferralStatus.SENT
    ref.started_at = None
    ref.assigned_lab_specialist_id = None
    ref.assigned_at = None


def release(db: Session, ref: Referral, user: User) -> None:
    _require_assignee(db, ref, user)
    _back_to_queue(ref)
    audit.record(db, "referral_released", "referral", ref.id, actor_id=user.id, metadata={"reason": "declined"})


def release_all_of(db: Session, lab_user_id: uuid.UUID, actor_id: uuid.UUID | None, reason: str) -> int:
    refs = db.scalars(
        select(Referral)
        .where(Referral.assigned_lab_specialist_id == lab_user_id, Referral.status == ReferralStatus.IN_PROGRESS)
        .with_for_update()
    ).all()
    for ref in refs:
        _back_to_queue(ref)
        audit.record(db, "referral_released", "referral", ref.id, actor_id=actor_id, metadata={"reason": reason})
    return len(refs)


def _check_dates(ref: Referral, examined_at: date | None) -> None:
    if examined_at is None:
        return
    if examined_at > today_local():
        raise ApiError(422, "EXAMINED_AT_FUTURE", "Дата дослідження не може бути в майбутньому")
    if examined_at < local_date(ref.created_at):
        raise ApiError(422, "EXAMINED_AT_BEFORE_REFERRAL", "Дата дослідження не може бути раніше дати направлення")


def _check_accession(db: Session, ref: Referral, number: str | None) -> None:
    if number is None:
        return
    taken = db.scalar(
        select(LabResult.id).where(LabResult.lab_accession_number == number, LabResult.referral_id != ref.id)
    )
    if taken:
        raise ApiError(409, "ACCESSION_EXISTS", "Такий номер лабораторного дослідження вже використано")


def _apply(db: Session, ref: Referral, user: User, data: LabInput) -> tuple[LabResult, list[str]]:
    _check_dates(ref, data.examined_at)
    _check_accession(db, ref, data.lab_accession_number)
    result = lab_result_of(db, ref.id)
    if result is None:
        result = LabResult(referral_id=ref.id, lab_specialist_id=user.id)
        db.add(result)
    changed = [f for f in FIELDS if getattr(result, f) != getattr(data, f)]
    for f in changed:
        setattr(result, f, getattr(data, f))
    result.lab_specialist_id = user.id
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "ACCESSION_EXISTS", "Такий номер лабораторного дослідження вже використано") from None
    return result, changed


def save_draft(db: Session, ref: Referral, user: User, data: LabInput) -> LabResult:
    _require_assignee(db, ref, user)
    result, changed = _apply(db, ref, user, data)
    if changed:
        audit.record(db, "lab_result_draft_saved", "referral", ref.id, actor_id=user.id, metadata={"fields": changed})
    return result


def _same(result: LabResult, data: LabInput) -> bool:
    return all(getattr(result, f) == getattr(data, f) for f in FIELDS)


def approve(db: Session, ref: Referral, user: User, data: LabInput | None) -> Approval:
    if ref.status != ReferralStatus.SENT and ref.assigned_lab_specialist_id != user.id:
        raise _assigned_to_other(db, ref)
    if ref.status == ReferralStatus.COMPLETED:
        result = lab_result_of(db, ref.id)
        if data is None or _same(result, data):
            return Approval(result, created=False)  # idempotent repeat: no new records
        raise _completed()

    if data is not None:
        result, _ = _apply(db, ref, user, data)
    else:
        result = lab_result_of(db, ref.id)
        if result is None:
            result = LabResult(referral_id=ref.id, lab_specialist_id=user.id)
            db.add(result)
    missing = [label for f, label in REQUIRED.items() if getattr(result, f) is None]
    if missing:
        raise ApiError(422, "LAB_RESULT_INCOMPLETE", "Для затвердження заповніть: " + ", ".join(missing))
    _check_dates(ref, result.examined_at)

    now = datetime.now(UTC)
    result.is_approved = True
    result.approved_at = now
    result.lab_specialist_id = user.id
    previous = ref.status
    if previous == ReferralStatus.SENT:
        _assign(ref, user.id)
    ref.status = ReferralStatus.COMPLETED
    ref.completed_at = now

    case = db.get(Case, ref.case_id)
    patient = db.get(Patient, case.patient_id)
    notified = _notify_doctor(db, ref)
    emailed = outbox.queue_lab_result_ready(db, ref, patient)
    audit.record(
        db,
        "lab_result_approved",
        "referral",
        ref.id,
        actor_id=user.id,
        metadata={"from": previous.value, "notificationCreated": notified, "emailQueued": emailed},
    )
    db.flush()
    return Approval(result, created=True)


def _notify_doctor(db: Session, ref: Referral) -> bool:
    stmt = (
        insert(Notification)
        .values(
            id=uuid.uuid4(),
            user_id=ref.doctor_id,
            type=NOTIFICATION_LAB_RESULT_READY,
            title="Готовий результат лабораторії",
            message=f"Затверджено результат гістопатологічного дослідження за направленням {ref.referral_number}.",
            referral_id=ref.id,
            is_read=False,
        )
        .on_conflict_do_nothing(constraint="uq_notifications_user_type_referral")
        .returning(Notification.id)
    )
    return db.execute(stmt).scalar() is not None  # None: it already existed


def unread_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.is_read.is_(False))) or 0
