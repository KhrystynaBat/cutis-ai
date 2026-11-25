from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import case as sql_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.auth.deps import require_lab, require_roles
from app.core.errors import ApiError
from app.core.names import name_matches
from app.db.models import (
    AiAnalysis,
    Case,
    CaseImage,
    CaseStatus,
    LabResult,
    Patient,
    Referral,
    ReferralStatus,
    Role,
    User,
    XaiArtifact,
)
from app.db.session import get_db
from app.email import outbox
from app.schemas.common import Page
from app.schemas.patients import PatientRef
from app.schemas.referrals import (
    LabResultIn,
    LabResultOut,
    PersonRef,
    ReassignIn,
    ReferralCase,
    ReferralOut,
    ReferralSummary,
)
from app.services import lab_pdf as lab_pdf_service
from app.services import lab_workflow
from app.storage.local import Storage, get_storage

from .analyses import analysis_out
from .cases import current_image, image_out, private_file

router = APIRouter(prefix="/referrals", tags=["referrals"])
logger = logging.getLogger("dermalab")

require_doctor_or_lab = require_roles(Role.DOCTOR, Role.LAB_SPECIALIST)

_STATUS_ORDER = sql_case(
    {ReferralStatus.SENT.value: 0, ReferralStatus.IN_PROGRESS.value: 1}, value=Referral.status, else_=2
)


def _referral(db: Session, user: User, referral_id: uuid.UUID, *, for_update: bool = False) -> Referral:
    ref = db.get(Referral, referral_id, with_for_update=for_update)
    if ref is None or (user.role == Role.DOCTOR and ref.doctor_id != user.id):
        raise ApiError(404, "NOT_FOUND", "Направлення не знайдено")
    return ref


def _person(u: User) -> PersonRef:
    return PersonRef(
        id=u.id,
        first_name=u.first_name,
        last_name=u.last_name,
        middle_name=u.middle_name,
        phone=u.phone,
    )


def _person_or_none(db: Session, user_id: uuid.UUID | None) -> PersonRef | None:
    return _person(db.get(User, user_id)) if user_id else None


def _visible_result(db: Session, user: User, ref: Referral) -> LabResult | None:
    result = lab_workflow.lab_result_of(db, ref.id)
    if result is not None and user.role == Role.DOCTOR and not result.is_approved:
        return None
    return result


def lab_result_out(db: Session, result: LabResult) -> LabResultOut:
    return LabResultOut(
        id=result.id,
        lab_accession_number=result.lab_accession_number,
        histopathology_diagnosis=result.histopathology_diagnosis,
        histopathology_description=result.histopathology_description,
        examined_at=result.examined_at,
        comment=result.comment,
        is_approved=result.is_approved,
        approved_at=result.approved_at,
        lab_specialist=_person(db.get(User, result.lab_specialist_id)),
        updated_at=result.updated_at,
        pdf_url=f"/api/v1/referrals/{result.referral_id}/lab-result.pdf" if result.is_approved else None,
    )


