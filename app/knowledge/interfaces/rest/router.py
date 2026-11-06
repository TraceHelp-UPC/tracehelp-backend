"""Endpoints REST del Bounded Context Knowledge Management.

Carga, ingesta y vectorización de manuales técnicos (TS01, US06).
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.core.config import get_settings
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.knowledge.application.knowledge_command_service import (
    KnowledgeCommandService,
    UploadTechnicalDocumentCommand,
)
from app.knowledge.application.knowledge_query_service import KnowledgeQueryService
from app.knowledge.domain.exceptions import DocumentNotFoundError
from app.knowledge.domain.technical_document import MAX_TITLE_LENGTH
from app.knowledge.domain.value_objects import MAX_DOCUMENT_BYTES
from app.knowledge.interfaces.rest.dependencies import (
    get_knowledge_command_service,
    get_knowledge_query_service,
    require_knowledge_reader,
)
from app.knowledge.interfaces.rest.schemas import DocumentResponse, IngestionJobResponse
from app.shared.domain.exceptions import DomainValidationError

router = APIRouter(tags=["Knowledge Management"])

_WORKSPACE_NOT_FOUND = "El workspace no existe."


def _ensure_own_workspace(workspace_id: uuid.UUID, user: CurrentUser) -> None:
    """Un usuario solo opera sobre su workspace; cualquier otro se trata como inexistente (no se revela que existe)."""
    if workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _WORKSPACE_NOT_FOUND)


def _job_url(job_id: uuid.UUID) -> str:
    return f"{get_settings().api_prefix}/documents/jobs/{job_id}"


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cargar un manual técnico",
    responses={
        400: {"description": "Formato no soportado, archivo vacío o mayor a 25 MB"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no puede cargar manuales (requiere kb:write)"},
        404: {"description": "El workspace no existe"},
    },
)
def upload_document(
    workspace_id: uuid.UUID,
    response: Response,
    file: Annotated[
        UploadFile,
        File(description="Manual en PDF (.pdf) o Markdown (.md) de hasta 25 MB", json_schema_extra={"format": "binary"}),
    ],
    title: Annotated[str | None, Form(max_length=MAX_TITLE_LENGTH, description="Título visible (opcional)")] = None,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_WRITE)),
    service: KnowledgeCommandService = Depends(get_knowledge_command_service),
) -> IngestionJobResponse:
    """Recibe el manual, lo valida y responde 202 con el jobId; la extracción y vectorización siguen en segundo plano (TS01).

    Consulta el avance en GET /documents/jobs/{job_id}: PENDING → PROCESSING → VECTORIZED o FAILED.
    """
    _ensure_own_workspace(workspace_id, current_user)
    # Se lee un byte más del límite para detectar archivos grandes sin cargarlos completos en memoria
    content = file.file.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo supera el tamaño máximo permitido de 25 MB.")

    command = UploadTechnicalDocumentCommand(
        workspace_id=current_user.workspace_id,
        uploaded_by=current_user.id,
        file_name=file.filename or "",
        content=content,
        title=title,
    )
    try:
        document = service.upload(command)
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc

    status_url = _job_url(document.job_id)
    response.headers["Location"] = status_url
    return IngestionJobResponse.from_domain(document, status_url)


@router.get(
    "/documents/jobs/{job_id}",
    response_model=DocumentResponse,
    summary="Consultar el estado de una ingesta",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no puede consultar manuales"},
        404: {"description": "El trabajo no existe o es de otro workspace"},
    },
)
def get_ingestion_job(
    job_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_knowledge_reader),
    service: KnowledgeQueryService = Depends(get_knowledge_query_service),
) -> DocumentResponse:
    """Devuelve el estado del manual (PENDING, PROCESSING, VECTORIZED o FAILED), los fragmentos indexados y el error si falló."""
    try:
        document = service.get_ingestion_job(job_id=job_id, workspace_id=current_user.workspace_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    return DocumentResponse.from_domain(document)


@router.get(
    "/workspaces/{workspace_id}/documents",
    response_model=list[DocumentResponse],
    summary="Listar los manuales del workspace",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no puede consultar manuales"},
        404: {"description": "El workspace no existe"},
    },
)
def list_documents(
    workspace_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_knowledge_reader),
    service: KnowledgeQueryService = Depends(get_knowledge_query_service),
) -> list[DocumentResponse]:
    """Manuales cargados en el workspace, del más reciente al más antiguo, con su estado de ingesta (pantalla D-02)."""
    _ensure_own_workspace(workspace_id, current_user)
    return [DocumentResponse.from_domain(d) for d in service.list_documents(workspace_id)]
