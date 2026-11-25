from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.constants import CLASS_LABELS_UK
from app.ai.gatekeeper import GateService
from app.auth.deps import require_doctor
from app.auth.sessions import now_utc
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.names import name_matches
from app.db.models import (
    AiAnalysis,
    AnalysisStatus,
    Case,
    CaseImage,
    CaseStatus,
    Patient,
    Referral,
    ReferralStatus,
    User,
)
from app.db.session import get_db
from app.schemas.analyses import AiResultRef
from app.schemas.cases import (
    AssessmentUpdate,
    CaseCreate,
    CaseImageOut,
    CaseOut,
    CaseSummary,
    CaseUpdate,
    DashboardOut,
    ImageCheckOut,
    ReferralBrief,
    ReferralRef,
)
from app.schemas.common import Page
from app.schemas.patients import PatientRef
from app.services import audit, case_workflow
from app.services.access import own_case, own_patient
from app.storage.images import ValidatedImage, sanitize_filename, validate_image
from app.storage.local import Storage, get_storage

router = APIRouter(tags=["cases"])

ACTIVE_STATUSES = (CaseStatus.OPEN, CaseStatus.FOLLOW_UP_PLANNED, CaseStatus.REFERRED)

NOT_DERMOSCOPIC = (
    "Зображення не схоже на дерматоскопічне. Аналіз ШІ розрахований лише на дерматоскопічні знімки, "
    "тому для цього фото результат може бути недостовірним. Завантажте інше фото або підтвердіть, "
    "що це дерматоскопічне зображення."
)


def current_image(db: Session, case_id: uuid.UUID) -> CaseImage | None:
    return db.scalar(
        select(CaseImage).where(CaseImage.case_id == case_id).order_by(CaseImage.uploaded_at.desc()).limit(1)
    )


def image_out(img: CaseImage) -> CaseImageOut:
    return CaseImageOut(
        id=img.id,
        original_filename=img.original_filename,
        mime_type=img.mime_type,
        byte_size=img.byte_size,
        uploaded_at=img.uploaded_at,
        url=f"/api/v1/cases/{img.case_id}/images/{img.id}",
        gate_overridden=gate_overridden(img),
    )


def gate_overridden(img: CaseImage | None) -> bool:
    return img is not None and img.gate_passed is False and img.gate_confirmed_by_id is not None


def get_gate(request: Request) -> GateService:
    return request.app.state.gate


def _upload_budget(request: Request, user: User) -> None:
    limiter = request.app.state.upload_limiter
    key = f"upload|{user.id}"
    retry = limiter.retry_after(key)
    if retry:
        raise ApiError(429, "TOO_MANY_UPLOADS", f"Забагато завантажень. Спробуйте через {retry // 60 + 1} хв")
    limiter.record_failure(key)


def _read_image(file: UploadFile) -> ValidatedImage:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    return validate_image(data, max_bytes)


@router.post("/images/check", response_model=ImageCheckOut)
def check_image(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_doctor),
    gate: GateService = Depends(get_gate),
) -> ImageCheckOut:
    _upload_budget(request, user)
    image = _read_image(file)
    result = gate.check(image.data)
    return (
        ImageCheckOut(passed=True, score=None)
        if result is None
        else ImageCheckOut(passed=result.passed, score=result.score)
    )


def _summary(
    case: Case,
    patient: Patient,
    has_image: bool,
    ai_code: str | None = None,
    ai_score: float | None = None,
    referral: Referral | None = None,
) -> CaseSummary:
    return CaseSummary(
        id=case.id,
        patient=PatientRef.model_validate(patient),
        examined_at=case.examined_at,
        body_location=case.body_location,
        status=case.status,
        has_image=has_image,
        ai_result=(
            AiResultRef(code=ai_code, label_uk=CLASS_LABELS_UK.get(ai_code, ai_code), score=ai_score)
            if ai_code is not None and ai_score is not None
            else None
        ),
        referral=ReferralRef.model_validate(referral) if referral else None,
        created_at=case.created_at,
    )


def _latest_referrals(db: Session, case_ids: list[uuid.UUID]) -> dict[uuid.UUID, Referral]:
    if not case_ids:
        return {}
    rows = db.scalars(
        select(Referral)
        .where(Referral.case_id.in_(case_ids))
        .order_by(Referral.case_id, Referral.created_at.desc())
        .distinct(Referral.case_id)
    )
    return {r.case_id: r for r in rows}


