from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Case, Patient, User


def own_patient(db: Session, user: User, patient_id: uuid.UUID, *, for_update: bool = False) -> Patient:
    patient = db.get(Patient, patient_id, with_for_update=for_update)
    if patient is None or patient.doctor_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Пацієнта не знайдено")
    return patient


def own_case(db: Session, user: User, case_id: uuid.UUID, *, for_update: bool = False) -> Case:
    case = db.get(Case, case_id, with_for_update=for_update)
    if case is None or case.doctor_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Випадок не знайдено")
    return case
