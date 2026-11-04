"""Pruebas unitarias del proveedor de tokens JWT (TS03)."""
import uuid

import pytest

from app.iam.domain.enums import RoleName
from app.iam.domain.exceptions import InvalidTokenError
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider

FAKE_HASH = PasswordHash("$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm")


def _provider(**overrides) -> JwtTokenProvider:
    data = dict(secret_key="test-secret-key-de-al-menos-32-bytes", algorithm="HS256", access_minutes=30, refresh_days=7)
    data.update(overrides)
    return JwtTokenProvider(**data)


def _user() -> User:
    return User.register(
        workspace_id=uuid.uuid4(), full_name="Ana", email=EmailAddress("ana@empresa.pe"),
        password_hash=FAKE_HASH, role=RoleName.IT_LEADER, department="TI",
    )


def test_access_token_carries_role_and_permissions():
    provider, user = _provider(), _user()
    claims = provider.decode_access_token(provider.issue_tokens(user).access_token)
    assert claims.user_id == user.id and claims.role == "IT_LEADER"
    assert "kb:write" in claims.permissions


def test_refresh_token_returns_user_id():
    provider, user = _provider(), _user()
    assert provider.decode_refresh_token(provider.issue_tokens(user).refresh_token) == user.id


def test_token_types_cannot_be_swapped():
    provider = _provider()
    pair = provider.issue_tokens(_user())
    with pytest.raises(InvalidTokenError):
        provider.decode_refresh_token(pair.access_token)
    with pytest.raises(InvalidTokenError):
        provider.decode_access_token(pair.refresh_token)


def test_expired_token_is_rejected():
    provider = _provider(access_minutes=-1)
    with pytest.raises(InvalidTokenError):
        provider.decode_access_token(provider.issue_tokens(_user()).access_token)


def test_token_signed_with_another_key_is_rejected():
    token = _provider(secret_key="otra-clave-distinta-de-al-menos-32-bytes").issue_tokens(_user()).access_token
    with pytest.raises(InvalidTokenError):
        _provider().decode_access_token(token)
