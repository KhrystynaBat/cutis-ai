from __future__ import annotations

import logging
import re
import smtplib
import ssl
import time
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import EmailOutbox, EmailStatus, Patient, Referral, User
from app.email import letters
from app.email.letters import TEST_LETTER, Attachment, Letter  # noqa: F401  (re-exported)

logger = logging.getLogger("dermalab.email")

LAB_RESULT_READY = "lab_result_ready"
USER_INVITATION = "user_invitation"
PASSWORD_RESET = "password_reset"  # noqa: S105 (a template key, not a password)
LOGIN_LINK = "login_link"
EMAIL_CHANGE_CONFIRM = "email_change_confirm"  # the link to the new address
EMAIL_CHANGED = "email_changed"  # the notice to the old address, without a link
LINK_TEMPLATES = (USER_INVITATION, PASSWORD_RESET, LOGIN_LINK, EMAIL_CHANGE_CONFIRM)
LINK_ATTEMPTS = 3
LINK_RETRY_DELAYS = (1.0, 3.0)
ORPHAN_AFTER = timedelta(minutes=10)


class EmailConfigError(Exception):
    pass


class Mailer(Protocol):
    provider: str
    delivers: bool

    def send(self, to: str, letter: Letter, outbox_id: uuid.UUID | None) -> None: ...


class LogMailer:
    provider = "log"
    delivers = False

    def __init__(self, show_body: bool = False):
        self.show_body = show_body

    def send(self, to: str, letter: Letter, outbox_id: uuid.UUID | None) -> None:
        if self.show_body:
            text = re.sub(r"token=[\w-]+", "token=<hidden>", letter.body)
            files = [a.filename for a in letter.attachments]
            logger.info(
                "EMAIL (provider=log) to=%s subject=%r attachments=%s\n%s",
                mask_email(to),
                letter.subject,
                files,
                text,
            )
            return
        body = "<not logged: personal data>" if letter.personal else letter.body
        logger.info(
            "EMAIL NOT DELIVERED (provider=log) outbox=%s to=%s subject=%r attachments=%d body=%r",
            outbox_id,
            mask_email(to),
            letter.subject,
            len(letter.attachments),
            body,
        )
        if letter.dev_link:
            logger.info(
                "%s LINK (provider=log, not delivered) to=%s: %s", letter.dev_link_kind, mask_email(to), letter.dev_link
            )


class SmtpMailer:
    provider = "smtp"
    delivers = True

    def __init__(self, settings: Settings):
        missing = [
            name
            for name, value in (("SMTP_HOST", settings.smtp_host), ("SMTP_FROM", settings.smtp_from))
            if not value.strip()
        ]
        if settings.smtp_username and not settings.smtp_password.get_secret_value():
            missing.append("SMTP_PASSWORD")
        if missing:
            raise EmailConfigError("EMAIL_PROVIDER=smtp, але не задано: " + ", ".join(missing))
        self.s = settings

    def _message(self, to: str, letter: Letter) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.s.smtp_from_name, self.s.smtp_from))
        msg["To"] = to
        msg["Subject"] = letter.subject
        msg["Message-ID"] = make_msgid(domain=self.s.smtp_from.partition("@")[2] or None)
        msg.set_content(letter.body, charset="utf-8")
        if letter.html:
            msg.add_alternative(letter.html, subtype="html", charset="utf-8")
        for a in letter.attachments:
            msg.add_attachment(a.content, maintype=a.maintype, subtype=a.subtype, filename=a.filename)
        return msg

    def send(self, to: str, letter: Letter, outbox_id: uuid.UUID | None) -> None:
        s = self.s
        context = ssl.create_default_context()
        timeout = s.smtp_timeout_seconds
        if s.smtp_port == 465:  # implicit TLS
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=timeout, context=context)
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout)
        with client:
            client.ehlo()
            if s.smtp_port != 465 and s.smtp_starttls:
                client.starttls(context=context)
                client.ehlo()
            if s.smtp_username:
                client.login(s.smtp_username, s.smtp_password.get_secret_value())
            client.send_message(self._message(to, letter))
        logger.info("email outbox=%s sent via smtp to=%s", outbox_id, mask_email(to))


