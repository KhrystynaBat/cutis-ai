from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db


def test_live_does_not_need_db(client_no_db):
    r = client_no_db.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ready_with_migrated_db(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_ready_returns_503_when_db_down(client_no_db):
    dead = sessionmaker(
        bind=create_engine("postgresql+psycopg://x:y@127.0.0.1:9/none", connect_args={"connect_timeout": 1})
    )

    def broken_db():
        with dead() as s:
            yield s

    client_no_db.app.dependency_overrides[get_db] = broken_db
    r = client_no_db.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_unknown_route_uses_uniform_error_format(client_no_db):
    r = client_no_db.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND" and err["correlationId"] == r.headers["X-Request-ID"]


def test_correlation_id_echoed_only_if_safe(client_no_db):
    r = client_no_db.get("/api/v1/health/live", headers={"X-Request-ID": "abcDEF12-3456"})
    assert r.headers["X-Request-ID"] == "abcDEF12-3456"
    r = client_no_db.get("/api/v1/health/live", headers={"X-Request-ID": "<script>"})
    assert r.headers["X-Request-ID"] != "<script>" and len(r.headers["X-Request-ID"]) == 32


def test_cors_allows_only_configured_origins(client_no_db):
    ok = client_no_db.options(
        "/api/v1/health/live",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:4200"
    bad = client_no_db.options(
        "/api/v1/health/live",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_openapi_served_under_api_prefix(client_no_db):
    r = client_no_db.get("/api/v1/openapi.json")
    assert r.status_code == 200 and "/api/v1/health/ready" in r.json()["paths"]
