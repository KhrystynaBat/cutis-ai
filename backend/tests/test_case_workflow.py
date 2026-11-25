from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, text
from test_patients_cases import jpeg, new_case, new_patient, upload

from app.core.clock import today_local
from app.db.models import AiAnalysis, AnalysisStatus, AuditEvent, Case, Referral, ReferralStatus, Role, User
from app.services.case_workflow import ALLOWED

OPEN, FOLLOW_UP, REFERRED, CLOSED = "Open", "FollowUpPlanned", "Referred", "Closed"
STATUSES = (OPEN, FOLLOW_UP, REFERRED, CLOSED)
TOMORROW = (today_local() + timedelta(days=1)).isoformat()


@pytest.fixture
def doctor(make_user, login_as):
    user = make_user(Role.DOCTOR)
    return user, login_as(user)


def make_case(c, photo: bool = True) -> dict:
    case = new_case(c, new_patient(c)["id"])
    if photo:
        assert upload(c, case["id"], jpeg()).status_code == 201
    return case


def lab_user_id(db) -> uuid.UUID:
    user = User(
        first_name="Лаб", last_name="Тест", email=f"lab-{uuid.uuid4().hex[:8]}@example.test", role=Role.LAB_SPECIALIST
    )
    db.add(user)
    db.flush()
    return user.id


def force_status(db, case_id: str, status: str, doctor_id, referral_status: str = "Sent") -> None:
    db.execute(
        text("UPDATE cases SET status = :s, follow_up_date = :d WHERE id = :id"),
        {"s": status, "d": today_local() + timedelta(days=7) if status == FOLLOW_UP else None, "id": case_id},
    )
    if status == REFERRED:
        db.add(
            Referral(
                referral_number=f"REF-TEST-{uuid.uuid4().hex[:8]}",
                case_id=uuid.UUID(case_id),
                doctor_id=doctor_id,
                status=ReferralStatus(referral_status),
                reason="тест",
                completed_at=datetime.now(UTC) if referral_status == "Completed" else None,
                assigned_lab_specialist_id=lab_user_id(db) if referral_status != "Sent" else None,
                assigned_at=datetime.now(UTC) if referral_status != "Sent" else None,
            )
        )
    db.commit()


def act(c, case_id: str, target: str):
    if target == OPEN:
        return c.post(f"/api/v1/cases/{case_id}/reopen")
    body = {
        FOLLOW_UP: {"decision": "FollowUp", "followUpDate": TOMORROW, "followUpNote": "дерматоскопія"},
        REFERRED: {"decision": "Refer", "referralReason": "Виключити меланому"},
        CLOSED: {"decision": "Close", "doctorAssessment": "Доброякісне утворення"},
    }[target]
    return c.patch(f"/api/v1/cases/{case_id}/assessment", json=body)


def add_analysis(db, case_id: str, status: AnalysisStatus, minutes_ago: int, code: str | None = None) -> uuid.UUID:
    image_id = db.scalar(text("SELECT id FROM case_images WHERE case_id = :c"), {"c": case_id})
    a = AiAnalysis(
        case_id=uuid.UUID(case_id),
        image_id=image_id,
        status=status,
        model_name="ensemble_best",
        model_sha256="f" * 64,
        preprocessing_version="ham10000-bgr128-cubic-std-v1",
        predicted_class_code=code,
        score=0.5 if code else None,
        scores_json={code: 0.5} if code else None,
    )
    db.add(a)
    db.flush()
    db.execute(
        text("UPDATE ai_analyses SET created_at = :t WHERE id = :id"),
        {"t": datetime.now(UTC) - timedelta(minutes=minutes_ago), "id": a.id},
    )
    db.commit()
    return a.id


def test_transition_table_is_exactly_spec_7_1():
    assert {(a.value, b.value) for a, b in ALLOWED} == {
        (OPEN, FOLLOW_UP),
        (OPEN, REFERRED),
        (OPEN, CLOSED),
        (FOLLOW_UP, OPEN),
        (FOLLOW_UP, CLOSED),
        (FOLLOW_UP, REFERRED),
        (REFERRED, CLOSED),
    }


