from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.sessions import now_utc
from app.db.models import AuditEvent, EmailChangeRequest, EmailOutbox, Role, User, UserSession
from app.email import outbox
from tests.conftest import PASSWORD

ME = "/api/v1/auth/me"
START = "/api/v1/auth/me/email-change"
CONFIRM = "/api/v1/auth/email-change/confirm"
NEW = "Nadia.New@Gmail.com"


class CapturingMailer:
    provider = "log"
    delivers = False

    def __init__(self):
        self.sent: list[tuple[str, outbox.Letter]] = []

    def send(self, to, letter, outbox_id):
        self.sent.append((to, letter))

    def token(self) -> str:
        bodies = [letter.body for _, letter in self.sent if "/email/confirm?token=" in letter.body]
        return re.search(r"/email/confirm\?token=([\w-]+)", bodies[-1]).group(1)


@pytest.fixture
def mailer(monkeypatch):
    m = CapturingMailer()
    monkeypatch.setattr(outbox, "get_mailer", lambda: m)
    return m


@pytest.fixture
def doctor(make_user, login_as):
    user = make_user(
        Role.DOCTOR,
        email="olena.old@example.test",
        first_name="Олена",
        last_name="Гончаренко",
        middle_name="Віталіївна",
    )
    return user, login_as(user)


def _actions(db) -> list[str]:
    return list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.occurred_at)).all())


