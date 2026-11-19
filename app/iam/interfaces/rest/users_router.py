"""Endpoints de administración de usuarios y roles (US09, T69). Todos exigen el permiso iam:admin."""
import uuid

from fastapi import APIRouter, Depends, Query, Response, status

from app.iam.application.user_admin_service import CreateUserCommand, UpdateUserCommand, UserAdministrationService
from app.iam.domain.enums import RoleName
from app.iam.domain.permissions import Permission
from app.iam.domain.repositories import UserSearchCriteria
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.iam.interfaces.rest.dependencies import get_user_administration_service
from app.iam.interfaces.rest.schemas import (
    CreatedUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
    UserAdminPageResponse,
    UserAdminResponse,
)
from app.shared.domain.pagination import PageRequest
from app.shared.domain.specialist_group import SpecialistGroup

router = APIRouter(prefix="/users", tags=["IAM · Usuarios y roles"])

_PROBLEM = "application/problem+json"


def _problem_example(type_slug: str, title: str, status_code: int, detail: str, instance: str = "/api/v1/users") -> dict:
    return {
        "description": title,
        "content": {
            _PROBLEM: {
                "example": {
                    "type": f"urn:tracehelp:problems:{type_slug}",
                    "title": title,
                    "status": status_code,
                    "detail": detail,
                    "instance": instance,
                }
            }
        },
    }


_USER_EXAMPLE = {
    "id": "1a2b3c4d-0000-4000-8000-000000000003",
    "full_name": "Carlos Reátegui",
    "email": "especialista@demo.tracehelp.pe",
    "role": "SPECIALIST_L2",
    "department": "Infraestructura",
    "specialist_group": "INFRAESTRUCTURA",
    "is_active": True,
    "status": "ACTIVE",
    "availability_status": "AVAILABLE",
    "created_at": "2026-11-03T15:00:00Z",
    "last_login_at": "2026-11-18T22:41:10Z",
}

_FORBIDDEN = _problem_example(
    "forbidden", "Prohibido", 403, "Tu rol no tiene el permiso requerido: iam:admin."
)
_UNAUTHORIZED = _problem_example("unauthorized", "No autenticado", 401, "Se requiere un token de acceso.")


@router.get(
    "",
    response_model=UserAdminPageResponse,
    summary="Listar usuarios del workspace",
    description=(
        "Lista paginada de los usuarios del workspace del líder de TI, ordenada por nombre. Permite filtrar por rol, "
        "grupo de especialista y estado, y buscar por nombre o correo (sin distinguir mayúsculas). "
        "Requiere el permiso `iam:admin`."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"items": [_USER_EXAMPLE], "page": 1, "size": 20, "total": 1, "total_pages": 1}
                }
            }
        },
        400: _problem_example(
            "invalid-page-request", "Solicitud no válida", 400, "El tamaño de página debe estar entre 1 y 100."
        ),
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
    },
)
def list_users(
    role: RoleName | None = Query(None, description="Filtrar por rol"),
    specialist_group: SpecialistGroup | None = Query(None, description="Filtrar por grupo de especialista"),
    is_active: bool | None = Query(None, description="true = solo activos; false = inactivos o bloqueados"),
    search: str | None = Query(None, max_length=100, description="Texto a buscar en nombre o correo"),
    page: int = Query(1, description="Número de página (empieza en 1)"),
    size: int = Query(20, description="Usuarios por página (1 a 100)"),
    current_user: CurrentUser = Depends(require_permission(Permission.IAM_ADMIN)),
    service: UserAdministrationService = Depends(get_user_administration_service),
) -> UserAdminPageResponse:
    criteria = UserSearchCriteria(
        workspace_id=current_user.workspace_id,
        role=role,
        specialist_group=specialist_group,
        is_active=is_active,
        search=search,
    )
    return UserAdminPageResponse.from_page(service.list_users(criteria, PageRequest(page=page, size=size)))


@router.post(
    "",
    response_model=CreatedUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario",
    description=(
        "Da de alta un usuario en el workspace del líder de TI. El servidor genera una contraseña temporal de "
        "12 caracteres y la devuelve **una sola vez** en esta respuesta (`Cache-Control: no-store`); no se puede "
        "recuperar después ni queda en logs o auditoría. El correo es único en todo el sistema. "
        "`specialist_group` solo se admite con el rol `SPECIALIST_L2`. Requiere el permiso `iam:admin`."
    ),
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "user": {**_USER_EXAMPLE, "last_login_at": None},
                        "temporary_password": "Rk7#mWq2Tz9!",
                        "password_notice": "Esta contraseña se muestra una sola vez. Entrégala al usuario por un canal seguro.",
                    }
                }
            }
        },
        400: _problem_example("invalid-email", "Solicitud no válida", 400, "El correo 'abc' no tiene un formato válido."),
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        409: _problem_example(
            "email-already-registered",
            "Conflicto con el estado actual",
            409,
            "Ya existe una cuenta con el correo lucia.torres@empresa.pe.",
        ),
        422: _problem_example(
            "specialist-group-not-allowed",
            "Entidad no procesable",
            422,
            "Solo los especialistas L2 pueden tener un grupo asignado.",
        ),
    },
)
def create_user(
    body: CreateUserRequest,
    response: Response,
    current_user: CurrentUser = Depends(require_permission(Permission.IAM_ADMIN)),
    service: UserAdministrationService = Depends(get_user_administration_service),
) -> CreatedUserResponse:
    created = service.create_user(
        CreateUserCommand(
            workspace_id=current_user.workspace_id,
            created_by=current_user.id,
            full_name=body.full_name,
            email=body.email,
            role=body.role,
            department=body.department,
            specialist_group=body.specialist_group,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return CreatedUserResponse(user=UserAdminResponse.from_domain(created.user), temporary_password=created.temporary_password)


@router.patch(
    "/{user_id}",
    response_model=UserAdminResponse,
    summary="Actualizar rol, departamento, grupo o estado de un usuario",
    description=(
        "Actualiza solo los campos enviados: `role`, `department`, `specialist_group` (null lo quita) e `is_active`. "
        "Al cambiar a un rol que no es `SPECIALIST_L2` el grupo se borra. Desactivar deja la cuenta INACTIVE y no "
        "disponible: no podrá iniciar sesión ni renovar el token (su access token vigente sigue valiendo hasta 30 min). "
        "El líder no puede quitarse su propio rol ni desactivarse. Requiere el permiso `iam:admin`."
    ),
    responses={
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        404: _problem_example("user-not-found", "No encontrado", 404, "El usuario no existe.", "/api/v1/users/{user_id}"),
        422: _problem_example(
            "self-lockout", "Entidad no procesable", 422, "No puedes desactivar tu propia cuenta.", "/api/v1/users/{user_id}"
        ),
    },
)
def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.IAM_ADMIN)),
    service: UserAdministrationService = Depends(get_user_administration_service),
) -> UserAdminResponse:
    user = service.update_user(
        UpdateUserCommand(
            workspace_id=current_user.workspace_id,
            user_id=user_id,
            changed_by=current_user.id,
            role=body.role,
            department=body.department,
            specialist_group=body.specialist_group,
            set_specialist_group="specialist_group" in body.model_fields_set,
            is_active=body.is_active,
        )
    )
    return UserAdminResponse.from_domain(user)
