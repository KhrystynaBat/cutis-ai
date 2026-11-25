from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.core.errors import ApiError
from app.core.names import name_matches
from app.db.models import Role, TokenPurpose, User
from app.db.session import get_db
from app.email import outbox
from app.schemas.common import Page
from app.schemas.users import PasswordToken, UserCreate, UserCreated, UserOut, UserStatus, UserUpdate
from app.services import audit, email_change
from app.services import users as user_service

router = APIRouter(prefix="/admin/users", tags=["admin"])

STAFF_ROLES = (Role.DOCTOR, Role.LAB_SPECIALIST)


def _get_staff(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.role not in STAFF_ROLES:
        raise ApiError(404, "NOT_FOUND", "Користувача не знайдено")
    return user


@router.get("", response_model=Page[UserOut])
def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: Literal["Doctor", "LabSpecialist"] | None = None,
    status_: UserStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Page[UserOut]:
    stmt = select(User).where(User.role.in_(STAFF_ROLES))
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(User.email.like(like), name_matches(User, like)))
    if role:
        stmt = stmt.where(User.role == Role(role))
    if status_ == "Active":
        stmt = stmt.where(User.is_active.is_(True), User.deactivated_at.is_(None))
    elif status_ == "Blocked":
        stmt = stmt.where(User.is_active.is_(False), User.deactivated_at.is_(None))
    elif status_ == "Deactivated":
        stmt = stmt.where(User.deactivated_at.is_not(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(User.last_name, User.first_name, User.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[UserOut](items=[UserOut.of(u) for u in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserCreated:
    user = user_service.create_user(
        db,
        first_name=body.first_name,
        last_name=body.last_name,
        middle_name=body.middle_name,
        phone=body.phone,
        birth_date=body.birth_date,
        sex=body.sex,
        email=body.email,
        role=Role(body.role),
        is_active=body.is_active,
        actor_id=admin.id,
    )
    invitation = user_service.issue_password_token(db, user, TokenPurpose.INVITATION)
    audit.record(db, "invitation_issued", "user", user.id, actor_id=admin.id)
    _email_link(db, background, user, invitation)
    db.commit()
    return UserCreated(user=UserOut.of(user), invitation=invitation)


def _email_link(db: Session, background: BackgroundTasks, user: User, token: PasswordToken) -> None:
    outbox_id = outbox.queue_user_link(db, user, token.purpose)
    if outbox_id is not None:
        token.email_queued = True
        background.add_task(outbox.send_user_link, outbox_id, token.token, token.expires_at)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> UserOut:
    return UserOut.of(_get_staff(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = _get_staff(db, user_id)
    changed: list[str] = []
    if body.email is not None and user_service.normalize_email(body.email) != user.email:
        user_service.ensure_email_free(db, body.email, except_id=user.id)
        email_change.apply_new_email(db, user, user_service.normalize_email(body.email))
        background.add_task(outbox.dispatch_in_background)
        changed.append("email")
    if body.role is not None and Role(body.role) != user.role:
        if user_service.has_dependent_records(db, user.id):
            raise ApiError(409, "USER_HAS_RECORDS", "Роль не можна змінити: користувач уже має робочі записи")
        user.role = Role(body.role)
        changed.append("role")
    for field in ("first_name", "last_name"):
        value = getattr(body, field)
        if value is not None and value != getattr(user, field):
            setattr(user, field, value)
            changed.append(field)
    for field in ("middle_name", "phone", "birth_date", "sex"):
        current = getattr(user, field)
        if field in body.model_fields_set and getattr(body, field) != getattr(current, "value", current):
            setattr(user, field, user_service.column_value(field, getattr(body, field)))
            changed.append(field)
    if changed:
        audit.record(db, "user_updated", "user", user.id, actor_id=admin.id, metadata={"fields": changed})
    db.commit()
    return UserOut.of(user)


def _status_endpoint(action: str):
    def handler(user_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> UserOut:
        user = _get_staff(db, user_id)
        user_service.set_status(db, user, action, admin.id)
        db.commit()
        return UserOut.of(user)

    handler.__name__ = f"{action}_user"
    return handler


for _action in ("block", "unblock", "deactivate", "reactivate"):
    router.add_api_route(f"/{{user_id}}/{_action}", _status_endpoint(_action), methods=["POST"], response_model=UserOut)


@router.post("/{user_id}/password-reset", response_model=PasswordToken)
def issue_password_reset(
    user_id: uuid.UUID,
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PasswordToken:
    user = _get_staff(db, user_id)
    if user.deactivated_at is not None:
        raise ApiError(409, "USER_DEACTIVATED", "Користувача деактивовано")
    purpose = TokenPurpose.PASSWORD_RESET if user.password_hash else TokenPurpose.INVITATION
    token = user_service.issue_password_token(db, user, purpose)
    audit.record(db, "password_reset_issued", "user", user.id, actor_id=admin.id)
    _email_link(db, background, user, token)
    db.commit()
    return token


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    user_service.delete_user(db, _get_staff(db, user_id), admin.id)
    db.commit()
