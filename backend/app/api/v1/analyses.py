from __future__ import annotations

import uuid
from functools import partial

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.constants import CLASS_LABELS_UK, MODEL_NAME, XAI_COMPONENTS
from app.ai.preprocessing import PREPROCESSING_VERSION
from app.ai.service import AiBusy, AiService, AiState
from app.ai.types import METHODS
from app.auth.deps import get_current_user, require_doctor
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    AiAnalysis,
    AnalysisStatus,
    Case,
    CaseImage,
    CaseStatus,
    ExplanationStatus,
    User,
    XaiArtifact,
    XaiStatus,
)
from app.db.session import get_db, get_sessionmaker
from app.explain import service as explain
from app.explain.service import ExplanationService
from app.schemas.analyses import AiStatusOut, AnalysisOut, ClassLabel, ClassScore, ExplanationOut, XaiArtifactOut
from app.services import analyses as jobs
from app.services import audit
from app.services.access import own_case
from app.storage.local import Storage, get_storage

from .cases import current_image, gate_overridden

router = APIRouter(tags=["analyses"])

ANALYZABLE = (CaseStatus.OPEN, CaseStatus.FOLLOW_UP_PLANNED)

XAI_REASONS = {
    "XAI_ZERO_GRADIENT": (
        "Карта тотожно нульова: для цього компонента жодна ознака не має додатного внеску в клас, "
        "обраний ансамблем. Порожню картинку не показано"
    ),
    "XAI_NAN": "Під час обчислення карти виникли некоректні значення",
    "XAI_NO_GRADIENT": "Градієнт для цього компонента недоступний",
    "XAI_ENCODE": "Не вдалося зберегти зображення карти",
}
_GRID = {name: grid for name, _, grid in XAI_COMPONENTS}
_COMPONENT_ORDER = {name: i for i, (name, _, _) in enumerate(XAI_COMPONENTS)}


def get_ai(request: Request) -> AiService:
    return request.app.state.ai


def get_explainer(request: Request) -> ExplanationService:
    return request.app.state.explainer


def explanation_out(a: AiAnalysis) -> ExplanationOut | None:
    if a.status != AnalysisStatus.COMPLETED or a.explanation_status is None:
        return None
    out = ExplanationOut(status=a.explanation_status)
    if a.explanation_status == ExplanationStatus.FAILED:
        out.error_code = a.explanation_error_code
        out.error_message = explain.EXPLAIN_ERRORS.get(
            a.explanation_error_code or "", explain.EXPLAIN_ERRORS["EXPLAIN_INTERNAL"]
        )
    elif a.explanation_status == ExplanationStatus.COMPLETED and a.explanation_json:
        try:
            data = explain.Explanation.model_validate(a.explanation_json)
        except ValidationError:  # unreadable stored text: let the doctor retry
            out.status, out.error_code = ExplanationStatus.FAILED, "EXPLAIN_BAD_RESPONSE"
            out.error_message = explain.EXPLAIN_ERRORS["EXPLAIN_BAD_RESPONSE"]
            return out
        out = ExplanationOut.model_validate({**data.model_dump(), "status": out.status, "model": a.explanation_model})
    return out


def _label(code: str) -> ClassLabel:
    return ClassLabel(code=code, label_uk=CLASS_LABELS_UK.get(code, code))


