"""Emisión y validación de tokens JWT firmados (TS03)."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.iam.domain.exceptions import InvalidTokenError
from app.iam.domain.tokens import AccessTokenClaims, ITokenProvider, TokenPair
from app.iam.domain.user import User

ACCESS = "access"
REFRESH = "refresh"


class JwtTokenProvider(ITokenProvider):
    def __init__(self, secret_key: str, algorithm: str, access_minutes: int, refresh_days: int) -> None:
        self._secret = secret_key
        self._algorithm = algorithm
        self._access_ttl = timedelta(minutes=access_minutes)
        self._refresh_ttl = timedelta(days=refresh_days)

    def issue_tokens(self, user: User) -> TokenPair:
        access_token, expires_in = self.issue_access_token(user)
        refresh_token = self._encode(
            {"sub": str(user.id), "type": REFRESH}, self._refresh_ttl
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    def issue_access_token(self, user: User) -> tuple[str, int]:
        token = self._encode(
            {
                "sub": str(user.id),
                "type": ACCESS,
                "workspace_id": str(user.workspace_id),
                "role": user.role.value,
                "permissions": sorted(p.value for p in user.role_permission.permissions),
            },
            self._access_ttl,
        )
        return token, int(self._access_ttl.total_seconds())

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        payload = self._decode(token, expected_type=ACCESS)
        try:
            return AccessTokenClaims(
                user_id=uuid.UUID(payload["sub"]),
                workspace_id=uuid.UUID(payload["workspace_id"]),
                role=payload["role"],
                permissions=frozenset(payload.get("permissions", [])),
            )
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("El token de acceso no es válido.") from exc

    def decode_refresh_token(self, token: str) -> uuid.UUID:
        payload = self._decode(token, expected_type=REFRESH)
        try:
            return uuid.UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("El refresh token no es válido.") from exc

    # ------------------------------------------------------------------ internos
    def _encode(self, claims: dict, ttl: timedelta) -> str:
        now = datetime.now(UTC)
        payload = {**claims, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def _decode(self, token: str, expected_type: str) -> dict:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm], options={"require": ["exp", "sub"]})
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("El token ha expirado.") from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("El token no es válido.") from exc
        if payload.get("type") != expected_type:
            raise InvalidTokenError("El tipo de token no corresponde a esta operación.")
        return payload
