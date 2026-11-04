"""Dependencias de autenticación y autorización para los endpoints protegidos de todos los módulos.

Uso en un router:
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_CREATE))
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.iam.domain.exceptions import InvalidTokenError
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider

_bearer = HTTPBearer(auto_error=False, description="Access token obtenido en POST /api/v1/auth/login")


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    workspace_id: uuid.UUID
    role: str
    permissions: frozenset[str]

    def can(self, permission: Permission) -> bool:
        return permission.value in self.permissions


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    tokens: JwtTokenProvider = Depends(get_token_provider),
) -> CurrentUser:
    """Valida el access token del encabezado Authorization: Bearer <token>."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Se requiere un token de acceso.", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        claims = tokens.decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.detail, headers={"WWW-Authenticate": "Bearer"}) from exc
    return CurrentUser(
        id=claims.user_id, workspace_id=claims.workspace_id, role=claims.role, permissions=claims.permissions
    )


def require_permission(permission: Permission) -> Callable[..., CurrentUser]:
    """Crea una dependencia que exige un permiso de la matriz RBAC (responde 403 si falta)."""

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Tu rol no tiene el permiso requerido: {permission.value}.")
        return user

    return _dependency