def analysis_out(db: Session, a: AiAnalysis, *, with_explanation: bool = False) -> AnalysisOut:
    xai = []
    if a.status == AnalysisStatus.COMPLETED:
        rows = db.scalars(select(XaiArtifact).where(XaiArtifact.analysis_id == a.id)).all()
        rows = sorted(rows, key=lambda x: (_COMPONENT_ORDER.get(x.component_name, 99), METHODS.index(x.method.value)))
        xai = [
            XaiArtifactOut(
                id=x.id,
                method=x.method,
                component=x.component_name,
                layer_name=x.layer_name,
                grid_size=_GRID.get(x.component_name),
                status=x.status,
                error_code=x.error_code,
                reason=None if x.status == XaiStatus.COMPLETED else XAI_REASONS.get(x.error_code or "", "Недоступно"),
                url=f"/api/v1/analyses/{a.id}/xai/{x.id}" if x.status == XaiStatus.COMPLETED else None,
            )
            for x in rows
        ]
    scores = sorted((a.scores_json or {}).items(), key=lambda kv: kv[1], reverse=True)
    return AnalysisOut(
        id=a.id,
        case_id=a.case_id,
        image_id=a.image_id,
        status=a.status,
        model=a.model_name,
        model_version=a.model_sha256[:12] if a.model_sha256 else None,
        preprocessing_version=a.preprocessing_version,
        predicted_class=_label(a.predicted_class_code) if a.predicted_class_code else None,
        score=a.score,
        scores=[ClassScore(code=c, label_uk=CLASS_LABELS_UK.get(c, c), score=s) for c, s in scores],
        error_code=a.error_code,
        error_message=a.error_message_safe,
        created_at=a.created_at,
        started_at=a.started_at,
        completed_at=a.completed_at,
        xai=xai,
        image_gate_overridden=gate_overridden(db.get(CaseImage, a.image_id)),
        explanation=explanation_out(a) if with_explanation else None,
    )


def _own_analysis(db: Session, user: User, analysis_id: uuid.UUID) -> AiAnalysis:
    a = db.get(AiAnalysis, analysis_id)
    case = db.get(Case, a.case_id) if a else None
    if a is None or case is None or case.doctor_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Аналіз не знайдено")
    return a


def _refresh(db: Session, a: AiAnalysis) -> AiAnalysis:
    settings = get_settings()
    if jobs.expire_if_stale(db, a, settings.analysis_timeout_seconds):
        db.refresh(a)
    if jobs.expire_explanation_if_stale(db, a, 2 * settings.gemini_timeout_seconds + 30):
        db.refresh(a)
    return a


@router.post("/cases/{case_id}/analyses", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(
    case_id: uuid.UUID,
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    ai: AiService = Depends(get_ai),
    explainer: ExplanationService = Depends(get_explainer),
) -> AnalysisOut:
    case = own_case(db, user, case_id, for_update=True)
    if case.status not in ANALYZABLE:
        raise ApiError(409, "CASE_NOT_ANALYZABLE", "Аналіз можна запускати лише для відкритого випадку або на контролі")
    img = current_image(db, case.id)
    if img is None:
        raise ApiError(409, "NO_IMAGE", "Спершу додайте фото до випадку")
    if ai.state == AiState.LOADING:
        raise ApiError(503, "AI_LOADING", ai.message)
    if ai.state != AiState.READY or ai.engine is None:
        raise ApiError(503, "AI_UNAVAILABLE", f"Аналіз ШІ недоступний: {ai.message}")
    settings = get_settings()
    active = db.scalars(select(AiAnalysis).where(AiAnalysis.case_id == case.id, AiAnalysis.status.in_(jobs.ACTIVE)))
    for a in active:
        jobs.expire_if_stale(db, a, settings.analysis_timeout_seconds)
    if db.scalar(select(AiAnalysis.id).where(AiAnalysis.case_id == case.id, AiAnalysis.status.in_(jobs.ACTIVE))):
        raise ApiError(409, "ANALYSIS_IN_PROGRESS", "Аналіз цього випадку вже виконується")
    if not ai.has_capacity():
        raise ApiError(503, "AI_BUSY", "Черга аналізів заповнена. Спробуйте за хвилину")

    engine = ai.engine
    analysis = AiAnalysis(
        case_id=case.id,
        image_id=img.id,
        status=AnalysisStatus.QUEUED,
        model_name=engine.model_name,
        model_sha256=engine.model_sha256,
        preprocessing_version=engine.preprocessing_version,
    )
    db.add(analysis)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "ANALYSIS_IN_PROGRESS", "Аналіз цього випадку вже виконується") from None
    audit.record(
        db,
        "analysis_requested",
        "ai_analysis",
        analysis.id,
        actor_id=user.id,
        metadata={"caseId": str(case.id), "imageId": str(img.id)},
    )
    db.commit()
    try:
        explain_next = partial(explainer.submit, storage) if explainer.enabled else None
        ai.submit(
            jobs.run_analysis,
            engine,
            get_sessionmaker(),
            storage,
            analysis.id,
            settings.xai_overlay_max_side,
            explain_next,
        )
    except AiBusy:
        jobs.mark_failed(db, analysis, "AI_BUSY")
        db.commit()
        raise ApiError(503, "AI_BUSY", "Черга аналізів заповнена. Спробуйте за хвилину") from None
    return analysis_out(db, analysis, with_explanation=True)


