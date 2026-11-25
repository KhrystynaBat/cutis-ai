from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from test_analyses import FakeEngine, wait_done
from test_patients_cases import jpeg, new_case, new_patient

from app.ai import gatekeeper
from app.ai.gatekeeper import GateService
from app.api.v1.cases import NOT_DERMOSCOPIC
from app.db.models import AuditEvent, CaseImage, Role
from app.services import image_gate
from app.storage.local import LocalStorage

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "gatekeeper.h5"
CHECK_CSV = Path(__file__).parent / "data" / "gatekeeper_check.csv"
HAM_DIR = ROOT / "data" / "images"


class FakeGate:
    model_sha256 = "a" * 64
    threshold = 0.5

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.calls = 0

    def predict(self, image_bytes: bytes) -> float:
        self.calls += 1
        if self.fail:
            raise self.fail
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        return 0.9 if img.mean() > 100 else 0.1


def photo(value: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", np.full((240, 320, 3), value, np.uint8))
    assert ok
    return buf.tobytes()


DERMOSCOPIC, CAT = photo(200), photo(20)


@pytest.fixture
def doctor(make_user, login_as):
    return login_as(make_user(Role.DOCTOR))


@pytest.fixture
def use_gate(app):
    def _use(model=None) -> GateService:
        app.state.gate = GateService(model)
        return app.state.gate

    return _use


def _case(c) -> dict:
    return new_case(c, new_patient(c)["id"])


def _upload(c, case_id, data, confirm: bool | None = None):
    form = {} if confirm is None else {"confirm_non_dermoscopic": "true" if confirm else "false"}
    return c.post(f"/api/v1/cases/{case_id}/images", files={"file": ("p.jpg", data, "image/jpeg")}, data=form)


def test_preprocess_is_rgb_uint8_160():
    bgr = np.zeros((300, 200, 3), np.uint8)
    bgr[..., 2] = 255  # pure red in OpenCV's BGR order
    ok, buf = cv2.imencode(".png", bgr)
    x = gatekeeper.preprocess(buf.tobytes())
    assert x.shape == (1, 160, 160, 3) and x.dtype == np.uint8
    assert x[0, ..., 0].min() >= 250 and x[0, ..., 2].max() == 0


def test_preprocess_matches_tf_resize_with_antialias():
    import tensorflow as tf

    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    expected = tf.cast(tf.clip_by_value(tf.image.resize(rgb, (160, 160), antialias=True), 0, 255), tf.uint8)
    assert np.array_equal(gatekeeper.preprocess(buf.tobytes())[0], expected.numpy())


def test_config_matches_training_config():
    cfg = gatekeeper.load_config()
    assert cfg.input_size == (160, 160) and cfg.threshold == 0.5 and len(cfg.sha256) == 64


def test_rejected_photo_needs_confirmation(doctor, use_gate, db, storage_root):
    use_gate(FakeGate())
    case = _case(doctor)
    for confirm in (None, False):
        r = _upload(doctor, case["id"], CAT, confirm)
        assert r.status_code == 422, r.text
        assert r.json()["error"] == {**r.json()["error"], "code": "IMAGE_NOT_DERMOSCOPIC", "message": NOT_DERMOSCOPIC}
    assert db.scalar(select(CaseImage)) is None
    assert not storage_root.exists() or not any(p.is_file() for p in storage_root.rglob("*"))

    r = _upload(doctor, case["id"], CAT, confirm=True)
    assert r.status_code == 201, r.text
    assert r.json()["gateOverridden"] is True
    img = db.scalar(select(CaseImage))
    assert img.gate_passed is False and img.gate_score == pytest.approx(0.1)
    assert img.gate_model_sha256 == "a" * 64
    assert img.gate_confirmed_by_id is not None and img.gate_confirmed_at is not None
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "image_gate_override"))
    assert ev.entity_id == case["id"] and ev.metadata_json == {"imageId": str(img.id)}
    # the case card shows the flag on the photo
    assert doctor.get(f"/api/v1/cases/{case['id']}").json()["image"]["gateOverridden"] is True


def test_dermoscopic_photo_is_stored_with_the_result(doctor, use_gate, db):
    use_gate(FakeGate())
    case = _case(doctor)
    r = _upload(doctor, case["id"], DERMOSCOPIC)
    assert r.status_code == 201 and r.json()["gateOverridden"] is False
    img = db.scalar(select(CaseImage))
    assert img.gate_passed is True and img.gate_score == pytest.approx(0.9)
    assert img.gate_confirmed_by_id is None and img.gate_confirmed_at is None
    r = _upload(doctor, case["id"], DERMOSCOPIC, confirm=True)
    assert r.status_code == 201 and r.json()["gateOverridden"] is False
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "image_gate_override")) is None


@pytest.mark.parametrize("model", [None, FakeGate(fail=RuntimeError("tf"))], ids=["not-loaded", "error"])
def test_unavailable_filter_does_not_block(doctor, use_gate, db, caplog, model):
    use_gate(model)
    case = _case(doctor)
    with caplog.at_level(logging.WARNING, logger="dermalab.ai"):
        r = _upload(doctor, case["id"], CAT)
    assert r.status_code == 201, r.text
    img = db.scalar(select(CaseImage))
    assert (img.gate_score, img.gate_passed, img.gate_model_sha256, img.gate_confirmed_by_id) == (None,) * 4
    assert any("image filter" in rec.getMessage() for rec in caplog.records)
    check = doctor.post("/api/v1/images/check", files={"file": ("p.jpg", CAT, "image/jpeg")})
    assert check.json() == {"passed": True, "score": None}


