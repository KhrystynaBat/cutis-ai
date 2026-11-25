from __future__ import annotations

import logging
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.security import token_hash
from app.auth.sessions import now_utc
from app.core.config import get_settings
from app.db.models import AuditEvent, EmailOutbox, EmailStatus, LoginChallenge, Role, User, UserSession
from app.email import letters, outbox
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
CONFIRM = "/api/v1/auth/login/confirm"
RESEND = "/api/v1/auth/login/resend"
ME = "/api/v1/auth/me"


class CapturingMailer:
    provider = "log"
    delivers = False

    def __init__(self):
        self.sent: list[tuple[str, outbox.Letter]] = []

    def send(self, to, letter, outbox_id):
        self.sent.append((to, letter))

    def tokens(self) -> list[str]:
        return [re.search(r"/login/confirm\?token=([\w-]+)", letter.body).group(1) for _, letter in self.sent]


@pytest.fixture
def mailer(monkeypatch):
    monkeypatch.setenv("LOGIN_EMAIL_CONFIRMATION", "true")
    get_settings.cache_clear()
    m = CapturingMailer()
    monkeypatch.setattr(outbox, "get_mailer", lambda: m)
    return m


@pytest.fixture
def browser(app):
    clients = []

    def _new() -> TestClient:
        c = TestClient(app)
        clients.append(c)
        return c

    yield _new
    for c in clients:
        c.close()


def _login(c: TestClient, user: User, password: str = PASSWORD):
    return c.post(LOGIN, json={"email": user.email, "password": password})


def test_two_step_sign_in(mailer, browser, make_user, db):
    user = make_user(Role.DOCTOR, email="katerynakalyna2026+doctor1@gmail.com")
    c = browser()
    r = _login(c, user)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "confirmation_required", "emailMasked": "k***@gmail.com", "expiresInMinutes": 10}
    # no session yet: only the pending cookie
    assert "dl_session" not in c.cookies and "login_pending" in c.cookies
    assert c.get(ME).status_code == 401
    assert db.scalar(select(UserSession).where(UserSession.user_id == user.id)) is None

    [(to, letter)] = mailer.sent
    assert to == user.email
    assert letter.subject == "Підтвердження входу в CutisAI"
    assert "http://localhost:8080/login/confirm?token=" in letter.body
    assert "Посилання діє 10 хвилин і спрацює лише один раз." in letter.body
    challenge_at = db.scalar(select(LoginChallenge.created_at).where(LoginChallenge.user_id == user.id))
    assert f"Час запиту: {letters.local_time(challenge_at)} (за київським часом)" in letter.body
    assert "просто проігноруйте цей лист — без підтвердження вхід не відбудеться" in letter.body
    [token] = mailer.tokens()

    # opening the link (GET) confirms nothing
    assert c.get(CONFIRM, params={"token": token}).status_code == 405
    assert db.scalar(select(LoginChallenge.used_at).where(LoginChallenge.user_id == user.id)) is None

    r = c.post(CONFIRM, json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == user.email and r.json()["role"] == "Doctor"
    assert "dl_session" in c.cookies and "dl_csrf" in c.cookies and "login_pending" not in c.cookies
    assert c.get(ME).status_code == 200
    db.expire_all()
    assert db.get(User, user.id).last_login_at is not None
    actions = {e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == str(user.id)))}
    assert {"login_link_sent", "login_confirmed"} <= actions

    # the link is single-use
    again = c.post(CONFIRM, json={"token": token})
    assert again.status_code == 410 and again.json()["error"]["code"] == "LOGIN_LINK_EXPIRED"


def test_only_hashes_are_stored(mailer, browser, make_user, db):
    user = make_user(Role.LAB_SPECIALIST)
    c = browser()
    _login(c, user)
    [token] = mailer.tokens()
    nonce = c.cookies["login_pending"]
    row = db.scalar(select(LoginChallenge).where(LoginChallenge.user_id == user.id))
    assert row.token_hash == token_hash(token) and row.browser_nonce_hash == token_hash(nonce)
    values = {str(getattr(row, col.name)) for col in LoginChallenge.__table__.columns}
    assert token not in values and nonce not in values
    out = db.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    assert out.template_key == "login_link" and out.status == EmailStatus.LOGGED
    assert token not in (out.last_error_safe or "")
    audit = db.scalars(select(AuditEvent.metadata_json).where(AuditEvent.entity_id == str(user.id))).all()
    assert token not in str(audit)


def test_wrong_password_sends_nothing(mailer, browser, make_user, db):
    user = make_user(Role.DOCTOR)
    c = browser()
    r = _login(c, user, "Wrong-password-1")
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    unknown = c.post(LOGIN, json={"email": "nobody@example.test", "password": PASSWORD})
    assert unknown.status_code == 401 and unknown.json()["error"]["message"] == r.json()["error"]["message"]
    assert mailer.sent == []
    assert "login_pending" not in c.cookies
    assert db.scalar(select(LoginChallenge)) is None


