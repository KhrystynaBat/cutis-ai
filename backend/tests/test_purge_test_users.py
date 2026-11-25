# ruff: noqa: F811  (fixtures imported from test_lab are used as test parameters)

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from test_lab import approve, make_referral

from app.core.config import get_settings
from app.db.models import Case, Patient, Referral, Role, User

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "purge_test_users.py"


def run(monkeypatch, *argv: str) -> int:
    spec = importlib.util.spec_from_file_location("purge_test_users", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["purge", *argv])
    return mod.main()


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model).execution_options(populate_existing=True))


@pytest.fixture
def world(client, make_user, login_as, db, storage_root, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", storage_root)
    test_doc = make_user(Role.DOCTOR, email="e2e-x-doctor@dermalab.test")
    test_lab = make_user(Role.LAB_SPECIALIST, email="e2e-x-lab@dermalab.test")
    real_doc = make_user(Role.DOCTOR, email="real.doctor@dermalab.test")
    ref = make_referral(login_as(test_doc), db, storage_root)  # photo + 1 XAI map on disk
    approve(login_as(test_lab), ref["id"])  # + PDF on disk
    make_referral(login_as(real_doc), db, storage_root, with_ai=False)
    return real_doc


def test_dry_run_changes_nothing_then_delete_removes_only_test_data(world, monkeypatch, db, storage_root, capsys):
    files_before = sum(1 for p in storage_root.rglob("*") if p.is_file())
    assert run(monkeypatch, "--prefix", "e2e-") == 0
    assert "Пробний запуск" in capsys.readouterr().out
    assert count(db, User) == 3 and count(db, Referral) == 2

    assert run(monkeypatch, "--prefix", "e2e-", "--yes") == 0
    assert db.scalars(select(User.email).execution_options(populate_existing=True)).all() == [
        "real.doctor@dermalab.test"
    ]
    assert count(db, Patient) == 1 and count(db, Case) == 1 and count(db, Referral) == 1
    files_after = sum(1 for p in storage_root.rglob("*") if p.is_file())
    assert files_before - files_after == 3  # the test doctor's photo, XAI map and PDF
    assert files_after == 1  # the real doctor's photo stays


def test_refuses_when_a_test_account_worked_on_real_records(world, monkeypatch, db, storage_root, login_as, capsys):
    real_ref = db.scalar(select(Referral).join(Case).where(Case.doctor_id == world.id))
    lab = db.scalar(select(User).where(User.email == "e2e-x-lab@dermalab.test"))
    assert login_as(lab).post(f"/api/v1/referrals/{real_ref.id}/start").status_code == 200
    assert run(monkeypatch, "--prefix", "e2e-", "--yes") == 1
    assert "Зупинено" in capsys.readouterr().err
    assert count(db, User) == 3


def test_rejects_a_strange_prefix(monkeypatch):
    assert run(monkeypatch, "--prefix", "%") == 2
