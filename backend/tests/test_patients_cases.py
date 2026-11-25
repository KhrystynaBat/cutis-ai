from datetime import timedelta

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from app.core.clock import today_local
from app.db.models import AuditEvent, Case, CaseImage, CaseStatus, Role

PATIENT = {
    "firstName": "Синтетичний",
    "lastName": "Пацієнт",
    "dateOfBirth": "1985-04-12",
    "email": "",
    "phone": "+380 (44) 123-45-67",
    "notes": "  ",
}


def jpeg(w: int = 320, h: int = 240) -> bytes:
    img = np.random.default_rng(0).integers(0, 256, (h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def png(w: int = 200, h: int = 200) -> bytes:
    ok, buf = cv2.imencode(".png", np.full((h, w, 3), 128, np.uint8))
    return buf.tobytes()


@pytest.fixture
def doctors(make_user, login_as):
    a, b = make_user(Role.DOCTOR), make_user(Role.DOCTOR)
    return login_as(a), login_as(b)


def new_patient(c, **over):
    r = c.post("/api/v1/patients", json={**PATIENT, **over})
    assert r.status_code == 201, r.text
    return r.json()


def new_case(c, patient_id, **over):
    body = {
        "patientId": patient_id,
        "examinedAt": today_local().isoformat(),
        "bodyLocation": "спина",
        "clinicalDescription": "Пігментне утворення 6 мм",
        **over,
    }
    r = c.post("/api/v1/cases", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(c, case_id, data: bytes, name="photo.jpg", mime="image/jpeg"):
    return c.post(f"/api/v1/cases/{case_id}/images", files={"file": (name, data, mime)})


def test_create_and_edit_patient(doctors):
    a, _ = doctors
    p = new_patient(a)
    assert p["email"] is None and p["notes"] is None
    assert p["casesCount"] == 0 and p["age"] >= 40
    r = a.patch(f"/api/v1/patients/{p['id']}", json={"lastName": "Змінений", "email": "p@example.test"})
    assert r.status_code == 200
    assert (r.json()["lastName"], r.json()["email"]) == ("Змінений", "p@example.test")
    assert a.patch(f"/api/v1/patients/{p['id']}", json={"firstName": None}).status_code == 422


@pytest.mark.parametrize(
    "override",
    [
        {"dateOfBirth": (today_local() + timedelta(days=1)).isoformat()},
        {"dateOfBirth": "1850-01-01"},
        {"email": "not-an-email"},
        {"phone": "abc"},
        {"firstName": "   "},
        {"notes": "x" * 2001},
    ],
)
def test_patient_validation(doctors, override):
    a, _ = doctors
    assert a.post("/api/v1/patients", json={**PATIENT, **override}).status_code == 422


def test_patient_search_and_archive(doctors):
    a, _ = doctors
    new_patient(a, lastName="Мельник")
    p2 = new_patient(a, lastName="Ткаченко")
    assert a.get("/api/v1/patients", params={"search": "мельн"}).json()["total"] == 1
    assert a.post(f"/api/v1/patients/{p2['id']}/archive").json()["isArchived"] is True
    assert a.get("/api/v1/patients").json()["total"] == 1
    assert a.get("/api/v1/patients", params={"includeArchived": True}).json()["total"] == 2
    r = a.post(
        "/api/v1/cases",
        json={"patientId": p2["id"], "examinedAt": "2026-01-01", "bodyLocation": "x", "clinicalDescription": "y"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "PATIENT_ARCHIVED"


def test_case_lifecycle_with_photo(doctors, storage_root, db):
    a, _ = doctors
    p = new_patient(a)
    c = new_case(a, p["id"])
    assert c["status"] == "Open" and c["image"] is None and c["isEditable"] is True

    data = jpeg()
    r = upload(a, c["id"], data, name="../../etc/Мій знімок?.jpg")
    assert r.status_code == 201, r.text
    img = r.json()
    assert img["mimeType"] == "image/jpeg" and img["byteSize"] == len(data)
    assert "/" not in img["originalFilename"] and ".." not in img["originalFilename"]

    row = db.scalar(select(CaseImage))
    assert row.storage_key.startswith("images/") and "Мій" not in row.storage_key
    assert (storage_root / row.storage_key).read_bytes() == data

    got = a.get(img["url"])
    assert got.status_code == 200 and got.content == data
    assert got.headers["content-type"] == "image/jpeg"
    assert "no-store" in got.headers["cache-control"] and got.headers["x-content-type-options"] == "nosniff"

    detail = a.get(f"/api/v1/cases/{c['id']}").json()
    assert detail["image"]["id"] == img["id"] and detail["hasImage"] is True
    listed = a.get("/api/v1/cases", params={"patientId": p["id"]}).json()
    assert listed["total"] == 1 and listed["items"][0]["hasImage"] is True
    assert a.get(f"/api/v1/patients/{p['id']}").json()["casesCount"] == 1

    img2 = upload(a, c["id"], png()).json()
    assert a.get(f"/api/v1/cases/{c['id']}").json()["image"]["id"] == img2["id"]
    assert a.get(img["url"]).status_code == 200

    actions = {e.action for e in db.scalars(select(AuditEvent))}
    assert {"patient_created", "case_created", "case_image_uploaded"} <= actions


@pytest.mark.parametrize(
    ("data", "name", "mime", "status", "code"),
    [
        (b"%PDF-1.7 not an image", "scan.pdf", "application/pdf", 415, "UNSUPPORTED_FILE_TYPE"),
        (b"just text", "photo.jpg", "image/jpeg", 415, "UNSUPPORTED_FILE_TYPE"),  # name/MIME lie
        (b"\xff\xd8\xff\xe0" + b"\x00" * 100, "broken.jpg", "image/jpeg", 422, "IMAGE_DECODE_FAILED"),
        (b"", "empty.jpg", "image/jpeg", 422, "FILE_EMPTY"),
    ],
)
def test_upload_rejects_non_images(doctors, data, name, mime, status, code):
    a, _ = doctors
    c = new_case(a, new_patient(a)["id"])
    r = upload(a, c["id"], data, name, mime)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert a.get(f"/api/v1/cases/{c['id']}").json()["image"] is None


def test_upload_rejects_too_small_and_too_large(doctors, monkeypatch):
    from app.core.config import get_settings

    a, _ = doctors
    c = new_case(a, new_patient(a)["id"])
    r = upload(a, c["id"], jpeg(40, 40))
    assert r.status_code == 422 and r.json()["error"]["code"] == "IMAGE_TOO_SMALL"

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = np.random.default_rng(1).integers(0, 256, (1200, 1200, 3), dtype=np.uint8)
    data = cv2.imencode(".png", big)[1].tobytes()
    assert len(data) > 1024 * 1024
    r = upload(a, c["id"], data, "big.png", "image/png")
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_case_validation(doctors):
    a, _ = doctors
    p = new_patient(a, dateOfBirth="2000-01-01")
    base = {"patientId": p["id"], "examinedAt": "2026-01-01", "bodyLocation": "спина", "clinicalDescription": "опис"}
    tomorrow = (today_local() + timedelta(days=1)).isoformat()
    assert a.post("/api/v1/cases", json={**base, "examinedAt": tomorrow}).status_code == 422
    r = a.post("/api/v1/cases", json={**base, "examinedAt": "1999-12-31"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "DATE_CONFLICT"
    assert a.post("/api/v1/cases", json={**base, "bodyLocation": "  "}).status_code == 422


def test_case_and_photo_editable_only_when_open(doctors, db):
    a, _ = doctors
    c = new_case(a, new_patient(a)["id"])
    assert a.patch(f"/api/v1/cases/{c['id']}", json={"bodyLocation": "плече"}).json()["bodyLocation"] == "плече"
    row = db.get(Case, c["id"])
    row.status = CaseStatus.FOLLOW_UP_PLANNED
    row.follow_up_date = today_local() + timedelta(days=7)  # required by the DB in this status
    db.commit()
    r = a.patch(f"/api/v1/cases/{c['id']}", json={"bodyLocation": "стегно"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_NOT_EDITABLE"
    assert upload(a, c["id"], jpeg()).status_code == 409
    assert a.get(f"/api/v1/cases/{c['id']}").json()["isEditable"] is False


def test_upload_rate_limit(doctors, app):
    a, _ = doctors
    c = new_case(a, new_patient(a)["id"])
    app.state.upload_limiter.max_failures = 2
    assert upload(a, c["id"], jpeg()).status_code == 201
    assert upload(a, c["id"], b"junk").status_code == 415  # failed attempts count too
    r = upload(a, c["id"], jpeg())
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_UPLOADS"


def test_doctor_cannot_see_or_touch_another_doctors_records(doctors):
    a, b = doctors
    p = new_patient(a)
    c = new_case(a, p["id"])
    img = upload(a, c["id"], jpeg()).json()

    assert b.get("/api/v1/patients").json()["total"] == 0
    assert b.get("/api/v1/cases").json()["total"] == 0
    assert b.get("/api/v1/cases", params={"patientId": p["id"]}).json()["total"] == 0
    for r in (
        b.get(f"/api/v1/patients/{p['id']}"),
        b.patch(f"/api/v1/patients/{p['id']}", json={"lastName": "Злам"}),
        b.post(f"/api/v1/patients/{p['id']}/archive"),
        b.get(f"/api/v1/cases/{c['id']}"),
        b.patch(f"/api/v1/cases/{c['id']}", json={"bodyLocation": "x"}),
        upload(b, c["id"], jpeg()),
        b.get(img["url"]),
        b.post(
            "/api/v1/cases",
            json={"patientId": p["id"], "examinedAt": "2026-01-01", "bodyLocation": "x", "clinicalDescription": "y"},
        ),
    ):
        assert r.status_code == 404, r.request.url
    other = new_case(a, p["id"])
    assert a.get(f"/api/v1/cases/{other['id']}/images/{img['id']}").status_code == 404
    assert a.get(f"/api/v1/patients/{p['id']}").json()["lastName"] == "Пацієнт"
    dash_b = b.get("/api/v1/doctor/dashboard").json()
    assert dash_b["patients"] == 0 and dash_b["recentCases"] == []


@pytest.mark.parametrize("role", [Role.ADMIN, Role.LAB_SPECIALIST])
def test_other_roles_have_no_access_to_patients_or_images(doctors, make_user, login_as, role):
    a, _ = doctors
    p = new_patient(a)
    c = new_case(a, p["id"])
    img = upload(a, c["id"], jpeg()).json()
    other = login_as(make_user(role))
    for r in (other.get("/api/v1/patients"), other.get(f"/api/v1/cases/{c['id']}"), other.get(img["url"])):
        assert r.status_code == 403


def test_dashboard_counters(doctors):
    a, _ = doctors
    p = new_patient(a)
    new_case(a, p["id"])
    new_case(a, p["id"])
    d = a.get("/api/v1/doctor/dashboard").json()
    assert (d["patients"], d["activeCases"], d["pendingReferrals"], d["readyResults"]) == (1, 2, 0, 0)
    assert len(d["recentCases"]) == 2 and d["recentCases"][0]["patient"]["id"] == p["id"]
