from datetime import date

from sqlalchemy import select

from app.cli import main as cli_main
from app.db.models import Patient, Role, User, UserToken

USERS = "/api/v1/admin/users"
NEW_DOCTOR = {"firstName": " Олена ", "lastName": "Коваль", "email": "Olena.Koval@Example.test", "role": "Doctor"}


def test_create_user_returns_one_time_invitation(login_as, make_user, client, db):
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(USERS, json=NEW_DOCTOR)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "olena.koval@example.test"
    assert body["user"]["firstName"] == "Олена"
    assert body["user"]["status"] == "Active" and body["user"]["hasPassword"] is False
    token = body["invitation"]["token"]
    # only the hash is stored
    assert db.scalar(select(UserToken.token_hash)) != token

    login = {"email": "olena.koval@example.test", "password": "Nowe-Haslo-123"}
    assert client.post("/api/v1/auth/login", json=login).status_code == 401
    weak = client.post("/api/v1/auth/set-password", json={"token": token, "newPassword": "123"})
    assert weak.status_code == 422
    assert (
        client.post("/api/v1/auth/set-password", json={"token": token, "newPassword": "Nowe-Haslo-123"}).status_code
        == 204
    )
    again = client.post("/api/v1/auth/set-password", json={"token": token, "newPassword": "Inne-Haslo-456"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "TOKEN_INVALID"
    assert client.post("/api/v1/auth/login", json=login).json()["role"] == "Doctor"


def test_admin_cannot_create_admins_and_email_is_unique(login_as, make_user):
    admin = login_as(make_user(Role.ADMIN))
    assert admin.post(USERS, json={**NEW_DOCTOR, "role": "Admin"}).status_code == 422
    assert admin.post(USERS, json=NEW_DOCTOR).status_code == 201
    dup = admin.post(USERS, json={**NEW_DOCTOR, "email": "OLENA.koval@example.test", "role": "LabSpecialist"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EMAIL_TAKEN"


def test_list_search_filter_and_paging(login_as, make_user):
    admin_user = make_user(Role.ADMIN)
    admin = login_as(admin_user)
    make_user(Role.DOCTOR, first_name="Андрій", last_name="Шевченко")
    make_user(Role.DOCTOR, first_name="Ірина", last_name="Бондар")
    lab = make_user(Role.LAB_SPECIALIST, first_name="Марта", last_name="Шевчук")
    r = admin.get(USERS).json()
    assert r["total"] == 3
    assert [u["lastName"] for u in r["items"]] == ["Бондар", "Шевченко", "Шевчук"]
    assert admin.get(USERS, params={"search": "шевч"}).json()["total"] == 2
    assert admin.get(USERS, params={"search": "андрій шевч"}).json()["total"] == 1
    assert admin.get(USERS, params={"role": "LabSpecialist"}).json()["items"][0]["id"] == str(lab.id)
    page2 = admin.get(USERS, params={"page": 2, "pageSize": 2}).json()
    assert page2["page"] == 2 and len(page2["items"]) == 1
    assert admin.get(f"{USERS}/{admin_user.id}").status_code == 404


def test_block_unblock_deactivate_reactivate(login_as, make_user, client):
    admin = login_as(make_user(Role.ADMIN))
    doc = make_user(Role.DOCTOR)
    doc_client = login_as(doc)
    assert admin.post(f"{USERS}/{doc.id}/block").json()["status"] == "Blocked"
    assert doc_client.get("/api/v1/auth/me").status_code == 401
    assert admin.get(USERS, params={"status": "Blocked"}).json()["total"] == 1
    assert admin.post(f"{USERS}/{doc.id}/unblock").json()["status"] == "Active"
    assert admin.post(f"{USERS}/{doc.id}/deactivate").json()["status"] == "Deactivated"
    r = admin.post(f"{USERS}/{doc.id}/unblock")
    assert r.status_code == 409
    assert admin.post(f"{USERS}/{doc.id}/password-reset").status_code == 409
    assert admin.post(f"{USERS}/{doc.id}/reactivate").json()["status"] == "Active"
    assert login_as(doc).get("/api/v1/auth/me").status_code == 200


def test_update_profile_and_role(login_as, make_user, db):
    admin = login_as(make_user(Role.ADMIN))
    uid = admin.post(USERS, json=NEW_DOCTOR).json()["user"]["id"]
    r = admin.patch(
        f"{USERS}/{uid}", json={"lastName": "Коваленко", "role": "LabSpecialist", "email": "new@example.test"}
    )
    assert r.status_code == 200
    assert (r.json()["lastName"], r.json()["role"], r.json()["email"]) == (
        "Коваленко",
        "LabSpecialist",
        "new@example.test",
    )
    assert admin.patch(f"{USERS}/{uid}", json={"firstName": "  "}).status_code == 422


def test_role_change_and_delete_blocked_when_user_has_records(login_as, make_user, db):
    admin = login_as(make_user(Role.ADMIN))
    doc = make_user(Role.DOCTOR)
    db.add(Patient(doctor_id=doc.id, first_name="Син", last_name="Тетичний", date_of_birth=date(1990, 5, 1)))
    db.commit()
    r = admin.patch(f"{USERS}/{doc.id}", json={"role": "LabSpecialist"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "USER_HAS_RECORDS"
    assert admin.delete(f"{USERS}/{doc.id}").status_code == 409
    assert db.get(User, doc.id) is not None


def test_delete_unused_account(login_as, make_user, db):
    admin = login_as(make_user(Role.ADMIN))
    uid = admin.post(USERS, json=NEW_DOCTOR).json()["user"]["id"]
    assert admin.delete(f"{USERS}/{uid}").status_code == 204
    assert admin.get(f"{USERS}/{uid}").status_code == 404


def test_password_reset_link_replaces_previous_tokens(login_as, make_user, client):
    admin = login_as(make_user(Role.ADMIN))
    doc = make_user(Role.DOCTOR)
    t1 = admin.post(f"{USERS}/{doc.id}/password-reset").json()
    t2 = admin.post(f"{USERS}/{doc.id}/password-reset").json()
    assert t2["purpose"] == "PasswordReset"
    assert (
        client.post(
            "/api/v1/auth/set-password", json={"token": t1["token"], "newPassword": "Nowe-Haslo-123"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/set-password", json={"token": t2["token"], "newPassword": "Nowe-Haslo-123"}
        ).status_code
        == 204
    )


def test_cli_create_admin_is_idempotent(clean_db, monkeypatch, db, capsys):
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("ADMIN_EMAIL", "Root@Example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin-Passw0rd-1")
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    try:
        assert cli_main(["create-admin"]) == 0
        assert cli_main(["create-admin"]) == 0
        assert "уже існує" in capsys.readouterr().out
        admins = db.scalars(select(User).where(User.role == Role.ADMIN)).all()
        assert [a.email for a in admins] == ["root@example.test"]
        assert admins[0].password_hash.startswith("$argon2id$")
    finally:
        get_settings.cache_clear()


def test_cli_rejects_weak_admin_password(clean_db, monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("ADMIN_EMAIL", "root@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "123")
    get_settings.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    try:
        assert cli_main(["create-admin"]) == 1
    finally:
        get_settings.cache_clear()
