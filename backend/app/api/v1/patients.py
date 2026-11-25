from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_doctor
from app.core.clock import today_local
from app.core.errors import ApiError
from app.core.names import name_matches
from app.db.models import Case, Patient, User
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.patients import PatientCreate, PatientOut, PatientUpdate
from app.services import audit
from app.services.access import own_patient

router = APIRouter(prefix="/patients", tags=["patients"])


def age_on(born: date, today: date | None = None) -> int:
    today = today or today_local()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _case_stats():
    return (
        select(
            Case.patient_id.label("patient_id"),
            func.count(Case.id).label("cases_count"),
            func.max(Case.examined_at).label("last_visit"),
        )
        .group_by(Case.patient_id)
        .subquery()
    )


def _out(p: Patient, cases_count: int | None, last_visit: date | None) -> PatientOut:
    return PatientOut(
        id=p.id,
        first_name=p.first_name,
        last_name=p.last_name,
        middle_name=p.middle_name,
        date_of_birth=p.date_of_birth,
        age=age_on(p.date_of_birth),
        email=p.email,
        phone=p.phone,
        notes=p.notes,
        is_archived=p.is_archived,
        cases_count=cases_count or 0,
        last_visit=last_visit,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _load_out(db: Session, patient: Patient) -> PatientOut:
    stats = _case_stats()
    row = db.execute(select(stats.c.cases_count, stats.c.last_visit).where(stats.c.patient_id == patient.id)).first()
    return _out(patient, *(row or (0, None)))


@router.get("", response_model=Page[PatientOut])
def list_patients(
    search: str | None = Query(default=None, max_length=100),
    include_archived: bool = Query(default=False, alias="includeArchived"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
) -> Page[PatientOut]:
    stats = _case_stats()
    stmt = (
        select(Patient, stats.c.cases_count, stats.c.last_visit)
        .outerjoin(stats, stats.c.patient_id == Patient.id)
        .where(Patient.doctor_id == user.id)
    )
    if not include_archived:
        stmt = stmt.where(Patient.is_archived.is_(False))
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                name_matches(Patient, like),
                func.lower(func.coalesce(Patient.email, "")).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Patient.last_name, Patient.first_name, Patient.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[PatientOut](items=[_out(*r) for r in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCreate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient = Patient(doctor_id=user.id, **body.model_dump())
    db.add(patient)
    db.flush()
    audit.record(db, "patient_created", "patient", patient.id, actor_id=user.id)
    db.commit()
    return _out(patient, 0, None)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return _load_out(db, own_patient(db, user, patient_id))


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: uuid.UUID, body: PatientUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)
):
    patient = own_patient(db, user, patient_id, for_update=True)
    changes = body.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name", "date_of_birth"):
        if field in changes and changes[field] is None:
            raise ApiError(422, "VALIDATION_ERROR", "Обов'язкове поле не може бути порожнім")
    if "date_of_birth" in changes:
        first_exam = db.scalar(select(func.min(Case.examined_at)).where(Case.patient_id == patient.id))
        if first_exam is not None and changes["date_of_birth"] > first_exam:
            raise ApiError(422, "DATE_CONFLICT", "Дата народження пізніша за дату огляду в наявному випадку")
    changed = [k for k, v in changes.items() if getattr(patient, k) != v]
    for k in changed:
        setattr(patient, k, changes[k])
    if changed:
        audit.record(db, "patient_updated", "patient", patient.id, actor_id=user.id, metadata={"fields": changed})
    db.commit()
    return _load_out(db, patient)


def _set_archived(archived: bool):
    def handler(patient_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
        patient = own_patient(db, user, patient_id, for_update=True)
        if patient.is_archived != archived:
            patient.is_archived = archived
            action = "patient_archived" if archived else "patient_unarchived"
            audit.record(db, action, "patient", patient.id, actor_id=user.id)
        db.commit()
        return _load_out(db, patient)

    handler.__name__ = "archive_patient" if archived else "unarchive_patient"
    return handler


router.add_api_route("/{patient_id}/archive", _set_archived(True), methods=["POST"], response_model=PatientOut)
router.add_api_route("/{patient_id}/unarchive", _set_archived(False), methods=["POST"], response_model=PatientOut)
