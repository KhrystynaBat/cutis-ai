from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
from sqlalchemy import select, text
from test_patients_cases import jpeg, new_case, new_patient, upload

from app.ai.constants import CLASS_CODES, XAI_COMPONENTS
from app.ai.overlay import fit_display
from app.ai.service import AiService, AiState
from app.ai.types import AnalysisOutput, CamResult, InferenceError, Prediction, XaiError
from app.db.models import AuditEvent, CaseStatus, Role

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "models"
TEST_PHOTO = ROOT / "data" / "images" / "ISIC_0027175.jpg"  # HAM10000, ground truth bcc

FAKE_SCORES = [0.05, 0.10, 0.08, 0.02, 0.30, 0.40, 0.05]  # nv first, mel second


class FakeEngine:
    model_name = "ensemble_best"
    model_sha256 = "f" * 64
    preprocessing_version = "ham10000-bgr128-cubic-std-v1"

    def __init__(self, fail: Exception | None = None, gate: threading.Event | None = None):
        self.fail, self.gate, self.calls = fail, gate, 0

    def analyze(self, image_bytes: bytes) -> AnalysisOutput:
        self.calls += 1
        if self.gate is not None:
            assert self.gate.wait(10)
        if self.fail is not None:
            raise self.fail
        bgr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        p = np.array(FAKE_SCORES)
        idx = int(p.argmax())
        out = AnalysisOutput(
            Prediction(idx, CLASS_CODES[idx], float(p[idx]), dict(zip(CLASS_CODES, p.tolist(), strict=True))),
            cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
        )
        for name, layer, grid in XAI_COMPONENTS:
            for method in ("gradcam", "gradcam_pp"):
                if (name, method) == ("AlexNet", "gradcam"):
                    out.cams[(name, method)] = XaiError("XAI_ZERO_GRADIENT", "zero")
                else:
                    cam = np.linspace(0, 1, grid * grid, dtype=np.float32).reshape(grid, grid)
                    out.cams[(name, method)] = CamResult(method, name, layer, cam)
        return out


@pytest.fixture
def doctor(make_user, login_as):
    return login_as(make_user(Role.DOCTOR))


@pytest.fixture
def use_engine(app):
    services: list[AiService] = []

    def _use(engine, **kw) -> AiService:
        app.state.ai = AiService.ready_with(engine, **kw)
        services.append(app.state.ai)
        return app.state.ai

    yield _use
    for gate in [getattr(svc.engine, "gate", None) for svc in services]:
        if gate is not None:
            gate.set()
    deadline = time.monotonic() + 30
    while any(svc.pending for svc in services) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(svc.pending for svc in services), "background analysis jobs did not finish"


def case_with_photo(c, data: bytes | None = None) -> dict:
    case = new_case(c, new_patient(c)["id"])
    r = upload(c, case["id"], data or jpeg(320, 240))
    assert r.status_code == 201, r.text
    return case


