import re
import uuid

import pytest

from app.db.models import Role

PUBLIC = {
    ("get", "/api/v1/health/live"),
    ("get", "/api/v1/health/ready"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/login/confirm"),
    ("post", "/api/v1/auth/email-change/confirm"),
    ("post", "/api/v1/auth/login/resend"),
    ("post", "/api/v1/auth/set-password"),
}


def _operations(app):
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            yield method, path


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_public_endpoint_list_is_exact(app):
    assert PUBLIC <= set(_operations(app))


def test_every_other_endpoint_requires_a_session(app, client):
    checked = 0
    for method, path in _operations(app):
        if (method, path) in PUBLIC:
            continue
        r = client.request(method.upper(), _concrete(path), json={})
        assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
        checked += 1
    assert checked >= 10


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.LAB_SPECIALIST])
def test_admin_endpoints_forbidden_for_other_roles(app, role, make_user, login_as):
    c = login_as(make_user(role))
    target = make_user(Role.DOCTOR)
    for method, path in _operations(app):
        if not path.startswith("/api/v1/admin/"):
            continue
        r = c.request(method.upper(), path.replace("{user_id}", str(target.id)), json={})
        assert r.status_code == 403, f"{role} {method.upper()} {path} -> {r.status_code}"
        assert r.json()["error"]["code"] == "FORBIDDEN"
