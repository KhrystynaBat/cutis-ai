from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Role, User, UserSession
from app.db.session import get_db

from .security import csrf_matches
from .sessions import CSRF_HEADER, SESSION_COOKIE, resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
BACKGROUND_HEADER = "X-Background-Poll"


@dataclass
class AuthContext:
    user: User
    session: UserSession
    token: str


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    background = request.method in SAFE_METHODS and request.headers.get(BACKGROUND_HEADER) == "1"
    resolved = resolve_session(db, token, touch=not background) if token else None
    if resolved is None:
        raise ApiError(401, "UNAUTHORIZED", "Потрібно увійти в систему")
    sess, user = resolved
    if request.method not in SAFE_METHODS and not csrf_matches(token, request.headers.get(CSRF_HEADER)):
        raise ApiError(403, "CSRF_FAILED", "Недійсний CSRF-токен. Оновіть сторінку")
    return AuthContext(user=user, session=sess, token=token)


def get_current_user(auth: AuthContext = Depends(get_auth)) -> User:
    return auth.user


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ApiError(403, "FORBIDDEN", "Недостатньо прав")
        return user

    return dependency


require_admin = require_roles(Role.ADMIN)
require_doctor = require_roles(Role.DOCTOR)
require_lab = require_roles(Role.LAB_SPECIALIST)
