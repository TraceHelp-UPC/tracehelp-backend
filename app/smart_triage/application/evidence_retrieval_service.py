"""Recuperación y evaluación de la evidencia para el diagnóstico (US11, T30).

1. Anonimiza la consulta (T27): ni la consulta ni su vector salen hacia Gemini con datos personales.
2. Recupera los top-k fragmentos de los manuales del workspace.
3. Evalúa si la evidencia sostiene una respuesta (GroundingEvaluationDomainService).
4. Si no la sostiene, registra una alerta de baja confianza: un log de advertencia y el evento
   LowConfidenceAlertRaised, que la bitácora de auditoría (T36) guardará.
El triaje automático (T28) y el adaptador de Gemini (T31) usan esta evaluación para decidir qué hacer.
"""
import logging
import uuid
from dataclasses import dataclass

from app.shared.domain.pii import IPiiMasker
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.ports import IKnowledgeRetriever
from app.smart_triage.domain.events import LowConfidenceAlertRaised
from app.smart_triage.domain.exceptions import EmptyTriageQueryError
from app.smart_triage.domain.grounding import (
    GroundingEvaluation,
    GroundingEvaluationDomainService,
    GroundingThresholds,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MAX_QUERY_CHARACTERS = 4000  # el modelo de embeddings acepta ~2048 tokens; el inicio del texto es lo más relevante


@dataclass(frozen=True)
class RetrieveEvidenceCommand:
    workspace_id: uuid.UUID
    query_text: str
    ticket_id: uuid.UUID | None = None
    top_k: int | None = None


class EvidenceRetrievalService:
    def __init__(
        self,
        *,
        retriever: IKnowledgeRetriever,
        masker: IPiiMasker,
        events: InMemoryEventBus,
        thresholds: GroundingThresholds,
        top_k: int = DEFAULT_TOP_K,
        evaluator: GroundingEvaluationDomainService | None = None,
    ) -> None:
        self._retriever = retriever
        self._masker = masker
        self._events = events
        self._thresholds = thresholds
        self._top_k = top_k
        self._evaluator = evaluator or GroundingEvaluationDomainService()

    @property
    def thresholds(self) -> GroundingThresholds:
        return self._thresholds

    def retrieve_and_evaluate(self, command: RetrieveEvidenceCommand) -> GroundingEvaluation:
        text = (command.query_text or "").strip()
        if not text:
            raise EmptyTriageQueryError("No hay texto para buscar en los manuales.")
        query = self._masker.mask(text[:MAX_QUERY_CHARACTERS])

        fragments = self._retriever.retrieve(command.workspace_id, query, top_k=command.top_k or self._top_k)
        evaluation = self._evaluator.evaluate(fragments, self._thresholds)

        if evaluation.requires_low_confidence_alert:
            logger.warning(
                "Alerta de baja confianza: workspace=%s ticket=%s mejor_similitud=%.4f umbral=%.2f fragmentos=%s",
                command.workspace_id,
                command.ticket_id,
                evaluation.best_score,
                self._thresholds.similarity,
                len(evaluation.retrieved),
            )
            self._events.publish(
                LowConfidenceAlertRaised(
                    workspace_id=command.workspace_id,
                    ticket_id=command.ticket_id,
                    best_score=evaluation.best_score,
                    similarity_threshold=self._thresholds.similarity,
                    fragments_retrieved=len(evaluation.retrieved),
                )
            )
        return evaluation
