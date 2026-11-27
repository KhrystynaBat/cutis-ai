from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.constants import CLASS_LABELS_UK, XAI_COMPONENTS
from app.ai.overlay import fit_display
from app.db.models import AiAnalysis, CaseImage, ExplanationStatus, XaiArtifact, XaiMethod, XaiStatus
from app.storage.local import Storage

from .gemini import ExplainClient, ExplainError, GeminiClient, ImagePart

logger = logging.getLogger("dermalab.explain")

EXPLAIN_ERRORS = {
    "EXPLAIN_NO_KEY": "Пояснення ШІ не налаштовано на сервері",
    "EXPLAIN_RATE_LIMIT": "Перевищено ліміт запитів до Gemini. Спробуйте пізніше",
    "EXPLAIN_UNAVAILABLE": "Сервіс Gemini зараз недоступний",
    "EXPLAIN_TIMEOUT": "Gemini не відповів вчасно",
    "EXPLAIN_AUTH": "Gemini відхилив ключ доступу",
    "EXPLAIN_REJECTED": "Gemini відхилив запит",
    "EXPLAIN_BAD_RESPONSE": "Gemini повернув некоректну відповідь",
    "EXPLAIN_IMAGE": "Не вдалося підготувати фото для пояснення",
    "EXPLAIN_INTERRUPTED": "Підготовку пояснення перервано перезапуском сервера",
    "EXPLAIN_INTERNAL": "Не вдалося отримати пояснення",
}

_str = {"type": "string"}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "object",
            "properties": {"result": _str, "heatmaps": _str},
            "required": ["result", "heatmaps"],
        },
        "discrepancy": _str,
        "description": {
            "type": "object",
            "properties": {
                "intro": _str,
                "features": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"label": _str, "value": _str},
                        "required": ["label", "value"],
                    },
                },
            },
            "required": ["intro", "features"],
        },
        "assessment": {
            "type": "object",
            "properties": {
                "intro": _str,
                "differential": {"type": "array", "minItems": 2, "maxItems": 3, "items": _str},
            },
            "required": ["intro", "differential"],
        },
        "recommendations": _str,
        "conclusion": _str,
    },
    "required": ["classification", "discrepancy", "description", "assessment", "recommendations", "conclusion"],
}

SYSTEM_PROMPT = """Ти — помічник лікаря-дерматолога. Ти отримуєш дерматоскопічне фото \
новоутворення, результат системи ШІ, яка класифікує такі фото (ансамбль нейромереж AlexNet, \
ResNet, DenseNet), і теплові карти Grad-CAM++ поверх фото, що показують, які ділянки найбільше \
вплинули на рішення. Поясни лікарю результат класифікації та карт і опиши новоутворення.
Лікар не фахівець з машинного навчання, тож пояснення класифікації пиши простою зрозумілою \
мовою, як колега-клініцист: називай це «система» і не згадуй назви нейромереж, Grad-CAM, \
ансамбль, шари, градієнти чи інші технічні терміни; оцінки подавай у відсотках.
Ознаки в описі визначай за самим фото, а не підганяй під клас системи.
Пиши українською, професійною медичною мовою, стисло, \
без привітань і без застережень про те, що це не діагноз.
Без розмітки (*, #) усередині текстів.
Структура відповіді:
classification — пояснення класифікації для лікаря:
  result — 1–2 речення: до якого типу новоутворення система віднесла фото і з якою \
впевненістю (у відсотках), що вона розглядала як наступні варіанти і чи впевнене це рішення \
(чи близькі відсотки інших варіантів);
  heatmaps — 1–2 речення: на які ділянки новоутворення система звертала найбільше уваги \
(наприклад, «найбільше уваги система приділила темнішій центральній ділянці та нерівному \
краю») і чи це ті ділянки, де видно клінічно важливі ознаки.
discrepancy — на що звернути увагу: порівняй ознаки на фото з типом, який обрала система. \
Якщо на фото є ознаки іншого, особливо небезпечнішого стану (наприклад, система віднесла \
утворення до невусу чи кератозу, а видно ознаки, характерні для меланоми або базаліоми), \
напиши 2–3 речення нейтральним клінічним тоном: які саме ознаки видно, для чого вони \
характерні і чому варто додатково оцінити утворення. Не пиши, що система помилилась чи \
працює некоректно, і не вживай слів «розбіжність», «помилка», «некоректно». Тоді попередня \
оцінка, рекомендації й висновок теж мають це враховувати (небезпечніший стан — у переліку \
можливих варіантів, рекомендація біопсії з гістологією). Якщо таких ознак немає — порожній рядок.
description — дерматоскопічний опис новоутворення:
  intro — одне речення, наприклад «На представленому зображенні візуалізується пігментоване \
новоутворення шкіри з такими характеристиками:»;
  features — пункти «назва: значення» по порядку: Форма (з оцінкою асиметрії), Межі, Забарвлення, \
Пігментна сітка, Розподіл пігменту, Судинний малюнок, Лущення, Розмір; значення — коротка фраза \
з малої літери; якщо ознаку не оцінити з фото (наприклад, розмір без масштабної шкали), так і напиши.
assessment — попередня оцінка:
  intro — одне речення: до якої групи уражень найімовірніше належить новоутворення \
і що це може бути, наприклад «Новоутворення найімовірніше належить до меланоцитарних \
уражень; можливі варіанти:»;
  differential — 2–3 можливі стани, від найімовірнішого; кожен — назва з малої літери \
і коротке обґрунтування через тире, без кодів класів і абревіатур у дужках.
recommendations — один абзац: дообстеження (клінічний огляд, анамнез динаміки, дерматоскопія \
в динаміці, біопсія з гістопатологічним дослідженням або спостереження).
conclusion — одне речення висновку без слова «Висновок».
Не давай рекомендацій щодо лікування (препарати, процедури, видалення, дози)."""


