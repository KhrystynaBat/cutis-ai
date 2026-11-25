from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_lab
from app.db.models import User
from app.db.session import get_db
from app.schemas.referrals import PersonRef
from app.services import lab_workflow

router = APIRouter(prefix="/lab", tags=["lab"])


@router.get("/specialists", response_model=list[PersonRef])
def lab_specialists(_: User = Depends(require_lab), db: Session = Depends(get_db)) -> list[PersonRef]:
    return [
        PersonRef(id=u.id, first_name=u.first_name, last_name=u.last_name, middle_name=u.middle_name)
        for u in lab_workflow.active_lab_specialists(db)
    ]
