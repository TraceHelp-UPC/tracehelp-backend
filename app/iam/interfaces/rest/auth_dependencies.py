"""Dependencias de autenticación y autorización (JWT + RBAC) para los endpoints protegidos de todos los módulos.

Uso en un endpoint que exige un permiso de la matriz RBAC:
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_CREATE))

Uso en un endpoint que solo exige estar autenticado:
    current_user: CurrentUser = Depends(get_current_user)

Para proteger todos los endpoints de un router con el mismo permiso:
    router = APIRouter(dependencies=[Depends(require_permission(Permission.ANALYTICS_READ))])

Respuestas: 401 si el token falta, es inválido, expiró o no es un access token; 403 si el rol no tiene el permiso.
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


def require_permission(*permissions: Permission) -> Callable[..., CurrentUser]:
    """Crea una dependencia que exige uno o más permisos de la matriz RBAC (responde 403 si falta alguno)."""
    if not permissions:
        raise ValueError("require_permission necesita al menos un permiso.")

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        missing = [p.value for p in permissions if not user.can(p)]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Tu rol no tiene el permiso requerido: {', '.join(missing)}."
            )
        return user

    return _dependency
