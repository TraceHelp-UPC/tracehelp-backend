"""Dependencias de FastAPI para el Bounded Context Smart Triage."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.analytics.infrastructure.persistence.audit_trail_repository import SqlAlchemyAuditTrailRepository
from app.core.database import get_db
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.shared.infrastructure.event_bus import event_bus
from app.smart_triage.application.triage_service import TriageService
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)


def get_triage_service(session: Session = Depends(get_db)) -> TriageService:
    return TriageService(
        session=session,
        diagnoses=SqlAlchemyTriageDiagnosisRepository(session),
        tickets=SqlAlchemyTicketRepository(session),
        audit_logs=SqlAlchemyAuditTrailRepository(session),
        events=event_bus,
    )
