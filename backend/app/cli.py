from __future__ import annotations

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Role
from app.db.session import get_sessionmaker
from app.services import users as user_service


def create_admin(args: argparse.Namespace) -> int:
    settings = get_settings()
    email = args.email or settings.admin_email
    if not email:
        print("Вкажіть --email або ADMIN_EMAIL", file=sys.stderr)
        return 2
    with get_sessionmaker()() as db:
        if user_service.get_by_email(db, email) is not None:
            print(f"Користувач {user_service.normalize_email(email)} уже існує — нічого не змінено.")
            return 0
        password = settings.admin_password
        if not password:
            if not sys.stdin.isatty():
                print("ADMIN_PASSWORD не задано, а інтерактивний ввід недоступний", file=sys.stderr)
                return 2
            password = getpass.getpass("Пароль адміністратора: ")
            if password != getpass.getpass("Повторіть пароль: "):
                print("Паролі не збігаються", file=sys.stderr)
                return 2
        try:
            user_service.create_user(
                db,
                first_name=args.first_name or None,
                last_name=args.last_name or None,
                middle_name=args.middle_name or None,
                email=email,
                role=Role.ADMIN,
                password=password,
            )
        except ApiError as e:
            print(f"Помилка: {e.message}", file=sys.stderr)
            return 1
        db.commit()
    print(f"Адміністратора {user_service.normalize_email(email)} створено.")
    return 0


def process_outbox(_: argparse.Namespace) -> int:
    from app.email import outbox

    provider = get_settings().email_provider
    with get_sessionmaker()() as db:
        done = outbox.dispatch_pending(db)
    note = "надіслано через SMTP" if provider == "smtp" else "лише записано в журнал, не доставлено"
    print(f"Оброблено листів: {done} (provider={provider}: {note})")
    return 0


def send_test_email(args: argparse.Namespace) -> int:
    from app.email import outbox

    to = outbox.mask_email(args.to)
    try:
        provider = outbox.send_test(args.to)
    except outbox.EmailConfigError as e:
        print(f"Помилка налаштувань: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Не вдалося надіслати на {to}: {outbox.safe_error(get_settings().email_provider, e)}", file=sys.stderr)
        return 1
    if provider == "smtp":
        print(f"Тестовий лист передано SMTP-серверу для {to}. Перевірте скриньку (і папку «Спам»).")
    else:
        print(f"EMAIL_PROVIDER=log: лист для {to} лише записано в журнал backend, не надіслано.")
    return 0


def regenerate_lab_pdfs(_: argparse.Namespace) -> int:
    from app.services import lab_pdf
    from app.storage.local import get_storage

    with get_sessionmaker()() as db:
        done = lab_pdf.regenerate_all(db, get_storage())
    print(f"Згенеровано PDF за новим шаблоном: {done}")
    return 0


def gate_backfill(args: argparse.Namespace) -> int:
    from app.ai.gatekeeper import GateService
    from app.services import image_gate
    from app.storage.local import get_storage

    gate = GateService.loading()
    gate.load(get_settings().models_dir)
    if gate.model is None:
        print(f"Фільтр зображень недоступний ({gate.reason_code}): нічого не змінено", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        rows = image_gate.backfill(db, get_storage(), gate, recheck=args.all)
        passed = [r for r in rows if r.score is not None and r.image.gate_passed]
        failed = [r for r in rows if r.score is not None and not r.image.gate_passed]
        errors = [r for r in rows if r.score is None]
        print(f"Перевірено фото: {len(rows)}; пройшли фільтр: {len(passed)}; не пройшли: {len(failed)}", end="")
        print(f"; не вдалося перевірити: {len(errors)}" if errors else "")
        for r in failed + errors:
            score = "—" if r.score is None else f"{r.score:.4f}"
            print(f"  case={r.image.case_id} image={r.image.id} file={r.image.original_filename!r} score={score}")
    return 0


def preview_letters(args: argparse.Namespace) -> int:
    import logging
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.models import Case, EmailOutbox, LabResult, Patient, Referral, User
    from app.email import letters, outbox

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mailer = outbox.LogMailer(show_body=True)
    now = datetime.now(UTC)
    base = get_settings().app_base_url.rstrip("/")
    dummy = "PREVIEW-not-a-real-token"
    with get_sessionmaker()() as db:
        staff = db.scalars(select(User).where(User.role != Role.ADMIN).order_by(User.last_name).limit(args.limit)).all()
        admin = db.scalars(select(User).where(User.role == Role.ADMIN)).first()
        for u in [*staff, *([admin] if admin else [])]:
            link = f"{base}/set-password#token={dummy}"
            mailer.send(u.email, letters.invitation(u, link, now + timedelta(hours=72)), None)
            mailer.send(u.email, letters.password_reset(u, link, now + timedelta(hours=24)), None)
            mailer.send(u.email, letters.login_link(u, f"{base}/login/confirm?token={dummy}", now), None)
            confirm_link = f"{base}/email/confirm?token={dummy}"
            mailer.send(u.email, letters.email_change_confirm(u, confirm_link, now + timedelta(hours=24)), None)
            mailer.send(u.email, letters.email_changed(u, outbox.mask_email(u.email)), None)
        refs = db.scalars(
            select(Referral).join(LabResult, LabResult.referral_id == Referral.id).where(LabResult.is_approved)
        ).all()
        settings = get_settings()
        for ref in refs[: args.limit]:
            patient = db.get(Patient, db.get(Case, ref.case_id).patient_id)
            row = EmailOutbox(referral_id=ref.id, patient_id=patient.id, template_key=outbox.LAB_RESULT_READY)
            for attach in (True, False):
                settings.patient_email_attach_pdf = attach
                mailer.send(patient.email or "-", outbox.lab_result_letter(db, row), None)
        mailer.send("test@example.org", letters.TEST_LETTER, None)
        db.rollback()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="create the first administrator (idempotent)")
    p.add_argument("--email")
    p.add_argument("--first-name", default=None)
    p.add_argument("--last-name", default=None)
    p.add_argument("--middle-name", default=None, help="по батькові (необов'язково)")
    p.set_defaults(func=create_admin)
    o = sub.add_parser("process-outbox", help="dispatch pending e-mails from the outbox")
    o.set_defaults(func=process_outbox)
    t = sub.add_parser("send-test-email", help="send a test letter through the configured provider")
    t.add_argument("--to", required=True)
    t.set_defaults(func=send_test_email)
    g = sub.add_parser("regenerate-lab-pdfs", help="re-render stored lab result PDFs in the current layout")
    g.set_defaults(func=regenerate_lab_pdfs)
    b = sub.add_parser("gate-backfill", help="run the dermoscopy filter on stored photos")
    b.add_argument("--all", action="store_true", help="re-check photos that already have a result")
    b.set_defaults(func=gate_backfill)
    v = sub.add_parser("preview-letters", help="write every kind of letter for real users and patients to the log")
    v.add_argument("--limit", type=int, default=3, help="staff members and approved referrals to use")
    v.set_defaults(func=preview_letters)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
