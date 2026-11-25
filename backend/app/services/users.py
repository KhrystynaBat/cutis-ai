from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.auth.security import hash_password, new_token, password_policy_errors, token_hash
from app.auth.sessions import now_utc, revoke_user_sessions
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    AuditEvent,
    Case,
    LabResult,
    Notification,
    Patient,
    Referral,
    Role,
    Sex,
    TokenPurpose,
    User,
    UserSession,
    UserToken,
)
from app.schemas.users import PasswordToken

from . import audit


def column_value(field: str, value: object) -> object:
    if field == "sex" and value is not None:
        return Sex(value)
    return value


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def ensure_email_free(db: Session, email: str, except_id: uuid.UUID | None = None) -> None:
    stmt = select(User.id).where(User.email == normalize_email(email))
    if except_id is not None:
        stmt = stmt.where(User.id != except_id)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "EMAIL_TAKEN", "Ця адреса вже використовується")


def check_password_policy(password: str, email: str, names: tuple[str | None, ...] = ()) -> None:
    errors = password_policy_errors(password, email, names)
    if errors:
        raise ApiError(422, "WEAK_PASSWORD", "; ".join(errors))


def set_password(db: Session, user: User, password: str) -> None:
    check_password_policy(password, user.email, (user.first_name, user.last_name, user.middle_name))
    user.password_hash = hash_password(password)


def issue_password_token(db: Session, user: User, purpose: TokenPurpose) -> PasswordToken:
    settings = get_settings()
    now = now_utc()
    db.execute(
        update(UserToken)
        .where(UserToken.user_id == user.id, UserToken.used_at.is_(None), UserToken.expires_at > now)
        .values(expires_at=now)
    )
    hours = settings.invitation_ttl_hours if purpose == TokenPurpose.INVITATION else settings.password_reset_ttl_hours
    token = new_token()
    expires_at = now + timedelta(hours=hours)
    db.add(UserToken(user_id=user.id, purpose=purpose, token_hash=token_hash(token), expires_at=expires_at))
    return PasswordToken(token=token, expires_at=expires_at, purpose=purpose.value)


def consume_password_token(db: Session, token: str, new_password: str) -> User:
    now = now_utc()
    row = db.scalar(
        select(UserToken)
        .where(UserToken.token_hash == token_hash(token), UserToken.used_at.is_(None), UserToken.expires_at > now)
        .with_for_update()
    )
    user = db.get(User, row.user_id) if row else None
    if row is None or user is None or user.deactivated_at is not None:
        raise ApiError(400, "TOKEN_INVALID", "Посилання недійсне або термін його дії минув")
    set_password(db, user, new_password)
    row.used_at = now
    revoke_user_sessions(db, user.id)
    audit.record(db, "password_set", "user", user.id, actor_id=user.id, metadata={"via": row.purpose.value})
    return user


def create_user(
    db: Session,
    *,
    first_name: str | None,
    last_name: str | None,
    email: str,
    role: Role,
    middle_name: str | None = None,
    phone: str | None = None,
    birth_date: date | None = None,
    sex: str | None = None,
    is_active: bool = True,
    password: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> User:
    email = normalize_email(email)
    ensure_email_free(db, email)
    user = User(
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        phone=phone,
        birth_date=birth_date,
        sex=column_value("sex", sex),
        email=email,
        role=role,
        is_active=is_active,
    )
    if password is not None:
        set_password(db, user, password)
    db.add(user)
    db.flush()
    audit.record(db, "user_created", "user", user.id, actor_id=actor_id, metadata={"role": role.value})
    return user


def has_dependent_records(db: Session, user_id: uuid.UUID) -> bool:
    checks = [
        exists().where(Patient.doctor_id == user_id),
        exists().where(Case.doctor_id == user_id),
        exists().where(Referral.doctor_id == user_id),
        exists().where(LabResult.lab_specialist_id == user_id),
        exists().where(Referral.assigned_lab_specialist_id == user_id),
        exists().where(Notification.user_id == user_id),
        exists().where(AuditEvent.actor_user_id == user_id),
    ]
    return any(db.scalar(select(c)) for c in checks)


def set_status(db: Session, user: User, action: str, actor_id: uuid.UUID) -> None:
    if action == "block":
        if user.deactivated_at is not None:
            raise ApiError(409, "USER_DEACTIVATED", "Користувача деактивовано")
        user.is_active = False
    elif action == "unblock":
        if user.deactivated_at is not None:
            raise ApiError(409, "USER_DEACTIVATED", "Спочатку відновіть деактивованого користувача")
        user.is_active = True
    elif action == "deactivate":
        user.is_active = False
        user.deactivated_at = user.deactivated_at or now_utc()
    elif action == "reactivate":
        user.deactivated_at = None
        user.is_active = True
    else:  # pragma: no cover
        raise ValueError(action)
    if not user.is_active:
        revoke_user_sessions(db, user.id)
    audit.record(db, f"user_{action}", "user", user.id, actor_id=actor_id)
    if not user.is_active and user.role == Role.LAB_SPECIALIST:
        from app.services.lab_workflow import release_all_of  # import here: avoids an import cycle

        release_all_of(db, user.id, actor_id, reason=f"assignee_{action}")


def delete_user(db: Session, user: User, actor_id: uuid.UUID) -> None:
    if has_dependent_records(db, user.id):
        raise ApiError(409, "USER_HAS_RECORDS", "Видалення неможливе: є пов'язані записи. Використайте деактивацію")
    db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    db.query(UserToken).filter(UserToken.user_id == user.id).delete()
    audit.record(db, "user_deleted", "user", user.id, actor_id=actor_id, metadata={"role": user.role.value})
    db.delete(user)


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0
