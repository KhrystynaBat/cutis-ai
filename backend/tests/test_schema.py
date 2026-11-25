import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.db.models import AiAnalysis, AnalysisStatus, Case, CaseImage, Patient, Role, User


@pytest.fixture
def db(test_db_url):
    engine = create_engine(test_db_url)
    with Session(engine) as s:
        yield s
        s.rollback()
    engine.dispose()


def _case(db: Session) -> tuple[Case, CaseImage]:
    doc = User(first_name="Тест", last_name="Лікар", email=f"{uuid.uuid4().hex}@example.test", role=Role.DOCTOR)
    db.add(doc)
    db.flush()
    p = Patient(doctor_id=doc.id, first_name="Син", last_name="Тетичний", date_of_birth=date(1980, 1, 1))
    db.add(p)
    db.flush()
    c = Case(
        patient_id=p.id, doctor_id=doc.id, examined_at=today_local(), body_location="спина", clinical_description="-"
    )
    db.add(c)
    db.flush()
    img = CaseImage(
        case_id=c.id,
        storage_key=uuid.uuid4().hex,
        original_filename="a.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        checksum_sha256="0" * 64,
    )
    db.add(img)
    db.flush()
    return c, img


def _analysis(c: Case, img: CaseImage, status: AnalysisStatus) -> AiAnalysis:
    return AiAnalysis(
        case_id=c.id, image_id=img.id, status=status, model_name="ensemble_best", preprocessing_version="v"
    )


def test_case_defaults_to_open(db):
    c, _ = _case(db)
    db.refresh(c)
    assert c.status.value == "Open"


def test_only_one_active_analysis_per_case(db):
    c, img = _case(db)
    db.add(_analysis(c, img, AnalysisStatus.COMPLETED))
    db.add(_analysis(c, img, AnalysisStatus.QUEUED))
    db.flush()
    db.add(_analysis(c, img, AnalysisStatus.RUNNING))
    with pytest.raises(IntegrityError):
        db.flush()


def test_status_check_constraint_rejects_unknown_value(db):
    c, _ = _case(db)
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE cases SET status = 'Deleted' WHERE id = :id"), {"id": c.id})


def test_medical_records_are_not_cascade_deleted(db):
    c, _ = _case(db)
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM patients WHERE id = :id"), {"id": c.patient_id})


def test_email_unique(db):
    email = f"{uuid.uuid4().hex}@example.test"
    db.add(User(first_name="a", last_name="b", email=email, role=Role.ADMIN))
    db.flush()
    db.add(User(first_name="c", last_name="d", email=email, role=Role.DOCTOR))
    with pytest.raises(IntegrityError):
        db.flush()
