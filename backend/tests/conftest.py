from __future__ import annotations

import os
import smtplib
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, get_settings

_FROM_OUTSIDE = {"DATABASE_URL", "TEST_DATABASE_URL"}
TEST_ENV = {
    "ENVIRONMENT": "test",
    "SECRET_KEY": "test-secret-key-not-for-production",
    "AI_ENABLED": "false",
    "EMAIL_PROVIDER": "log",
    "SMTP_HOST": "",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_FROM": "",
    "ADMIN_EMAIL": "",
    "ADMIN_PASSWORD": "",
    "APP_BASE_URL": "http://localhost:8080",
    "CORS_ORIGINS": "http://localhost:4200",
    "LOGIN_EMAIL_CONFIRMATION": "false",
}


def _isolate_settings() -> None:
    if "DATABASE_URL" not in os.environ:
        from dotenv import dotenv_values

        backend_env = os.path.join(os.path.dirname(__file__), "..", ".env")
        url = dotenv_values(backend_env).get("DATABASE_URL") if os.path.isfile(backend_env) else None
        if url:
            os.environ["DATABASE_URL"] = url
    for name in Settings.model_fields:
        if name.upper() not in _FROM_OUTSIDE:
            os.environ.pop(name.upper(), None)
    os.environ.update(TEST_ENV)
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()


_isolate_settings()


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _ForbiddenSMTP:
    attempts: list[tuple[str, int]] = []

    def __init__(self, host="", port=0, *args, **kwargs):
        _ForbiddenSMTP.attempts.append((host, port))
        raise ConnectionRefusedError("tests must never connect to a real SMTP server")


@pytest.fixture(autouse=True)
def _no_real_smtp(monkeypatch):
    _ForbiddenSMTP.attempts = []
    monkeypatch.setattr(smtplib, "SMTP", _ForbiddenSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _ForbiddenSMTP)
    yield
    assert not _ForbiddenSMTP.attempts, f"a test tried to reach a real SMTP server: {_ForbiddenSMTP.attempts}"


def _test_db_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    url = make_url(_test_db_url())
    admin_url = url.set(database="postgres")
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        admin.dispose()
    except OperationalError as e:
        pytest.skip(f"PostgreSQL not reachable: {e.orig.__class__.__name__}")

    from alembic import command
    from alembic.config import Config

    rendered = url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = rendered
    get_settings.cache_clear()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield rendered


@pytest.fixture
def clean_db(test_db_url: str) -> str:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
        ).scalars()
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    engine.dispose()
    return test_db_url


@pytest.fixture
def storage_root(tmp_path):
    return tmp_path / "storage"


@pytest.fixture
def app(clean_db: str, storage_root, monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session
    from app.main import create_app
    from app.storage.local import LocalStorage, get_storage

    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    application = create_app()
    application.dependency_overrides[get_storage] = lambda: LocalStorage(storage_root)
    monkeypatch.setattr(get_settings(), "storage_dir", storage_root)
    return application


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(clean_db: str):
    from sqlalchemy.orm import Session

    engine = create_engine(clean_db)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


PASSWORD = "Sicher-Passw0rt"


@pytest.fixture
def make_user(db):
    import uuid as _uuid

    from app.db.models import Role
    from app.services import users as user_service

    def _make(role: Role, email: str | None = None, password: str = PASSWORD, **kw):
        user = user_service.create_user(
            db,
            first_name=kw.pop("first_name", "Тест"),
            last_name=kw.pop("last_name", role.value),
            email=email or f"{role.value.lower()}-{_uuid.uuid4().hex[:8]}@example.test",
            role=role,
            password=password,
            **kw,
        )
        db.commit()
        return user

    return _make


@pytest.fixture
def login_as(app):
    from fastapi.testclient import TestClient

    clients = []

    def _login(user, password: str = PASSWORD):
        c = TestClient(app)
        clients.append(c)
        r = c.post("/api/v1/auth/login", json={"email": user.email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = c.cookies["dl_csrf"]
        return c

    yield _login
    for c in clients:
        c.close()


@pytest.fixture
def client_no_db():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c
