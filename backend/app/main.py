from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai import gatekeeper
from app.ai.service import AiService
from app.api.v1 import admin_users, analyses, auth, cases, health, lab, notifications, patients, referrals
from app.auth.rate_limit import FailureLimiter
from app.core import errors
from app.core.config import get_settings
from app.email import outbox

API_PREFIX = "/api/v1"


def _fail_interrupted() -> None:
    from app.db.session import get_sessionmaker
    from app.services.analyses import fail_interrupted

    fail_interrupted(get_sessionmaker())


def create_app(ai_service: AiService | None = None, gate_service: gatekeeper.GateService | None = None) -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ai = ai_service or AiService.from_settings(settings, on_start=_fail_interrupted)
    gate = gate_service or gatekeeper.from_settings(settings)
    if gate.state == "loading":
        if ai_service is None:
            ai.after_load(lambda: gate.load(settings.models_dir))
        else:
            gate.state = "unavailable"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        ai.start()
        if settings.email_provider == "smtp":
            threading.Thread(target=outbox.dispatch_in_background, name="email-retry", daemon=True).start()
        yield
        ai.shutdown()

    app = FastAPI(
        title="CutisAI API",
        version="0.1.0",
        description="CutisAI: аналіз дерматологічних зображень з інтерпретацією рішень моделей.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    errors.install(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "X-Background-Poll"],
    )

    app.state.login_limiter = FailureLimiter(settings.login_max_failures, settings.login_window_seconds)
    app.state.upload_limiter = FailureLimiter(settings.upload_max_per_window, settings.upload_window_seconds)
    app.state.ai = ai
    app.state.gate = gate

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(admin_users.router)
    api.include_router(patients.router)
    api.include_router(cases.router)
    api.include_router(analyses.router)
    api.include_router(referrals.router)
    api.include_router(notifications.router)
    api.include_router(lab.router)
    app.include_router(api)
    return app


app = create_app()