_CLASS_CODE = re.compile(r"\s*\((?:NV|MEL|BCC|AKIEC|BKL|DF|VASC)\)", re.IGNORECASE)


class _Classification(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    result: str = Field(min_length=1, max_length=1500)
    heatmaps: str = Field(min_length=1, max_length=2000)


class _Feature(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=600)


class _Description(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    intro: str = Field(min_length=1, max_length=600)
    features: list[_Feature] = Field(min_length=1, max_length=12)


class _Assessment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    intro: str = Field(min_length=1, max_length=1500)
    differential: list[str] = Field(min_length=1, max_length=3)

    @field_validator("differential")
    @classmethod
    def _drop_class_codes(cls, items: list[str]) -> list[str]:
        return [_CLASS_CODE.sub("", x).strip() for x in items]


class Explanation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    classification: _Classification
    discrepancy: str = Field(default="", max_length=2000)
    description: _Description
    assessment: _Assessment
    recommendations: str = Field(min_length=1, max_length=2000)
    conclusion: str = Field(min_length=1, max_length=1000)


def _now() -> datetime:
    return datetime.now(UTC)


def fail(a: AiAnalysis, code: str) -> None:
    a.explanation_status = ExplanationStatus.FAILED
    a.explanation_error_code = code if code in EXPLAIN_ERRORS else "EXPLAIN_INTERNAL"
    a.explanation_updated_at = _now()


def mark_pending(a: AiAnalysis) -> None:
    a.explanation_status = ExplanationStatus.PENDING
    a.explanation_error_code = None
    a.explanation_json = None
    a.explanation_updated_at = _now()


def build_request(
    a: AiAnalysis, photo: bytes, heatmaps: list[tuple[str, bytes]], max_side: int
) -> list[str | ImagePart]:
    bgr = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ExplainError("EXPLAIN_IMAGE", "cannot decode photo")
    ok, jpg = cv2.imencode(".jpg", fit_display(bgr, max_side), [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ExplainError("EXPLAIN_IMAGE", "cannot encode photo")
    top3 = sorted((a.scores_json or {}).items(), key=lambda kv: kv[1], reverse=True)[:3]
    code = a.predicted_class_code or ""
    lines = [
        f"Клас, обраний ансамблем: {CLASS_LABELS_UK.get(code, code)} ({code.upper()}), оцінка {a.score or 0:.3f}.",
        "Топ-3 класи ансамблю:",
        *(f"- {CLASS_LABELS_UK.get(c, c)} ({c.upper()}): {s:.3f}" for c, s in top3),
        "Дерматоскопічне фото:",
    ]
    parts: list[str | ImagePart] = ["\n".join(lines), ImagePart("image/jpeg", jpg.tobytes())]
    for component, png in heatmaps:
        parts += [f"Теплова карта Grad-CAM++ моделі {component}:", ImagePart("image/png", png)]
    if not heatmaps:
        parts.append("Теплові карти недоступні.")
    return parts


def _heatmap_keys(db: Session, analysis_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = db.scalars(
        select(XaiArtifact).where(
            XaiArtifact.analysis_id == analysis_id,
            XaiArtifact.status == XaiStatus.COMPLETED,
            XaiArtifact.method == XaiMethod.GRADCAM_PP,
        )
    ).all()
    order = {name: i for i, (name, _, _) in enumerate(XAI_COMPONENTS)}
    rows = sorted(rows, key=lambda x: order.get(x.component_name, 99))
    return [(x.component_name, x.storage_key) for x in rows if x.storage_key]


def run_explanation(
    client: ExplainClient, sm: sessionmaker[Session], storage: Storage, analysis_id: uuid.UUID, max_side: int
) -> None:
    error: str | None = None
    result: dict[str, Any] | None = None
    try:
        with sm() as db:
            a = db.get(AiAnalysis, analysis_id)
            if a is None or a.explanation_status != ExplanationStatus.PENDING:
                return
            photo_key = db.get(CaseImage, a.image_id).storage_key
            heat_keys = _heatmap_keys(db, a.id)
            try:
                photo = storage.get(photo_key)
                heatmaps = [(c, storage.get(k)) for c, k in heat_keys]
            except OSError:
                raise ExplainError("EXPLAIN_IMAGE", "file missing") from None
            parts = build_request(a, photo, heatmaps, max_side)
        raw = client.generate_json(SYSTEM_PROMPT, parts, SCHEMA)
        try:
            result = Explanation.model_validate(raw).model_dump()
        except ValidationError:
            raise ExplainError("EXPLAIN_BAD_RESPONSE", "schema mismatch") from None
    except ExplainError as e:
        logger.warning("explanation %s failed: %s", analysis_id, e.code)
        error = e.code
    except Exception as e:  # noqa: BLE001 - recorded as a code; details only in the server log
        logger.error("explanation %s failed: %s", analysis_id, e.__class__.__name__)
        error = "EXPLAIN_INTERNAL"

    with sm() as db:
        a = db.get(AiAnalysis, analysis_id, with_for_update=True)
        if a is None or a.explanation_status != ExplanationStatus.PENDING:
            return
        if error is not None:
            fail(a, error)
        else:
            a.explanation_status = ExplanationStatus.COMPLETED
            a.explanation_json = result
            a.explanation_model = client.model
            a.explanation_updated_at = _now()
        db.commit()


class ExplanationService:
    def __init__(
        self,
        client_factory: Callable[[], ExplainClient | None],
        sm_factory: Callable[[], sessionmaker[Session]],
        max_side: int = 1024,
    ):
        self._client_factory = client_factory
        self._sm_factory = sm_factory
        self.max_side = max_side
        self._pool: ThreadPoolExecutor | None = None
        self._pending = 0
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Any) -> ExplanationService:
        from app.db.session import get_sessionmaker

        def client() -> ExplainClient | None:
            key = settings.gemini_api_key.get_secret_value().strip()
            if not key:
                return None
            return GeminiClient(
                key,
                settings.gemini_model,
                settings.gemini_timeout_seconds,
                fallback_models=(settings.gemini_fallback_model.strip(),),
            )

        return cls(client, get_sessionmaker, settings.xai_overlay_max_side)

    @property
    def enabled(self) -> bool:
        return self._client_factory() is not None

    @property
    def pending(self) -> int:
        return self._pending

    def submit(self, storage: Storage, analysis_id: uuid.UUID) -> None:
        client = self._client_factory()
        if client is None:
            return
        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="explain")
            self._pending += 1
        future = self._pool.submit(run_explanation, client, self._sm_factory(), storage, analysis_id, self.max_side)
        future.add_done_callback(self._done)

    def _done(self, future: Any) -> None:
        with self._lock:
            self._pending -= 1

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