def wait_done(c, analysis_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = c.get(f"/api/v1/analyses/{analysis_id}").json()
        if body["status"] in ("Completed", "Failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"analysis {analysis_id} did not finish: {body['status']}")


def test_analysis_job_result_and_xai_artifacts(doctor, use_engine, db):
    use_engine(FakeEngine())
    case = case_with_photo(doctor, jpeg(1600, 1200))

    r = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
    assert r.status_code == 202, r.text
    assert r.json()["status"] in ("Queued", "Running", "Completed")
    res = wait_done(doctor, r.json()["id"])

    assert res["status"] == "Completed"
    assert res["predictedClass"] == {"code": "nv", "labelUk": "Меланоцитарний невус"}
    assert res["score"] == pytest.approx(0.40)
    assert [s["code"] for s in res["scores"]][:2] == ["nv", "mel"]
    assert len(res["scores"]) == 7 and sum(s["score"] for s in res["scores"]) == pytest.approx(1.0)
    assert res["scores"][1]["labelUk"] == "Меланома"
    assert res["model"] == "ensemble_best" and res["modelVersion"] == "f" * 12
    assert res["preprocessingVersion"] == "ham10000-bgr128-cubic-std-v1"
    assert res["startedAt"] and res["completedAt"] and res["errorCode"] is None

    assert [(x["component"], x["method"]) for x in res["xai"]] == [
        (n, m) for n, _, _ in XAI_COMPONENTS for m in ("gradcam", "gradcam_pp")
    ]
    failed = res["xai"][0]
    assert failed["status"] == "Failed" and failed["errorCode"] == "XAI_ZERO_GRADIENT"
    assert failed["url"] is None and "нульова" in failed["reason"]
    ok = [x for x in res["xai"] if x["status"] == "Completed"]
    assert len(ok) == 5
    assert {x["component"]: x["gridSize"] for x in ok} == {"AlexNet": 8, "ResNet": 5, "DenseNet": 4}
    assert {x["layerName"] for x in ok if x["component"] == "ResNet"} == {"activation_29"}

    png = doctor.get(ok[0]["url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.headers["cache-control"] == "private, no-store"
    overlay = cv2.imdecode(np.frombuffer(png.content, np.uint8), cv2.IMREAD_COLOR)
    assert overlay.shape[:2] == fit_display(np.zeros((1200, 1600, 3), np.uint8), 1024).shape[:2] == (768, 1024)

    assert doctor.get(f"/api/v1/cases/{case['id']}").json()["aiResult"] == {
        "code": "nv",
        "labelUk": "Меланоцитарний невус",
        "score": pytest.approx(0.40),
    }
    assert doctor.get("/api/v1/cases").json()["items"][0]["aiResult"]["code"] == "nv"

    actions = db.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == "ai_analysis")).all()
    assert sorted(actions) == ["analysis_completed", "analysis_requested"]
    for meta in db.scalars(select(AuditEvent.metadata_json).where(AuditEvent.entity_type == "ai_analysis")):
        assert set(meta) <= {"caseId", "imageId", "xaiCompleted", "xaiFailed"}


def test_one_active_analysis_per_case_and_history(doctor, use_engine):
    gate = threading.Event()
    use_engine(FakeEngine(gate=gate))
    case = case_with_photo(doctor)
    first = doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()

    r = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ANALYSIS_IN_PROGRESS"
    assert doctor.get(f"/api/v1/analyses/{first['id']}").json()["status"] in ("Queued", "Running")
    assert doctor.get(f"/api/v1/cases/{case['id']}").json()["aiResult"] is None

    gate.set()
    assert wait_done(doctor, first["id"])["status"] == "Completed"
    second = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
    assert second.status_code == 202
    wait_done(doctor, second.json()["id"])
    history = doctor.get(f"/api/v1/cases/{case['id']}/analyses").json()
    assert [a["id"] for a in history] == [second.json()["id"], first["id"]]  # newest first, old kept


@pytest.mark.parametrize(
    "exc, code",
    [
        (InferenceError("AI_NAN", "non-finite model output"), "AI_NAN"),
        (RuntimeError("secret internal detail /models/x.h5"), "AI_INTERNAL"),
    ],
)
def test_failed_analysis_keeps_safe_code_and_allows_retry(doctor, use_engine, exc, code):
    use_engine(FakeEngine(fail=exc))
    case = case_with_photo(doctor)
    res = wait_done(doctor, doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"])
    assert res["status"] == "Failed" and res["errorCode"] == code
    assert res["predictedClass"] is None and res["scores"] == [] and res["xai"] == []
    assert "secret" not in res["errorMessage"] and "/models" not in str(res)

    use_engine(FakeEngine())
    retry = wait_done(doctor, doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"])
    assert retry["status"] == "Completed"
    assert len(doctor.get(f"/api/v1/cases/{case['id']}/analyses").json()) == 2


def test_preconditions_photo_and_case_status(doctor, use_engine, db):
    use_engine(FakeEngine())
    no_photo = new_case(doctor, new_patient(doctor)["id"])
    r = doctor.post(f"/api/v1/cases/{no_photo['id']}/analyses")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_IMAGE"

    case = case_with_photo(doctor)
    for status, allowed in ((CaseStatus.FOLLOW_UP_PLANNED, True), (CaseStatus.CLOSED, False)):
        db.execute(
            text("UPDATE cases SET status = :s, follow_up_date = CURRENT_DATE + 7 WHERE id = :id"),
            {"s": status.value, "id": case["id"]},
        )
        db.commit()
        r = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
        if allowed:
            assert r.status_code == 202
            wait_done(doctor, r.json()["id"])
        else:
            assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_NOT_ANALYZABLE"


def test_queue_limit_returns_busy(doctor, use_engine):
    gate = threading.Event()
    use_engine(FakeEngine(gate=gate), max_concurrent=1, max_queued=1)
    cases = [case_with_photo(doctor) for _ in range(3)]
    assert doctor.post(f"/api/v1/cases/{cases[0]['id']}/analyses").status_code == 202
    assert doctor.post(f"/api/v1/cases/{cases[1]['id']}/analyses").status_code == 202
    r = doctor.post(f"/api/v1/cases/{cases[2]['id']}/analyses")
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI_BUSY"
    gate.set()


def test_stale_analysis_times_out_and_late_job_writes_nothing(doctor, use_engine, db, app, storage_root):
    from app.db.session import get_sessionmaker
    from app.services.analyses import run_analysis
    from app.storage.local import LocalStorage

    gate = threading.Event()
    engine = FakeEngine(gate=gate)
    use_engine(engine)
    case = case_with_photo(doctor)
    aid = doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"]
    db.execute(
        text("UPDATE ai_analyses SET created_at = :t WHERE id = :id"),
        {"t": datetime.now(UTC) - timedelta(hours=1), "id": aid},
    )
    db.commit()
    res = doctor.get(f"/api/v1/analyses/{aid}").json()
    assert res["status"] == "Failed" and res["errorCode"] == "AI_TIMEOUT"

    gate.set()
    deadline = time.monotonic() + 10
    while app.state.ai.pending and time.monotonic() < deadline:
        time.sleep(0.05)
    assert doctor.get(f"/api/v1/analyses/{aid}").json()["status"] == "Failed"
    calls = engine.calls
    run_analysis(engine, get_sessionmaker(), LocalStorage(storage_root), aid, 1024)
    assert engine.calls == calls
    # a new run is possible right away
    assert doctor.post(f"/api/v1/cases/{case['id']}/analyses").status_code == 202


def test_restart_marks_unfinished_analyses_interrupted(doctor, use_engine, db):
    from app.db.session import get_sessionmaker
    from app.services.analyses import fail_interrupted

    gate = threading.Event()
    use_engine(FakeEngine(gate=gate))
    case = case_with_photo(doctor)
    aid = doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"]
    assert fail_interrupted(get_sessionmaker()) == 1
    gate.set()
    res = doctor.get(f"/api/v1/analyses/{aid}").json()
    assert res["status"] == "Failed" and res["errorCode"] == "AI_INTERRUPTED"


@pytest.mark.parametrize(
    "service, status, code",
    [
        (AiService(None, unavailable_code="MODEL_FILE_MISSING"), "unavailable", "AI_UNAVAILABLE"),
        (AiService(lambda: FakeEngine()), "loading", "AI_LOADING"),
    ],
)
def test_ai_not_ready_returns_503_and_rest_of_api_works(app, doctor, service, status, code):
    app.state.ai = service
    case = case_with_photo(doctor)  # patients, cases and uploads keep working
    r = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
    assert r.status_code == 503 and r.json()["error"]["code"] == code
    assert doctor.get("/api/v1/patients").status_code == 200
    assert doctor.get("/api/v1/health/ready").status_code == 200

    st = doctor.get("/api/v1/system/ai-status").json()
    assert st["status"] == status and st["model"] == "ensemble_best"
    assert st["components"] == ["AlexNet", "ResNet", "DenseNet"]
    assert st["xaiMethods"] == ["gradcam", "gradcam_pp"]
    if status == "unavailable":
        assert st["code"] == "MODEL_FILE_MISSING" and st["message"] == "Файл моделі не знайдено на сервері"
        assert st["modelVersion"] is None


def test_ai_status_ready_for_every_role_without_internal_details(app, make_user, login_as, use_engine):
    use_engine(FakeEngine())
    for role in Role:
        st = login_as(make_user(role)).get("/api/v1/system/ai-status")
        assert st.status_code == 200
        body = st.json()
        assert body["status"] == "ready" and body["code"] is None and body["modelVersion"] == "f" * 12
        assert set(body) == {  # nothing about paths, hosts or exceptions
            "status",
            "code",
            "message",
            "model",
            "modelVersion",
            "preprocessingVersion",
            "components",
            "xaiMethods",
            "maxConcurrentAnalyses",
            "pendingAnalyses",
            "gateStatus",
        }


def test_loader_failures_become_unavailable_codes(tmp_path):
    from app.ai.loader import ModelUnavailable
    from app.ai.preprocessing import NormalizationUnavailable

    def boom(exc):
        def _load():
            raise exc

        return _load

    for exc, code in [
        (ModelUnavailable("MODEL_CHECKSUM_MISMATCH", "x"), "MODEL_CHECKSUM_MISMATCH"),
        (NormalizationUnavailable("x"), "NORMALIZATION_UNAVAILABLE"),
        (OSError("disk"), "MODEL_LOAD_FAILED"),
    ]:
        svc = AiService(boom(exc))
        svc.start()
        assert svc.wait_loaded(10)
        assert svc.state == AiState.UNAVAILABLE and svc.reason_code == code and svc.engine is None


def test_missing_model_file_reports_model_file_missing(tmp_path):
    from app.ai.engine import EnsembleEngine

    svc = AiService(lambda: EnsembleEngine(tmp_path))
    svc.start()
    assert svc.wait_loaded(60)
    assert svc.state == AiState.UNAVAILABLE and svc.reason_code == "MODEL_FILE_MISSING"


def test_other_doctor_gets_404_and_other_roles_403(doctor, use_engine, make_user, login_as):
    use_engine(FakeEngine())
    case = case_with_photo(doctor)
    res = wait_done(doctor, doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"])
    art = next(x for x in res["xai"] if x["url"])

    other = login_as(make_user(Role.DOCTOR))
    for method, url in [
        ("POST", f"/api/v1/cases/{case['id']}/analyses"),
        ("GET", f"/api/v1/cases/{case['id']}/analyses"),
        ("GET", f"/api/v1/analyses/{res['id']}"),
        ("GET", art["url"]),
    ]:
        assert other.request(method, url).status_code == 404, url
    case2 = case_with_photo(other)
    res2 = wait_done(other, other.post(f"/api/v1/cases/{case2['id']}/analyses").json()["id"])
    assert other.get(f"/api/v1/analyses/{res2['id']}/xai/{art['id']}").status_code == 404

    for role in (Role.ADMIN, Role.LAB_SPECIALIST):  # the lab sees analyses only through referrals
        c = login_as(make_user(role))
        assert c.get(f"/api/v1/analyses/{res['id']}").status_code == 403
        assert c.get(art["url"]).status_code == 403
        assert c.post(f"/api/v1/cases/{case['id']}/analyses").status_code == 403


@pytest.mark.skipif(
    not ((MODELS_DIR / "ensemble_best.h5").is_file() and TEST_PHOTO.is_file()),
    reason="model weights or HAM10000 test photo not available locally",
)
def test_real_ensemble_end_to_end(app, doctor, monkeypatch):
    from app.ai.engine import EnsembleEngine

    svc = AiService(lambda: EnsembleEngine(MODELS_DIR))
    svc.start()
    assert svc.wait_loaded(180) and svc.state == AiState.READY, svc.reason_code
    app.state.ai = svc

    case = case_with_photo(doctor, TEST_PHOTO.read_bytes())
    res = wait_done(doctor, doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"], timeout=120)
    assert res["status"] == "Completed", res
    assert res["predictedClass"]["code"] == "bcc"
    assert res["score"] == pytest.approx(0.658, abs=1e-3)
    assert sum(s["score"] for s in res["scores"]) == pytest.approx(1.0, abs=1e-4)
    assert res["modelVersion"] == "4890489c3ea6"
    assert len(res["xai"]) == 6 and all(x["status"] == "Completed" for x in res["xai"]), res["xai"]
    for x in res["xai"]:
        img = cv2.imdecode(np.frombuffer(doctor.get(x["url"]).content, np.uint8), cv2.IMREAD_COLOR)
        assert img.shape[:2] == (450, 600)  # same geometry as the original photo


def test_xai_component_constants_match_loader():
    from app.ai.loader import COMPONENTS

    assert [(c.name, c.feature_layer) for c in COMPONENTS] == [(n, layer) for n, layer, _ in XAI_COMPONENTS]
