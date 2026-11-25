# ruff: noqa: F811  (fixtures imported from other test modules are used as test parameters)

from __future__ import annotations

import smtplib
from datetime import UTC, datetime, timedelta
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import func, select, update
from test_email import PASSWORD, smtp  # noqa: F401 (fixture)
from test_lab import approve, doctor, lab, make_referral, referral  # noqa: F401 (fixtures)

from app import cli
from app.core.config import get_settings
from app.db.models import AuditEvent, EmailOutbox, EmailStatus, LabResult, Role, User
from app.email import outbox
from app.storage.local import LocalStorage

USERS = "/api/v1/admin/users"
NEW_DOCTOR = {
    "firstName": "Олена",
    "lastName": "Коваленко",
    "middleName": "Петрівна",
    "email": "olena.k@example.test",
    "role": "Doctor",
}


def _rows(db):
    return db.scalars(select(EmailOutbox).execution_options(populate_existing=True)).all()


def test_patient_letter_carries_the_lab_pdf(smtp, doctor, lab, referral, db, caplog):
    caplog.set_level("INFO", logger="dermalab.email")
    assert approve(lab[1], referral["id"]).status_code == 200
    (row,) = _rows(db)
    assert row.status == EmailStatus.SENT and row.attempts == 1

    msg = smtp.instances[0].sent[0]
    assert msg["Subject"] == "Результат дослідження — CutisAI"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert body.startswith("Шановний(а) Ганно!")
    assert "Результат вашого гістопатологічного дослідження готовий. Він у вкладенні до цього листа" in body
    assert "Ваш лікар — Будак Світлана." in body
    assert body.rstrip().endswith(
        "З повагою,\nкоманда CutisAI\n\nЦе автоматичний лист, відповідати на нього не потрібно."
    )
    assert "CutisAI" in body and "карцином" not in body.lower()  # the diagnosis is only in the PDF

    (att,) = list(msg.iter_attachments())
    assert att.get_content_type() == "application/pdf"
    assert att.get_filename() == f"{referral['referralNumber']}-lab-result.pdf"
    pdf = att.get_content()
    assert pdf.startswith(b"%PDF-")
    # the same document the doctor downloads
    assert pdf == doctor[1].get(f"/api/v1/referrals/{referral['id']}/lab-result.pdf").content
    assert "patient@example.test" not in caplog.text and "Шановн" not in caplog.text and "%PDF" not in caplog.text


def test_patient_letter_uses_the_patronymic(smtp, doctor, lab, db, storage_root):
    _, dc = doctor
    ref = make_referral(dc, db, storage_root)
    pid = dc.get(f"/api/v1/referrals/{ref['id']}").json()["patient"]["id"]
    dc.patch(f"/api/v1/patients/{pid}", json={"middleName": "Михайлівна"})
    assert approve(lab[1], ref["id"]).status_code == 200
    body = smtp.instances[0].sent[0].get_body(preferencelist=("plain",)).get_content()
    assert body.startswith("Шановна Ганно Михайлівно!")


def test_invitation_link_is_emailed_and_still_shown_to_the_admin(smtp, login_as, make_user, client, db, caplog):
    caplog.set_level("INFO")
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(USERS, json=NEW_DOCTOR)
    assert r.status_code == 201, r.text
    invitation = r.json()["invitation"]
    assert invitation["emailQueued"] is True and invitation["token"]  # the dialog keeps the link

    (row,) = _rows(db)
    assert row.status == EmailStatus.SENT and row.template_key == "user_invitation"
    assert row.user_id is not None and row.patient_id is None and row.referral_id is None

    msg = smtp.instances[0].sent[0]
    assert msg["To"] == "olena.k@example.test"
    assert msg["Subject"] == "Запрошення до системи CutisAI"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    link = f"http://localhost:8080/set-password#token={invitation['token']}"
    assert body.startswith("Доброго дня, Олено Петрівно!")
    assert "Ваша роль — лікар." in body and link in body and "спрацює лише один раз і діє до" in body
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert f'<a href="{link}"' in html and "Олено Петрівно" in html
    assert invitation["token"] not in caplog.text and "olena.k@example.test" not in caplog.text
    ok = client.post("/api/v1/auth/set-password", json={"token": invitation["token"], "newPassword": "Nowe-Haslo-123"})
    assert ok.status_code == 204


def test_password_reset_link_is_emailed(smtp, login_as, make_user, monkeypatch, db):
    monkeypatch.setattr(get_settings(), "app_base_url", "https://dermalab.example.test/")
    admin = login_as(make_user(Role.ADMIN))
    lab_user = make_user(Role.LAB_SPECIALIST, first_name="Тарас", last_name="Мельник", middle_name="Іванович")
    r = admin.post(f"{USERS}/{lab_user.id}/password-reset")
    assert r.status_code == 200 and r.json()["purpose"] == "PasswordReset" and r.json()["emailQueued"] is True
    msg = smtp.instances[0].sent[0]
    assert msg["Subject"] == "Відновлення пароля в системі CutisAI"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert body.startswith("Доброго дня, Тарасе Івановичу!") and "лабораторний спеціаліст" in body
    assert f"https://dermalab.example.test/set-password#token={r.json()['token']}" in body


