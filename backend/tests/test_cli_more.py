from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.db.models import Role, User


@pytest.fixture
def fresh_settings(monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session

    def _apply(**env: str | None) -> None:
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        db_session.get_engine.cache_clear()
        db_session.get_sessionmaker.cache_clear()

    yield _apply
    get_settings.cache_clear()


def test_create_admin_needs_an_email(clean_db, fresh_settings, capsys):
    fresh_settings(ADMIN_EMAIL="", ADMIN_PASSWORD="Admin-Passw0rd-1")
    assert cli_main(["create-admin"]) == 2
    assert "ADMIN_EMAIL" in capsys.readouterr().err


def test_create_admin_without_password_and_without_a_terminal(clean_db, fresh_settings, monkeypatch, capsys):
    fresh_settings(ADMIN_EMAIL="root@example.test", ADMIN_PASSWORD="")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli_main(["create-admin"]) == 2
    assert "інтерактивний ввід недоступний" in capsys.readouterr().err


def test_create_admin_interactive_password(clean_db, fresh_settings, monkeypatch, db):
    fresh_settings(ADMIN_EMAIL="root@example.test", ADMIN_PASSWORD="")

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", Tty(""))
    answers = iter(["Zx!9mLpR2tq#", "Different-1!"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(answers))
    assert cli_main(["create-admin"]) == 2

    answers = iter(["Zx!9mLpR2tq#", "Zx!9mLpR2tq#"])
    assert cli_main(["create-admin"]) == 0
    admin = db.scalar(select(User).where(User.role == Role.ADMIN))
    assert admin.email == "root@example.test"
    assert admin.first_name is None and admin.last_name is None


def test_process_outbox_reports_the_provider(clean_db, fresh_settings, capsys):
    fresh_settings(EMAIL_PROVIDER="log")
    assert cli_main(["process-outbox"]) == 0
    out = capsys.readouterr().out
    assert "Оброблено листів: 0" in out and "provider=log" in out


def test_regenerate_lab_pdfs_with_nothing_to_do(clean_db, fresh_settings, tmp_path, capsys):
    fresh_settings(STORAGE_DIR=str(tmp_path))
    assert cli_main(["regenerate-lab-pdfs"]) == 0
    assert "Згенеровано PDF за новим шаблоном: 0" in capsys.readouterr().out
