from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.security import new_token, token_hash, verify_password
from app.auth.sessions import now_utc, revoke_user_sessions
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import EmailChangeRequest, LoginChallenge, User
from app.email import outbox

from . import audit
from . import users as user_service

LINK_INVALID = "Посилання недійсне або прострочене. Надішліть запит на зміну адреси ще раз."


@dataclass(frozen=True)
class Issued:
    outbox_id: uuid.UUID
    token: str
    expires_at: datetime
    new_email: str


def pending(db: Session, user: User) -> EmailChangeRequest | None:
    return db.scalar(
        select(EmailChangeRequest)
        .where(
            EmailChangeRequest.user_id == user.id,
            EmailChangeRequest.confirmed_at.is_(None),
            EmailChangeRequest.cancelled_at.is_(None),
            EmailChangeRequest.expires_at > now_utc(),
        )
        .order_by(EmailChangeRequest.created_at.desc())
        .limit(1)
    )


def _close_pending(db: Session, user_id: uuid.UUID, now: datetime, except_id: uuid.UUID | None = None) -> int:
    stmt = update(EmailChangeRequest).where(
        EmailChangeRequest.user_id == user_id,
        EmailChangeRequest.confirmed_at.is_(None),
        EmailChangeRequest.cancelled_at.is_(None),
        EmailChangeRequest.expires_at > now,
    )
    if except_id is not None:
        stmt = stmt.where(EmailChangeRequest.id != except_id)
    return db.execute(stmt.values(cancelled_at=now)).rowcount or 0


def request_change(db: Session, user: User, new_email: str, current_password: str) -> Issued:
    s = get_settings()
    now = now_utc()
    if not verify_password(user.password_hash, current_password):
        audit.record(db, "email_change_rejected", "user", user.id, actor_id=user.id, metadata={"reason": "password"})
        db.commit()
        raise ApiError(400, "WRONG_PASSWORD", "Поточний пароль невірний")
    new_email = user_service.normalize_email(new_email)
    if new_email == user.email:
        raise ApiError(422, "SAME_EMAIL", "Це ваша поточна адреса")
    user_service.ensure_email_free(db, new_email, except_id=user.id)
    recent = db.scalar(
        select(func.count()).where(
            EmailChangeRequest.user_id == user.id,
            EmailChangeRequest.created_at > now - timedelta(minutes=s.email_change_window_minutes),
        )
    )
    if (recent or 0) >= s.email_change_requests_max:
        raise ApiError(
            429,
            "TOO_MANY_EMAIL_CHANGES",
            f"Забагато запитів на зміну адреси. Спробуйте через {s.email_change_window_minutes} хв",
        )
    _close_pending(db, user.id, now)  # an earlier link stops working
    token = new_token()
    row = EmailChangeRequest(
        user_id=user.id,
        new_email=new_email,
        token_hash=token_hash(token),
        created_at=now,
        expires_at=now + timedelta(hours=s.email_change_ttl_hours),
    )
    db.add(row)
    outbox_id = outbox.queue_email_change_confirm(db, user, new_email)
    audit.record(db, "email_change_requested", "user", user.id, actor_id=user.id)
    db.flush()
    return Issued(outbox_id=outbox_id, token=token, expires_at=row.expires_at, new_email=new_email)


def cancel(db: Session, user: User) -> bool:
    if not _close_pending(db, user.id, now_utc()):
        return False
    audit.record(db, "email_change_cancelled", "user", user.id, actor_id=user.id)
    return True


def apply_new_email(db: Session, user: User, new_email: str, *, keep_session_id: uuid.UUID | None = None) -> uuid.UUID:
    now = now_utc()
    old_email = user.email
    user.email = new_email
    notice_id = outbox.queue_email_changed(db, user, old_email)
    revoke_user_sessions(db, user.id, except_session_id=keep_session_id)
    db.execute(
        update(LoginChallenge)
        .where(LoginChallenge.user_id == user.id, LoginChallenge.used_at.is_(None), LoginChallenge.expires_at > now)
        .values(expires_at=now)
    )
    _close_pending(db, user.id, now)
    return notice_id


def confirm(db: Session, token: str, session_user_id: uuid.UUID | None, session_id: uuid.UUID | None) -> User:
    now = now_utc()
    row = db.scalar(
        select(EmailChangeRequest).where(EmailChangeRequest.token_hash == token_hash(token)).with_for_update()
    )
    if row is None:
        raise ApiError(400, "EMAIL_CHANGE_LINK_INVALID", LINK_INVALID)
    if row.confirmed_at is not None or row.cancelled_at is not None or row.expires_at <= now:
        raise ApiError(410, "EMAIL_CHANGE_LINK_EXPIRED", LINK_INVALID)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or user.deactivated_at is not None:
        raise ApiError(400, "ACCOUNT_DISABLED", "Обліковий запис заблоковано. Зверніться до адміністратора")
    user_service.ensure_email_free(db, row.new_email, except_id=user.id)
    row.confirmed_at = now
    keep = session_id if session_user_id == user.id else None
    apply_new_email(db, user, row.new_email, keep_session_id=keep)
    audit.record(db, "email_change_confirmed", "user", user.id, actor_id=user.id)
    return user
