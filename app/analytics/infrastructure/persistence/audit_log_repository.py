"""Implementación SQLAlchemy de la bitácora de auditoría encadenada (US15, T36; US21, T96)."""
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analytics.domain.audit_entry import AuditEntry
from app.analytics.domain.repositories import AuditLogFilter, IAuditLogRepository
from app.analytics.infrastructure.persistence.models import AuditLogModel


class SqlAlchemyAuditLogRepository(IAuditLogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, entry: AuditEntry) -> AuditEntry:
        # Serializa escrituras de la cadena dentro del mismo workspace sin bloquear otros workspaces (D29)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('audit_chain:' || :workspace_id))"),
            {"workspace_id": str(entry.workspace_id)},
        )
        last_hash = self._session.scalar(
            select(AuditLogModel.integrity_hash)
            .where(AuditLogModel.workspace_id == entry.workspace_id)
            .order_by(AuditLogModel.seq.desc())
            .limit(1)
        )
        chained = entry.chained_to(last_hash)

        model = AuditLogModel(
            id=chained.id,
            workspace_id=chained.workspace_id,
            event_type=chained.event_type,
            actor_id=chained.actor_id,
            entity_type=chained.entity_type,
            entity_id=chained.entity_id,
            ticket_id=chained.ticket_id,
            detail=dict(chained.detail),
            integrity_hash=chained.integrity_hash,
            previous_hash=chained.previous_hash,
            occurred_at=chained.occurred_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_domain(model)

    def query(self, criteria: AuditLogFilter, *, offset: int = 0, limit: int = 20) -> tuple[list[AuditEntry], int]:
        stmt = select(AuditLogModel).where(AuditLogModel.workspace_id == criteria.workspace_id)
        if criteria.event_type:
            stmt = stmt.where(AuditLogModel.event_type == criteria.event_type)
        if criteria.ticket_id is not None:
            stmt = stmt.where(AuditLogModel.ticket_id == criteria.ticket_id)
        if criteria.actor_id is not None:
            stmt = stmt.where(AuditLogModel.actor_id == criteria.actor_id)
        if criteria.from_date is not None:
            stmt = stmt.where(AuditLogModel.occurred_at >= criteria.from_date)
        if criteria.to_date is not None:
            stmt = stmt.where(AuditLogModel.occurred_at <= criteria.to_date)

        total = int(self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        if total == 0:
            return [], 0

        rows = self._session.scalars(
            stmt.order_by(AuditLogModel.occurred_at.desc(), AuditLogModel.seq.desc()).offset(offset).limit(limit)
        ).all()
        return [self._to_domain(row) for row in rows], total

    def find_by_id(self, workspace_id: uuid.UUID, entry_id: uuid.UUID) -> AuditEntry | None:
        model = self._session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.workspace_id == workspace_id,
                AuditLogModel.id == entry_id,
            )
        ).one_or_none()
        return self._to_domain(model) if model is not None else None

    def find_previous(self, workspace_id: uuid.UUID, seq: int) -> AuditEntry | None:
        model = self._session.scalars(
            select(AuditLogModel)
            .where(
                AuditLogModel.workspace_id == workspace_id,
                AuditLogModel.seq < seq,
            )
            .order_by(AuditLogModel.seq.desc())
            .limit(1)
        ).one_or_none()
        return self._to_domain(model) if model is not None else None

    def list_for_ticket(self, workspace_id: uuid.UUID, ticket_id: uuid.UUID) -> list[AuditEntry]:
        rows = self._session.scalars(
            select(AuditLogModel)
            .where(
                AuditLogModel.workspace_id == workspace_id,
                AuditLogModel.ticket_id == ticket_id,
            )
            .order_by(AuditLogModel.occurred_at.asc(), AuditLogModel.seq.asc())
        ).all()
        return [self._to_domain(row) for row in rows]

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
            previous_hash=model.previous_hash,
            seq=model.seq,
        )
