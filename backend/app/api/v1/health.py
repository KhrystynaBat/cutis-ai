from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["system"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        raise ApiError(503, "DB_UNAVAILABLE", "Database is not available") from None
    if revision is None:
        raise ApiError(503, "DB_NOT_MIGRATED", "Database migrations have not been applied")
    return {"status": "ok", "database": "ok"}