@pytest.mark.parametrize("source", STATUSES)
@pytest.mark.parametrize("target", STATUSES)
def test_every_status_pair(doctor, db, source, target):
    user, c = doctor
    case = make_case(c)
    force_status(db, case["id"], source, user.id, referral_status="Completed")
    r = act(c, case["id"], target)
    if (source, target) in {(a.value, b.value) for a, b in ALLOWED}:
        assert r.status_code == 200, r.text
        assert r.json()["status"] == target
    else:
        assert r.status_code == 409, f"{source} -> {target}: {r.status_code}"
        assert r.json()["error"]["code"] in ("INVALID_TRANSITION", "CASE_CLOSED")
        status = db.scalar(
            select(Case.status).where(Case.id == uuid.UUID(case["id"])).execution_options(populate_existing=True)
        )
        assert status.value == source  # nothing changed


def test_referred_case_closes_only_after_completed_referral(doctor, db):
    user, c = doctor
    for ref_status, expected in (("Sent", 409), ("InProgress", 409), ("Completed", 200)):
        case = make_case(c)
        force_status(db, case["id"], REFERRED, user.id, referral_status=ref_status)
        detail = c.get(f"/api/v1/cases/{case['id']}").json()
        assert ("Close" in detail["availableActions"]) is (expected == 200)
        r = act(c, case["id"], CLOSED)
        assert r.status_code == expected, ref_status
        if expected == 409:
            assert r.json()["error"]["code"] == "REFERRAL_NOT_COMPLETED"


def test_available_actions_follow_the_table(doctor, db):
    user, c = doctor
    expected = {
        OPEN: ["Close", "FollowUp", "Refer"],
        FOLLOW_UP: ["Close", "FollowUp", "Refer", "Reopen"],
        REFERRED: [],
        CLOSED: [],
    }
    expected[FOLLOW_UP].remove("FollowUp")
    for status, actions in expected.items():
        case = make_case(c)
        force_status(db, case["id"], status, user.id)
        assert sorted(c.get(f"/api/v1/cases/{case['id']}").json()["availableActions"]) == sorted(actions)


def test_close_requires_assessment_and_makes_case_read_only(doctor, db):
    _, c = doctor
    case = make_case(c)
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"decision": "Close", "doctorAssessment": "  "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ASSESSMENT_REQUIRED"
    assert c.get(f"/api/v1/cases/{case['id']}").json()["status"] == OPEN

    r = c.patch(
        f"/api/v1/cases/{case['id']}/assessment",
        json={"decision": "Close", "doctorAssessment": "  Себорейний кератоз, спостереження не потрібне  "},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == CLOSED and body["decision"] == "Close"
    assert body["doctorAssessment"] == "Себорейний кератоз, спостереження не потрібне"
    assert body["isEditable"] is False and body["availableActions"] == []

    assert c.patch(f"/api/v1/cases/{case['id']}", json={"bodyLocation": "x"}).status_code == 409
    assert upload(c, case["id"], jpeg()).status_code == 409
    assert c.post(f"/api/v1/cases/{case['id']}/analyses").status_code == 409
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"doctorAssessment": "інше"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_CLOSED"
    assert c.post(f"/api/v1/cases/{case['id']}/reopen").status_code == 409


def test_close_uses_previously_saved_assessment(doctor):
    _, c = doctor
    case = make_case(c)
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"doctorAssessment": "Чернетка висновку"})
    assert r.status_code == 200 and r.json()["status"] == OPEN and r.json()["decision"] is None
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"decision": "Close"})
    assert r.status_code == 200 and r.json()["status"] == CLOSED


@pytest.mark.parametrize(
    "follow_up_date, code",
    [
        (None, "FOLLOW_UP_DATE_REQUIRED"),
        ((today_local() - timedelta(days=1)).isoformat(), "FOLLOW_UP_DATE_PAST"),
        ((today_local() + timedelta(days=800)).isoformat(), "FOLLOW_UP_DATE_TOO_FAR"),
    ],
)
def test_follow_up_date_validation(doctor, follow_up_date, code):
    _, c = doctor
    case = make_case(c)
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"decision": "FollowUp", "followUpDate": follow_up_date})
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert c.get(f"/api/v1/cases/{case['id']}").json()["status"] == OPEN