def test_wrong_or_missing_password(doctor, mailer, db):
    _, c = doctor
    assert c.post(START, json={"newEmail": NEW}).status_code == 422
    assert c.post(START, json={"newEmail": NEW, "currentPassword": ""}).status_code == 422
    r = c.post(START, json={"newEmail": NEW, "currentPassword": "not-my-password"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "WRONG_PASSWORD"
    assert mailer.sent == [] and db.scalar(select(EmailChangeRequest)) is None


def test_full_change(doctor, mailer, db, app, login_as):
    user, c = doctor
    other_device = login_as(user)  # a second session of the same user
    r = c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    assert r.status_code == 202, r.text
    assert r.json()["pendingEmailMasked"] == "n***@gmail.com"

    to, letter = mailer.sent[-1]
    assert to == "nadia.new@gmail.com"
    assert letter.subject == "Підтвердження нової адреси в CutisAI"
    assert letter.body.startswith("Доброго дня, Олено Віталіївно!")
    assert "Підтвердіть нову адресу за посиланням" in letter.body and "команда CutisAI" in letter.body
    token = mailer.token()
    req = db.scalar(select(EmailChangeRequest))
    assert token not in req.token_hash and len(req.token_hash) == 64
    assert timedelta(hours=23, minutes=59) < req.expires_at - req.created_at <= timedelta(hours=24)

    me = c.get(ME).json()
    assert me["email"] == "olena.old@example.test" and me["pendingEmailMasked"] == "n***@gmail.com"

    assert c.get(f"{CONFIRM}?token={token}").status_code == 405
    db.expire_all()
    assert db.get(User, user.id).email == "olena.old@example.test"

    r = c.post(CONFIRM, json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json() == {"emailMasked": "n***@gmail.com", "signedIn": True}
    db.expire_all()
    assert db.get(User, user.id).email == "nadia.new@gmail.com"

    to, notice = mailer.sent[-1]
    assert to == "olena.old@example.test"
    assert notice.subject == "Адресу електронної пошти в CutisAI змінено"
    assert (
        "Адресу вашого облікового запису CutisAI змінено на n***@gmail.com. "
        "Якщо це були не ви — зверніться до адміністратора." in notice.body
    )
    assert "nadia.new" not in notice.body

    assert c.get(ME).json()["email"] == "nadia.new@gmail.com"
    assert other_device.get(ME).status_code == 401

    # the link works once
    r = c.post(CONFIRM, json={"token": token})
    assert r.status_code == 410 and r.json()["error"]["code"] == "EMAIL_CHANGE_LINK_EXPIRED"
    assert c.get(ME).json()["pendingEmailMasked"] is None

    fresh = TestClient(app)
    assert (
        fresh.post("/api/v1/auth/login", json={"email": "olena.old@example.test", "password": PASSWORD}).status_code
        == 401
    )
    assert fresh.post("/api/v1/auth/login", json={"email": NEW, "password": PASSWORD}).status_code == 200
    fresh.close()

    assert {"email_change_requested", "email_change_confirmed"} <= set(_actions(db))
    rows = db.scalars(select(EmailOutbox.template_key).where(EmailOutbox.user_id == user.id)).all()
    assert sorted(rows) == ["email_change_confirm", "email_changed"]


def test_confirm_without_a_session_ends_all_sessions(doctor, mailer, db, app):
    user, c = doctor
    c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    anonymous = TestClient(app)
    r = anonymous.post(CONFIRM, json={"token": mailer.token()})
    assert r.status_code == 200 and r.json()["signedIn"] is False
    assert c.get(ME).status_code == 401
    db.expire_all()
    assert db.scalar(select(UserSession).where(UserSession.revoked_at.is_(None))) is None
    anonymous.close()


def test_expired_and_unknown_tokens(doctor, mailer, db):
    _, c = doctor
    c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    token = mailer.token()
    db.execute(update(EmailChangeRequest).values(expires_at=now_utc() - timedelta(seconds=1)))
    db.commit()
    assert c.post(CONFIRM, json={"token": token}).status_code == 410
    r = c.post(CONFIRM, json={"token": "x" * 43})
    assert r.status_code == 400 and r.json()["error"]["code"] == "EMAIL_CHANGE_LINK_INVALID"
    assert c.get(ME).json()["email"] == "olena.old@example.test"


def test_busy_address_case_insensitive(doctor, mailer, make_user, db):
    make_user(Role.LAB_SPECIALIST, email="taken@example.test")
    _, c = doctor
    r = c.post(START, json={"newEmail": "TAKEN@example.test", "currentPassword": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["message"] == "Ця адреса вже використовується"
    r = c.post(START, json={"newEmail": "OLENA.OLD@example.test", "currentPassword": PASSWORD})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SAME_EMAIL"


def test_address_taken_before_confirmation(doctor, mailer, make_user, db):
    _, c = doctor
    c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    make_user(Role.DOCTOR, email=NEW)  # someone else got it meanwhile
    r = c.post(CONFIRM, json={"token": mailer.token()})
    assert r.status_code == 409 and r.json()["error"]["message"] == "Ця адреса вже використовується"
    assert c.get(ME).json()["email"] == "olena.old@example.test"


def test_cancel(doctor, mailer, db):
    _, c = doctor
    c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    token = mailer.token()
    assert c.delete(START).status_code == 204
    assert c.get(ME).json()["pendingEmailMasked"] is None
    assert c.post(CONFIRM, json={"token": token}).status_code == 410
    assert "email_change_cancelled" in _actions(db)


def test_a_new_request_replaces_the_previous_link(doctor, mailer, db):
    _, c = doctor
    c.post(START, json={"newEmail": "first@example.test", "currentPassword": PASSWORD})
    first = mailer.token()
    c.post(START, json={"newEmail": NEW, "currentPassword": PASSWORD})
    assert c.post(CONFIRM, json={"token": first}).status_code == 410
    assert c.post(CONFIRM, json={"token": mailer.token()}).status_code == 200
    assert c.get(ME).json()["email"] == "nadia.new@gmail.com"


def test_rate_limit(doctor, mailer, db):
    _, c = doctor
    for i in range(3):
        assert c.post(START, json={"newEmail": f"n{i}@example.test", "currentPassword": PASSWORD}).status_code == 202
    r = c.post(START, json={"newEmail": "n9@example.test", "currentPassword": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_EMAIL_CHANGES"


def test_admin_change_notifies_the_old_address_and_ends_sessions(doctor, mailer, make_user, login_as, db):
    user, c = doctor
    admin = login_as(make_user(Role.ADMIN))
    r = admin.patch(f"/api/v1/admin/users/{user.id}", json={"email": "olena.admin@example.test"})
    assert r.status_code == 200 and r.json()["email"] == "olena.admin@example.test"
    to, notice = mailer.sent[-1]
    assert to == "olena.old@example.test" and "змінено на o***@example.test" in notice.body
    assert c.get(ME).status_code == 401  # the user signs in again with the new address
