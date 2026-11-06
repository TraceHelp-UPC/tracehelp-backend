"""Implementación SQLAlchemy del repositorio de bitácora de auditoría (append-only)."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.domain.audit_trail_entry import AuditTrailEntry
from app.analytics.domain.repositories import IAuditTrailRepository
from app.analytics.domain.value_objects import IntegrityHash
from app.analytics.infrastructure.persistence.models import AuditLogModel


class SqlAlchemyAuditTrailRepository(IAuditTrailRepository):
    """Repositorio append-only sobre analytics_audit_logs (US15, US21)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, entry: AuditTrailEntry) -> AuditTrailEntry:
        model = AuditLogModel(
            id=entry.id,
            workspace_id=entry.workspace_id,
            ticket_id=entry.ticket_id,
            action_type=entry.action_type,
            consulted_sources=list(entry.consulted_sources),
            validator_analyst_id=entry.validator_analyst_id,
            confidence_score=entry.confidence_score,
            details=entry.details,
            integrity_hash_sha256=entry.integrity_hash_sha256,
            occurred_at=entry.occurred_at,
        )
        self._session.add(model)
        self._session.flush()
        return entry

    def find_by_ticket(self, ticket_id: uuid.UUID, workspace_id: uuid.UUID) -> list[AuditTrailEntry]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.ticket_id == ticket_id, AuditLogModel.workspace_id == workspace_id)
            .order_by(AuditLogModel.occurred_at.asc())
        )
        models = self._session.scalars(stmt).all()
        return [self._to_domain(m) for m in models]

    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        ticket_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditTrailEntry], int]:
        filters = [AuditLogModel.workspace_id == workspace_id]
        if ticket_id is not None:
            filters.append(AuditLogModel.ticket_id == ticket_id)

        count_stmt = select(func.count()).select_from(AuditLogModel).where(*filters)
        total = int(self._session.scalar(count_stmt) or 0)

        offset = max(0, (page - 1) * page_size)
        stmt = (
            select(AuditLogModel)
            .where(*filters)
            .order_by(AuditLogModel.occurred_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        models = self._session.scalars(stmt).all()
        return [self._to_domain(m) for m in models], total

    def _to_domain(self, model: AuditLogModel) -> AuditTrailEntry:
        return AuditTrailEntry(
            id=model.id,
            workspace_id=model.workspace_id,
            ticket_id=model.ticket_id,
            action_type=model.action_type,
            consulted_sources=model.consulted_sources,
            validator_analyst_id=model.validator_analyst_id,
            confidence_score=model.confidence_score,
            details=model.details,
            occurred_at=model.occurred_at,
            integrity_hash=IntegrityHash(model.integrity_hash_sha256),
        )