def test_blocked_user_gets_no_letter_and_cannot_confirm(mailer, browser, make_user, db):
    blocked = make_user(Role.DOCTOR, is_active=False)
    r = _login(browser(), blocked)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    assert mailer.sent == []

    user = make_user(Role.DOCTOR)
    c = browser()
    _login(c, user)
    [token] = mailer.tokens()
    db.execute(update(User).where(User.id == user.id).values(is_active=False))
    db.commit()
    r = c.post(CONFIRM, json={"token": token})
    assert r.status_code == 400 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    assert "dl_session" not in c.cookies


def test_expired_link(mailer, browser, make_user, db):
    user = make_user(Role.DOCTOR)
    c = browser()
    _login(c, user)
    [token] = mailer.tokens()
    db.execute(update(LoginChallenge).values(expires_at=now_utc() - timedelta(seconds=1)))
    db.commit()
    r = c.post(CONFIRM, json={"token": token})
    assert r.status_code == 410 and r.json()["error"]["code"] == "LOGIN_LINK_EXPIRED"
    assert r.json()["error"]["message"] == "Посилання недійсне або прострочене. Увійдіть ще раз."
    reasons = db.scalars(select(AuditEvent.metadata_json).where(AuditEvent.action == "login_link_rejected")).all()
    assert reasons == [{"reason": "expired"}]


def test_unknown_token(mailer, browser):
    r = browser().post(CONFIRM, json={"token": "x" * 43})
    assert r.status_code == 400 and r.json()["error"]["code"] == "LOGIN_LINK_INVALID"


def test_link_works_only_in_the_same_browser(mailer, browser, make_user):
    user = make_user(Role.DOCTOR)
    first = browser()
    _login(first, user)
    [token] = mailer.tokens()

    no_cookie = browser()
    r = no_cookie.post(CONFIRM, json={"token": token})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LOGIN_OTHER_BROWSER"
    assert r.json()["error"]["message"] == "Відкрийте посилання в тому браузері, де ви вводили пароль."

    other = browser()
    _login(other, make_user(Role.DOCTOR))
    assert other.post(CONFIRM, json={"token": token}).status_code == 409

    assert first.post(CONFIRM, json={"token": token}).status_code == 200


def test_confirming_ends_other_pending_sign_ins(mailer, browser, make_user):
    user = make_user(Role.DOCTOR)
    a, b = browser(), browser()
    _login(a, user)
    _login(b, user)
    token_a, token_b = mailer.tokens()
    assert b.post(CONFIRM, json={"token": token_b}).status_code == 200
    assert a.post(CONFIRM, json={"token": token_a}).status_code == 410


def test_resend_limits(mailer, browser, make_user, db):
    user = make_user(Role.DOCTOR)
    c = browser()
    _login(c, user)

    soon = c.post(RESEND)
    assert soon.status_code == 429 and soon.json()["error"]["code"] == "RESEND_TOO_SOON"
    assert len(mailer.sent) == 1

    def age_letters(seconds: int) -> None:
        db.execute(update(EmailOutbox).values(created_at=EmailOutbox.created_at - timedelta(seconds=seconds)))
        db.commit()

    age_letters(61)
    r = c.post(RESEND)
    assert r.status_code == 200 and r.json()["status"] == "confirmation_required"
    old, new = mailer.tokens()
    assert c.post(CONFIRM, json={"token": old}).status_code == 400

    for _ in range(3):  # letters 3..5
        age_letters(61)
        assert c.post(RESEND).status_code == 200
    age_letters(61)
    too_many = c.post(RESEND)
    assert too_many.status_code == 429 and too_many.json()["error"]["code"] == "TOO_MANY_LETTERS"
    blocked = _login(browser(), user)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "TOO_MANY_LETTERS"
    assert len(mailer.sent) == 5
    # after the window the latest link still works
    assert c.post(CONFIRM, json={"token": mailer.tokens()[-1]}).status_code == 200


def test_resend_without_pending_sign_in(mailer, browser):
    r = browser().post(RESEND)
    assert r.status_code == 410 and r.json()["error"]["code"] == "LOGIN_LINK_EXPIRED"


def test_switched_off_signs_in_with_the_password(browser, make_user, monkeypatch):
    monkeypatch.setattr(outbox, "get_mailer", lambda: pytest.fail("no letter expected"))
    user = make_user(Role.DOCTOR)
    c = browser()
    r = _login(c, user)
    assert r.status_code == 200 and r.json()["role"] == "Doctor"
    assert c.get(ME).status_code == 200


def test_log_provider_prints_the_link(monkeypatch, browser, make_user, caplog):
    monkeypatch.setenv("LOGIN_EMAIL_CONFIRMATION", "true")
    get_settings.cache_clear()
    user = make_user(Role.DOCTOR)
    c = browser()
    with caplog.at_level(logging.INFO, logger="dermalab.email"):
        _login(c, user)
    lines = [r.getMessage() for r in caplog.records if "SIGN-IN LINK" in r.getMessage()]
    assert len(lines) == 1 and user.email not in lines[0]
    token = re.search(r"token=([\w-]+)", lines[0]).group(1)
    assert c.post(CONFIRM, json={"token": token}).status_code == 200
