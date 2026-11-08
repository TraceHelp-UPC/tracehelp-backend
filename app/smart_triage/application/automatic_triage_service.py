"""Triaje automático de tickets (TS02, T28).

Se ejecuta en segundo plano después de registrar un ticket (evento TicketRegistered):
analiza el incidente, guarda el diagnóstico y publica TriageCompleted para que Helpdesk mueva el ticket.
Nunca deja un ticket sin triar: si la IA o el OCR fallan, guarda un diagnóstico con el motivo y el ticket
pasa a la cola de asignación para que lo atienda un analista.
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app.knowledge.application.ports import EmbeddingProviderError
from app.shared.domain.exceptions import DomainError
from app.shared.domain.pii import IPiiMasker
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.ports import ITicketReader, LlmProviderError
from app.smart_triage.application.triage_analysis_service import (
    AnalyzeIncidentCommand,
    IncidentAnalysis,
    TriageAnalysisService,
)
from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import OcrSummary, TriageDiagnosis

logger = logging.getLogger(__name__)


class AutomaticTriageService:
    def __init__(
        self,
        *,
        session: Session,
        tickets: ITicketReader,
        diagnoses: ITriageDiagnosisRepository,
        analysis: TriageAnalysisService,
        masker: IPiiMasker,
        events: InMemoryEventBus,
    ) -> None:
        self._session = session
        self._tickets = tickets
        self._diagnoses = diagnoses
        self._analysis = analysis
        self._masker = masker
        self._events = events

    def triage(self, ticket_id: uuid.UUID) -> TriageDiagnosis | None:
        """Tría el ticket una sola vez. Devuelve None si no existe o ya tenía diagnóstico."""
        if self._diagnoses.find_by_ticket_id(ticket_id) is not None:
            logger.info("El ticket %s ya tenía diagnóstico; se omite el triaje", ticket_id)
            return None
        incident = self._tickets.get(ticket_id)
        if incident is None:
            logger.warning("No se encontró el ticket %s para el triaje", ticket_id)
            return None

        command = AnalyzeIncidentCommand(
            workspace_id=incident.workspace_id,
            ticket_id=incident.ticket_id,
            title=incident.title,
            description=incident.description,
            affected_module=incident.affected_module,
            screenshots=incident.screenshots,
        )
        try:
            analysis = self._analysis.analyze(command)
            diagnosis = TriageDiagnosis.from_analysis(
                workspace_id=incident.workspace_id,
                ticket_id=incident.ticket_id,
                evaluation=analysis.evaluation,
                outcome=analysis.outcome,
                ocr=self._ocr_summary(analysis) if incident.screenshots else None,
            )
        except (EmbeddingProviderError, LlmProviderError) as exc:
            logger.warning("La IA no respondió durante el triaje del ticket %s: %s", ticket_id, exc)
            diagnosis = TriageDiagnosis.failed(
                workspace_id=incident.workspace_id,
                ticket_id=incident.ticket_id,
                reason=f"El servicio de IA no respondió: {exc}",
            )
        except DomainError as exc:
            # Por ejemplo, todas las capturas ilegibles y una descripción muy corta
            diagnosis = TriageDiagnosis.failed(
                workspace_id=incident.workspace_id, ticket_id=incident.ticket_id, reason=exc.detail
            )

        self._diagnoses.save(diagnosis)
        self._session.commit()
        self._events.publish_all(diagnosis.pull_events())
        logger.info(
            "Ticket %s triado: %s (%s), pasa a %s",
            ticket_id,
            diagnosis.outcome.value,
            diagnosis.confidence_level.value if diagnosis.confidence_level else "sin evaluación",
            diagnosis.route.value,
        )
        return diagnosis

    def _ocr_summary(self, analysis: IncidentAnalysis) -> OcrSummary:
        text = analysis.ocr_text
        return OcrSummary(
            legible=analysis.screenshots_legible,
            error_codes=analysis.error_codes,
            masked_text=self._masker.mask(text).text if text else None,
        )