def get_mailer() -> Mailer:
    settings = get_settings()
    return SmtpMailer(settings) if settings.email_provider == "smtp" else LogMailer()


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def safe_error(provider: str, exc: BaseException) -> str:
    code = getattr(exc, "smtp_code", None)
    return f"{provider}: {exc.__class__.__name__}" + (f" {code}" if code else "")


def queue_lab_result_ready(db: Session, referral: Referral, patient: Patient) -> bool:
    if not get_settings().patient_email_notifications or not patient.email:
        return False
    stmt = (
        insert(EmailOutbox)
        .values(
            id=uuid.uuid4(),
            patient_id=patient.id,
            referral_id=referral.id,
            recipient_email=patient.email,
            template_key=LAB_RESULT_READY,
            status=EmailStatus.PENDING,
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_email_outbox_referral_template")
        .returning(EmailOutbox.id)
    )
    return db.execute(stmt).scalar() is not None  # None: it already existed


def lab_result_letter(db: Session, row: EmailOutbox) -> Letter:
    patient = db.get(Patient, row.patient_id)
    if not get_settings().patient_email_attach_pdf:
        return letters.lab_result_neutral(patient)
    from app.services import lab_pdf
    from app.storage.local import get_storage

    ref = db.get(Referral, row.referral_id)
    doctor = db.get(User, ref.doctor_id)
    pdf = lab_pdf.pdf_bytes(db, get_storage(), ref)  # no commit: the row stays locked
    return letters.lab_result_with_pdf(patient, doctor, Attachment(f"{ref.referral_number}-lab-result.pdf", pdf))


def dispatch_pending(db: Session, mailer: Mailer | None = None, limit: int = 50) -> int:
    max_attempts = get_settings().email_max_attempts
    _fail_orphaned_link_letters(db)
    try:
        mailer = mailer or get_mailer()
        config_error = None
    except EmailConfigError as exc:
        mailer, config_error = None, exc
        logger.error("email outbox: %s", exc)
    done = 0
    tried: set[uuid.UUID] = set()
    for _ in range(limit):
        row = db.scalar(
            select(EmailOutbox)
            .where(
                EmailOutbox.status == EmailStatus.PENDING,
                EmailOutbox.template_key.not_in(LINK_TEMPLATES),
                EmailOutbox.id.not_in(tried),
            )
            .order_by(EmailOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            break
        tried.add(row.id)
        row.attempts += 1
        try:
            if config_error is not None:
                raise config_error
            if row.template_key == LAB_RESULT_READY:
                letter = lab_result_letter(db, row)
            elif row.template_key == EMAIL_CHANGED:
                letter = email_changed_letter(db, row)
            else:
                raise LookupError("unknown template")
            mailer.send(row.recipient_email, letter, row.id)
        except Exception as exc:
            row.last_error_safe = safe_error(mailer.provider if mailer else "smtp", exc)
            if row.attempts >= max_attempts:
                row.status = EmailStatus.FAILED
            logger.warning("email outbox=%s attempt %d failed: %s", row.id, row.attempts, row.last_error_safe)
        else:
            _mark_done(row, mailer)
            done += 1
        db.commit()
    return done


def _mark_done(row: EmailOutbox, mailer: Mailer) -> None:
    row.last_error_safe = None
    if mailer.delivers:
        row.status = EmailStatus.SENT
        row.sent_at = datetime.now(UTC)
    else:
        row.status = EmailStatus.LOGGED


def _fail_orphaned_link_letters(db: Session) -> None:
    db.execute(
        update(EmailOutbox)
        .where(
            EmailOutbox.template_key.in_(LINK_TEMPLATES),
            EmailOutbox.status == EmailStatus.PENDING,
            EmailOutbox.created_at < datetime.now(UTC) - ORPHAN_AFTER,
        )
        .values(status=EmailStatus.FAILED, last_error_safe="not sent: interrupted, the link is not stored")
    )
    db.commit()


def dispatch_in_background() -> None:
    from app.db.session import get_sessionmaker

    try:
        with get_sessionmaker()() as db:
            dispatch_pending(db)
    except Exception:
        logger.exception("email outbox dispatch failed")


def queue_user_link(db: Session, user: User, purpose: str) -> uuid.UUID | None:
    if get_settings().email_provider != "smtp":
        return None
    template = USER_INVITATION if purpose == "Invitation" else PASSWORD_RESET
    row = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user.id,
        recipient_email=user.email,
        template_key=template,
        status=EmailStatus.PENDING,
        attempts=0,
    )
    db.add(row)
    db.flush()
    return row.id


def queue_login_link(db: Session, user: User) -> uuid.UUID:
    row = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user.id,
        recipient_email=user.email,
        template_key=LOGIN_LINK,
        status=EmailStatus.PENDING,
        attempts=0,
    )
    db.add(row)
    db.flush()
    return row.id


def queue_email_change_confirm(db: Session, user: User, new_email: str) -> uuid.UUID:
    row = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user.id,
        recipient_email=new_email,
        template_key=EMAIL_CHANGE_CONFIRM,
        status=EmailStatus.PENDING,
        attempts=0,
    )
    db.add(row)
    db.flush()
    return row.id