@router.get("", response_model=Page[ReferralSummary])
def list_referrals(
    status_: ReferralStatus | None = Query(default=None, alias="status"),
    case_status: CaseStatus | None = Query(default=None, alias="caseStatus"),
    scope: Literal["all", "queue", "mine", "unassigned"] = Query(
        default="all",
        description="lab only: queue = not taken + mine; mine = assigned to me; unassigned = not taken",
    ),
    search: str | None = Query(default=None, max_length=100, description="patient name or referral number"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: User = Depends(require_doctor_or_lab),
    db: Session = Depends(get_db),
) -> Page[ReferralSummary]:
    doctor = aliased(User)
    assignee = aliased(User)
    accession = select(LabResult.lab_accession_number).where(LabResult.referral_id == Referral.id)
    if user.role == Role.DOCTOR:
        accession = accession.where(LabResult.is_approved.is_(True))
    stmt = (
        select(Referral, Case, Patient, doctor, assignee, accession.scalar_subquery().label("accession"))
        .join(Case, Case.id == Referral.case_id)
        .join(Patient, Patient.id == Case.patient_id)
        .join(doctor, doctor.id == Referral.doctor_id)
        .outerjoin(assignee, assignee.id == Referral.assigned_lab_specialist_id)
    )
    if user.role == Role.DOCTOR:
        stmt = stmt.where(Referral.doctor_id == user.id)
    elif scope == "queue":
        stmt = stmt.where(
            or_(Referral.assigned_lab_specialist_id.is_(None), Referral.assigned_lab_specialist_id == user.id)
        )
    elif scope == "mine":
        stmt = stmt.where(Referral.assigned_lab_specialist_id == user.id)
    elif scope == "unassigned":
        stmt = stmt.where(Referral.assigned_lab_specialist_id.is_(None))
    if status_ is not None:
        stmt = stmt.where(Referral.status == status_)
    if case_status is not None:
        stmt = stmt.where(Case.status == case_status)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Referral.referral_number).like(like),
                name_matches(Patient, like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (Referral.created_at.desc(),) if user.role == Role.DOCTOR else (_STATUS_ORDER, Referral.created_at.desc())
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        ReferralSummary(
            id=r.id,
            referral_number=r.referral_number,
            status=r.status,
            created_at=r.created_at,
            patient=PatientRef.model_validate(p),
            doctor=_person(d),
            assignee=_person(a) if a else None,
            case_id=c.id,
            body_location=c.body_location,
            lab_accession_number=acc,
        )
        for r, c, p, d, a, acc in rows
    ]
    return Page[ReferralSummary](items=items, total=total, page=page, page_size=page_size)


def _detail(db: Session, user: User, ref: Referral) -> ReferralOut:
    case = db.get(Case, ref.case_id)
    patient = db.get(Patient, case.patient_id)
    img = current_image(db, case.id)
    analysis = db.get(AiAnalysis, ref.analysis_id) if ref.analysis_id else None
    result = _visible_result(db, user, ref)
    base = f"/api/v1/referrals/{ref.id}"

    image = image_out(img) if img else None
    if image is not None:
        image.url = f"{base}/images/{img.id}"
    ai = None
    if analysis is not None:
        ai = analysis_out(db, analysis)
        for x in ai.xai:
            if x.url:
                x.url = f"{base}/xai/{x.id}"
    return ReferralOut(
        id=ref.id,
        referral_number=ref.referral_number,
        status=ref.status,
        reason=ref.reason,
        created_at=ref.created_at,
        started_at=ref.started_at,
        completed_at=ref.completed_at,
        patient=PatientRef.model_validate(patient),
        doctor=_person(db.get(User, ref.doctor_id)),
        assignee=_person_or_none(db, ref.assigned_lab_specialist_id),
        assigned_at=ref.assigned_at,
        case=ReferralCase(
            id=case.id,
            status=case.status,
            examined_at=case.examined_at,
            body_location=case.body_location,
            clinical_description=case.clinical_description,
            doctor_assessment=case.doctor_assessment,
            image=image,
        ),
        analysis=ai,
        analysis_image_url=f"{base}/images/{analysis.image_id}" if analysis else None,
        lab_accession_number=result.lab_accession_number if result else None,
        lab_result=lab_result_out(db, result) if result else None,
    )


@router.get("/{referral_id}", response_model=ReferralOut)
def get_referral(
    referral_id: uuid.UUID, user: User = Depends(require_doctor_or_lab), db: Session = Depends(get_db)
) -> ReferralOut:
    return _detail(db, user, _referral(db, user, referral_id))


