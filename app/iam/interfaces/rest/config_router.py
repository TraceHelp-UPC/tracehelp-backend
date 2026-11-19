"""Endpoints de configuración de parámetros RAG por workspace (US07, T63).

GET /api/v1/config/rag exige `analytics:read`; PUT /api/v1/config/rag exige `config:write`.
Siempre operan sobre el `workspace_id` del token autenticado.
"""
from fastapi import APIRouter, Depends

from app.iam.application.workspace_settings_service import UpdateRagSettingsCommand, WorkspaceSettingsService
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.iam.interfaces.rest.dependencies import get_workspace_settings_service
from app.iam.interfaces.rest.schemas import RagSettingsResponse, UpdateRagSettingsRequest

router = APIRouter(prefix="/config", tags=["Configuración"])

_PROBLEM = "application/problem+json"
_RAG_INSTANCE = "/api/v1/config/rag"


def _problem_example(
    type_slug: str,
    title: str,
    status_code: int,
    detail: str,
    *,
    errors: list[dict[str, str]] | None = None,
) -> dict:
    example: dict = {
        "type": f"urn:tracehelp:problems:{type_slug}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": _RAG_INSTANCE,
    }
    if errors is not None:
        example["errors"] = errors
    return {
        "description": title,
        "content": {_PROBLEM: {"example": example}},
    }


_RAG_RESPONSE_EXAMPLE = {
    "similarity_threshold": 0.72,
    "self_service_threshold": 0.85,
    "retrieval_top_k": 5,
    "strict_grounding": True,
    "is_default": False,
    "updated_at": "2026-11-20T15:15:03Z",
    "updated_by": "1a2b3c4d-0000-4000-8000-000000000004",
    "updated_by_name": "Roberto Pérez",
    "defaults": {
        "similarity_threshold": 0.68,
        "self_service_threshold": 0.80,
        "retrieval_top_k": 5,
        "strict_grounding": True,
    },
    "limits": {
        "similarity_threshold": {"min": 0.50, "max": 0.95, "step": 0.01, "warning_below": 0.65},
        "self_service_threshold": {"min": "similarity_threshold", "max": 0.99, "step": 0.01},
        "retrieval_top_k": {"min": 1, "max": 10},
    },
}

_UNAUTHORIZED = _problem_example("unauthorized", "No autenticado", 401, "Se requiere un token de acceso.")
_FORBIDDEN_READ = _problem_example(
    "forbidden", "Acceso denegado", 403, "Tu rol no tiene el permiso requerido: analytics:read."
)
_FORBIDDEN_WRITE = _problem_example(
    "forbidden", "Acceso denegado", 403, "Tu rol no tiene el permiso requerido: config:write."
)
_VALIDATION_ERROR = _problem_example(
    "validation-error",
    "Datos de entrada no válidos",
    422,
    "Hay datos no válidos en la solicitud. similarity_threshold: debe ser mayor o igual que 0.50.",
    errors=[
        {
            "field": "similarity_threshold",
            "message": "debe ser mayor o igual que 0.50",
            "type": "greater_than_equal",
        }
    ],
)


@router.get(
    "/rag",
    response_model=RagSettingsResponse,
    summary="Consultar parámetros RAG",
    description=(
        "Devuelve la configuración vigente del motor RAG para el workspace del usuario autenticado: "
        "umbral de fundamentación (`similarity_threshold`), umbral de autoservicio (`self_service_threshold`), "
        "cantidad máxima de fragmentos recuperados (`retrieval_top_k`) y modo de citas obligatorias (`strict_grounding`). "
        "Incluye `is_default`, metadatos de la última modificación, valores por defecto (`defaults`) y rangos "
        "permitidos (`limits`) para calibrar los controles del panel D-04. Requiere el permiso `analytics:read`."
    ),
    responses={
        200: {"content": {"application/json": {"example": _RAG_RESPONSE_EXAMPLE}}},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN_READ,
    },
)
def get_rag_settings(
    current_user: CurrentUser = Depends(require_permission(Permission.ANALYTICS_READ)),
    service: WorkspaceSettingsService = Depends(get_workspace_settings_service),
) -> RagSettingsResponse:
    return RagSettingsResponse.from_view(service.get_rag(current_user.workspace_id))


@router.put(
    "/rag",
    response_model=RagSettingsResponse,
    summary="Actualizar parámetros RAG",
    description=(
        "Reemplaza la configuración completa del motor RAG del workspace del líder de TI. Los 4 parámetros son "
        "obligatorios: `similarity_threshold` (0.50–0.95, máximo 2 decimales), `self_service_threshold` "
        "(mayor o igual que `similarity_threshold` y hasta 0.99, máximo 2 decimales), `retrieval_top_k` (1–10) "
        "y `strict_grounding` (booleano). Los cambios se aplican de inmediato a las siguientes inferencias de "
        "Smart Triage sin reiniciar el servidor y registran el evento `ConfigurationChanged` en la bitácora de "
        "auditoría con los valores anteriores y nuevos. Si no hay cambios efectivos, responde 200 sin modificar "
        "`updated_at` ni generar entrada de auditoría. Requiere el permiso `config:write`."
    ),
    responses={
        200: {"content": {"application/json": {"example": _RAG_RESPONSE_EXAMPLE}}},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN_WRITE,
        422: _VALIDATION_ERROR,
    },
)
def update_rag_settings(
    body: UpdateRagSettingsRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.CONFIG_WRITE)),
    service: WorkspaceSettingsService = Depends(get_workspace_settings_service),
) -> RagSettingsResponse:
    view = service.update_rag(
        UpdateRagSettingsCommand(
            workspace_id=current_user.workspace_id,
            changed_by=current_user.id,
            similarity_threshold=body.similarity_threshold,
            self_service_threshold=body.self_service_threshold,
            retrieval_top_k=body.retrieval_top_k,
            strict_grounding=body.strict_grounding,
        )
    )
    return RagSettingsResponse.from_view(view)
