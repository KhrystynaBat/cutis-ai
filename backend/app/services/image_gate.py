from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gatekeeper import GateService
from app.db.models import CaseImage
from app.storage.local import Storage


@dataclass(frozen=True)
class Checked:
    image: CaseImage
    score: float | None


def backfill(db: Session, storage: Storage, gate: GateService, *, recheck: bool = False) -> list[Checked]:
    stmt = select(CaseImage).order_by(CaseImage.uploaded_at)
    if not recheck:
        stmt = stmt.where(CaseImage.gate_score.is_(None))
    done = []
    for img in db.scalars(stmt).all():
        result = gate.check(storage.get(img.storage_key))
        if result is not None:
            img.gate_score = result.score
            img.gate_passed = result.passed
            img.gate_model_sha256 = result.model_sha256
        done.append(Checked(img, result.score if result else None))
    db.commit()
    return done
