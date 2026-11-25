from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select, text
from test_case_workflow import add_analysis
from test_patients_cases import jpeg, new_case, new_patient, upload

from app.core.clock import today_local
from app.db.models import (
    AnalysisStatus,
    AuditEvent,
    EmailOutbox,
    EmailStatus,
    LabResult,
    Notification,
    Referral,
    Role,
    XaiArtifact,
    XaiMethod,
    XaiStatus,
)
from app.email import outbox
from app.storage.local import LocalStorage

TODAY = today_local().isoformat()
RESULT = {
    "labAccessionNumber": "hp-26-0042",
    "histopathologyDiagnosis": "Базальноклітинна карцинома, нодулярний тип",
    "histopathologyDescription": "Гнізда базалоїдних клітин з периферичною палісадою.\nКраї резекції вільні.",
    "examinedAt": TODAY,
    "comment": "Ґрунтовний опис — у протоколі №7",
}


def count(db, model, **where) -> int:
    stmt = select(func.count()).select_from(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return db.scalar(stmt.execution_options(populate_existing=True))


@pytest.fixture
def doctor(make_user, login_as):
    user = make_user(Role.DOCTOR, first_name="Світлана", last_name="Будак")
    return user, login_as(user)


@pytest.fixture
def lab(make_user, login_as):
    user = make_user(Role.LAB_SPECIALIST, first_name="Тарас", last_name="Франко")
    return user, login_as(user)


def make_referral(c, db, storage_root, *, email: str = "patient@example.test", with_ai: bool = True) -> dict:
    patient = new_patient(c, email=email, lastName="Шевченко", firstName="Ганна")
    case = new_case(c, patient["id"])
    assert upload(c, case["id"], jpeg()).status_code == 201
    if with_ai:
        analysis_id = add_analysis(db, case["id"], AnalysisStatus.COMPLETED, 5, "bcc")
        storage = LocalStorage(storage_root)
        for method, status in ((XaiMethod.GRADCAM, XaiStatus.COMPLETED), (XaiMethod.GRADCAM_PP, XaiStatus.FAILED)):
            db.add(
                XaiArtifact(
                    analysis_id=analysis_id,
                    method=method,
                    component_name="AlexNet",
                    layer_name="activation_5",
                    storage_key=storage.put(b"\x89PNG fake map", "xai", ".png")
                    if status == XaiStatus.COMPLETED
                    else None,
                    status=status,
                    error_code=None if status == XaiStatus.COMPLETED else "XAI_ZERO_GRADIENT",
                )
            )
        db.commit()
    r = c.patch(
        f"/api/v1/cases/{case['id']}/assessment",
        json={"decision": "Refer", "referralReason": "Виключити BCC", "doctorAssessment": "Підозра на BCC"},
    )
    assert r.status_code == 200, r.text
    return {"case": case, "patient": patient, **r.json()["referral"]}


@pytest.fixture
def referral(doctor, db, storage_root):
    return make_referral(doctor[1], db, storage_root)


def approve(c, ref_id: str, body: dict | None = RESULT):
    url = f"/api/v1/referrals/{ref_id}/lab-result/approve"
    return c.post(url, json=body) if body is not None else c.post(url)


def test_lab_sees_all_referrals_new_first(doctor, lab, make_user, login_as, db, storage_root, referral):
    _, lc = lab
    other = login_as(make_user(Role.DOCTOR, first_name="Марія", last_name="Шевченко"))
    second = make_referral(other, db, storage_root, with_ai=False)
    lc.post(f"/api/v1/referrals/{referral['id']}/start")

    lst = lc.get("/api/v1/referrals").json()
    assert lst["total"] == 2
    assert [i["status"] for i in lst["items"]] == ["Sent", "InProgress"]  # new ones first
    assert lst["items"][0]["id"] == second["id"] and lst["items"][0]["doctor"]["lastName"] == "Шевченко"
    assert lc.get("/api/v1/referrals", params={"status": "InProgress"}).json()["total"] == 1
    assert lc.get("/api/v1/referrals", params={"search": referral["referralNumber"]}).json()["total"] == 1
    # each doctor still sees only their own
    assert doctor[1].get("/api/v1/referrals").json()["total"] == 1


def test_lab_detail_photo_ai_and_xai_only_through_the_referral(doctor, lab, referral, db, storage_root):
    _, dc = doctor
    _, lc = lab
    d = lc.get(f"/api/v1/referrals/{referral['id']}").json()
    assert d["doctor"]["lastName"] == "Будак" and d["reason"] == "Виключити BCC"
    assert d["case"]["clinicalDescription"] == "Пігментне утворення 6 мм"
    assert d["case"]["doctorAssessment"] == "Підозра на BCC" and d["labResult"] is None
    assert d["analysis"]["predictedClass"]["code"] == "bcc"

    photo = lc.get(d["case"]["image"]["url"])
    assert photo.status_code == 200 and photo.headers["cache-control"] == "private, no-store"
    assert photo.content == dc.get(f"/api/v1/cases/{referral['case']['id']}/images/{d['case']['image']['id']}").content
    assert lc.get(d["analysisImageUrl"]).status_code == 200

    done = [x for x in d["analysis"]["xai"] if x["status"] == "Completed"]
    failed = [x for x in d["analysis"]["xai"] if x["status"] == "Failed"]
    assert done[0]["url"] == f"/api/v1/referrals/{referral['id']}/xai/{done[0]['id']}"
    assert lc.get(done[0]["url"]).content == b"\x89PNG fake map"
    assert failed[0]["url"] is None and failed[0]["reason"]

    other = make_referral(dc, db, storage_root)
    od = lc.get(f"/api/v1/referrals/{other['id']}").json()
    other_map = next(x for x in od["analysis"]["xai"] if x["url"])
    assert lc.get(f"/api/v1/referrals/{referral['id']}/xai/{other_map['id']}").status_code == 404
    assert lc.get(f"/api/v1/referrals/{referral['id']}/images/{od['case']['image']['id']}").status_code == 404
    assert lc.get(f"/api/v1/cases/{referral['case']['id']}").status_code == 403
    assert lc.get(f"/api/v1/analyses/{d['analysis']['id']}").status_code == 403
    assert (
        lc.patch(f"/api/v1/cases/{referral['case']['id']}/assessment", json={"doctorAssessment": "x"}).status_code
        == 403
    )
    assert upload(lc, referral["case"]["id"], jpeg()).status_code == 403


def test_roles_on_lab_endpoints(doctor, lab, referral, make_user, login_as):
    _, dc = doctor
    admin = login_as(make_user(Role.ADMIN))
    rid = referral["id"]
    for c in (dc, admin):  # only the lab starts, drafts and approves
        assert c.post(f"/api/v1/referrals/{rid}/start").status_code == 403
        assert c.put(f"/api/v1/referrals/{rid}/lab-result/draft", json=RESULT).status_code == 403
        assert approve(c, rid).status_code == 403
    for path in ("", "/lab-result", "/lab-result.pdf"):
        assert admin.get(f"/api/v1/referrals/{rid}{path}").status_code == 403
    b = login_as(make_user(Role.DOCTOR))  # another doctor: 404 everywhere
    for path in ("", "/lab-result", "/lab-result.pdf", f"/images/{uuid.uuid4()}"):
        assert b.get(f"/api/v1/referrals/{rid}{path}").status_code == 404
    assert lab[1].get(f"/api/v1/referrals/{uuid.uuid4()}").status_code == 404


def test_start_is_sent_to_in_progress_once(lab, referral, db):
    _, lc = lab
    r = lc.post(f"/api/v1/referrals/{referral['id']}/start")
    assert r.status_code == 200 and r.json()["status"] == "InProgress" and r.json()["startedAt"]
    again = lc.post(f"/api/v1/referrals/{referral['id']}/start")
    assert again.status_code == 200 and again.json()["startedAt"] == r.json()["startedAt"]
    assert count(db, AuditEvent, action="referral_started") == 1


def test_draft_keeps_status_and_is_hidden_from_the_doctor(doctor, lab, referral, db):
    _, dc = doctor
    _, lc = lab
    rid = referral["id"]
    draft = {"labAccessionNumber": " hp-26-0042 ", "comment": " "}
    r = lc.put(f"/api/v1/referrals/{rid}/lab-result/draft", json=draft)  # take it first
    assert r.status_code == 409 and r.json()["error"]["code"] == "REFERRAL_NOT_STARTED"
    lc.post(f"/api/v1/referrals/{rid}/start")
    r = lc.put(f"/api/v1/referrals/{rid}/lab-result/draft", json=draft)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "InProgress"
    res = body["labResult"]
    assert res["labAccessionNumber"] == "HP-26-0042" and res["comment"] is None and res["isApproved"] is False
    assert res["histopathologyDiagnosis"] is None and res["pdfUrl"] is None
    assert res["labSpecialist"]["lastName"] == "Франко"

    # update the draft
    r = lc.put(f"/api/v1/referrals/{rid}/lab-result/draft", json={**RESULT, "comment": None})
    assert r.json()["labResult"]["histopathologyDiagnosis"] == RESULT["histopathologyDiagnosis"]
    assert count(db, LabResult) == 1

    d = dc.get(f"/api/v1/referrals/{rid}").json()
    assert d["labResult"] is None and d["labAccessionNumber"] is None
    assert dc.get("/api/v1/referrals").json()["items"][0]["labAccessionNumber"] is None
    r = dc.get(f"/api/v1/referrals/{rid}/lab-result")
    assert r.status_code == 404 and r.json()["error"]["code"] == "LAB_RESULT_NOT_READY"
    assert dc.get(f"/api/v1/referrals/{rid}/lab-result.pdf").status_code == 404
    # the lab sees it
    assert lc.get(f"/api/v1/referrals/{rid}/lab-result").json()["labAccessionNumber"] == "HP-26-0042"
    assert count(db, Notification) == 0


@pytest.mark.parametrize(
    ("override", "status", "code"),
    [
        ({"examinedAt": (today_local() + timedelta(days=1)).isoformat()}, 422, "EXAMINED_AT_FUTURE"),
        ({"examinedAt": (today_local() - timedelta(days=3)).isoformat()}, 422, "EXAMINED_AT_BEFORE_REFERRAL"),
        ({"labAccessionNumber": "HP 26"}, 422, "VALIDATION_ERROR"),
        ({"histopathologyDescription": "x" * 10001}, 422, "VALIDATION_ERROR"),
    ],
)
def test_draft_validation(lab, referral, override, status, code):
    lab[1].post(f"/api/v1/referrals/{referral['id']}/start")
    r = lab[1].put(f"/api/v1/referrals/{referral['id']}/lab-result/draft", json={**RESULT, **override})
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_accession_number_is_unique(doctor, lab, referral, db, storage_root):
    _, lc = lab
    other = make_referral(doctor[1], db, storage_root, with_ai=False)
    for rid in (referral["id"], other["id"]):
        lc.post(f"/api/v1/referrals/{rid}/start")
    assert lc.put(f"/api/v1/referrals/{referral['id']}/lab-result/draft", json=RESULT).status_code == 200
    r = lc.put(f"/api/v1/referrals/{other['id']}/lab-result/draft", json={**RESULT, "labAccessionNumber": "HP-26-0042"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACCESSION_EXISTS"
    assert approve(lc, other["id"]).status_code == 409
    assert db.scalar(select(Referral.status).where(Referral.id == uuid.UUID(other["id"]))).value == "InProgress"


def test_approval_requires_all_fields(lab, referral, db):
    _, lc = lab
    r = approve(lc, referral["id"], {**RESULT, "histopathologyDiagnosis": "  ", "examinedAt": None})
    assert r.status_code == 422 and r.json()["error"]["code"] == "LAB_RESULT_INCOMPLETE"
    assert "гістопатологічний висновок" in r.json()["error"]["message"] and "дата" in r.json()["error"]["message"]
    assert count(db, Referral, status="Completed") == 0 and count(db, Notification) == 0
    assert db.scalar(select(LabResult.is_approved)) in (None, False)
    assert approve(lc, referral["id"], None).status_code == 422


def test_approval_completes_notifies_and_queues_neutral_email(doctor, lab, referral, db, caplog):
    user, dc = doctor
    _, lc = lab
    lc.post(f"/api/v1/referrals/{referral['id']}/start")
    caplog.set_level("INFO", logger="dermalab.email")
    r = approve(lc, referral["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Completed" and body["completedAt"]
    res = body["labResult"]
    assert res["isApproved"] and res["approvedAt"] and res["labSpecialist"]["lastName"] == "Франко"
    assert res["pdfUrl"] == f"/api/v1/referrals/{referral['id']}/lab-result.pdf"

    n = db.scalars(select(Notification)).all()
    assert len(n) == 1 and n[0].user_id == user.id and n[0].referral_id == uuid.UUID(referral["id"])
    assert referral["referralNumber"] in n[0].message and "карцином" not in n[0].message

    mail = db.scalars(select(EmailOutbox)).all()
    assert len(mail) == 1 and mail[0].recipient_email == "patient@example.test"
    assert mail[0].status == EmailStatus.LOGGED and mail[0].attempts == 1 and mail[0].sent_at is None
    log = caplog.text
    assert "EMAIL NOT DELIVERED" in log and "Результат дослідження — CutisAI" in log and "attachments=1" in log
    assert "patient@example.test" not in log and "p***@example.test" in log
    assert "карцином" not in log.lower() and "%PDF" not in log and "Ганна" not in log

    meta = db.scalar(select(AuditEvent.metadata_json).where(AuditEvent.action == "lab_result_approved"))
    assert meta == {"from": "InProgress", "notificationCreated": True, "emailQueued": True}
    for m in db.scalars(select(AuditEvent.metadata_json)):
        assert "карцином" not in str(m).lower() and "patient@" not in str(m)

    # the doctor now sees the result
    d = dc.get(f"/api/v1/referrals/{referral['id']}").json()
    assert d["labResult"]["histopathologyDiagnosis"] == RESULT["histopathologyDiagnosis"]
    assert d["labAccessionNumber"] == "HP-26-0042"
    assert dc.get(f"/api/v1/referrals/{referral['id']}/lab-result").status_code == 200


def test_repeated_approval_creates_nothing_new(lab, referral, db):
    _, lc = lab
    first = approve(lc, referral["id"]).json()
    for again in (approve(lc, referral["id"]), approve(lc, referral["id"], None)):
        assert again.status_code == 200
        assert again.json()["labResult"]["approvedAt"] == first["labResult"]["approvedAt"]
    assert count(db, Notification) == 1 and count(db, EmailOutbox) == 1
    assert count(db, AuditEvent, action="lab_result_approved") == 1

    # an approved result cannot be changed
    r = approve(lc, referral["id"], {**RESULT, "histopathologyDiagnosis": "Інше"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RESULT_APPROVED"
    assert lc.put(f"/api/v1/referrals/{referral['id']}/lab-result/draft", json=RESULT).status_code == 409
    assert lc.post(f"/api/v1/referrals/{referral['id']}/start").status_code == 409
    assert db.scalar(select(LabResult.histopathology_diagnosis)) == RESULT["histopathologyDiagnosis"]


def test_concurrent_approvals_make_one_notification(lab, referral, login_as, db):
    user, _ = lab
    clients = [login_as(user), login_as(user)]
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda c: approve(c, referral["id"]).status_code, clients))
    assert codes == [200, 200]
    assert count(db, Notification) == 1 and count(db, EmailOutbox) == 1


def test_approval_straight_from_sent(lab, referral, db):
    r = approve(lab[1], referral["id"])
    assert r.status_code == 200 and r.json()["status"] == "Completed" and r.json()["startedAt"] is None
    meta = db.scalar(select(AuditEvent.metadata_json).where(AuditEvent.action == "lab_result_approved"))
    assert meta["from"] == "Sent"


def test_approval_is_one_transaction(lab, referral, db, monkeypatch):
    from app.services import lab_workflow

    def boom(*_):
        raise RuntimeError("db down")

    monkeypatch.setattr(lab_workflow, "_notify_doctor", boom)
    lab[1].post(f"/api/v1/referrals/{referral['id']}/start")
    from fastapi.testclient import TestClient

    c = TestClient(lab[1].app, raise_server_exceptions=False, cookies=lab[1].cookies, headers=lab[1].headers)
    r = approve(c, referral["id"])
    assert r.status_code == 500 and "db down" not in r.text
    assert db.scalar(select(Referral.status).execution_options(populate_existing=True)).value == "InProgress"
    assert count(db, LabResult) == 0 and count(db, EmailOutbox) == 0
    assert count(db, AuditEvent, action="lab_result_approved") == 0


def test_email_failure_does_not_undo_approval(lab, referral, db, monkeypatch):
    class Broken:
        provider = "log"

        def send(self, *_):
            raise ConnectionError("smtp down: secret host 10.0.0.1")

    monkeypatch.setattr(outbox, "get_mailer", lambda: Broken())
    r = approve(lab[1], referral["id"])
    assert r.status_code == 200 and r.json()["status"] == "Completed"
    row = db.scalar(select(EmailOutbox).execution_options(populate_existing=True))
    assert row.status == EmailStatus.PENDING and row.attempts == 1
    assert row.last_error_safe == "log: ConnectionError"  # no exception text

    for _ in range(4):
        outbox.dispatch_pending(db, Broken())
    db.refresh(row)
    assert row.status == EmailStatus.FAILED and row.attempts == 5
    assert outbox.dispatch_pending(db, Broken()) == 0


def test_no_email_without_address_or_when_disabled(doctor, lab, db, storage_root, monkeypatch):
    _, dc = doctor
    no_email = make_referral(dc, db, storage_root, email="", with_ai=False)
    assert approve(lab[1], no_email["id"], {**RESULT, "labAccessionNumber": "A-1"}).status_code == 200
    assert count(db, EmailOutbox) == 0

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "patient_email_notifications", False)
    disabled = make_referral(dc, db, storage_root, with_ai=False)
    assert approve(lab[1], disabled["id"], {**RESULT, "labAccessionNumber": "A-2"}).status_code == 200
    assert count(db, EmailOutbox) == 0 and count(db, Notification) == 2


def _pdf_text(content: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(content))
    return "\n".join(p.extract_text() for p in reader.pages), len(reader.pages)


def test_pdf_with_cyrillic_for_doctor_and_lab(doctor, lab, referral, db):
    _, dc = doctor
    _, lc = lab
    long = {**RESULT, "histopathologyDescription": "Гнізда базалоїдних клітин <без змін> & стroma. " * 150}
    approve(lc, referral["id"], long)

    r = dc.get(f"/api/v1/referrals/{referral['id']}/lab-result.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'inline; filename="{referral["referralNumber"]}-lab-result.pdf"'
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    dl = dc.get(f"/api/v1/referrals/{referral['id']}/lab-result.pdf?download=1")
    assert dl.headers["content-disposition"] == f'attachment; filename="{referral["referralNumber"]}-lab-result.pdf"'
    assert dl.content == r.content
    text_, pages = _pdf_text(r.content)
    flat = " ".join(text_.split())
    for expected in (
        "Результат гістопатологічного дослідження",
        "CutisAI",
        referral["referralNumber"],
        "HP-26-0042",
        "Шевченко Ганна",
        "Будак Світлана",
        "Франко Тарас",
        "Базальноклітинна карцинома, нодулярний тип",
        "<без змін> &",
        "Ґрунтовний опис",
    ):
        assert expected in flat, expected
    assert pages >= 2 and f"Сторінка {pages} з {pages}" in flat  # long text flows onto more pages
    assert "Оцінка моделі" not in flat and "bcc" not in flat  # no AI in the lab PDF
    assert "прототип" not in flat.lower()  # no prototype labels
    for heading in ("Пацієнт", "Лікар, що направив", "Лабораторний спеціаліст", "Висновок", "Опис", "Коментар"):
        assert heading in flat, heading
    assert "незалежно від результатів AI" not in flat and "AI-дані" not in flat

    assert lc.get(f"/api/v1/referrals/{referral['id']}/lab-result.pdf").content == r.content
    assert count(db, AuditEvent, action="lab_result_pdf_generated") == 1
    key = db.scalar(select(LabResult.pdf_storage_key))
    assert key.startswith("pdf/") and key.endswith(".v5.pdf")  # the template version is in the key


def test_notifications_bell_and_read(doctor, lab, referral, make_user, login_as):
    _, dc = doctor
    assert dc.get("/api/v1/notifications/unread-count").json() == {"unread": 0}
    approve(lab[1], referral["id"])
    assert dc.get("/api/v1/notifications/unread-count").json() == {"unread": 1}
    lst = dc.get("/api/v1/notifications").json()
    n = lst["items"][0]
    assert lst["total"] == 1 and n["isRead"] is False and n["title"] == "Готовий результат лабораторії"
    assert n["referral"] == {
        "id": referral["id"],
        "referralNumber": referral["referralNumber"],
        "caseId": referral["case"]["id"],
    }

    other = login_as(make_user(Role.DOCTOR))
    assert other.get("/api/v1/notifications").json()["total"] == 0
    assert other.post(f"/api/v1/notifications/{n['id']}/read").status_code == 404

    r = dc.post(f"/api/v1/notifications/{n['id']}/read")
    assert r.status_code == 200 and r.json()["isRead"] and r.json()["readAt"]
    assert dc.get("/api/v1/notifications", params={"unreadOnly": True}).json()["total"] == 0
    assert dc.post("/api/v1/notifications/read-all").json() == {"unread": 0}


def test_doctor_closes_case_after_approval(doctor, lab, referral):
    _, dc = doctor
    cid = referral["case"]["id"]
    assert "Close" not in dc.get(f"/api/v1/cases/{cid}").json()["availableActions"]
    assert dc.patch(f"/api/v1/cases/{cid}/assessment", json={"decision": "Close"}).status_code == 409

    approve(lab[1], referral["id"])
    case = dc.get(f"/api/v1/cases/{cid}").json()
    assert case["status"] == "Referred"
    assert case["availableActions"] == ["Close"] and case["referral"]["status"] == "Completed"
    assert dc.get("/api/v1/doctor/dashboard").json()["readyResults"] == 1
    waiting = dc.get("/api/v1/referrals", params={"status": "Completed", "caseStatus": "Referred"}).json()
    assert waiting["total"] == 1

    r = dc.patch(
        f"/api/v1/cases/{cid}/assessment",
        json={"decision": "Close", "doctorAssessment": "Гістологія: BCC. Направлено до онколога."},
    )
    assert r.status_code == 200 and r.json()["status"] == "Closed"
    assert dc.get("/api/v1/doctor/dashboard").json()["readyResults"] == 0
    assert dc.get(f"/api/v1/referrals/{referral['id']}/lab-result.pdf").status_code == 200


def test_database_rejects_incomplete_approved_result(lab, referral, db):
    approve(lab[1], referral["id"])
    with pytest.raises(Exception, match="approved_is_complete"):
        db.execute(text("UPDATE lab_results SET histopathology_diagnosis = NULL"))
    db.rollback()
    with pytest.raises(Exception, match="completed_has_date"):
        db.execute(text("UPDATE referrals SET completed_at = NULL"))
    db.rollback()


def test_bell_polling_does_not_extend_the_idle_timeout(doctor, db):
    from datetime import UTC, datetime

    from app.db.models import UserSession

    _, dc = doctor
    old = datetime.now(UTC) - timedelta(minutes=30)
    db.execute(text("UPDATE user_sessions SET last_seen_at = :t"), {"t": old})
    db.commit()
    poll = dc.get("/api/v1/notifications/unread-count", headers={"X-Background-Poll": "1"})
    assert poll.status_code == 200
    seen = db.scalar(select(UserSession.last_seen_at).execution_options(populate_existing=True))
    assert seen == old
    dc.get("/api/v1/notifications")
    seen = db.scalar(select(UserSession.last_seen_at).execution_options(populate_existing=True))
    assert seen > old  # a real request slides it
