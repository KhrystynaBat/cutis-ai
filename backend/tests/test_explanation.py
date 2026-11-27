from __future__ import annotations

import base64
import json
import time
import uuid

import cv2
import httpx
import numpy as np
import pytest
from sqlalchemy import select
from test_analyses import FakeEngine, case_with_photo, wait_done
from test_lab import RESULT, _pdf_text, approve, make_referral
from test_patients_cases import jpeg

from app.ai.service import AiService
from app.db.models import AiAnalysis, ExplanationStatus, Role
from app.db.session import get_sessionmaker
from app.explain.gemini import API_URL, ExplainError, GeminiClient, ImagePart
from app.explain.service import SCHEMA, ExplanationService
from app.services.analyses import fail_interrupted

GOOD = {
    "classification": {
        "result": "Система віднесла утворення до меланоцитарного невусу (40%), меланома близько (30%).",
        "heatmaps": "Найбільше уваги система приділила темнішій центральній ділянці.",
    },
    "discrepancy": "",
    "description": {
        "intro": "На представленому зображенні візуалізується пігментоване новоутворення шкіри:",
        "features": [
            {"label": "Форма", "value": "видовжена, з ознаками асиметрії"},
            {"label": "Пігментна сітка", "value": "виражена, неоднорідна"},
            {"label": "Розмір", "value": "неможливо визначити без масштабної шкали"},
        ],
    },
    "assessment": {
        "intro": "Новоутворення може належати до меланоцитарних уражень.",
        "differential": ["меланоцитарний невус (NV)", "атиповий меланоцитарний невус", "меланома (MEL)"],
    },
    "recommendations": "Рекомендовано клінічний огляд і дерматоскопію в динаміці.",
    "conclusion": "пігментоване новоутворення з ознаками колірної неоднорідності.",
}
BROKEN = {"summary": "текст"}


class FakeClient:
    model = "gemini-test"

    def __init__(self, reply: dict | Exception = GOOD):
        self.reply = reply
        self.calls: list[tuple[str, list, dict]] = []

    def generate_json(self, system, parts, schema):
        self.calls.append((system, parts, schema))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def doctor(make_user, login_as):
    return login_as(make_user(Role.DOCTOR))


@pytest.fixture
def ai_ready(app):
    app.state.ai = svc = AiService.ready_with(FakeEngine())
    yield svc
    deadline = time.monotonic() + 30
    while svc.pending and time.monotonic() < deadline:
        time.sleep(0.05)


@pytest.fixture
def use_client(app):
    services: list[ExplanationService] = []

    def _use(client: FakeClient | None) -> ExplanationService:
        app.state.explainer = ExplanationService(lambda: client, get_sessionmaker, 1024)
        services.append(app.state.explainer)
        return app.state.explainer

    yield _use
    deadline = time.monotonic() + 30
    while any(s.pending for s in services) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(s.pending for s in services), "background explanation jobs did not finish"