@router.get(
    "/{referral_id}/images/{image_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}},
)
def get_referral_image(
    referral_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(require_doctor_or_lab),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    ref = _referral(db, user, referral_id)
    img = db.get(CaseImage, image_id)
    if img is None or img.case_id != ref.case_id or not storage.exists(img.storage_key):
        raise ApiError(404, "NOT_FOUND", "Зображення не знайдено")
    return private_file(storage.get(img.storage_key), img.mime_type)


@router.get(
    "/{referral_id}/xai/{artifact_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def get_referral_xai(
    referral_id: uuid.UUID,
    artifact_id: uuid.UUID,
    user: User = Depends(require_doctor_or_lab),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    ref = _referral(db, user, referral_id)
    art = db.get(XaiArtifact, artifact_id)
    if (
        art is None
        or ref.analysis_id is None
        or art.analysis_id != ref.analysis_id
        or not art.storage_key
        or not storage.exists(art.storage_key)
    ):
        raise ApiError(404, "NOT_FOUND", "Карту пояснення не знайдено")
    return private_file(storage.get(art.storage_key), "image/png")


@router.post("/{referral_id}/start", response_model=ReferralOut)
def start_referral(
    referral_id: uuid.UUID, user: User = Depends(require_lab), db: Session = Depends(get_db)
) -> ReferralOut:
    ref = _referral(db, user, referral_id, for_update=True)
    lab_workflow.start(db, ref, user)
    db.commit()
    return _detail(db, user, ref)


@router.post("/{referral_id}/reassign", response_model=ReferralOut)
def reassign_referral(
    referral_id: uuid.UUID, body: ReassignIn, user: User = Depends(require_lab), db: Session = Depends(get_db)
) -> ReferralOut:
    ref = _referral(db, user, referral_id, for_update=True)
    lab_workflow.reassign(db, ref, user, body.lab_specialist_id)
    db.commit()
    return _detail(db, user, ref)


@router.post("/{referral_id}/release", response_model=ReferralOut)
def release_referral(
    referral_id: uuid.UUID, user: User = Depends(require_lab), db: Session = Depends(get_db)
) -> ReferralOut:
    ref = _referral(db, user, referral_id, for_update=True)
    lab_workflow.release(db, ref, user)
    db.commit()
    return _detail(db, user, ref)


def _input(body: LabResultIn) -> lab_workflow.LabInput:
    return lab_workflow.LabInput(**body.model_dump())


@router.put("/{referral_id}/lab-result/draft", response_model=ReferralOut)
def save_draft(
    referral_id: uuid.UUID, body: LabResultIn, user: User = Depends(require_lab), db: Session = Depends(get_db)
) -> ReferralOut:
    ref = _referral(db, user, referral_id, for_update=True)
    lab_workflow.save_draft(db, ref, user, _input(body))
    db.commit()
    return _detail(db, user, ref)


@router.post("/{referral_id}/lab-result/approve", response_model=ReferralOut)
def approve(
    referral_id: uuid.UUID,
    background: BackgroundTasks,
    body: LabResultIn | None = None,
    user: User = Depends(require_lab),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> ReferralOut:
    ref = _referral(db, user, referral_id, for_update=True)  # serialises concurrent approvals
    approval = lab_workflow.approve(db, ref, user, _input(body) if body is not None else None)
    db.commit()
    if approval.created:
        background.add_task(outbox.dispatch_in_background)
        _after_approval(db, storage, ref)
    return _detail(db, user, ref)


def _after_approval(db: Session, storage: Storage, ref: Referral) -> None:
    try:
        lab_pdf_service.ensure_pdf(db, storage, ref)
    except Exception:
        db.rollback()
        logger.exception("lab result PDF generation failed for referral %s", ref.id)


@router.get("/{referral_id}/lab-result", response_model=LabResultOut)
def get_lab_result(
    referral_id: uuid.UUID, user: User = Depends(require_doctor_or_lab), db: Session = Depends(get_db)
) -> LabResultOut:
    ref = _referral(db, user, referral_id)
    result = _visible_result(db, user, ref)
    if result is None:
        raise ApiError(404, "LAB_RESULT_NOT_READY", "Результат лабораторії ще не затверджено")
    return lab_result_out(db, result)


@router.get(
    "/{referral_id}/lab-result.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_lab_result_pdf(
    referral_id: uuid.UUID,
    download: bool = Query(False, description="true — зберегти файл (attachment); інакше показати в браузері"),
    user: User = Depends(require_doctor_or_lab),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    ref = _referral(db, user, referral_id)
    result = lab_workflow.lab_result_of(db, ref.id)
    if result is None or not result.is_approved:
        raise ApiError(404, "LAB_RESULT_NOT_READY", "Результат лабораторії ще не затверджено")
    kind = "attachment" if download else "inline"
    return private_file(
        lab_pdf_service.ensure_pdf(db, storage, ref),
        "application/pdf",
        disposition=f'{kind}; filename="{ref.referral_number}-lab-result.pdf"',
        sandbox=False,
    )
