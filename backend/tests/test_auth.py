from datetime import timedelta

from sqlalchemy import select

from app.auth.security import hash_password, password_policy_errors, verify_password
from app.db.models import AuditEvent, Role, UserSession
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_password_hash_is_argon2id_and_verifies():
    h = hash_password("Довгий-пароль-1")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "Довгий-пароль-1")
    assert not verify_password(h, "інший")
    assert not verify_password(None, "будь-що")


def test_password_policy():
    assert password_policy_errors("short1")
    assert password_policy_errors("1234567890123")
    assert password_policy_errors("aaaaaaaaaaaa")
    assert password_policy_errors("doctor.one@x.test", email="doctor.one@x.test")
    assert password_policy_errors("Sicher-Passw0rt") == []


def test_login_sets_httponly_session_and_csrf_cookies(client, make_user, db):
    user = make_user(Role.DOCTOR)
    r = client.post(LOGIN, json={"email": user.email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    assert r.json() == {
        "id": str(user.id),
        "firstName": user.first_name,
        "lastName": user.last_name,
        "middleName": None,
        "phone": None,
        "birthDate": None,
        "sex": None,
        "email": user.email,
        "role": "Doctor",
        "pendingEmailMasked": None,
        "lastLoginAt": r.json()["lastLoginAt"],  # set by this sign-in
        "greetingName": "Тесте",
    }
    set_cookie = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in set_cookie if c.startswith("dl_session="))
    assert "HttpOnly" in session_cookie and "Path=/api" in session_cookie and "SameSite=lax" in session_cookie
    csrf_cookie = next(c for c in set_cookie if c.startswith("dl_csrf="))
    assert "HttpOnly" not in csrf_cookie
    stored = db.scalars(select(UserSession.token_hash)).all()
    assert client.cookies["dl_session"] not in stored and len(stored) == 1
    assert client.get(ME).json()["role"] == "Doctor"


def test_wrong_password_and_unknown_email_look_the_same(client, make_user):
    user = make_user(Role.DOCTOR)
    wrong = client.post(LOGIN, json={"email": user.email, "password": "Wrong-passw0rd"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.test", "password": "Wrong-passw0rd"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_session(client):
    r = client.get(ME)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_revokes_session(login_as, make_user):
    c = login_as(make_user(Role.DOCTOR))
    stolen = c.cookies["dl_session"]
    assert c.post("/api/v1/auth/logout").status_code == 204
    c.cookies.set("dl_session", stolen, path="/api")
    assert c.get(ME).status_code == 401


def test_unsafe_requests_need_csrf_header(login_as, make_user):
    c = login_as(make_user(Role.DOCTOR))
    del c.headers["X-CSRF-Token"]
    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    c.headers["X-CSRF-Token"] = "0" * 64
    assert c.post("/api/v1/auth/logout").status_code == 403
    assert c.get(ME).status_code == 200


def test_login_rate_limited_after_repeated_failures(client, make_user):
    user = make_user(Role.DOCTOR)
    for _ in range(5):
        assert client.post(LOGIN, json={"email": user.email, "password": "Wrong-passw0rd"}).status_code == 401
    r = client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"


def test_blocked_user_cannot_login_and_loses_sessions(login_as, make_user, client, db):
    from app.services import users as user_service

    admin = make_user(Role.ADMIN)
    doc = make_user(Role.DOCTOR)
    c = login_as(doc)
    db.add(doc)
    user_service.set_status(db, doc, "block", admin.id)
    db.commit()
    assert c.get(ME).status_code == 401
    r = client.post(LOGIN, json={"email": doc.email, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_expired_and_idle_sessions_are_rejected(login_as, make_user, db):
    from app.auth.sessions import now_utc

    c = login_as(make_user(Role.DOCTOR))
    sess = db.scalar(select(UserSession))
    sess.last_seen_at = now_utc() - timedelta(hours=2)  # idle > 60 min
    db.commit()
    assert c.get(ME).status_code == 401


def test_change_password_keeps_current_session_and_ends_others(login_as, make_user, client):
    user = make_user(Role.LAB_SPECIALIST)
    c1, c2 = login_as(user), login_as(user)
    bad = c1.post("/api/v1/auth/change-password", json={"currentPassword": "nope", "newPassword": "Nowe-Haslo-123"})
    assert bad.status_code == 400
    weak = c1.post("/api/v1/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "123"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "WEAK_PASSWORD"
    ok = c1.post("/api/v1/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "Nowe-Haslo-123"})
    assert ok.status_code == 204
    assert c1.get(ME).status_code == 200
    assert c2.get(ME).status_code == 401
    assert client.post(LOGIN, json={"email": user.email, "password": "Nowe-Haslo-123"}).status_code == 200


def test_audit_has_no_password_or_email(client, make_user, db):
    user = make_user(Role.DOCTOR)
    client.post(LOGIN, json={"email": user.email, "password": "Wrong-passw0rd"})
    client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    events = db.scalars(select(AuditEvent)).all()
    assert {"login_failed", "login"} <= {e.action for e in events}
    dumped = " ".join(str(e.metadata_json) for e in events)
    assert PASSWORD not in dumped and user.email not in dumped
