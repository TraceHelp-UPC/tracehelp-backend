"""Dependencias de FastAPI para el contexto Analytics."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.analytics.application.audit_trail_service import AuditTrailService
from app.analytics.infrastructure.persistence.audit_trail_repository import SqlAlchemyAuditTrailRepository
from app.core.database import get_db


def get_audit_trail_service(session: Session = Depends(get_db)) -> AuditTrailService:
    return AuditTrailService(session=session, repository=SqlAlchemyAuditTrailRepository(session))
