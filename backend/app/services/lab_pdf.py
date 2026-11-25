from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.names import full_name
from app.db.models import Case, LabResult, Patient, Referral, User
from app.pdf import lab_result as lab_pdf
from app.services import audit
from app.storage.local import Storage

logger = logging.getLogger("dermalab.pdf")

SUFFIX = f".v{lab_pdf.TEMPLATE_VERSION}.pdf"


def pdf_data(db: Session, ref: Referral, result: LabResult) -> lab_pdf.LabResultPdf:
    case = db.get(Case, ref.case_id)
    patient = db.get(Patient, case.patient_id)
    doctor = db.get(User, ref.doctor_id)
    specialist = db.get(User, result.lab_specialist_id)
    return lab_pdf.LabResultPdf(
        referral_number=ref.referral_number,
        lab_accession_number=result.lab_accession_number,
        examined_at=result.examined_at,
        approved_at=result.approved_at,
        patient_name=full_name(patient),
        patient_birth_date=patient.date_of_birth,
        doctor_name=full_name(doctor),
        doctor_phone=doctor.phone,
        lab_specialist_name=full_name(specialist),
        diagnosis=result.histopathology_diagnosis,
        description=result.histopathology_description,
        comment=result.comment,
        referral_date=ref.created_at,
        timezone=get_settings().display_timezone,
    )


def is_current(key: str | None) -> bool:
    return bool(key) and key.endswith(SUFFIX)


def ensure_pdf(db: Session, storage: Storage, ref: Referral) -> bytes:
    result = db.scalar(select(LabResult).where(LabResult.referral_id == ref.id))
    old_key = result.pdf_storage_key
    if is_current(old_key) and storage.exists(old_key):
        return storage.get(old_key)
    data = lab_pdf.render(pdf_data(db, ref, result))
    key = storage.put(data, prefix="pdf", suffix=SUFFIX)
    same = LabResult.pdf_storage_key.is_(None) if old_key is None else LabResult.pdf_storage_key == old_key
    stored = db.execute(update(LabResult).where(LabResult.id == result.id, same).values(pdf_storage_key=key)).rowcount
    if stored:
        audit.record(
            db,
            "lab_result_pdf_generated",
            "referral",
            ref.id,
            metadata={"template": lab_pdf.TEMPLATE_VERSION, "replaced": old_key is not None},
        )
    db.commit()
    if not stored:  # someone else stored theirs first
        storage.delete(key)
    elif old_key:
        storage.delete(old_key)  # the outdated layout
    return data


def pdf_bytes(db: Session, storage: Storage, ref: Referral) -> bytes:
    result = db.scalar(select(LabResult).where(LabResult.referral_id == ref.id))
    if is_current(result.pdf_storage_key) and storage.exists(result.pdf_storage_key):
        return storage.get(result.pdf_storage_key)
    return lab_pdf.render(pdf_data(db, ref, result))


def regenerate_all(db: Session, storage: Storage) -> int:
    rows = db.execute(
        select(Referral, LabResult.pdf_storage_key)
        .join(LabResult, LabResult.referral_id == Referral.id)
        .where(LabResult.is_approved.is_(True))
    ).all()
    done = 0
    for ref, key in rows:
        if is_current(key) and storage.exists(key):
            continue
        ensure_pdf(db, storage, ref)
        done += 1
    return done