def wait_explained(c, analysis_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = c.get(f"/api/v1/analyses/{analysis_id}").json()
        if body["explanation"] and body["explanation"]["status"] != "Pending":
            return body
        time.sleep(0.05)
    raise AssertionError(f"explanation for {analysis_id} did not finish")


def analyzed(doctor, photo: bytes | None = None) -> str:
    case = case_with_photo(doctor, photo)
    r = doctor.post(f"/api/v1/cases/{case['id']}/analyses")
    assert r.status_code == 202, r.text
    assert wait_done(doctor, r.json()["id"])["status"] == "Completed"
    return r.json()["id"]


def test_explanation_after_analysis_is_stored_and_not_requested_again(doctor, ai_ready, use_client):
    client = FakeClient()
    use_client(client)
    aid = analyzed(doctor, jpeg(1600, 1200))

    body = wait_explained(doctor, aid)
    assert body["status"] == "Completed" and body["predictedClass"]["code"] == "nv"  # analysis unchanged
    e = body["explanation"]
    assert e["status"] == "Completed" and e["model"] == "gemini-test" and e["errorCode"] is None
    assert e["classification"]["result"].startswith("Система віднесла")
    assert "уваги" in e["classification"]["heatmaps"]
    assert e["description"]["intro"].startswith("На представленому зображенні")
    assert [f["label"] for f in e["description"]["features"]] == ["Форма", "Пігментна сітка", "Розмір"]
    assert e["assessment"]["differential"] == ["меланоцитарний невус", "атиповий меланоцитарний невус", "меланома"]
    assert e["recommendations"].startswith("Рекомендовано") and e["conclusion"]

    system, parts, schema = client.calls[0]
    assert schema is SCHEMA
    assert "Поясни лікарю результат класифікації та карт" in system and "щодо лікування" in system
    assert "не підганяй під клас системи" in system and "без застережень" in system
    assert "без кодів класів" in system and "AKIEC" not in system
    assert "на що звернути увагу" in system and "характерні для меланоми" in system
    assert "Не пиши, що система помилилась" in system
    assert e["discrepancy"] == ""
    assert "простою зрозумілою" in system and "не згадуй назви нейромереж" in system
    assert "у відсотках" in system and "note" not in system
    text = parts[0]
    assert "Меланоцитарний невус (NV), оцінка 0.400" in text
    top3 = [line for line in text.splitlines() if line.startswith("- ")]
    assert [line.split("(")[-1].split(")")[0] for line in top3] == ["NV", "MEL", "BCC"]
    labels = [p for p in parts[2:] if isinstance(p, str)]
    assert labels == [f"Теплова карта Grad-CAM++ моделі {n}:" for n in ("AlexNet", "ResNet", "DenseNet")]
    images = [p for p in parts if isinstance(p, ImagePart)]
    assert [p.mime_type for p in images] == ["image/jpeg", "image/png", "image/png", "image/png"]
    photo = cv2.imdecode(np.frombuffer(images[0].data, np.uint8), cv2.IMREAD_COLOR)
    assert photo.shape[:2] == (768, 1024)  # display copy, longest side 1024

    for _ in range(3):  # reopening the page reads the stored text
        assert doctor.get(f"/api/v1/analyses/{aid}").json()["explanation"]["status"] == "Completed"
        assert doctor.get(f"/api/v1/cases/{body['caseId']}/analyses").json()[0]["explanation"]["status"] == "Completed"
    assert len(client.calls) == 1


def test_disagreement_with_the_system_is_returned(doctor, ai_ready, use_client):
    warning = "Система віднесла утворення до невусу, але на фото видно атипову сітку й регресію."
    use_client(FakeClient({**GOOD, "discrepancy": warning}))
    e = wait_explained(doctor, analyzed(doctor))["explanation"]
    assert e["status"] == "Completed" and e["discrepancy"] == warning


def test_without_key_explanation_fails_and_analysis_still_completes(doctor, ai_ready, use_client):
    use_client(None)
    aid = analyzed(doctor)
    body = doctor.get(f"/api/v1/analyses/{aid}").json()
    assert body["status"] == "Completed" and len(body["xai"]) == 6
    assert body["explanation"]["status"] == "Failed"
    assert body["explanation"]["errorCode"] == "EXPLAIN_NO_KEY"
    assert body["explanation"]["errorMessage"]

    client = FakeClient()
    use_client(client)
    r = doctor.post(f"/api/v1/analyses/{aid}/explanation")
    assert r.status_code == 202 and r.json()["explanation"]["status"] == "Pending"
    assert wait_explained(doctor, aid)["explanation"]["status"] == "Completed"


@pytest.mark.parametrize(
    "reply, code",
    [
        (ExplainError("EXPLAIN_RATE_LIMIT"), "EXPLAIN_RATE_LIMIT"),
        (ExplainError("EXPLAIN_UNAVAILABLE"), "EXPLAIN_UNAVAILABLE"),
        ({**GOOD, "conclusion": ""}, "EXPLAIN_BAD_RESPONSE"),
        ({**GOOD, "assessment": {"intro": "x", "differential": []}}, "EXPLAIN_BAD_RESPONSE"),
        (BROKEN, "EXPLAIN_BAD_RESPONSE"),
        (RuntimeError("boom"), "EXPLAIN_INTERNAL"),
    ],
)
def test_gemini_errors_become_a_retryable_failed_state(doctor, ai_ready, use_client, reply, code):
    use_client(FakeClient(reply))
    aid = analyzed(doctor)
    body = wait_explained(doctor, aid)
    assert body["status"] == "Completed"
    assert body["explanation"]["status"] == "Failed" and body["explanation"]["errorCode"] == code

    use_client(FakeClient())
    assert doctor.post(f"/api/v1/analyses/{aid}/explanation").status_code == 202
    assert wait_explained(doctor, aid)["explanation"]["status"] == "Completed"


def test_retry_rules(doctor, ai_ready, use_client, db, make_user, login_as):
    use_client(FakeClient())
    aid = analyzed(doctor)
    wait_explained(doctor, aid)
    a = db.get(AiAnalysis, uuid.UUID(aid))
    a.explanation_status = ExplanationStatus.PENDING
    db.commit()
    r = doctor.post(f"/api/v1/analyses/{aid}/explanation")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EXPLANATION_IN_PROGRESS"

    other = login_as(make_user(Role.DOCTOR))
    assert other.post(f"/api/v1/analyses/{aid}/explanation").status_code == 404
    lab = login_as(make_user(Role.LAB_SPECIALIST))
    assert lab.post(f"/api/v1/analyses/{aid}/explanation").status_code == 403


def test_unreadable_stored_explanation_offers_a_retry(doctor, ai_ready, use_client, db):
    use_client(FakeClient())
    aid = analyzed(doctor)
    wait_explained(doctor, aid)
    a = db.get(AiAnalysis, uuid.UUID(aid))
    a.explanation_json = BROKEN
    db.commit()
    e = doctor.get(f"/api/v1/analyses/{aid}").json()["explanation"]
    assert e["status"] == "Failed" and e["errorCode"] == "EXPLAIN_BAD_RESPONSE"
    assert doctor.post(f"/api/v1/analyses/{aid}/explanation").status_code == 202
    assert wait_explained(doctor, aid)["explanation"]["status"] == "Completed"


def test_restart_and_stale_pending_explanations_fail(doctor, ai_ready, use_client, db):
    use_client(FakeClient())
    aid = analyzed(doctor)
    wait_explained(doctor, aid)
    a = db.get(AiAnalysis, uuid.UUID(aid))
    a.explanation_status = ExplanationStatus.PENDING
    db.commit()
    fail_interrupted(get_sessionmaker())
    assert doctor.get(f"/api/v1/analyses/{aid}").json()["explanation"]["errorCode"] == "EXPLAIN_INTERRUPTED"

    db.refresh(a)
    a.explanation_status = ExplanationStatus.PENDING
    a.explanation_updated_at = a.explanation_updated_at.replace(year=2020)
    db.commit()
    assert doctor.get(f"/api/v1/analyses/{aid}").json()["explanation"]["errorCode"] == "EXPLAIN_TIMEOUT"


def test_lab_never_sees_the_explanation_and_pdf_has_none(make_user, login_as, db, storage_root):
    dc = login_as(make_user(Role.DOCTOR))
    lc = login_as(make_user(Role.LAB_SPECIALIST))
    ref = make_referral(dc, db, storage_root)
    a = db.scalar(select(AiAnalysis))
    a.explanation_status = ExplanationStatus.COMPLETED
    a.explanation_json = {
        "classification": {"result": "СЕКРЕТНИЙ-МАРКЕР", "heatmaps": "СЕКРЕТНИЙ-МАРКЕР"},
        "discrepancy": "СЕКРЕТНИЙ-МАРКЕР",
        "description": {"intro": "СЕКРЕТНИЙ-МАРКЕР", "features": [{"label": "Форма", "value": "СЕКРЕТНИЙ-МАРКЕР"}]},
        "assessment": {"intro": "СЕКРЕТНИЙ-МАРКЕР", "differential": ["СЕКРЕТНИЙ-МАРКЕР"]},
        "recommendations": "СЕКРЕТНИЙ-МАРКЕР",
        "conclusion": "СЕКРЕТНИЙ-МАРКЕР",
    }
    db.commit()

    assert "СЕКРЕТНИЙ-МАРКЕР" in dc.get(f"/api/v1/analyses/{a.id}").text
    lab_detail = lc.get(f"/api/v1/referrals/{ref['id']}")
    assert lab_detail.status_code == 200
    assert lab_detail.json()["analysis"]["explanation"] is None
    assert "СЕКРЕТНИЙ-МАРКЕР" not in lab_detail.text
    assert lc.get(f"/api/v1/analyses/{a.id}").status_code == 403

    assert approve(lc, ref["id"], RESULT).status_code == 200
    pdf, _ = _pdf_text(lc.get(f"/api/v1/referrals/{ref['id']}/lab-result.pdf").content)
    assert "СЕКРЕТНИЙ-МАРКЕР" not in pdf and "Пояснення ШІ" not in pdf


# --- REST client, no network: httpx.MockTransport


def _reply(payload: dict | str, status: int = 200) -> httpx.Response:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(status, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_gemini_client_request_shape_and_parsing():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _reply(GOOD)

    client = GeminiClient("test-key", "gemini-x", transport=httpx.MockTransport(handler))
    out = client.generate_json("SYS", ["hello", ImagePart("image/png", b"\x89PNG")], {"type": "object"})
    assert out == GOOD

    req = seen[0]
    assert str(req.url) == API_URL.format(model="gemini-x")
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "hello"}
    assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": base64.b64encode(b"\x89PNG").decode()}
    assert body["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseJsonSchema": {"type": "object"},
    }


@pytest.mark.parametrize(
    "response, code",
    [
        (httpx.Response(429, json={}), "EXPLAIN_RATE_LIMIT"),
        (httpx.Response(503, json={}), "EXPLAIN_UNAVAILABLE"),
        (httpx.Response(403, json={}), "EXPLAIN_AUTH"),
        (httpx.Response(400, json={}), "EXPLAIN_REJECTED"),
        (_reply("not json"), "EXPLAIN_BAD_RESPONSE"),
        (httpx.Response(200, json={"candidates": []}), "EXPLAIN_BAD_RESPONSE"),
    ],
)
def test_gemini_client_error_codes(response, code):
    client = GeminiClient("k", "m", transport=httpx.MockTransport(lambda r: response))
    with pytest.raises(ExplainError) as e:
        client.generate_json("s", ["t"], {})
    assert e.value.code == code


def test_gemini_client_network_errors():
    def timeout(request):
        raise httpx.ReadTimeout("slow")

    def down(request):
        raise httpx.ConnectError("down")

    for handler, code in ((timeout, "EXPLAIN_TIMEOUT"), (down, "EXPLAIN_UNAVAILABLE")):
        with pytest.raises(ExplainError) as e:
            GeminiClient("k", "m", transport=httpx.MockTransport(handler)).generate_json("s", ["t"], {})
        assert e.value.code == code


def test_thought_parts_are_skipped():
    payload = {
        "candidates": [{"content": {"parts": [{"text": "thinking…", "thought": True}, {"text": json.dumps(GOOD)}]}}]
    }
    client = GeminiClient("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    assert client.generate_json("s", ["t"], {}) == GOOD


def test_key_comes_only_from_settings(monkeypatch):
    from app.core.config import Settings

    assert Settings().gemini_api_key.get_secret_value() == ""
    assert ExplanationService.from_settings(Settings()).enabled is False
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    s = Settings()
    assert ExplanationService.from_settings(s).enabled is True
    assert "abc" not in repr(s)


def test_overloaded_model_falls_back_to_the_next_one():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path.rsplit("/", 1)[-1])
        if "main" in request.url.path:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return _reply(GOOD)

    client = GeminiClient("k", "main", transport=httpx.MockTransport(handler), fallback_models=("backup",))
    assert client.generate_json("s", ["t"], {}) == GOOD
    assert seen == ["main:generateContent", "backup:generateContent"]
    assert client.model == "backup"


@pytest.mark.parametrize(
    "status, code", [(503, "EXPLAIN_UNAVAILABLE"), (429, "EXPLAIN_RATE_LIMIT"), (403, "EXPLAIN_AUTH")]
)
def test_fallback_only_for_overload(status, code):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(status, json={})

    client = GeminiClient("k", "main", transport=httpx.MockTransport(handler), fallback_models=("backup",))
    with pytest.raises(ExplainError) as e:
        client.generate_json("s", ["t"], {})
    assert e.value.code == code
    assert len(seen) == (2 if status == 503 else 1)
