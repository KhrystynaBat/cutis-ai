from __future__ import annotations

import smtplib

import pytest

from app.core.config import Settings, get_settings


def test_settings_are_the_fixed_test_settings(test_db_url):
    s = get_settings()
    assert s.environment == "test"
    assert s.email_provider == "log"
    assert s.smtp_host == "" and s.smtp_username == "" and s.smtp_from == ""
    assert s.smtp_password.get_secret_value() == ""
    assert s.admin_email == "" and s.admin_password == ""
    assert s.ai_enabled is False
    assert Settings.model_config["env_file"] is None  # no .env file is read in tests
    assert s.database_url.rsplit("/", 1)[-1].endswith("_test")


def test_a_real_smtp_connection_is_impossible():
    with pytest.raises(ConnectionRefusedError):
        smtplib.SMTP("smtp.example.test", 587)
    with pytest.raises(ConnectionRefusedError):
        smtplib.SMTP_SSL("smtp.example.test", 465)
    from conftest import _ForbiddenSMTP

    assert _ForbiddenSMTP.attempts == [("smtp.example.test", 587), ("smtp.example.test", 465)]
    _ForbiddenSMTP.attempts.clear()  # this test made them on purpose
