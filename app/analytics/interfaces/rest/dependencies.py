"""Inyección de dependencias para los endpoints de Analytics."""
import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.core.database import get_db
from app.iam.infrastructure.persistence.models import UserModel


def _resolve_user_names(session: Session):
    def _lookup(user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        rows = session.execute(select(UserModel.id, UserModel.full_name).where(UserModel.id.in_(user_ids))).all()
        return {row.id: row.full_name for row in rows}

    return _lookup


def get_audit_log_service(db: Session = Depends(get_db)) -> AuditLogService:
    return AuditLogService(
        repository=SqlAlchemyAuditLogRepository(db),
        user_names=_resolve_user_names(db),
    )
