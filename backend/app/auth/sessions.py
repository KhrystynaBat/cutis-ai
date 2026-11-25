from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User, UserSession

from .security import csrf_token_for, new_token, token_hash

SESSION_COOKIE = "dl_session"
CSRF_COOKIE = "dl_csrf"
CSRF_HEADER = "X-CSRF-Token"
_TOUCH_INTERVAL = timedelta(seconds=60)


def now_utc() -> datetime:
    return datetime.now(UTC)


def create_session(db: Session, user: User) -> str:
    settings = get_settings()
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now_utc() + timedelta(hours=settings.session_ttl_hours),
            last_seen_at=now_utc(),
        )
    )
    return token


def resolve_session(db: Session, token: str, *, touch: bool = True) -> tuple[UserSession, User] | None:
    settings = get_settings()
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_hash(token), UserSession.revoked_at.is_(None))
    ).first()
    if row is None:
        return None
    sess, user = row
    now = now_utc()
    idle_limit = timedelta(minutes=settings.session_idle_minutes)
    if sess.expires_at <= now or now - sess.last_seen_at > idle_limit or not user.is_active:
        sess.revoked_at = now
        db.commit()
        return None
    if touch and now - sess.last_seen_at > _TOUCH_INTERVAL:
        sess.last_seen_at = now
        db.commit()
    return sess, user


def revoke_user_sessions(db: Session, user_id: uuid.UUID, except_session_id: uuid.UUID | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    db.execute(stmt.values(revoked_at=now_utc()))


def set_auth_cookies(response: Response, token: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/api",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token_for(token),
        max_age=max_age,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(SESSION_COOKIE, path="/api", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
