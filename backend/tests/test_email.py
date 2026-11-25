# ruff: noqa: F811  (fixtures imported from test_lab are used as test parameters)

from __future__ import annotations

import smtplib

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from test_lab import RESULT, approve, doctor, lab, make_referral, referral  # noqa: F401 (fixtures)

from app import cli
from app.core.config import get_settings
from app.db.models import EmailOutbox, EmailStatus, Referral
from app.email import outbox

PASSWORD = "app-pass-word-123"  # noqa: S105 (fake)


class FakeSMTP:
    instances: list[FakeSMTP] = []
    fail: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent: list = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        assert context is not None  # certificate verification on
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}")
        if FakeSMTP.fail:
            raise FakeSMTP.fail
        assert password == PASSWORD

    def send_message(self, msg):
        self.calls.append("send")
        self.sent.append(msg)


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    s = get_settings()
    for k, v in {
        "email_provider": "smtp",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "clinic@gmail.com",
        "smtp_password": SecretStr(PASSWORD),
        "smtp_from": "clinic@gmail.com",
        "smtp_from_name": "CutisAI",
        "smtp_starttls": True,
    }.items():
        monkeypatch.setattr(s, k, v)
    return FakeSMTP


def test_smtp_mailer_uses_starttls_login_and_a_neutral_utf8_letter(smtp):
    outbox.get_mailer().send("patient@example.test", outbox.Letter("Тема", "Текст листа"), None)
    (c,) = smtp.instances
    assert (c.host, c.port) == ("smtp.gmail.com", 587)
    assert c.calls == ["ehlo", "starttls", "ehlo", "login:clinic@gmail.com", "send", "quit"]
    msg = c.sent[0]
    assert msg["To"] == "patient@example.test" and msg["Subject"] == "Тема"
    assert msg["From"] == "CutisAI <clinic@gmail.com>"
    assert msg.get_content().strip() == "Текст листа" and not msg.is_multipart()  # no attachments


def test_port_465_uses_implicit_tls(smtp, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_port", 465)
    outbox.get_mailer().send("p@example.test", outbox.Letter("s", "b"), None)
    (c,) = smtp.instances
    assert isinstance(c, FakeSMTPSSL) and "starttls" not in c.calls


def test_approval_sends_the_neutral_letter_via_smtp(smtp, lab, referral, db, caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "patient_email_attach_pdf", False)
    caplog.set_level("INFO", logger="dermalab.email")
    r = approve(lab[1], referral["id"])
    assert r.status_code == 200 and r.json()["status"] == "Completed"
    row = db.scalar(select(EmailOutbox).execution_options(populate_existing=True))
    assert row.status == EmailStatus.SENT and row.sent_at is not None and row.attempts == 1
    msg = smtp.instances[0].sent[0]
    assert msg["Subject"] == "Інформація щодо результату дослідження"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Результат вашого дослідження готовий" in body and "зверніться, будь ласка, до свого лікаря" in body
    assert "карцином" not in body.lower() and referral["referralNumber"] not in body  # nothing medical
    assert list(msg.iter_attachments()) == []  # no PDF, no photo
    assert PASSWORD not in caplog.text and "patient@example.test" not in caplog.text
    assert "sent via smtp to=p***@example.test" in caplog.text


def test_smtp_failure_keeps_approval_and_records_a_safe_error(smtp, lab, referral, db, caplog):
    smtp.fail = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted " + PASSWORD.encode())
    r = approve(lab[1], referral["id"])
    assert r.status_code == 200 and r.json()["status"] == "Completed"
    row = db.scalar(select(EmailOutbox).execution_options(populate_existing=True))
    assert row.status == EmailStatus.PENDING and row.attempts == 1 and row.sent_at is None
    assert row.last_error_safe == "smtp: SMTPAuthenticationError 535"
    assert PASSWORD not in caplog.text and "Username and Password" not in caplog.text

    smtp.fail = None
    assert outbox.dispatch_pending(db) == 1
    db.refresh(row)
    assert row.status == EmailStatus.SENT and row.attempts == 2 and row.last_error_safe is None


def test_missing_smtp_settings_are_reported_without_secrets(smtp, lab, referral, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    with pytest.raises(outbox.EmailConfigError, match="SMTP_HOST"):
        outbox.get_mailer()
    assert approve(lab[1], referral["id"]).status_code == 200
    row = db.scalar(select(EmailOutbox).execution_options(populate_existing=True))
    assert row.status == EmailStatus.PENDING and row.last_error_safe == "smtp: EmailConfigError"
    assert db.scalar(select(Referral.status)).value == "Completed"


def test_cli_send_test_email(smtp, monkeypatch, capsys):
    assert cli.main(["send-test-email", "--to", "me@example.test"]) == 0
    out = capsys.readouterr().out
    assert "передано SMTP-серверу" in out and "m***@example.test" in out and "me@example.test" not in out
    assert smtp.instances[0].sent[0]["Subject"] == outbox.TEST_LETTER.subject

    smtp.fail = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    assert cli.main(["send-test-email", "--to", "me@example.test"]) == 1
    assert "SMTPAuthenticationError 535" in capsys.readouterr().err

    monkeypatch.setattr(get_settings(), "smtp_from", "")
    assert cli.main(["send-test-email", "--to", "me@example.test"]) == 2
    assert "SMTP_FROM" in capsys.readouterr().err

    monkeypatch.setattr(get_settings(), "email_provider", "log")
    assert cli.main(["send-test-email", "--to", "me@example.test"]) == 0
    assert "лише записано в журнал" in capsys.readouterr().out
