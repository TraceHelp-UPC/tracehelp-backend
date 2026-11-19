"""Manejador que reabre el diagnóstico para revisión HITL cuando el colaborador rechaza el autoservicio (US12, D10).

Se suscribe de forma permanente (fuera de triage_worker_enabled) tanto a SelfServiceRejected como a
TicketStatusChanged (SELF_SERVICE_PROPOSED -> PENDING_ASSIGNMENT), para cubrir el endpoint dedicado
POST /tickets/{id}/self-service/reject y cualquier transición manual por PATCH /status.
"""
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.helpdesk.domain.events import SelfServiceRejected, TicketStatusChanged
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)

logger = logging.getLogger(__name__)


class SelfServiceRejectionHandler:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    def __call__(self, event: SelfServiceRejected | TicketStatusChanged) -> bool:
        if isinstance(event, TicketStatusChanged):
            if event.previous_status != "SELF_SERVICE_PROPOSED" or event.new_status != "PENDING_ASSIGNMENT":
                return False

        with self._session_factory() as session:
            repo = SqlAlchemyTriageDiagnosisRepository(session)
            diagnosis = repo.find_by_ticket_id(event.ticket_id)
            if diagnosis is None:
                return False
            if not diagnosis.reopen_for_analyst_review():
                return False
            repo.save(diagnosis)
            session.commit()
            logger.info(
                "Diagnóstico %s reabierto a PENDING_REVIEW tras rechazo de autoservicio del ticket %s",
                diagnosis.id,
                event.ticket_id,
            )
            return True