def _summaries(db: Session, rows) -> list[CaseSummary]:
    referrals = _latest_referrals(db, [r[0].id for r in rows])
    return [_summary(*r, referrals.get(r[0].id)) for r in rows]


def _latest_completed(column):
    return (
        select(column)
        .where(AiAnalysis.case_id == Case.id, AiAnalysis.status == AnalysisStatus.COMPLETED)
        .order_by(AiAnalysis.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )


def _detail(db: Session, case: Case) -> CaseOut:
    patient = db.get(Patient, case.patient_id)
    img = current_image(db, case.id)
    latest = db.execute(
        select(AiAnalysis.predicted_class_code, AiAnalysis.score)
        .where(AiAnalysis.case_id == case.id, AiAnalysis.status == AnalysisStatus.COMPLETED)
        .order_by(AiAnalysis.created_at.desc())
        .limit(1)
    ).first()
    referral = case_workflow.latest_referral(db, case.id)
    return CaseOut(
        **_summary(case, patient, img is not None, *(latest or (None, None))).model_dump(exclude={"referral"}),
        clinical_description=case.clinical_description,
        doctor_assessment=case.doctor_assessment,
        follow_up_date=case.follow_up_date,
        follow_up_note=case.follow_up_note,
        updated_at=case.updated_at,
        image=image_out(img) if img else None,
        is_editable=case.status == CaseStatus.OPEN,
        decision=case.decision,
        referral=ReferralBrief.model_validate(referral) if referral else None,
        available_actions=case_workflow.available_actions(db, case),
    )


def _summaries_stmt(user: User):
    has_image = select(CaseImage.id).where(CaseImage.case_id == Case.id).exists().label("has_image")
    return (
        select(
            Case,
            Patient,
            has_image,
            _latest_completed(AiAnalysis.predicted_class_code).label("ai_code"),
            _latest_completed(AiAnalysis.score).label("ai_score"),
        )
        .join(Patient, Patient.id == Case.patient_id)
        .where(Case.doctor_id == user.id)
    )


def _require_open(case: Case) -> None:
    if case.status != CaseStatus.OPEN:
        raise ApiError(409, "CASE_NOT_EDITABLE", "Дані й фото випадку можна змінювати лише у статусі «Відкритий»")


@router.get("/cases", response_model=Page[CaseSummary])
def list_cases(
    status_: CaseStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100, description="patient name"),
    patient_id: uuid.UUID | None = Query(default=None, alias="patientId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
) -> Page[CaseSummary]:
    stmt = _summaries_stmt(user)
    if status_ is not None:
        stmt = stmt.where(Case.status == status_)
    if patient_id is not None:
        stmt = stmt.where(Case.patient_id == patient_id)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(name_matches(Patient, like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Case.examined_at.desc(), Case.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[CaseSummary](items=_summaries(db, rows), total=total, page=page, page_size=page_size)


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(body: CaseCreate, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseOut:
    patient = own_patient(db, user, body.patient_id)
    if patient.is_archived:
        raise ApiError(409, "PATIENT_ARCHIVED", "Пацієнта архівовано: спершу відновіть його")
    if body.examined_at < patient.date_of_birth:
        raise ApiError(422, "DATE_CONFLICT", "Дата огляду раніша за дату народження пацієнта")
    case = Case(doctor_id=user.id, status=CaseStatus.OPEN, **body.model_dump())
    db.add(case)
    db.flush()
    audit.record(db, "case_created", "case", case.id, actor_id=user.id)
    db.commit()
    return _detail(db, case)


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseOut:
    return _detail(db, own_case(db, user, case_id))


@router.patch("/cases/{case_id}", response_model=CaseOut)
def update_case(
    case_id: uuid.UUID, body: CaseUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)
) -> CaseOut:
    case = own_case(db, user, case_id, for_update=True)
    _require_open(case)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "examined_at" in changes:
        patient = db.get(Patient, case.patient_id)
        if changes["examined_at"] < patient.date_of_birth:
            raise ApiError(422, "DATE_CONFLICT", "Дата огляду раніша за дату народження пацієнта")
    changed = [k for k, v in changes.items() if getattr(case, k) != v]
    for k in changed:
        setattr(case, k, changes[k])
    if changed:
        audit.record(db, "case_updated", "case", case.id, actor_id=user.id, metadata={"fields": changed})
    db.commit()
    return _detail(db, case)


@router.patch("/cases/{case_id}/assessment", response_model=CaseOut)
def save_assessment(
    case_id: uuid.UUID, body: AssessmentUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)
) -> CaseOut:
    case = own_case(db, user, case_id, for_update=True)
    case_workflow.save_assessment(
        db,
        case,
        user,
        assessment=body.doctor_assessment,
        assessment_set="doctor_assessment" in body.model_fields_set,
        decision=body.decision,
        follow_up_date=body.follow_up_date,
        follow_up_note=body.follow_up_note,
        referral_reason=body.referral_reason,
    )
    db.commit()
    return _detail(db, case)


@router.post("/cases/{case_id}/reopen", response_model=CaseOut)
def reopen_case(case_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> CaseOut:
    case = own_case(db, user, case_id, for_update=True)
    case_workflow.reopen(db, case, user)
    db.commit()
    return _detail(db, case)


@router.post("/cases/{case_id}/images", response_model=CaseImageOut, status_code=status.HTTP_201_CREATED)
def upload_image(
    case_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    confirm_non_dermoscopic: bool = Form(False),
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    gate: GateService = Depends(get_gate),
) -> CaseImageOut:
    _upload_budget(request, user)
    case = own_case(db, user, case_id, for_update=True)
    _require_open(case)
    image = _read_image(file)
    gate_result = gate.check(image.data)
    overridden = gate_result is not None and not gate_result.passed
    if overridden and not confirm_non_dermoscopic:
        raise ApiError(422, "IMAGE_NOT_DERMOSCOPIC", NOT_DERMOSCOPIC)

    storage_key = storage.put(image.data, prefix="images", suffix=image.extension)
    row = CaseImage(
        case_id=case.id,
        storage_key=storage_key,
        original_filename=sanitize_filename(file.filename, image.extension),
        mime_type=image.mime_type,
        byte_size=len(image.data),
        checksum_sha256=image.sha256,
    )
    if gate_result is not None:
        row.gate_score = gate_result.score
        row.gate_passed = gate_result.passed
        row.gate_model_sha256 = gate_result.model_sha256
        if overridden:
            row.gate_confirmed_by_id = user.id
            row.gate_confirmed_at = now_utc()
    db.add(row)
    db.flush()
    if overridden:
        audit.record(db, "image_gate_override", "case", case.id, actor_id=user.id, metadata={"imageId": str(row.id)})
    audit.record(
        db,
        "case_image_uploaded",
        "case",
        case.id,
        actor_id=user.id,
        metadata={"imageId": str(row.id), "mime": image.mime_type, "bytes": len(image.data)},
    )
    db.commit()
    return image_out(row)


@router.get(
    "/cases/{case_id}/images/{image_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}},
)
def get_image(
    case_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    case = own_case(db, user, case_id)
    img = db.get(CaseImage, image_id)
    if img is None or img.case_id != case.id or not storage.exists(img.storage_key):
        raise ApiError(404, "NOT_FOUND", "Зображення не знайдено")
    return private_file(storage.get(img.storage_key), img.mime_type)


_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}


def private_file(content: bytes, media_type: str, disposition: str | None = None, *, sandbox: bool = True) -> Response:
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": disposition or f'inline; filename="case-image{_EXT.get(media_type, "")}"',
    }
    if sandbox:
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/doctor/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> DashboardOut:
    patients = db.scalar(select(func.count()).where(Patient.doctor_id == user.id, Patient.is_archived.is_(False)))
    active = db.scalar(select(func.count()).where(Case.doctor_id == user.id, Case.status.in_(ACTIVE_STATUSES)))
    pending = db.scalar(
        select(func.count()).where(
            Referral.doctor_id == user.id, Referral.status.in_((ReferralStatus.SENT, ReferralStatus.IN_PROGRESS))
        )
    )
    ready = db.scalar(
        select(func.count())
        .select_from(Referral)
        .join(Case, Case.id == Referral.case_id)
        .where(
            Referral.doctor_id == user.id,
            Referral.status == ReferralStatus.COMPLETED,
            Case.status == CaseStatus.REFERRED,
        )
    )
    recent = db.execute(_summaries_stmt(user).order_by(Case.created_at.desc()).limit(5)).all()
    return DashboardOut(
        patients=patients or 0,
        active_cases=active or 0,
        pending_referrals=pending or 0,
        ready_results=ready or 0,
        recent_cases=_summaries(db, recent),
    )
