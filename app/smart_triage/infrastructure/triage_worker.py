"""Worker de triaje automático en segundo plano (T28, TriageTicketConsumer).

Escucha TicketRegistered y tría el ticket en un hilo aparte con su propia sesión de base de datos, para que
POST /tickets responda de inmediato aunque el OCR y Gemini tarden. Al arrancar la API se triaan los tickets
que quedaron en OPEN sin diagnóstico (por ejemplo, si Render apagó el servicio a mitad del triaje).
"""
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.helpdesk.domain.events import TicketRegistered
from app.shared.infrastructure.event_bus import event_bus
from app.shared.infrastructure.pii_masker import get_pii_masker
from app.smart_triage.application.automatic_triage_service import AutomaticTriageService
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)

logger = logging.getLogger(__name__)


def build_triage_analysis_service(session) -> TriageAnalysisService:
    from app.smart_triage.interfaces.rest.dependencies import (
        build_diagnosis_generation_service,
        build_evidence_retrieval_service,
    )

    return TriageAnalysisService(
        ocr=TesseractOcrAdapter(),
        retrieval=build_evidence_retrieval_service(session, event_bus),
        generation=build_diagnosis_generation_service(),
    )


def build_automatic_triage_service(session) -> AutomaticTriageService:
    return AutomaticTriageService(
        session=session,
        tickets=HelpdeskTicketReader(session),
        diagnoses=SqlAlchemyTriageDiagnosisRepository(session),
        analysis=build_triage_analysis_service(session),
        masker=get_pii_masker(),
        events=event_bus,
    )


class BackgroundTriageWorker:
    def __init__(
        self, max_workers: int = 2, session_factory=SessionLocal, service_factory=build_automatic_triage_service
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="triage")
        self._session_factory = session_factory
        self._service_factory = service_factory

    def on_ticket_registered(self, event: TicketRegistered) -> None:
        """Manejador del bus de eventos: encola el ticket y regresa de inmediato."""
        self.enqueue(event.ticket_id)

    def enqueue(self, ticket_id: uuid.UUID) -> Future:
        return self._executor.submit(self._run, ticket_id)

    def _run(self, ticket_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            try:
                self._service_factory(session).triage(ticket_id)
            except Exception:  # noqa: BLE001 - el hilo nunca debe morir en silencio
                session.rollback()
                logger.exception("El triaje del ticket %s terminó con error", ticket_id)

    def resume_pending(self) -> int:
        """Encola los tickets OPEN que no tienen diagnóstico. Devuelve cuántos encoló."""
        with self._session_factory() as session:
            ids = HelpdeskTicketReader(session).find_untriaged_open_ticket_ids()
        for ticket_id in ids:
            self.enqueue(ticket_id)
        if ids:
            logger.info("Se reanudó el triaje de %s tickets", len(ids))
        return len(ids)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


triage_worker = BackgroundTriageWorker(max_workers=get_settings().triage_workers)
