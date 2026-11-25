from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from test_lab import RESULT, _pdf_text, approve, make_referral

from app.core.clock import today_local
from app.db.models import AuditEvent, Role, Sex, User
from app.email import letters

ME = "/api/v1/auth/me"


@pytest.fixture
def doctor(make_user, login_as):
    user = make_user(Role.DOCTOR, first_name="Олена", last_name="Гончаренко", middle_name="Віталіївна")
    return user, login_as(user)


def test_user_edits_own_profile(doctor, db):
    user, c = doctor
    r = c.patch(
        ME,
        json={
            "lastName": "Гончаренко-Будак",
            "phone": "+380 (50) 111-22-33",
            "birthDate": "1985-04-12",
            "sex": "Female",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lastName"] == "Гончаренко-Будак"
    assert "position" not in body
    assert body["birthDate"] == "1985-04-12" and body["sex"] == "Female"
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.sex == Sex.FEMALE and stored.birth_date == date(1985, 4, 12)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "profile_updated"))
    assert sorted(event.metadata_json["fields"]) == ["birth_date", "last_name", "phone", "sex"]
    assert "1985" not in str(event.metadata_json)
    # clearing optional fields
    r = c.patch(ME, json={"phone": "", "sex": None, "birthDate": None})
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["sex"] is None
    assert c.get(ME).json()["birthDate"] is None


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"firstName": "  "}, "firstName"),
        ({"lastName": ""}, "lastName"),
        ({"phone": "abc"}, "phone"),
        ({"position": "Лікар-дерматолог"}, "position"),  # no such field any more
        ({"birthDate": "2999-01-01"}, "birthDate"),  # in the future
        ({"birthDate": f"{today_local().year - 17}-01-01"}, "birthDate"),  # younger than 18
        ({"birthDate": "1900-01-01"}, "birthDate"),  # older than 100
        ({"sex": "Other"}, "sex"),
    ],
)
def test_profile_validation_is_the_admin_s(doctor, patch, field):
    _, c = doctor
    r = c.patch(ME, json=patch)
    assert r.status_code == 422, r.text
    assert field in r.text


def test_role_and_email_cannot_be_changed_in_the_profile(doctor, db):
    user, c = doctor
    for extra in ({"role": "Admin"}, {"email": "other@example.test"}, {"id": "x"}):
        r = c.patch(ME, json={"firstName": "Олена", **extra})
        assert r.status_code == 422, extra
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.role == Role.DOCTOR and stored.email == user.email


def test_profile_is_only_one_s_own(doctor, make_user, login_as, db):
    other = make_user(Role.DOCTOR, first_name="Марія", last_name="Шевченко")
    _, c = doctor
    assert c.patch(f"/api/v1/admin/users/{other.id}", json={"firstName": "Х"}).status_code == 403
    c.patch(ME, json={"firstName": "Оля"})
    db.expire_all()
    assert db.get(User, other.id).first_name == "Марія"


def test_profile_needs_a_session_and_csrf(client, doctor):
    assert client.patch(ME, json={"firstName": "X"}).status_code == 401
    _, c = doctor
    token = c.headers.pop("X-CSRF-Token")
    assert c.patch(ME, json={"firstName": "X"}).status_code == 403
    c.headers["X-CSRF-Token"] = token


def test_admin_sets_and_lists_the_new_fields(make_user, login_as, db):
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(
        "/api/v1/admin/users",
        json={
            "firstName": "Тарас",
            "lastName": "Франко",
            "middleName": "Миколайович",
            "email": "taras@example.test",
            "role": "LabSpecialist",
            "birthDate": "1980-02-29",
            "sex": "Male",
        },
    )
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert user["sex"] == "Male" and user["birthDate"] == "1980-02-29" and "position" not in user
    listed = admin.get("/api/v1/admin/users").json()["items"]
    assert [u["role"] for u in listed if u["id"] == user["id"]] == ["LabSpecialist"]
    r = admin.patch(f"/api/v1/admin/users/{user['id']}", json={"sex": None})
    assert r.status_code == 200 and r.json()["sex"] is None
    assert admin.patch(f"/api/v1/admin/users/{user['id']}", json={"birthDate": "2999-01-01"}).status_code == 422


def test_birth_date_and_sex_are_not_in_referrals_pdf_or_letters(make_user, login_as, db, storage_root):
    doctor = make_user(
        Role.DOCTOR,
        first_name="Світлана",
        last_name="Будак",
        birth_date=date(1979, 5, 6),
        sex="Female",
    )
    lab = make_user(
        Role.LAB_SPECIALIST,
        first_name="Тарас",
        last_name="Франко",
        birth_date=date(1975, 7, 8),
        sex="Male",
    )
    dc, lc = login_as(doctor), login_as(lab)
    ref = make_referral(dc, db, storage_root)
    detail = lc.get(f"/api/v1/referrals/{ref['id']}").json()
    assert "position" not in detail["doctor"]
    assert "birthDate" not in detail["doctor"] and "sex" not in detail["doctor"]
    listed = lc.get("/api/v1/referrals").json()["items"][0]
    assert "birthDate" not in listed["doctor"] and "sex" not in listed["doctor"]

    approve(lc, ref["id"], RESULT)
    assert "position" not in dc.get(f"/api/v1/referrals/{ref['id']}").json()["labResult"]["labSpecialist"]
    text, _ = _pdf_text(dc.get(f"/api/v1/referrals/{ref['id']}/lab-result.pdf").content)
    flat = " ".join(text.split())
    assert "Будак Світлана" in flat and "Франко Тарас" in flat and "Посада" not in flat
    for hidden in ("06.05.1979", "1979-05-06", "08.07.1975", "Жіноча", "Чоловіча", "Стать"):
        assert hidden not in flat, hidden

    for letter in (
        letters.login_link(doctor, "http://x/login/confirm?token=t", doctor.created_at),
        letters.email_changed(doctor, "n***@gmail.com"),
        letters.email_change_confirm(doctor, "http://x/email/confirm?token=t", doctor.created_at),
    ):
        assert "1979" not in letter.body and "Жіноча" not in letter.body and "Стать" not in letter.body
