"""Implementación SQLAlchemy de la bitácora de auditoría (US15, T36)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.domain.audit_entry import AuditEntry
from app.analytics.domain.repositories import AuditLogFilter, IAuditLogRepository
from app.analytics.infrastructure.persistence.models import AuditLogModel


class SqlAlchemyAuditLogRepository(IAuditLogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, entry: AuditEntry) -> AuditEntry:
        model = AuditLogModel(
            id=entry.id,
            workspace_id=entry.workspace_id,
            event_type=entry.event_type,
            actor_id=entry.actor_id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            ticket_id=entry.ticket_id,
            detail=dict(entry.detail),
            integrity_hash=entry.integrity_hash,
            occurred_at=entry.occurred_at,
        )
        self._session.add(model)
        self._session.flush()
        return entry

    def query(self, criteria: AuditLogFilter, *, offset: int = 0, limit: int = 20) -> tuple[list[AuditEntry], int]:
        stmt = select(AuditLogModel).where(AuditLogModel.workspace_id == criteria.workspace_id)
        if criteria.event_type:
            stmt = stmt.where(AuditLogModel.event_type == criteria.event_type)
        if criteria.ticket_id is not None:
            stmt = stmt.where(AuditLogModel.ticket_id == criteria.ticket_id)
        if criteria.from_date is not None:
            stmt = stmt.where(AuditLogModel.occurred_at >= criteria.from_date)
        if criteria.to_date is not None:
            stmt = stmt.where(AuditLogModel.occurred_at <= criteria.to_date)

        total = int(self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        if total == 0:
            return [], 0

        rows = self._session.scalars(
            stmt.order_by(AuditLogModel.occurred_at.desc(), AuditLogModel.id.desc()).offset(offset).limit(limit)
        ).all()
        return [self._to_domain(row) for row in rows], total

    @staticmethod
    def _to_domain(model: AuditLogModel) -> AuditEntry:
        return AuditEntry(
            id=model.id,
            workspace_id=model.workspace_id,
            event_type=model.event_type,
            actor_id=model.actor_id,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            ticket_id=model.ticket_id,
            detail=dict(model.detail or {}),
            integrity_hash=model.integrity_hash,
            occurred_at=model.occurred_at,
        )