def test_follow_up_then_reopen(doctor, db):
    _, c = doctor
    case = make_case(c)
    r = c.patch(
        f"/api/v1/cases/{case['id']}/assessment",
        json={
            "decision": "FollowUp",
            "followUpDate": TOMORROW,
            "followUpNote": " повторна дерматоскопія ",
            "doctorAssessment": "Атиповий невус",
        },
    )
    body = r.json()
    assert r.status_code == 200 and body["status"] == FOLLOW_UP and body["decision"] == "FollowUp"
    assert body["followUpDate"] == TOMORROW and body["followUpNote"] == "повторна дерматоскопія"
    assert body["isEditable"] is False  # data and photo are editable only in Open

    r = c.post(f"/api/v1/cases/{case['id']}/reopen")
    assert r.status_code == 200 and r.json()["status"] == OPEN and r.json()["decision"] is None
    assert r.json()["isEditable"] is True
    assert r.json()["followUpDate"] is None and r.json()["followUpNote"] is None  # plan cancelled

    events = db.scalars(
        select(AuditEvent.metadata_json)
        .where(AuditEvent.action == "case_status_changed")
        .order_by(AuditEvent.occurred_at)
    ).all()
    assert events == [
        {"from": OPEN, "to": FOLLOW_UP, "decision": "FollowUp"},
        {"from": FOLLOW_UP, "to": OPEN, "decision": "Reopen"},
    ]


def test_database_requires_follow_up_date(doctor, db):
    from sqlalchemy.exc import IntegrityError

    _, c = doctor
    case = make_case(c)
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE cases SET status = 'FollowUpPlanned', follow_up_date = NULL WHERE id = :id"),
            {"id": case["id"]},
        )
    db.rollback()


def test_refer_creates_sent_referral_with_current_analysis(doctor, db):
    _, c = doctor
    case = make_case(c)
    add_analysis(db, case["id"], AnalysisStatus.COMPLETED, 30, "nv")
    current = add_analysis(db, case["id"], AnalysisStatus.COMPLETED, 20, "mel")
    add_analysis(db, case["id"], AnalysisStatus.FAILED, 10)

    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"decision": "Refer", "referralReason": "  "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REFERRAL_REASON_REQUIRED"
    assert db.scalar(select(Referral.id)) is None

    r = c.patch(
        f"/api/v1/cases/{case['id']}/assessment",
        json={
            "decision": "Refer",
            "referralReason": "Асиметрія, підозра на меланому",
            "doctorAssessment": "Потрібна гістологія",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == REFERRED and body["decision"] == "Refer" and body["availableActions"] == []
    ref = body["referral"]
    assert re.fullmatch(rf"REF-{datetime.now(UTC).year}-\d{{6}}", ref["referralNumber"])
    assert ref["status"] == "Sent" and ref["reason"] == "Асиметрія, підозра на меланому"
    assert ref["analysisId"] == str(current)

    row = db.scalar(select(Referral))
    assert row.analysis_id == current and row.case_id == uuid.UUID(case["id"])

    # doctor's referral list and detail
    lst = c.get("/api/v1/referrals").json()
    assert lst["total"] == 1 and lst["items"][0]["referralNumber"] == ref["referralNumber"]
    assert lst["items"][0]["labAccessionNumber"] is None
    detail = c.get(f"/api/v1/referrals/{ref['id']}").json()
    assert detail["case"]["id"] == case["id"] and detail["case"]["doctorAssessment"] == "Потрібна гістологія"
    assert detail["case"]["image"]["url"].startswith(f"/api/v1/referrals/{ref['id']}/images/")  # via the referral
    assert detail["analysis"]["id"] == str(current) and detail["analysis"]["predictedClass"]["code"] == "mel"
    assert detail["patient"]["lastName"] == "Пацієнт"

    assert c.get("/api/v1/cases").json()["items"][0]["referral"]["referralNumber"] == ref["referralNumber"]
    assert c.get("/api/v1/doctor/dashboard").json()["pendingReferrals"] == 1

    # audit: ids only, no clinical text
    meta = db.scalar(select(AuditEvent.metadata_json).where(AuditEvent.action == "referral_created"))
    assert meta == {"caseId": case["id"], "analysisId": str(current)}
    for m in db.scalars(select(AuditEvent.metadata_json)):
        assert "меланом" not in str(m) and "гістолог" not in str(m)


def test_refer_without_analysis_and_from_follow_up(doctor):
    _, c = doctor
    case = make_case(c, photo=False)
    act(c, case["id"], FOLLOW_UP)
    r = act(c, case["id"], REFERRED)
    assert r.status_code == 200 and r.json()["referral"]["analysisId"] is None
    detail = c.get(f"/api/v1/referrals/{r.json()['referral']['id']}").json()
    assert detail["analysis"] is None and detail["case"]["image"] is None


def test_referral_numbers_are_unique_and_sequential(doctor):
    _, c = doctor
    numbers = [act(c, make_case(c)["id"], REFERRED).json()["referral"]["referralNumber"] for _ in range(3)]
    seq = [int(n.rsplit("-", 1)[1]) for n in numbers]
    assert len(set(numbers)) == 3 and seq == sorted(seq) and seq[2] - seq[0] == 2


def test_referral_and_status_change_are_one_transaction(doctor, db):
    user, c = doctor
    case = make_case(c)
    db.add(Referral(referral_number="REF-TEST-1", case_id=uuid.UUID(case["id"]), doctor_id=user.id, reason="x"))
    db.commit()
    r = act(c, case["id"], REFERRED)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REFERRAL_EXISTS"
    assert c.get(f"/api/v1/cases/{case['id']}").json()["status"] == OPEN
    assert db.scalar(select(text("count(*)")).select_from(Referral)) == 1
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "case_status_changed")) is None


