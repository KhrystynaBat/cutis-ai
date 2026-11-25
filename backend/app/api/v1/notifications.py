from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.core.errors import ApiError
from app.db.models import Notification, Referral, User
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.referrals import NotificationOut, NotificationReferral, UnreadCount
from app.services import lab_workflow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(n: Notification, ref: Referral | None) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type,
        title=n.title,
        message=n.message,
        is_read=n.is_read,
        created_at=n.created_at,
        read_at=n.read_at,
        referral=(
            NotificationReferral(id=ref.id, referral_number=ref.referral_number, case_id=ref.case_id) if ref else None
        ),
    )


@router.get("", response_model=Page[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False, alias="unreadOnly"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[NotificationOut]:
    stmt = (
        select(Notification, Referral)
        .outerjoin(Referral, Referral.id == Notification.referral_id)
        .where(Notification.user_id == user.id)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[NotificationOut](items=[_out(n, r) for n, r in rows], total=total, page=page, page_size=page_size)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UnreadCount:
    return UnreadCount(unread=lab_workflow.unread_count(db, user))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> NotificationOut:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Сповіщення не знайдено")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(UTC)
        db.commit()
    return _out(n, db.get(Referral, n.referral_id) if n.referral_id else None)


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UnreadCount:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    db.commit()
    return UnreadCount(unread=0)
