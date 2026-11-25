from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.security import new_token, token_hash
from app.auth.sessions import now_utc
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import EmailOutbox, LoginChallenge, User
from app.email import outbox

from . import audit

PENDING_COOKIE = "login_pending"

LINK_EXPIRED = "Посилання недійсне або прострочене. Увійдіть ще раз."
OTHER_BROWSER = "Відкрийте посилання в тому браузері, де ви вводили пароль."


@dataclass(frozen=True)
class Issued:
    outbox_id: object
    token: str
    expires_at: datetime
    requested_at: datetime


def _check_letter_limits(db: Session, user: User, *, cooldown: bool) -> None:
    s = get_settings()
    now = now_utc()
    window_start = now - timedelta(minutes=s.login_letters_window_minutes)
    rows = db.execute(
        select(func.count(), func.max(EmailOutbox.created_at)).where(
            EmailOutbox.user_id == user.id,
            EmailOutbox.template_key == outbox.LOGIN_LINK,
            EmailOutbox.created_at > window_start,
        )
    ).one()
    count, last = rows
    if cooldown and last is not None:
        wait = s.login_resend_cooldown_seconds - int((now - last).total_seconds())
        if wait > 0:
            raise ApiError(429, "RESEND_TOO_SOON", f"Лист можна надіслати ще раз через {wait} с")
    if count >= s.login_letters_max:
        raise ApiError(
            429,
            "TOO_MANY_LETTERS",
            f"Забагато листів для входу. Спробуйте через {s.login_letters_window_minutes} хв",
        )


def _issue_letter(db: Session, user: User, challenge: LoginChallenge) -> Issued:
    token = new_token()
    challenge.token_hash = token_hash(token)
    challenge.expires_at = now_utc() + timedelta(minutes=get_settings().login_link_ttl_minutes)
    outbox_id = outbox.queue_login_link(db, user)
    audit.record(db, "login_link_sent", "user", user.id, actor_id=user.id)
    return Issued(outbox_id=outbox_id, token=token, expires_at=challenge.expires_at, requested_at=challenge.created_at)


def start(db: Session, user: User, ip: str | None, user_agent: str | None) -> tuple[Issued, str]:
    _check_letter_limits(db, user, cooldown=False)
    nonce = secrets.token_urlsafe(32)
    challenge = LoginChallenge(
        user_id=user.id,
        token_hash="",
        browser_nonce_hash=token_hash(nonce),
        expires_at=now_utc(),
        created_at=now_utc(),
        ip=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:255],
    )
    db.add(challenge)
    issued = _issue_letter(db, user, challenge)
    db.flush()
    return issued, nonce


def _by_nonce(db: Session, nonce: str | None) -> LoginChallenge | None:
    if not nonce:
        return None
    return db.scalar(
        select(LoginChallenge).where(LoginChallenge.browser_nonce_hash == token_hash(nonce)).with_for_update()
    )


def resend(db: Session, nonce: str | None) -> tuple[Issued, User]:
    challenge = _by_nonce(db, nonce)
    if challenge is None or challenge.used_at is not None or challenge.expires_at <= now_utc():
        raise ApiError(410, "LOGIN_LINK_EXPIRED", LINK_EXPIRED)
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise ApiError(410, "LOGIN_LINK_EXPIRED", LINK_EXPIRED)
    _check_letter_limits(db, user, cooldown=True)
    return _issue_letter(db, user, challenge), user


def _reject(db: Session, user_id, reason: str, status: int, code: str, message: str) -> ApiError:
    audit.record(db, "login_link_rejected", "user", user_id, metadata={"reason": reason})
    db.commit()
    return ApiError(status, code, message)


def confirm(db: Session, token: str, nonce: str | None) -> User:
    now = now_utc()
    challenge = db.scalar(
        select(LoginChallenge).where(LoginChallenge.token_hash == token_hash(token)).with_for_update()
    )
    if challenge is None:
        raise _reject(db, None, "unknown", 400, "LOGIN_LINK_INVALID", LINK_EXPIRED)
    if challenge.used_at is not None or challenge.expires_at <= now:
        reason = "used" if challenge.used_at is not None else "expired"
        raise _reject(db, challenge.user_id, reason, 410, "LOGIN_LINK_EXPIRED", LINK_EXPIRED)
    if not nonce or not secrets.compare_digest(challenge.browser_nonce_hash, token_hash(nonce)):
        raise _reject(db, challenge.user_id, "other_browser", 409, "LOGIN_OTHER_BROWSER", OTHER_BROWSER)
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise _reject(
            db,
            challenge.user_id,
            "account_disabled",
            400,
            "ACCOUNT_DISABLED",
            "Обліковий запис заблоковано. Зверніться до адміністратора",
        )
    marked = db.execute(
        update(LoginChallenge)
        .where(LoginChallenge.id == challenge.id, LoginChallenge.used_at.is_(None))
        .values(used_at=now)
        .returning(LoginChallenge.id)
    ).scalar()
    if marked is None:  # pragma: no cover
        raise _reject(db, challenge.user_id, "used", 410, "LOGIN_LINK_EXPIRED", LINK_EXPIRED)
    db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.user_id == user.id,
            LoginChallenge.id != challenge.id,
            LoginChallenge.used_at.is_(None),
            LoginChallenge.expires_at > now,
        )
        .values(expires_at=now)
    )
    audit.record(db, "login_confirmed", "user", user.id, actor_id=user.id)
    return user


def set_pending_cookie(response: Response, nonce: str) -> None:
    s = get_settings()
    response.set_cookie(
        PENDING_COOKIE,
        nonce,
        max_age=s.login_link_ttl_minutes * 60,
        path="/api",
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
    )


def clear_pending_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(PENDING_COOKIE, path="/api", secure=s.cookie_secure, httponly=True, samesite="lax")