def test_broken_files_are_still_rejected_hard(doctor, use_gate):
    use_gate(FakeGate())
    case = _case(doctor)
    r = _upload(doctor, case["id"], b"not an image", confirm=True)
    assert r.status_code == 415


def test_check_endpoint_stores_nothing(doctor, use_gate, db, storage_root):
    gate = FakeGate()
    use_gate(gate)
    ok = doctor.post("/api/v1/images/check", files={"file": ("p.jpg", DERMOSCOPIC, "image/jpeg")})
    bad = doctor.post("/api/v1/images/check", files={"file": ("c.jpg", CAT, "image/jpeg")})
    assert ok.status_code == 200 and ok.json() == {"passed": True, "score": pytest.approx(0.9)}
    assert bad.json() == {"passed": False, "score": pytest.approx(0.1)}
    assert gate.calls == 2
    assert db.scalar(select(CaseImage)) is None
    assert not storage_root.exists() or not any(p.is_file() for p in storage_root.rglob("*"))
    # same validation as an upload
    assert doctor.post("/api/v1/images/check", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 415


@pytest.mark.parametrize("role", [Role.LAB_SPECIALIST, Role.ADMIN])
def test_check_is_for_doctors_only(role, make_user, login_as, use_gate):
    use_gate(FakeGate())
    c = login_as(make_user(role))
    assert c.post("/api/v1/images/check", files={"file": ("p.jpg", DERMOSCOPIC, "image/jpeg")}).status_code == 403


def test_check_uses_the_upload_rate_limit(doctor, use_gate, app):
    use_gate(FakeGate())
    app.state.upload_limiter.max_failures = 2
    for _ in range(2):
        assert doctor.post("/api/v1/images/check", files={"file": ("p.jpg", jpeg(), "image/jpeg")}).status_code == 200
    r = doctor.post("/api/v1/images/check", files={"file": ("p.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 429


def test_analysis_reports_the_manual_confirmation(doctor, use_gate, app):
    from app.ai.service import AiService

    use_gate(FakeGate())
    app.state.ai = AiService.ready_with(FakeEngine())
    case = _case(doctor)
    assert _upload(doctor, case["id"], CAT, confirm=True).status_code == 201
    res = wait_done(doctor, doctor.post(f"/api/v1/cases/{case['id']}/analyses").json()["id"])
    assert res["imageGateOverridden"] is True

    other = _case(doctor)
    assert _upload(doctor, other["id"], DERMOSCOPIC).status_code == 201
    res = wait_done(doctor, doctor.post(f"/api/v1/cases/{other['id']}/analyses").json()["id"])
    assert res["imageGateOverridden"] is False


def test_status_reports_the_filter(doctor, use_gate):
    use_gate(FakeGate())
    assert doctor.get("/api/v1/system/ai-status").json()["gateStatus"] == "ready"
    use_gate(None)
    assert doctor.get("/api/v1/system/ai-status").json()["gateStatus"] == "unavailable"


def test_missing_or_changed_model_file_leaves_filter_unavailable(tmp_path):
    svc = GateService.loading()
    svc.load(tmp_path)
    assert svc.state == "unavailable" and svc.reason_code == "GATE_FILE_MISSING" and svc.check(DERMOSCOPIC) is None
    (tmp_path / "gatekeeper.h5").write_bytes(b"not the audited file")
    svc = GateService.loading()
    svc.load(tmp_path)
    assert svc.reason_code == "GATE_CHECKSUM_MISMATCH"


def test_backfill_fills_old_photos_without_confirmation(doctor, use_gate, db, storage_root):
    use_gate(None)  # uploaded while the filter was unavailable
    case = _case(doctor)
    assert _upload(doctor, case["id"], CAT).status_code == 201
    case2 = _case(doctor)
    assert _upload(doctor, case2["id"], DERMOSCOPIC).status_code == 201

    rows = image_gate.backfill(db, LocalStorage(storage_root), GateService(FakeGate()))
    assert sorted(r.score for r in rows) == pytest.approx([0.1, 0.9])
    imgs = db.scalars(select(CaseImage)).all()
    assert sorted(i.gate_passed for i in imgs) == [False, True]
    assert all(i.gate_confirmed_by_id is None for i in imgs)
    assert image_gate.backfill(db, LocalStorage(storage_root), GateService(FakeGate())) == []


def test_real_model_matches_reference_predictions():
    if not MODEL.is_file() or not CHECK_CSV.is_file():
        pytest.skip("models/gatekeeper.h5 is not available")
    check = pd.read_csv(CHECK_CSV)
    check = check[[(HAM_DIR / f"{i}.jpg").is_file() for i in check.image_id]]
    if check.empty:
        pytest.skip("HAM10000 photos from check_predictions.csv are not available locally")
    svc = GateService.loading()
    svc.load(MODEL.parent)
    assert svc.state == "ready", svc.reason_code
    for image_id, p in zip(check.image_id, check.p, strict=True):
        result = svc.check((HAM_DIR / f"{image_id}.jpg").read_bytes())
        assert abs(result.score - p) < 1e-3, image_id
        assert result.passed
