"""Endpoints REST del Bounded Context IAM.

Autenticación, usuarios, roles y configuración RAG.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.iam.application.authentication_service import AuthenticationService
from app.iam.domain.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRoleOperationError,
    InvalidTokenError,
)
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user
from app.iam.interfaces.rest.dependencies import get_authentication_service, get_user_repository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.schemas import (
    AccessTokenResponse,
    AnalystSummaryResponse,
    AuthenticatedUser,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UpdateAvailabilityRequest,
)

router = APIRouter(tags=["IAM"])

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    responses={401: {"description": "Credenciales inválidas"}, 403: {"description": "Cuenta inactiva"}},
)
def login(body: LoginRequest, service: AuthenticationService = Depends(get_authentication_service)) -> TokenResponse:
    """Valida correo y contraseña y entrega el access token, el refresh token y los datos del usuario."""
    try:
        result = service.login(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.detail, headers=_UNAUTHORIZED) from exc
    except InactiveUserError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.detail) from exc

    return TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
        user=AuthenticatedUser.from_domain(result.user),
    )


@router.post(
    "/auth/refresh",
    response_model=AccessTokenResponse,
    summary="Renovar el access token",
    responses={401: {"description": "Refresh token inválido o expirado"}},
)
def refresh(
    body: RefreshTokenRequest, service: AuthenticationService = Depends(get_authentication_service)
) -> AccessTokenResponse:
    """Genera un nuevo access token a partir de un refresh token vigente."""
    try:
        access_token, expires_in = service.refresh(body.refresh_token)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, exc.detail, headers=_UNAUTHORIZED) from exc
    return AccessTokenResponse(access_token=access_token, expires_in=expires_in)


@router.get(
    "/auth/me",
    response_model=AuthenticatedUser,
    summary="Consultar el usuario autenticado",
    responses={401: {"description": "Token ausente, inválido o usuario deshabilitado"}},
)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    users: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> AuthenticatedUser:
    """Devuelve los datos y permisos del usuario del token. Las aplicaciones Appsmith lo usan para restaurar la sesión."""
    user = users.find_by_id(current_user.id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El usuario ya no está habilitado.", headers=_UNAUTHORIZED)
    return AuthenticatedUser.from_domain(user)


@router.patch(
    "/analysts/me/availability",
    response_model=AnalystSummaryResponse,
    summary="Cambiar mi estado de disponibilidad",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Solo los analistas L1 y especialistas L2 gestionan su disponibilidad"},
    },
)
def update_my_availability(
    body: UpdateAvailabilityRequest,
    current_user: CurrentUser = Depends(get_current_user),
    users: SqlAlchemyUserRepository = Depends(get_user_repository),
    db: Session = Depends(get_db),
) -> AnalystSummaryResponse:
    """Actualiza el estado de disponibilidad (AVAILABLE / UNAVAILABLE) del analista o especialista autenticado (US24, T47)."""
    user = users.find_by_id(current_user.id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El usuario ya no está habilitado.", headers=_UNAUTHORIZED)
    try:
        user.set_availability(body.availability_status)
    except InvalidRoleOperationError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.detail) from exc
    users.save(user)
    db.commit()
    return AnalystSummaryResponse.from_domain(user)


@router.get(
    "/analysts",
    response_model=list[AnalystSummaryResponse],
    summary="Listar analistas y especialistas del workspace",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Requiere el permiso tickets:manage o iam:admin"},
    },
)
def list_workspace_analysts(
    current_user: CurrentUser = Depends(get_current_user),
    users: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> list[AnalystSummaryResponse]:
    """Lista los analistas L1 y especialistas L2 del workspace con su estado de disponibilidad (US24, T47)."""
    if not (current_user.can(Permission.TICKETS_MANAGE) or current_user.can(Permission.IAM_ADMIN)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para consultar el equipo de soporte.")
    staff = users.find_support_staff_by_workspace(current_user.workspace_id)
    return [AnalystSummaryResponse.from_domain(u) for u in staff if u.is_active]
