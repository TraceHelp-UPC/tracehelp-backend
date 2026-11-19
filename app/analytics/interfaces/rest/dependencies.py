"""Inyección de dependencias para los endpoints de Analytics."""
import uuid
from datetime import UTC, datetime

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.domain.exceptions import InvalidDateRangeError
from app.analytics.domain.repositories import AuditLogFilter
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.core.database import get_db
from app.iam.domain.permissions import Permission
from app.iam.infrastructure.persistence.models import UserModel
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission


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


def _as_utc(value: datetime | None) -> datetime | None:
    """Las fechas sin zona horaria se interpretan como UTC antes de consultar."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def audit_log_filter(
    event_type: str | None = Query(
        None, max_length=80, description="Tipo de evento, coincidencia exacta (ej. AiResolutionReviewed)."
    ),
    ticket_id: uuid.UUID | None = Query(None, description="Solo las entradas de este ticket."),
    actor_id: uuid.UUID | None = Query(
        None, description="Solo las entradas cuyo actor es este usuario (validador, quien cambió el estado...)."
    ),
    from_date: datetime | None = Query(
        None, description="Fecha inicial inclusiva (ISO 8601). Sin zona horaria se toma como UTC."
    ),
    to_date: datetime | None = Query(
        None, description="Fecha final inclusiva (ISO 8601). Sin zona horaria se toma como UTC."
    ),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> AuditLogFilter:
    """Lee y valida los filtros de la bitácora. Lo reutilizan la consulta paginada y la exportación (T97)."""
    start, end = _as_utc(from_date), _as_utc(to_date)
    if start is not None and end is not None and start > end:
        raise InvalidDateRangeError("La fecha inicial no puede ser posterior a la fecha final.")
    return AuditLogFilter(
        workspace_id=current_user.workspace_id,
        event_type=event_type.strip() if event_type and event_type.strip() else None,
        ticket_id=ticket_id,
        actor_id=actor_id,
        from_date=start,
        to_date=end,
    )
