from __future__ import annotations

import enum
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .preprocessing import NormalizationUnavailable
from .types import AnalysisOutput

logger = logging.getLogger("dermalab.ai")


class Engine(Protocol):
    model_name: str
    model_sha256: str
    preprocessing_version: str

    def analyze(self, image_bytes: bytes) -> AnalysisOutput: ...


class AiState(enum.StrEnum):
    LOADING = "loading"
    READY = "ready"
    UNAVAILABLE = "unavailable"


UNAVAILABLE_MESSAGES = {
    "AI_DISABLED": "Модуль ШІ вимкнено в конфігурації сервера",
    "MODEL_FILE_MISSING": "Файл моделі не знайдено на сервері",
    "MODEL_CHECKSUM_MISMATCH": "Файл моделі не збігається з перевіреним в аудиті",
    "MODEL_BAD_SHAPE": "Модель має неочікувану структуру входу/виходу",
    "NORMALIZATION_UNAVAILABLE": "Відсутні перевірені параметри нормалізації",
    "MODEL_LOAD_FAILED": "Не вдалося завантажити модель",
}


class AiBusy(RuntimeError):
    pass


class AiService:
    def __init__(
        self,
        load: Callable[[], Engine] | None,
        *,
        max_concurrent: int = 1,
        max_queued: int = 10,
        on_start: Callable[[], None] | None = None,
        unavailable_code: str | None = None,
    ):
        self._load_fn = load
        self._on_start = on_start
        self.max_concurrent = max(1, max_concurrent)
        self.max_queued = max(1, max_queued)
        self.engine: Engine | None = None
        self.state = AiState.LOADING if load else AiState.UNAVAILABLE
        self.reason_code: str | None = None if load else (unavailable_code or "AI_DISABLED")
        self.load_seconds: float | None = None
        self._pool: ThreadPoolExecutor | None = None
        self._pending = 0
        self._lock = threading.Lock()
        self._loaded = threading.Event()
        self._after_load: list[Callable[[], None]] = []
        if load is None:
            self._loaded.set()

    def after_load(self, fn: Callable[[], None]) -> None:
        self._after_load.append(fn)

    @classmethod
    def ready_with(cls, engine: Engine, **kw: Any) -> AiService:
        svc = cls(None, **kw)
        svc.engine, svc.state, svc.reason_code = engine, AiState.READY, None
        return svc

    @classmethod
    def from_settings(cls, settings: Any, on_start: Callable[[], None] | None = None) -> AiService:
        if not settings.ai_enabled:
            return cls(None, max_concurrent=settings.max_concurrent_analyses, unavailable_code="AI_DISABLED")

        def load() -> Engine:
            from .engine import EnsembleEngine  # heavy: TensorFlow is imported only here

            return EnsembleEngine(settings.models_dir)

        return cls(
            load,
            max_concurrent=settings.max_concurrent_analyses,
            max_queued=settings.max_queued_analyses,
            on_start=on_start,
        )

    def start(self) -> None:
        if self._load_fn is None and self._on_start is None:
            return
        threading.Thread(target=self._startup, name="ai-loader", daemon=True).start()

    def _startup(self) -> None:
        if self._on_start is not None:
            try:
                self._on_start()
            except Exception:
                logger.exception("AI startup hook failed")
        if self._load_fn is None:
            return
        t0 = time.perf_counter()
        try:
            engine = self._load_fn()
            warmup = getattr(engine, "warmup", None)
            if warmup:
                warmup()
        except Exception as e:  # noqa: BLE001 - any failure leaves AI unavailable, never the whole API
            code = "NORMALIZATION_UNAVAILABLE" if isinstance(e, NormalizationUnavailable) else getattr(e, "code", None)
            self.reason_code = code if code in UNAVAILABLE_MESSAGES else "MODEL_LOAD_FAILED"
            self.state = AiState.UNAVAILABLE
            logger.error("AI unavailable: %s (%s)", self.reason_code, e.__class__.__name__)
        else:
            self.engine = engine
            self.load_seconds = round(time.perf_counter() - t0, 1)
            self.state = AiState.READY
            logger.info("AI ready: %s loaded in %.1f s", engine.model_name, self.load_seconds)
        finally:
            self._loaded.set()
        for fn in self._after_load:
            try:
                fn()
            except Exception:
                logger.exception("AI post-load step failed")

    def wait_loaded(self, timeout: float | None = None) -> bool:
        return self._loaded.wait(timeout)

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)

    @property
    def pending(self) -> int:
        return self._pending

    def has_capacity(self) -> bool:
        return self._pending < self.max_concurrent + self.max_queued

    def submit(self, fn: Callable[..., Any], *args: Any) -> None:
        with self._lock:
            if not self.has_capacity():
                raise AiBusy("analysis queue is full")
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=self.max_concurrent, thread_name_prefix="ai-job")
            self._pending += 1
        future = self._pool.submit(fn, *args)
        future.add_done_callback(self._done)

    def _done(self, future: Any) -> None:
        with self._lock:
            self._pending -= 1
        exc = future.exception() if not future.cancelled() else None
        if exc is not None:
            logger.error("analysis job crashed: %s", exc.__class__.__name__)

    @property
    def message(self) -> str:
        if self.state == AiState.READY:
            return "Модуль ШІ працює"
        if self.state == AiState.LOADING:
            return "Модель завантажується, зачекайте хвилину"
        return UNAVAILABLE_MESSAGES.get(self.reason_code or "", "Модуль ШІ недоступний")
