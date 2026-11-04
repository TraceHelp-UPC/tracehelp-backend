"""Puerto y modelos de los tokens de sesión (TS03)."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.iam.domain.user import User


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # segundos de vigencia del access token


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: str
    permissions: frozenset[str]


class ITokenProvider(ABC):
    @abstractmethod
    def issue_tokens(self, user: User) -> TokenPair: ...

    @abstractmethod
    def issue_access_token(self, user: User) -> tuple[str, int]:
        """Devuelve el access token y sus segundos de vigencia."""

    @abstractmethod
    def decode_access_token(self, token: str) -> AccessTokenClaims: ...

    @abstractmethod
    def decode_refresh_token(self, token: str) -> uuid.UUID:
        """Valida el refresh token y devuelve el id del usuario."""
