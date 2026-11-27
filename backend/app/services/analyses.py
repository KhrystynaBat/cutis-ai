from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.constants import XAI_COMPONENTS
from app.ai.overlay import fit_display, overlay_png
from app.ai.preprocessing import ImageDecodeError
from app.ai.service import Engine
from app.ai.types import CamResult, InferenceError, XaiError
from app.db.models import (
    AiAnalysis,
    AnalysisStatus,
    CaseImage,
    ExplanationStatus,
    XaiArtifact,
    XaiMethod,
    XaiStatus,
)
from app.explain import service as explain
from app.services import audit
from app.storage.local import Storage

logger = logging.getLogger("dermalab.ai")

ACTIVE = (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)

ANALYSIS_ERRORS = {
    "AI_IMAGE_MISSING": "Файл фото недоступний у сховищі",
    "AI_IMAGE_DECODE": "Не вдалося прочитати фото для аналізу",
    "AI_BAD_OUTPUT": "Модель повернула некоректний результат",
    "AI_NAN": "Модель повернула некоректний результат",
    "AI_TIMEOUT": "Аналіз не завершився вчасно",
    "AI_INTERRUPTED": "Аналіз перервано перезапуском сервера",
    "AI_BUSY": "Черга аналізів заповнена",
    "AI_INTERNAL": "Не вдалося виконати аналіз",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(a: AiAnalysis, code: str) -> None:
    a.status = AnalysisStatus.FAILED
    a.error_code = code
    a.error_message_safe = ANALYSIS_ERRORS.get(code, ANALYSIS_ERRORS["AI_INTERNAL"])
    a.completed_at = _now()


def mark_failed(db: Session, a: AiAnalysis, code: str) -> None:
    _fail(a, code)
    audit.record(db, "analysis_failed", "ai_analysis", a.id, metadata={"caseId": str(a.case_id), "errorCode": code})


def expire_if_stale(db: Session, a: AiAnalysis, timeout_seconds: int) -> bool:
    if a.status not in ACTIVE or a.created_at > _now() - timedelta(seconds=timeout_seconds):
        return False
    locked = db.get(AiAnalysis, a.id, with_for_update=True, populate_existing=True)
    if locked.status not in ACTIVE:
        return False
    mark_failed(db, locked, "AI_TIMEOUT")
    db.commit()
    return True


def expire_explanation_if_stale(db: Session, a: AiAnalysis, timeout_seconds: int) -> bool:
    if a.explanation_status != ExplanationStatus.PENDING or (
        a.explanation_updated_at and a.explanation_updated_at > _now() - timedelta(seconds=timeout_seconds)
    ):
        return False
    locked = db.get(AiAnalysis, a.id, with_for_update=True, populate_existing=True)
    if locked.explanation_status != ExplanationStatus.PENDING:
        return False
    explain.fail(locked, "EXPLAIN_TIMEOUT")
    db.commit()
    return True


def fail_interrupted(sm: sessionmaker[Session]) -> int:
    with sm() as db:
        rows = db.scalars(select(AiAnalysis).where(AiAnalysis.status.in_(ACTIVE)).with_for_update()).all()
        for a in rows:
            mark_failed(db, a, "AI_INTERRUPTED")
        pending = db.scalars(
            select(AiAnalysis).where(AiAnalysis.explanation_status == ExplanationStatus.PENDING).with_for_update()
        ).all()
        for a in pending:
            explain.fail(a, "EXPLAIN_INTERRUPTED")
        db.commit()
    if rows:
        logger.warning("marked %d interrupted analyses as Failed", len(rows))
    return len(rows)


def run_analysis(
    engine: Engine,
    sm: sessionmaker[Session],
    storage: Storage,
    analysis_id: uuid.UUID,
    overlay_max_side: int,
    explain_next: Callable[[uuid.UUID], None] | None = None,
) -> None:
    # 1. claim the job
    with sm() as db:
        result = db.execute(
            update(AiAnalysis)
            .where(AiAnalysis.id == analysis_id, AiAnalysis.status == AnalysisStatus.QUEUED)
            .values(status=AnalysisStatus.RUNNING, started_at=_now())
        )
        db.commit()
        if result.rowcount != 1:
            return  # failed meanwhile (timeout/restart) or unknown
        a = db.get(AiAnalysis, analysis_id)
        img = db.get(CaseImage, a.image_id)
        storage_key = img.storage_key

    error: str | None = None
    output = None
    artifacts: list[tuple[str, str, str, str | None, str | None]] = []  # component, method, layer, key, error
    try:
        data = storage.get(storage_key)
    except OSError:
        error = "AI_IMAGE_MISSING"
    if error is None:
        try:
            output = engine.analyze(data)
        except InferenceError as e:
            error = e.code if e.code in ANALYSIS_ERRORS else "AI_INTERNAL"
        except ImageDecodeError:
            error = "AI_IMAGE_DECODE"
        except Exception as e:  # noqa: BLE001 - recorded as a code; details only in the server log
            logger.error("analysis %s failed: %s", analysis_id, e.__class__.__name__)
            error = "AI_INTERNAL"
    if output is not None:
        display = fit_display(output.image_rgb, overlay_max_side)
        for (component, method), res in output.cams.items():
            if isinstance(res, CamResult):
                try:
                    key = storage.put(overlay_png(display, res.cam), prefix="xai", suffix=".png")
                    artifacts.append((component, method, res.layer_name, key, None))
                except XaiError as e:
                    artifacts.append((component, method, res.layer_name, None, e.code))
            else:
                artifacts.append((component, method, _layer_of(component), None, res.code))

    with sm() as db:
        a = db.get(AiAnalysis, analysis_id, with_for_update=True)
        if a is None or a.status != AnalysisStatus.RUNNING:
            return
        if error is not None:
            mark_failed(db, a, error)
        else:
            p = output.prediction
            a.status = AnalysisStatus.COMPLETED
            a.predicted_class_code = p.class_code
            a.score = p.score
            a.scores_json = p.scores
            a.completed_at = _now()
            if explain_next is not None:
                explain.mark_pending(a)
            else:
                explain.fail(a, "EXPLAIN_NO_KEY")
            for component, method, layer, key, err in artifacts:
                db.add(
                    XaiArtifact(
                        analysis_id=a.id,
                        method=XaiMethod(method),
                        component_name=component,
                        layer_name=layer,
                        storage_key=key,
                        status=XaiStatus.COMPLETED if key else XaiStatus.FAILED,
                        error_code=err,
                    )
                )
            audit.record(
                db,
                "analysis_completed",
                "ai_analysis",
                a.id,
                metadata={
                    "caseId": str(a.case_id),
                    "xaiCompleted": sum(1 for x in artifacts if x[3]),
                    "xaiFailed": sum(1 for x in artifacts if not x[3]),
                },
            )
        db.commit()
        completed = error is None
    if completed and explain_next is not None:
        explain_next(analysis_id)


def _layer_of(component: str) -> str:
    return next((layer for name, layer, _ in XAI_COMPONENTS if name == component), "")
