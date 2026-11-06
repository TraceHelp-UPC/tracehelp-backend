"""Endpoints REST del Bounded Context Smart Triage.

Triaje multimodal, diagnóstico RAG y validación HITL (US11, US15, TS07).
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.shared.domain.exceptions import DomainValidationError
from app.smart_triage.application.triage_service import ReviewAiResolutionCommand, TriageService
from app.smart_triage.domain.exceptions import (
    TriageDiagnosisAlreadyReviewedError,
    TriageDiagnosisNotFoundError,
)
from app.smart_triage.interfaces.rest.dependencies import get_triage_service
from app.smart_triage.interfaces.rest.schemas import HumanReviewRequest, TriageDiagnosisResponse

router = APIRouter(tags=["Smart Triage"])


@router.get(
    "/tickets/{ticket_id}/diagnosis",
    response_model=TriageDiagnosisResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener el diagnóstico RAG asociado a un ticket",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no tiene permiso para consultar diagnósticos"},
        404: {"description": "El diagnóstico o el ticket no existen"},
    },
)
def get_ticket_diagnosis(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE)),
    service: TriageService = Depends(get_triage_service),
) -> TriageDiagnosisResponse:
    """Devuelve la recomendación RAG, el puntaje de confianza y las citas oficiales del ticket (US11, TS07)."""
    try:
        diagnosis = service.get_diagnosis_by_ticket(ticket_id=ticket_id, workspace_id=current_user.workspace_id)
    except TriageDiagnosisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    return TriageDiagnosisResponse.from_domain(diagnosis)


@router.post(
    "/triage/diagnoses/{diagnosis_id}/review",
    response_model=TriageDiagnosisResponse,
    status_code=status.HTTP_200_OK,
    summary="Revisar, editar, aprobar o rechazar una recomendación de IA (HITL)",
    responses={
        400: {"description": "Datos de revisión inválidos"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El usuario carece del permiso triage:validate_hitl"},
        404: {"description": "El diagnóstico no existe"},
        409: {"description": "El diagnóstico ya fue revisado previamente"},
    },
)
def review_triage_diagnosis(
    diagnosis_id: uuid.UUID,
    body: HumanReviewRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.TRIAGE_VALIDATE_HITL)),
    service: TriageService = Depends(get_triage_service),
) -> TriageDiagnosisResponse:
    """Ejecuta la validación humana HITL sobre un diagnóstico (US15, TS07).

    Si se aprueba, edita o envía respuesta manual, publica el comentario en el ticket, pasa a RESOLVED
    y registra la trazabilidad inmutable en analytics_audit_logs.
    """
    command = ReviewAiResolutionCommand(
        diagnosis_id=diagnosis_id,
        workspace_id=current_user.workspace_id,
        reviewer_id=current_user.id,
        action=body.action,
        edited_text=body.edited_text,
        reason=body.reason,
    )
    try:
        diagnosis = service.review_diagnosis(command)
    except TriageDiagnosisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    except TriageDiagnosisAlreadyReviewedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.detail) from exc
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return TriageDiagnosisResponse.from_domain(diagnosis)
