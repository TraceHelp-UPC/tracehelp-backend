"""Adaptador ACL SQLAlchemy de solo lectura para trazabilidad de tickets (US21, T96).

Consulta las tablas helpdesk_tickets, triage_diagnoses e iam_users sin importar
servicios ni agregados de otros bounded contexts.
"""
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.application.ports import (
    DiagnosisTraceSummary,
    ITicketTraceReader,
    TicketTraceSnapshot,
    TicketTraceSummary,
    TraceSourceItem,
    UserIdentity,
)


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class SqlAlchemyTicketTraceReader(ITicketTraceReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_ticket_trace_snapshot(
        self, workspace_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> TicketTraceSnapshot | None:
        ticket_row = self._session.execute(
            text(
                """
                SELECT
                    t.id,
                    t.ticket_number,
                    t.title,
                    t.status,
                    t.priority,
                    t.category,
                    t.reporter_id,
                    rep.full_name AS reporter_name,
                    t.assigned_analyst_id,
                    ana.full_name AS assigned_analyst_name,
                    t.created_at,
                    t.resolved_at
                FROM helpdesk_tickets t
                LEFT JOIN iam_users rep ON rep.id = t.reporter_id
                LEFT JOIN iam_users ana ON ana.id = t.assigned_analyst_id
                WHERE t.workspace_id = :workspace_id
                  AND t.id = :ticket_id
                """
            ),
            {"workspace_id": workspace_id, "ticket_id": ticket_id},
        ).mappings().one_or_none()

        if ticket_row is None:
            return None

        ticket = TicketTraceSummary(
            id=_as_uuid(ticket_row["id"]),
            code=f"TK-{int(ticket_row['ticket_number']):04d}",
            title=ticket_row["title"],
            status=str(ticket_row["status"]),
            priority=str(ticket_row["priority"]),
            category=str(ticket_row["category"]) if ticket_row["category"] is not None else None,
            reporter_id=_as_uuid(ticket_row["reporter_id"]),
            reporter_name=ticket_row["reporter_name"] or "Usuario",
            assigned_analyst_id=(
                _as_uuid(ticket_row["assigned_analyst_id"])
                if ticket_row["assigned_analyst_id"] is not None
                else None
            ),
            assigned_analyst_name=ticket_row["assigned_analyst_name"],
            created_at=ticket_row["created_at"],
            resolved_at=ticket_row["resolved_at"],
        )

        diag_row = self._session.execute(
            text(
                """
                SELECT
                    id,
                    outcome,
                    confidence_level,
                    best_score,
                    similarity_threshold,
                    self_service_threshold,
                    model,
                    review_status,
                    sources,
                    reviewed_by,
                    reviewed_at
                FROM triage_diagnoses
                WHERE workspace_id = :workspace_id
                  AND ticket_id = :ticket_id
                """
            ),
            {"workspace_id": workspace_id, "ticket_id": ticket_id},
        ).mappings().one_or_none()

        diagnosis: DiagnosisTraceSummary | None = None
        sources: list[TraceSourceItem] = []

        if diag_row is not None:
            diagnosis = DiagnosisTraceSummary(
                id=_as_uuid(diag_row["id"]),
                outcome=str(diag_row["outcome"]),
                confidence_level=(
                    str(diag_row["confidence_level"]) if diag_row["confidence_level"] is not None else None
                ),
                best_score=float(diag_row["best_score"]) if diag_row["best_score"] is not None else None,
                similarity_threshold=(
                    float(diag_row["similarity_threshold"])
                    if diag_row["similarity_threshold"] is not None
                    else None
                ),
                self_service_threshold=(
                    float(diag_row["self_service_threshold"])
                    if diag_row["self_service_threshold"] is not None
                    else None
                ),
                model=diag_row["model"],
                review_status=str(diag_row["review_status"]),
                reviewed_by=_as_uuid(diag_row["reviewed_by"]) if diag_row["reviewed_by"] is not None else None,
                reviewed_at=diag_row["reviewed_at"],
            )
            for item in diag_row["sources"] or []:
                sources.append(
                    TraceSourceItem(
                        reference=str(item["reference"]),
                        chunk_id=_as_uuid(item["chunk_id"]),
                        document_id=_as_uuid(item["document_id"]),
                        document_title=str(item["document_title"]),
                        citation=str(item["citation"]),
                        similarity=float(item["similarity"]),
                    )
                )

        return TicketTraceSnapshot(ticket=ticket, diagnosis=diagnosis, sources=sources)

    def get_users_by_ids(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, UserIdentity]:
        if not user_ids:
            return {}
        rows = self._session.execute(
            text(
                """
                SELECT id, full_name, role
                FROM iam_users
                WHERE id = ANY(:user_ids)
                """
            ),
            {"user_ids": list(user_ids)},
        ).mappings().all()
        return {
            _as_uuid(row["id"]): UserIdentity(
                id=_as_uuid(row["id"]),
                full_name=row["full_name"],
                role=str(row["role"]),
            )
            for row in rows
        }
