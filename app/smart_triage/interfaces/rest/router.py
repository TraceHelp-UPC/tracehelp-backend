"""Endpoints REST del Bounded Context Smart Triage.

Triaje multimodal, diagnóstico RAG y validación HITL.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user, require_permission
from app.knowledge.application.ports import EmbeddingProviderError, EmbeddingProviderNotConfiguredError
from app.knowledge.interfaces.rest.dependencies import require_knowledge_reader
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.diagnosis_query_service import DiagnosisQueryService
from app.smart_triage.application.evidence_retrieval_service import (
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.application.hitl_review_service import HitlReviewService, ReviewDiagnosisCommand
from app.smart_triage.application.ports import LlmProviderError, LlmProviderNotConfiguredError, Reviewer
from app.smart_triage.application.triage_analysis_service import AnalyzeIncidentCommand, TriageAnalysisService
from app.smart_triage.interfaces.rest.dependencies import (
    get_diagnosis_generation_service,
    get_diagnosis_query_service,
    get_evidence_retrieval_service,
    get_hitl_review_service,
    get_triage_analysis_service,
)
from app.smart_triage.interfaces.rest.schemas import (
    AnalyzeIncidentResponse,
    DiagnosisResponse,
    DiagnosisPreviewRequest,
    DiagnosisPreviewResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    ReviewDiagnosisRequest,
    ReviewDiagnosisResponse,
)

router = APIRouter(tags=["Smart Triage"])


@router.post(
    "/triage/evidence-search",
    response_model=EvidenceSearchResponse,
    summary="Buscar evidencia en los manuales",
    responses={
        400: {"description": "Consulta vacía o top_k fuera de rango"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Requiere kb:write o tickets:manage"},
        502: {"description": "Gemini no respondió"},
        503: {"description": "GEMINI_API_KEY no está configurada"},
    },
)
def search_evidence(
    body: EvidenceSearchRequest,
    current_user: CurrentUser = Depends(require_knowledge_reader),
    service: EvidenceRetrievalService = Depends(get_evidence_retrieval_service),
) -> EvidenceSearchResponse:
    """Recupera los fragmentos más parecidos a la consulta y evalúa si sostienen una respuesta (US11).

    Sirve para revisar qué encontraría el triaje y para calibrar los umbrales (T33). La consulta se anonimiza
    antes de vectorizarse. Si ningún fragmento supera el umbral de evidencia, se registra una alerta de baja confianza.
    """
    command = RetrieveEvidenceCommand(workspace_id=current_user.workspace_id, query_text=body.query, top_k=body.top_k)
    try:
        evaluation = service.retrieve_and_evaluate(command)
    except EmbeddingProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La búsqueda no está disponible: falta GEMINI_API_KEY.") from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo vectorizar la consulta: {exc}") from exc
    return EvidenceSearchResponse.from_evaluation(evaluation)


@router.post(
    "/triage/diagnosis-preview",
    response_model=DiagnosisPreviewResponse,
    summary="Probar el diagnóstico de la IA",
    responses={
        400: {"description": "Incidente vacío"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Requiere kb:write o tickets:manage"},
        502: {"description": "Gemini no respondió"},
        503: {"description": "GEMINI_API_KEY no está configurada"},
    },
)
def preview_diagnosis(
    body: DiagnosisPreviewRequest,
    current_user: CurrentUser = Depends(require_knowledge_reader),
    retrieval: EvidenceRetrievalService = Depends(get_evidence_retrieval_service),
    generation: DiagnosisGenerationService = Depends(get_diagnosis_generation_service),
) -> DiagnosisPreviewResponse:
    """Recupera la evidencia (T30) y genera el diagnóstico fundamentado con citas (T31), sin crear ni cambiar tickets.

    Muestra lo que el triaje automático (T28) propondría para un incidente. Si la evidencia no supera el umbral,
    no se llama a la IA. Si la IA responde sin citas válidas, la respuesta se descarta y se explica el motivo.
    """
    command = RetrieveEvidenceCommand(workspace_id=current_user.workspace_id, query_text=body.incident)
    try:
        evaluation = retrieval.retrieve_and_evaluate(command)
        outcome = generation.generate(body.incident, evaluation)
    except (EmbeddingProviderNotConfiguredError, LlmProviderNotConfiguredError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La IA no está disponible: falta GEMINI_API_KEY.") from exc
    except (EmbeddingProviderError, LlmProviderError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"La IA no respondió: {exc}") from exc
    return DiagnosisPreviewResponse.build(evaluation, outcome)


MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024


@router.post(
    "/triage/analyze",
    response_model=AnalyzeIncidentResponse,
    summary="Analizar un incidente (texto y captura)",
    responses={
        400: {"description": "Faltan la descripción y la captura, la imagen no es válida o no se puede leer"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Requiere kb:write o tickets:manage"},
        404: {"description": "El workspace no existe"},
        502: {"description": "Gemini no respondió"},
        503: {"description": "GEMINI_API_KEY no está configurada"},
    },
)
def analyze_incident(
    workspace_id: Annotated[uuid.UUID, Form(description="Workspace cuyos manuales se consultan")],
    description: Annotated[str | None, Form(max_length=4000, description="Descripción del problema")] = None,
    title: Annotated[str | None, Form(max_length=200, description="Asunto (opcional)")] = None,
    affected_module: Annotated[str | None, Form(max_length=100, description="Sistema afectado (opcional)")] = None,
    screenshot: Annotated[
        UploadFile | None, File(description="Captura PNG o JPG del error (opcional)", json_schema_extra={"format": "binary"})
    ] = None,
    current_user: CurrentUser = Depends(require_knowledge_reader),
    service: TriageAnalysisService = Depends(get_triage_analysis_service),
) -> AnalyzeIncidentResponse:
    """Orquesta OCR, anonimización, recuperación de evidencia y diagnóstico con Gemini (TS02).

    Devuelve el diagnóstico con citas y el puntaje de confianza, sin crear ni modificar tickets. El triaje automático
    de los tickets registrados usa este mismo análisis en segundo plano.
    """
    if workspace_id != current_user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El workspace no existe.")
    screenshots: tuple[bytes, ...] = ()
    if screenshot is not None and screenshot.filename:
        content = screenshot.file.read(MAX_SCREENSHOT_BYTES + 1)
        if len(content) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La captura supera el tamaño máximo de 10 MB.")
        screenshots = (content,)
    command = AnalyzeIncidentCommand(
        workspace_id=workspace_id,
        description=description,
        title=title,
        affected_module=affected_module,
        screenshots=screenshots,
    )
    try:
        analysis = service.analyze(command)
    except (EmbeddingProviderNotConfiguredError, LlmProviderNotConfiguredError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La IA no está disponible: falta GEMINI_API_KEY.") from exc
    except (EmbeddingProviderError, LlmProviderError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"La IA no respondió: {exc}") from exc
    return AnalyzeIncidentResponse.from_analysis(analysis)


# --- Diagnóstico y revisión HITL (TS07) ---------------------------------------------------------------------


def _reviewer(user: CurrentUser) -> Reviewer:
    return Reviewer(id=user.id, workspace_id=user.workspace_id, permissions=user.permissions)


@router.get(
    "/tickets/{ticket_id}/diagnosis",
    response_model=DiagnosisResponse,
    response_model_exclude_none=False,
    summary="Ver el diagnóstico de la IA de un ticket",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El ticket es de otro colaborador, o el diagnóstico todavía está en revisión"},
        404: {"description": "El ticket no existe o el triaje sigue en curso"},
    },
)
def get_ticket_diagnosis(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: DiagnosisQueryService = Depends(get_diagnosis_query_service),
) -> DiagnosisResponse:
    """Diagnóstico del triaje automático (pantalla W-07).

    El equipo de soporte ve la propuesta de la IA con sus fuentes, puntajes, OCR y la revisión; `allowed_actions`
    indica qué revisiones puede hacer. El colaborador solo lo ve cuando se le propuso como autoservicio.
    """
    return DiagnosisResponse.from_view(service.for_ticket(_reviewer(current_user), ticket_id))


@router.post(
    "/triage/diagnoses/{diagnosis_id}/review",
    response_model=ReviewDiagnosisResponse,
    summary="Revisar la respuesta de la IA (HITL)",
    responses={
        400: {"description": "Faltan o sobran datos para la decisión (resumen, pasos, motivo o respuesta)"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no puede validar respuestas de la IA, o no puede resolver este ticket"},
        404: {"description": "El diagnóstico no existe"},
        409: {"description": "El diagnóstico ya fue revisado o no admite esa revisión"},
        422: {"description": "El ticket no puede resolverse en su estado actual (por ejemplo, nadie lo tomó)"},
    },
)
def review_diagnosis(
    diagnosis_id: uuid.UUID,
    body: ReviewDiagnosisRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.TRIAGE_VALIDATE_HITL)),
    service: HitlReviewService = Depends(get_hitl_review_service),
    queries: DiagnosisQueryService = Depends(get_diagnosis_query_service),
) -> ReviewDiagnosisResponse:
    """Aprobar (`APPROVE`), editar y aprobar (`EDIT_AND_APPROVE` con `summary` y `steps`), rechazar (`REJECT` con
    `reason`) o responder manualmente (`MANUAL_RESPONSE` con `response`).

    Todas las decisiones menos el rechazo resuelven el ticket y dejan la respuesta como comentario para el
    colaborador. Para resolver, el ticket debe estar tomado (ASSIGNED_L1) o escalado (ESCALATED_L2).
    """
    reviewer = _reviewer(current_user)
    result = service.review(
        ReviewDiagnosisCommand(
            diagnosis_id=diagnosis_id,
            reviewer=reviewer,
            decision=body.decision,
            summary=body.summary,
            steps=tuple(body.steps or ()),
            reason=body.reason,
            response=body.response,
        )
    )
    view = queries.for_ticket(reviewer, result.diagnosis.ticket_id)
    return ReviewDiagnosisResponse(ticket_resolved=result.ticket_resolved, diagnosis=DiagnosisResponse.from_view(view))
