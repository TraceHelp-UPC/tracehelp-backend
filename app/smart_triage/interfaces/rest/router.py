"""Endpoints REST del Bounded Context Smart Triage.

Triaje multimodal, diagnóstico RAG y validación HITL.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.iam.interfaces.rest.auth_dependencies import CurrentUser
from app.knowledge.application.ports import EmbeddingProviderError, EmbeddingProviderNotConfiguredError
from app.knowledge.interfaces.rest.dependencies import require_knowledge_reader
from app.smart_triage.application.evidence_retrieval_service import (
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.interfaces.rest.dependencies import get_evidence_retrieval_service
from app.smart_triage.interfaces.rest.schemas import EvidenceSearchRequest, EvidenceSearchResponse

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