@router.get("/cases/{case_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(
    case_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)
) -> list[AnalysisOut]:
    case = own_case(db, user, case_id)
    rows = db.scalars(
        select(AiAnalysis).where(AiAnalysis.case_id == case.id).order_by(AiAnalysis.created_at.desc())
    ).all()
    return [analysis_out(db, _refresh(db, a), with_explanation=True) for a in rows]


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)
) -> AnalysisOut:
    return analysis_out(db, _refresh(db, _own_analysis(db, user, analysis_id)), with_explanation=True)


@router.post("/analyses/{analysis_id}/explanation", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED)
def retry_explanation(
    analysis_id: uuid.UUID,
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    explainer: ExplanationService = Depends(get_explainer),
) -> AnalysisOut:
    a = _refresh(db, _own_analysis(db, user, analysis_id))
    if a.status != AnalysisStatus.COMPLETED:
        raise ApiError(409, "ANALYSIS_NOT_COMPLETED", "Пояснення доступне лише для завершеного аналізу")
    a = db.get(AiAnalysis, a.id, with_for_update=True, populate_existing=True)
    if a.explanation_status == ExplanationStatus.PENDING:
        raise ApiError(409, "EXPLANATION_IN_PROGRESS", "Пояснення вже готується")
    if explainer.enabled:
        explain.mark_pending(a)
    else:
        explain.fail(a, "EXPLAIN_NO_KEY")
    db.commit()
    if a.explanation_status == ExplanationStatus.PENDING:
        explainer.submit(storage, a.id)
    return analysis_out(db, a, with_explanation=True)


@router.get(
    "/analyses/{analysis_id}/xai/{artifact_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def get_xai_image(
    analysis_id: uuid.UUID,
    artifact_id: uuid.UUID,
    user: User = Depends(require_doctor),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Response:
    a = _own_analysis(db, user, analysis_id)
    art = db.get(XaiArtifact, artifact_id)
    if art is None or art.analysis_id != a.id or not art.storage_key or not storage.exists(art.storage_key):
        raise ApiError(404, "NOT_FOUND", "Карту пояснення не знайдено")
    return Response(
        content=storage.get(art.storage_key),
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.get("/system/ai-status", response_model=AiStatusOut, tags=["system"])
def ai_status(request: Request, _: User = Depends(get_current_user), ai: AiService = Depends(get_ai)) -> AiStatusOut:
    engine = ai.engine
    return AiStatusOut(
        status=ai.state.value,
        code=ai.reason_code,
        message=ai.message,
        model=engine.model_name if engine else MODEL_NAME,
        model_version=engine.model_sha256[:12] if engine else None,
        preprocessing_version=engine.preprocessing_version if engine else PREPROCESSING_VERSION,
        components=[name for name, _, _ in XAI_COMPONENTS],
        xai_methods=list(METHODS),
        max_concurrent_analyses=ai.max_concurrent,
        pending_analyses=ai.pending,
        gate_status=request.app.state.gate.state,
    )