def test_without_real_email_the_link_is_only_in_the_dialog(login_as, make_user, db, caplog):
    caplog.set_level("INFO")
    assert get_settings().email_provider == "log"
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(USERS, json=NEW_DOCTOR)
    assert r.status_code == 201 and r.json()["invitation"]["emailQueued"] is False
    assert _rows(db) == []
    assert r.json()["invitation"]["token"] not in caplog.text


def test_failed_link_letter_does_not_block_the_admin(smtp, login_as, make_user, db, monkeypatch):
    monkeypatch.setattr(outbox, "LINK_RETRY_DELAYS", (0.0,))
    smtp.fail = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    admin = login_as(make_user(Role.ADMIN))
    r = admin.post(USERS, json=NEW_DOCTOR)
    assert r.status_code == 201 and r.json()["invitation"]["token"]
    (row,) = _rows(db)
    assert row.status == EmailStatus.FAILED and row.attempts == outbox.LINK_ATTEMPTS
    assert row.last_error_safe == "smtp: SMTPAuthenticationError 535"
    smtp.fail = None
    assert outbox.dispatch_pending(db) == 0 and smtp.instances[-1].sent == []


def test_interrupted_link_letter_is_marked_failed(login_as, make_user, db):
    user = make_user(Role.DOCTOR)
    db.add(
        EmailOutbox(
            user_id=user.id,
            recipient_email=user.email,
            template_key=outbox.USER_INVITATION,
            status=EmailStatus.PENDING,
            attempts=0,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    db.commit()
    outbox.dispatch_pending(db)
    (row,) = _rows(db)
    assert row.status == EmailStatus.FAILED and "not stored" in row.last_error_safe


def test_deleting_a_user_removes_their_link_letters(smtp, login_as, make_user, db):
    admin = login_as(make_user(Role.ADMIN))
    uid = admin.post(USERS, json=NEW_DOCTOR).json()["user"]["id"]
    assert len(_rows(db)) == 1
    assert admin.delete(f"{USERS}/{uid}").status_code == 204
    assert (
        _rows(db) == []
        and db.scalar(select(func.count()).select_from(User).where(User.email == "olena.k@example.test")) == 0
    )


def test_pdf_of_an_older_layout_is_generated_again(doctor, lab, referral, db, storage_root):
    _, dc = doctor
    approve(lab[1], referral["id"])
    url = f"/api/v1/referrals/{referral['id']}/lab-result.pdf"
    current = dc.get(url).content

    storage = LocalStorage(storage_root)
    old_key = storage.put(b"%PDF-1.4 old layout", prefix="pdf", suffix=".pdf")
    db.execute(update(LabResult).values(pdf_storage_key=old_key))
    db.commit()

    fresh = dc.get(url).content
    assert fresh.startswith(b"%PDF-") and b"old layout" not in fresh
    text = " ".join("\n".join(p.extract_text() for p in PdfReader(BytesIO(fresh)).pages).split())
    assert "Лабораторний спеціаліст" in text and len(fresh) == len(current)
    new_key = db.scalar(select(LabResult.pdf_storage_key).execution_options(populate_existing=True))
    assert new_key.endswith(".v5.pdf") and new_key != old_key
    assert not storage.exists(old_key)  # the outdated file is removed
    meta = db.scalars(select(AuditEvent.metadata_json).where(AuditEvent.action == "lab_result_pdf_generated")).all()
    assert {"template": 5, "replaced": True} in meta


def test_cli_regenerates_all_outdated_pdfs(doctor, lab, referral, db, storage_root, capsys):
    approve(lab[1], referral["id"])
    assert cli.main(["regenerate-lab-pdfs"]) == 0
    assert "Згенеровано PDF за новим шаблоном: 0" in capsys.readouterr().out

    storage = LocalStorage(storage_root)
    db.execute(update(LabResult).values(pdf_storage_key=storage.put(b"old", prefix="pdf", suffix=".pdf")))
    db.commit()
    assert cli.main(["regenerate-lab-pdfs"]) == 0
    assert "Згенеровано PDF за новим шаблоном: 1" in capsys.readouterr().out
    assert db.scalar(select(LabResult.pdf_storage_key).execution_options(populate_existing=True)).endswith(".v5.pdf")


def test_smtp_password_never_in_letters(smtp, lab, referral):
    approve(lab[1], referral["id"])
    assert PASSWORD.encode() not in smtp.instances[0].sent[0].as_bytes()