def queue_email_changed(db: Session, user: User, old_email: str) -> uuid.UUID:
    row = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user.id,
        recipient_email=old_email,
        template_key=EMAIL_CHANGED,
        status=EmailStatus.PENDING,
        attempts=0,
    )
    db.add(row)
    db.flush()
    return row.id


def email_changed_letter(db: Session, row: EmailOutbox) -> Letter:
    user = db.get(User, row.user_id)
    return letters.email_changed(user, mask_email(user.email))


def user_link_letter(
    user: User, template: str, token: str, expires_at: datetime, requested_at: datetime | None = None
) -> Letter:
    base = get_settings().app_base_url.rstrip("/")
    if template == EMAIL_CHANGE_CONFIRM:
        return letters.email_change_confirm(user, f"{base}/email/confirm?token={token}", expires_at)
    if template == LOGIN_LINK:
        when = requested_at or expires_at - timedelta(minutes=get_settings().login_link_ttl_minutes)
        return letters.login_link(user, f"{base}/login/confirm?token={token}", when)
    link = f"{base}/set-password#token={token}"
    if template == USER_INVITATION:
        return letters.invitation(user, link, expires_at)
    return letters.password_reset(user, link, expires_at)


def send_user_link(
    outbox_id: uuid.UUID,
    token: str,
    expires_at: datetime,
    mailer: Mailer | None = None,
    requested_at: datetime | None = None,
) -> None:
    from app.db.session import get_sessionmaker

    try:
        with get_sessionmaker()() as db:
            row = db.scalar(select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update())
            if row is None or row.status != EmailStatus.PENDING:
                return
            user = db.get(User, row.user_id)
            letter = user_link_letter(user, row.template_key, token, expires_at, requested_at)
            for attempt in range(1, LINK_ATTEMPTS + 1):
                row.attempts = attempt
                try:
                    mailer = mailer or get_mailer()
                    mailer.send(row.recipient_email, letter, row.id)
                except Exception as exc:
                    row.last_error_safe = safe_error(mailer.provider if mailer else "smtp", exc)
                    logger.warning("email outbox=%s attempt %d failed: %s", row.id, attempt, row.last_error_safe)
                    if isinstance(exc, EmailConfigError) or attempt == LINK_ATTEMPTS:
                        row.status = EmailStatus.FAILED
                        break
                    time.sleep(LINK_RETRY_DELAYS[min(attempt - 1, len(LINK_RETRY_DELAYS) - 1)])
                else:
                    _mark_done(row, mailer)
                    break
            db.commit()
    except Exception:
        logger.exception("email outbox=%s: link letter failed", outbox_id)


def send_test(to: str) -> str:
    mailer = get_mailer()
    mailer.send(to, TEST_LETTER, None)
    return mailer.provider
