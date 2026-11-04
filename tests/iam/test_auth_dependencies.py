"""Pruebas del middleware JWT y RBAC (T07) sobre una mini aplicación de prueba."""
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.iam.domain.enums import RoleName
from app.iam.domain.permissions import Permission
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user, require_permission
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider

FAKE_HASH = PasswordHash("$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm")

app = FastAPI()


@app.get("/private")
def private(user: CurrentUser = Depends(get_current_user)):
    return {"role": user.role}


@app.get("/knowledge")
def knowledge(user: CurrentUser = Depends(require_permission(Permission.KB_WRITE))):
    return {"ok": True}


@app.get("/validate-and-escalate")
def both(user: CurrentUser = Depends(require_permission(Permission.TRIAGE_VALIDATE_HITL, Permission.TICKETS_ESCALATE))):
    return {"ok": True}


client = TestClient(app)


def _user(role: RoleName) -> User:
    return User.register(
        workspace_id=uuid.uuid4(), full_name="Prueba", email=EmailAddress("prueba@empresa.pe"),
        password_hash=FAKE_HASH, role=role, department="TI",
    )


def _headers(role: RoleName, provider: JwtTokenProvider | None = None) -> dict:
    token, _ = (provider or get_token_provider()).issue_access_token(_user(role))
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_returns_401():
    response = client.get("/private")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer token-invalido", "Basic dXNlcjpwYXNz"])
def test_invalid_token_or_scheme_returns_401(header):
    assert client.get("/private", headers={"Authorization": header}).status_code == 401


def test_expired_token_returns_401():
    settings_provider = get_token_provider()
    expired = JwtTokenProvider(settings_provider._secret, settings_provider._algorithm, access_minutes=-1, refresh_days=1)
    assert client.get("/private", headers=_headers(RoleName.ANALYST_L1, expired)).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token():
    refresh = get_token_provider().issue_tokens(_user(RoleName.ANALYST_L1)).refresh_token
    assert client.get("/private", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_valid_token_exposes_current_user():
    response = client.get("/private", headers=_headers(RoleName.ANALYST_L1))
    assert response.status_code == 200 and response.json() == {"role": "ANALYST_L1"}


def test_role_without_permission_gets_403():
    response = client.get("/knowledge", headers=_headers(RoleName.ANALYST_L1))
    assert response.status_code == 403
    assert "kb:write" in response.json()["detail"]


def test_role_with_permission_is_allowed():
    assert client.get("/knowledge", headers=_headers(RoleName.IT_LEADER)).status_code == 200


def test_all_listed_permissions_are_required():
    assert client.get("/validate-and-escalate", headers=_headers(RoleName.ANALYST_L1)).status_code == 200
    assert client.get("/validate-and-escalate", headers=_headers(RoleName.SPECIALIST_L2)).status_code == 403


def test_require_permission_needs_at_least_one_permission():
    with pytest.raises(ValueError):
        require_permission()
