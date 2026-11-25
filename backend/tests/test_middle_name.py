from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select
from test_lab import _pdf_text, approve, doctor, lab, make_referral  # noqa: F401 (fixtures)
from test_patients_cases import new_patient

from app.core.names import full_name, given_names, short_name
from app.db.models import Patient, Role, User

USERS = "/api/v1/admin/users"


def test_name_helpers():
    p = SimpleNamespace(first_name="Марія", last_name="Шевчук", middle_name="Василівна")
    assert full_name(p) == "Шевчук Марія Василівна"
    assert short_name(p) == "Шевчук М. В."
    assert given_names(p) == "Марія Василівна"
    old = SimpleNamespace(first_name="Тарас", last_name="Франко", middle_name=None)
    assert full_name(old) == "Франко Тарас"
    assert short_name(old) == "Франко Т."
    assert given_names(old) == "Тарас"


def test_staff_middle_name_create_update_clear_and_search(login_as, make_user, db):
    admin = login_as(make_user(Role.ADMIN))
    body = {
        "firstName": "Олена",
        "lastName": "Коваленко",
        "middleName": "  Петрівна ",
        "email": "olena.k@example.test",
        "role": "Doctor",
    }
    r = admin.post(USERS, json=body)
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert user["middleName"] == "Петрівна"
    uid = user["id"]

    # search by any word order, with the patronymic
    for q in ("Коваленко Олена Петрівна", "олена петрівна", "Петрівна"):
        found = admin.get(USERS, params={"search": q}).json()["items"]
        assert [u["id"] for u in found] == [uid], q

    assert admin.patch(f"{USERS}/{uid}", json={"firstName": "Олена"}).json()["middleName"] == "Петрівна"
    assert admin.patch(f"{USERS}/{uid}", json={"middleName": "Павлівна"}).json()["middleName"] == "Павлівна"
    assert admin.patch(f"{USERS}/{uid}", json={"middleName": ""}).json()["middleName"] is None
    assert db.scalar(select(User.middle_name).where(User.email == "olena.k@example.test")) is None
    too_long = admin.patch(f"{USERS}/{uid}", json={"middleName": "я" * 101})
    assert too_long.status_code == 422

    r = admin.post(USERS, json={**body, "email": "no.middle@example.test", "middleName": None})
    assert r.status_code == 201 and r.json()["user"]["middleName"] is None


def test_profile_returns_middle_name(make_user, login_as):
    c = login_as(make_user(Role.DOCTOR, first_name="Ірина", last_name="Бондар", middle_name="Олегівна"))
    assert c.get("/api/v1/auth/me").json()["middleName"] == "Олегівна"


def test_patient_middle_name_create_update_and_search(doctor, db):  # noqa: F811
    _, c = doctor
    p = new_patient(c, firstName="Марія", lastName="Шевчук", middleName=" Василівна ")
    assert p["middleName"] == "Василівна"
    other = new_patient(c, firstName="Марія", lastName="Шевчук")  # no patronymic: still valid
    assert other["middleName"] is None

    found = c.get("/api/v1/patients", params={"search": "Шевчук Марія Василівна"}).json()["items"]
    assert [x["id"] for x in found] == [p["id"]]
    assert {x["id"] for x in c.get("/api/v1/patients", params={"search": "шевчук марія"}).json()["items"]} == {
        p["id"],
        other["id"],
    }

    r = c.patch(f"/api/v1/patients/{other['id']}", json={"middleName": "Іванівна"})
    assert r.status_code == 200 and r.json()["middleName"] == "Іванівна"
    r = c.patch(f"/api/v1/patients/{other['id']}", json={"middleName": "  "})
    assert r.json()["middleName"] is None
    assert db.scalar(select(Patient.middle_name).where(Patient.id == other["id"])) is None


def test_referrals_and_pdf_show_full_names_with_patronymic(make_user, login_as, db, storage_root):
    doc = make_user(Role.DOCTOR, first_name="Олена", last_name="Коваленко", middle_name="Петрівна")
    lab_user = make_user(Role.LAB_SPECIALIST, first_name="Тарас", last_name="Мельник", middle_name="Іванович")
    dc, lc = login_as(doc), login_as(lab_user)
    ref = make_referral(dc, db, storage_root)
    pid = dc.get(f"/api/v1/referrals/{ref['id']}").json()["patient"]["id"]
    dc.patch(f"/api/v1/patients/{pid}", json={"middleName": "Михайлівна"})

    listed = lc.get("/api/v1/referrals", params={"search": "Шевченко Ганна Михайлівна"}).json()["items"]
    assert [r["id"] for r in listed] == [ref["id"]]
    assert listed[0]["patient"]["middleName"] == "Михайлівна"
    assert listed[0]["doctor"]["middleName"] == "Петрівна"
    cases = dc.get("/api/v1/cases", params={"search": "Михайлівна"}).json()["items"]
    assert len(cases) == 1

    assert lc.post(f"/api/v1/referrals/{ref['id']}/start").status_code == 200
    detail = lc.get(f"/api/v1/referrals/{ref['id']}").json()
    assert detail["assignee"]["middleName"] == "Іванович"
    assert approve(lc, ref["id"]).status_code == 200
    text_, _ = _pdf_text(dc.get(f"/api/v1/referrals/{ref['id']}/lab-result.pdf").content)
    flat = " ".join(text_.split())
    for name in ("Шевченко Ганна Михайлівна", "Коваленко Олена Петрівна", "Мельник Тарас Іванович"):
        assert name in flat, name
