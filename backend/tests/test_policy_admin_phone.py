# ruff: noqa: F811  (fixtures imported from other test modules are used as test parameters)

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from test_lab import approve, make_referral

from app import cli
from app.auth.password_policy import common_passwords, password_policy_errors
from app.db.models import Role, User

USERS = "/api/v1/admin/users"


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Ab1!xyzq", "щонайменше 12"),
        ("abcxyzmq!9pw", "велику літеру"),
        ("ABCXYZMQ!9PW", "малу літеру"),
        ("Abcxyzmq!pwR", "цифру"),
        ("Abcxyzmq9pwR", "спецсимвол"),
        ("Password123!", "поширених"),
        ("Qwerty!2Abcx", "послідовностей"),
        ("Zx!9aaaaPmLr", "послідовностей"),
        ("Zx!9mL1234pr", "послідовностей"),
        ("Zx!9mLйцукpr", "послідовностей"),
        ("Kovalenko#26x", "електронну пошту, ім'я чи прізвище"),
        ("Олена#2026xZq", "електронну пошту, ім'я чи прізвище"),
    ],
)
def test_policy_rejects_with_a_concrete_reason(password, reason):
    errors = password_policy_errors(password, "olena.kovalenko@x.test", ("Олена", "Коваленко", None))
    assert any(reason in e for e in errors), errors


def test_policy_accepts_a_strong_password_and_has_the_common_list():
    assert password_policy_errors("Zx!9mLpR2tq#", "olena@x.test", ("Олена", "Коваленко")) == []
    assert len(common_passwords()) == 10_000 and "qwerty" in common_passwords()


def test_api_rejects_a_weak_new_password_with_reasons(make_user, login_as):
    user = make_user(Role.DOCTOR, first_name="Олена", last_name="Коваленко")
    c = login_as(user)
    r = c.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "Sicher-Passw0rt", "newPassword": "Коваленко-2026x"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    assert "ім'я чи прізвище" in r.json()["error"]["message"]


def test_admin_without_a_name(make_user, login_as, db, capsys, monkeypatch):
    admin = make_user(Role.ADMIN, first_name=None, last_name=None)
    me = login_as(admin).get("/api/v1/auth/me").json()
    assert me["firstName"] is None and me["lastName"] is None

    monkeypatch.setenv("ADMIN_PASSWORD", "Zx!9mLpR2tq#")
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_password", "Zx!9mLpR2tq#")
    assert cli.main(["create-admin", "--email", "boss@example.test"]) == 0
    created = db.scalar(select(User).where(User.email == "boss@example.test"))
    assert created.first_name is None and created.last_name is None

    with pytest.raises(Exception, match="staff_has_name"):
        make_user(Role.DOCTOR, first_name=None, last_name=None)


def test_staff_phone_in_admin_api_profile_referral_and_pdf(make_user, login_as, db, storage_root):
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(
        USERS,
        json={
            "firstName": "Олена",
            "lastName": "Коваленко",
            "email": "olena.k@example.test",
            "role": "Doctor",
            "phone": " +380 (44) 555-01-02 ",
        },
    )
    assert r.status_code == 201 and r.json()["user"]["phone"] == "+380 (44) 555-01-02"
    uid = r.json()["user"]["id"]
    assert admin.patch(f"{USERS}/{uid}", json={"phone": "abc"}).status_code == 422
    assert admin.patch(f"{USERS}/{uid}", json={"firstName": "Олена"}).json()["phone"] == "+380 (44) 555-01-02"

    doc = make_user(Role.DOCTOR, first_name="Ірина", last_name="Бондар", phone="+380 67 000 11 22")
    lab_user = make_user(Role.LAB_SPECIALIST, first_name="Тарас", last_name="Мельник")
    dc, lc = login_as(doc), login_as(lab_user)
    assert dc.get("/api/v1/auth/me").json()["phone"] == "+380 67 000 11 22"
    ref = make_referral(dc, db, storage_root)
    assert lc.get(f"/api/v1/referrals/{ref['id']}").json()["doctor"]["phone"] == "+380 67 000 11 22"
    assert lc.post(f"/api/v1/referrals/{ref['id']}/start").status_code == 200
    assert approve(lc, ref["id"]).status_code == 200
    pdf = dc.get(f"/api/v1/referrals/{ref['id']}/lab-result.pdf").content
    text = " ".join("\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split())
    assert "Телефон +380 67 000 11 22" in text


def test_frontend_uses_the_same_common_passwords_list():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    backend = (root / "backend/app/auth/common_passwords.txt").read_bytes()
    assert (root / "frontend/public/common-passwords.txt").read_bytes() == backend
