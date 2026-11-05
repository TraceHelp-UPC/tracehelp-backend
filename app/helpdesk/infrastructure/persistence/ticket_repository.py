"""Implementación SQLAlchemy del repositorio de tickets.

El repositorio no hace commit: la capa de aplicación controla la transacción.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, undefer

from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket, TicketComment
from app.helpdesk.domain.value_objects import VisualEvidence
from app.helpdesk.infrastructure.persistence.models import TicketCommentModel, TicketEvidenceModel, TicketModel

_SCALAR_FIELDS = (
    "workspace_id",
    "reporter_id",
    "assigned_analyst_id",
    "title",
    "description",
    "affected_module",
    "impact_level",
    "status",
    "priority",
    "current_tier",
    "created_at",
    "updated_at",
    "resolved_at",
    "closed_at",
)


class SqlAlchemyTicketRepository(ITicketRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, ticket: Ticket) -> Ticket:
        model = self._session.get(TicketModel, ticket.id)
        if model is None:
            model = TicketModel(id=ticket.id)
            self._session.add(model)

        for name in _SCALAR_FIELDS:
            setattr(model, name, getattr(ticket, name))

        existing_evidences = {e.id for e in model.evidences}
        for evidence in ticket.evidences:
            if evidence.id not in existing_evidences:
                model.evidences.append(
                    TicketEvidenceModel(
                        id=evidence.id,
                        file_name=evidence.file_name,
                        mime_type=evidence.mime_type,
                        file_size_bytes=evidence.size_bytes,
                        file_data=evidence.content,
                        uploaded_at=evidence.uploaded_at,
                    )
                )

        existing_comments = {c.id for c in model.comments}
        for comment in ticket.comments:
            if comment.id not in existing_comments:
                model.comments.append(
                    TicketCommentModel(
                        id=comment.id,
                        author_id=comment.author_id,
                        content=comment.content,
                        is_ai_generated=comment.is_ai_generated,
                        is_internal_note=comment.is_internal_note,
                        created_at=comment.created_at,
                    )
                )

        self._session.flush()
        ticket.number = model.ticket_number
        return ticket

    def find_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        stmt = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .options(
                selectinload(TicketModel.evidences).undefer(TicketEvidenceModel.file_data),
                selectinload(TicketModel.comments),
            )
            .execution_options(populate_existing=True)
        )
        model = self._session.scalars(stmt).one_or_none()
        return self._to_domain(model) if model else None

    def find_by_reporter(self, reporter_id: uuid.UUID, workspace_id: uuid.UUID) -> list[Ticket]:
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.reporter_id == reporter_id,
                TicketModel.workspace_id == workspace_id,
            )
            .options(
                selectinload(TicketModel.evidences).undefer(TicketEvidenceModel.file_data),
                selectinload(TicketModel.comments),
            )
            .order_by(TicketModel.created_at.desc())
            .execution_options(populate_existing=True)
        )
        models = self._session.scalars(stmt).all()
        return [self._to_domain(m) for m in models]

    def _to_domain(self, model: TicketModel) -> Ticket:
        evidences = [
            VisualEvidence(
                id=e.id,
                file_name=e.file_name,
                mime_type=e.mime_type,
                content=e.file_data,
                uploaded_at=e.uploaded_at,
            )
            for e in model.evidences
        ]
        comments = [
            TicketComment(
                id=c.id,
                author_id=c.author_id,
                content=c.content,
                is_ai_generated=c.is_ai_generated,
                is_internal_note=c.is_internal_note,
                created_at=c.created_at,
            )
            for c in model.comments
        ]
        return Ticket(
            id=model.id,
            number=model.ticket_number,
            evidences=evidences,
            comments=comments,
            **{name: getattr(model, name) for name in _SCALAR_FIELDS},
        )
