"""Endpoints REST del Bounded Context IAM.

Autenticación, usuarios, roles y configuración RAG.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.iam.application.authentication_service import AuthenticationService
from app.iam.domain.exceptions import InactiveUserError, InvalidCredentialsError, InvalidTokenError
from app.iam.interfaces.rest.dependencies import get_authentication_service
from app.iam.interfaces.rest.schemas import (
    AccessTokenResponse,
    AuthenticatedUser,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
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

    user = result.user
    return TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
        user=AuthenticatedUser(
            id=user.id,
            workspace_id=user.workspace_id,
            full_name=user.full_name,
            email=user.email.value,
            role=user.role.value,
            permissions=sorted(p.value for p in user.role_permission.permissions),
        ),
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
