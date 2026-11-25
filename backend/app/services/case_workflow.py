from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import ApiError
from app.db.models import (
    AiAnalysis,
    AnalysisStatus,
    Case,
    CaseDecision,
    CaseStatus,
    Referral,
    ReferralStatus,
    User,
)
from app.services import audit

OPEN, FOLLOW_UP, REFERRED, CLOSED = (
    CaseStatus.OPEN,
    CaseStatus.FOLLOW_UP_PLANNED,
    CaseStatus.REFERRED,
    CaseStatus.CLOSED,
)

ALLOWED: frozenset[tuple[CaseStatus, CaseStatus]] = frozenset(
    {
        (OPEN, FOLLOW_UP),
        (OPEN, REFERRED),
        (OPEN, CLOSED),
        (FOLLOW_UP, OPEN),
        (FOLLOW_UP, CLOSED),
        (FOLLOW_UP, REFERRED),
        (REFERRED, CLOSED),
    }
)

DECISION_TARGET = {
    CaseDecision.CLOSE: CLOSED,
    CaseDecision.FOLLOW_UP: FOLLOW_UP,
    CaseDecision.REFER: REFERRED,
}

STATUS_UK = {OPEN: "Відкритий", FOLLOW_UP: "Заплановано контроль", REFERRED: "Направлено", CLOSED: "Закритий"}

MAX_FOLLOW_UP_DAYS = 730


def latest_referral(db: Session, case_id) -> Referral | None:
    return db.scalar(select(Referral).where(Referral.case_id == case_id).order_by(Referral.created_at.desc()).limit(1))


def current_analysis(db: Session, case_id) -> AiAnalysis | None:
    return db.scalar(
        select(AiAnalysis)
        .where(AiAnalysis.case_id == case_id, AiAnalysis.status == AnalysisStatus.COMPLETED)
        .order_by(AiAnalysis.created_at.desc())
        .limit(1)
    )


def transition_block(db: Session, case: Case, target: CaseStatus) -> ApiError | None:
    if (case.status, target) not in ALLOWED:
        return ApiError(
            409,
            "INVALID_TRANSITION",
            f"Перехід «{STATUS_UK[case.status]}» → «{STATUS_UK[target]}» не дозволений",
        )
    if (case.status, target) == (REFERRED, CLOSED):
        ref = latest_referral(db, case.id)
        if ref is None or ref.status != ReferralStatus.COMPLETED:
            return ApiError(
                409,
                "REFERRAL_NOT_COMPLETED",
                "Випадок із направленням можна закрити лише після затвердження результату лабораторії",
            )
    return None


def available_actions(db: Session, case: Case) -> list[str]:
    actions = [d.value for d, target in DECISION_TARGET.items() if transition_block(db, case, target) is None]
    if transition_block(db, case, OPEN) is None:
        actions.append("Reopen")
    return actions


def _move(db: Session, case: Case, target: CaseStatus, user: User, decision: CaseDecision | None) -> None:
    block = transition_block(db, case, target)
    if block is not None:
        raise block
    previous = case.status
    case.status = target
    case.decision = decision
    audit.record(
        db,
        "case_status_changed",
        "case",
        case.id,
        actor_id=user.id,
        metadata={"from": previous.value, "to": target.value, "decision": decision.value if decision else "Reopen"},
    )


def _text(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def save_assessment(
    db: Session,
    case: Case,
    user: User,
    *,
    assessment: str | None,
    assessment_set: bool,
    decision: CaseDecision | None,
    follow_up_date: date | None,
    follow_up_note: str | None,
    referral_reason: str | None,
) -> Referral | None:
    if case.status == CLOSED:
        raise ApiError(409, "CASE_CLOSED", "Випадок закрито: дані доступні лише для перегляду")
    if assessment_set:
        new_text = _text(assessment)
        if new_text != case.doctor_assessment:
            case.doctor_assessment = new_text
            audit.record(db, "case_assessment_saved", "case", case.id, actor_id=user.id)
    if decision is None:
        return None

    target = DECISION_TARGET[decision]
    block = transition_block(db, case, target)
    if block is not None:
        raise block

    if decision == CaseDecision.CLOSE and not case.doctor_assessment:
        raise ApiError(422, "ASSESSMENT_REQUIRED", "Щоб завершити випадок, заповніть оцінку лікаря")
    if decision == CaseDecision.FOLLOW_UP:
        today = today_local()
        if follow_up_date is None:
            raise ApiError(422, "FOLLOW_UP_DATE_REQUIRED", "Вкажіть дату контролю")
        if follow_up_date < today:
            raise ApiError(422, "FOLLOW_UP_DATE_PAST", "Дата контролю не може бути в минулому")
        if follow_up_date > today + timedelta(days=MAX_FOLLOW_UP_DAYS):
            raise ApiError(422, "FOLLOW_UP_DATE_TOO_FAR", "Дата контролю — не пізніше ніж через 2 роки")
        case.follow_up_date = follow_up_date
        case.follow_up_note = _text(follow_up_note)
    referral = None
    if decision == CaseDecision.REFER:
        reason = _text(referral_reason)
        if reason is None:
            raise ApiError(422, "REFERRAL_REASON_REQUIRED", "Вкажіть клінічне питання / підставу направлення")
        referral = _create_referral(db, case, user, reason)

    _move(db, case, target, user, decision)
    return referral


def reopen(db: Session, case: Case, user: User) -> None:
    _move(db, case, OPEN, user, None)
    case.follow_up_date = None
    case.follow_up_note = None


def _create_referral(db: Session, case: Case, user: User, reason: str) -> Referral:
    analysis = current_analysis(db, case.id)
    seq = db.scalar(text("SELECT nextval('referral_number_seq')"))
    referral = Referral(
        referral_number=f"REF-{datetime.now(UTC).year}-{seq:06d}",
        case_id=case.id,
        doctor_id=user.id,
        analysis_id=analysis.id if analysis else None,  # snapshot for the lab
        status=ReferralStatus.SENT,
        reason=reason,
    )
    db.add(referral)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "REFERRAL_EXISTS", "Для цього випадку вже є активне направлення") from None
    audit.record(
        db,
        "referral_created",
        "referral",
        referral.id,
        actor_id=user.id,
        metadata={"caseId": str(case.id), "analysisId": str(analysis.id) if analysis else None},
    )
    return referral