def test_referral_list_filters(doctor, db):
    _, c = doctor
    first = act(c, make_case(c)["id"], REFERRED).json()["referral"]
    act(c, make_case(c)["id"], REFERRED)
    db.execute(
        text(
            "UPDATE referrals SET status = 'Completed', completed_at = now(), "
            "assigned_lab_specialist_id = :lab, assigned_at = now() WHERE id = :id"
        ),
        {"id": first["id"], "lab": lab_user_id(db)},
    )
    db.commit()
    assert c.get("/api/v1/referrals", params={"status": "Completed"}).json()["total"] == 1
    assert c.get("/api/v1/referrals", params={"status": "Sent"}).json()["total"] == 1
    assert c.get("/api/v1/referrals", params={"search": first["referralNumber"].lower()}).json()["total"] == 1
    assert c.get("/api/v1/referrals", params={"search": "пацієнт"}).json()["total"] == 2
    assert c.get("/api/v1/referrals", params={"search": "нікого"}).json()["total"] == 0


def test_assessment_text_only_keeps_status(doctor, db):
    user, c = doctor
    for status in (OPEN, FOLLOW_UP, REFERRED):
        case = make_case(c)
        force_status(db, case["id"], status, user.id)
        r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"doctorAssessment": "Оновлена оцінка"})
        assert r.status_code == 200 and r.json()["status"] == status
        assert r.json()["doctorAssessment"] == "Оновлена оцінка"


def test_other_doctor_and_other_roles(doctor, make_user, login_as):
    _, c = doctor
    case = make_case(c)
    ref = act(c, case["id"], REFERRED).json()["referral"]
    other_case = make_case(c)

    b = login_as(make_user(Role.DOCTOR))
    assert act(b, other_case["id"], CLOSED).status_code == 404
    assert b.post(f"/api/v1/cases/{other_case['id']}/reopen").status_code == 404
    assert b.get(f"/api/v1/referrals/{ref['id']}").status_code == 404
    assert b.get("/api/v1/referrals").json()["total"] == 0
    assert c.get(f"/api/v1/cases/{other_case['id']}").json()["status"] == OPEN

    admin = login_as(make_user(Role.ADMIN))
    assert act(admin, other_case["id"], CLOSED).status_code == 403
    assert admin.get("/api/v1/referrals").status_code == 403
    assert admin.get(f"/api/v1/referrals/{ref['id']}").status_code == 403
    lab = login_as(make_user(Role.LAB_SPECIALIST))
    assert act(lab, other_case["id"], CLOSED).status_code == 403
    assert lab.get(f"/api/v1/referrals/{ref['id']}").status_code == 200


def test_dates_use_the_display_time_zone_not_utc(doctor, monkeypatch):
    from app.core import clock

    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 25, 22, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", Fixed)
    assert clock.today_local() == date(2026, 10, 26)
    _, c = doctor
    case = make_case(c, photo=False)
    r = c.patch(f"/api/v1/cases/{case['id']}/assessment", json={"decision": "FollowUp", "followUpDate": "2026-10-25"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FOLLOW_UP_DATE_PAST"
