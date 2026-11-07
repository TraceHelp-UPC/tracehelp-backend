"""Consultas SQL de tickets para las bandejas (TS08).

Selecciona columnas sueltas en lugar de entidades: así no se cargan las relaciones (evidencias y comentarios)
ni el contenido binario de las capturas.
"""
import re
import uuid

from sqlalchemy import Select, case, false, func, or_, select
from sqlalchemy.orm import Session, undefer

from app.helpdesk.application.ticket_queries import (
    EvidenceFile,
    ITicketReadModel,
    TicketOrder,
    TicketSearchCriteria,
    TicketSummary,
)
from app.helpdesk.domain.enums import TicketPriority
from app.helpdesk.infrastructure.persistence.models import TicketEvidenceModel, TicketModel
from app.shared.domain.pagination import Page, PageRequest

_CODE = re.compile(r"^(?:tk-?)?0*(\d{1,9})$", re.I)

_PRIORITY_RANK = case(
    {
        TicketPriority.CRITICAL: 0,
        TicketPriority.HIGH: 1,
        TicketPriority.MEDIUM: 2,
        TicketPriority.LOW: 3,
    },
    value=TicketModel.priority,
    else_=4,
)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyTicketReadModel(ITicketReadModel):
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, criteria: TicketSearchCriteria, page: PageRequest) -> Page[TicketSummary]:
        conditions = self._conditions(criteria)
        total = self._session.scalar(select(func.count()).select_from(TicketModel).where(*conditions)) or 0

        evidence_count = (
            select(func.count(TicketEvidenceModel.id))
            .where(TicketEvidenceModel.ticket_id == TicketModel.id)
            .correlate(TicketModel)
            .scalar_subquery()
        )
        stmt: Select = select(
            TicketModel.id,
            TicketModel.ticket_number,
            TicketModel.title,
            TicketModel.status,
            TicketModel.priority,
            TicketModel.impact_level,
            TicketModel.current_tier,
            TicketModel.affected_module,
            TicketModel.reporter_id,
            TicketModel.assigned_analyst_id,
            evidence_count.label("evidence_count"),
            TicketModel.created_at,
            TicketModel.updated_at,
        ).where(*conditions)
        if criteria.order is TicketOrder.PRIORITY:
            stmt = stmt.order_by(_PRIORITY_RANK, TicketModel.created_at.asc(), TicketModel.ticket_number.asc())
        else:
            stmt = stmt.order_by(TicketModel.created_at.desc(), TicketModel.ticket_number.desc())

        rows = self._session.execute(stmt.offset(page.offset).limit(page.size)).all()
        items = [
            TicketSummary(
                id=r.id,
                number=r.ticket_number,
                title=r.title,
                status=r.status,
                priority=r.priority,
                impact_level=r.impact_level.value,
                current_tier=r.current_tier.value,
                affected_module=r.affected_module,
                reporter_id=r.reporter_id,
                assigned_analyst_id=r.assigned_analyst_id,
                evidence_count=r.evidence_count,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]
        return Page(items=items, page=page.page, size=page.size, total=total)

    def get_evidence(self, ticket_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceFile | None:
        stmt = (
            select(TicketEvidenceModel)
            .where(TicketEvidenceModel.id == evidence_id, TicketEvidenceModel.ticket_id == ticket_id)
            .options(undefer(TicketEvidenceModel.file_data))
        )
        model = self._session.scalars(stmt).one_or_none()
        if model is None:
            return None
        return EvidenceFile(id=model.id, file_name=model.file_name, mime_type=model.mime_type, content=model.file_data)

    @staticmethod
    def _conditions(criteria: TicketSearchCriteria) -> list:
        conditions = [TicketModel.workspace_id == criteria.workspace_id]
        if criteria.statuses is not None:
            conditions.append(TicketModel.status.in_(criteria.statuses) if criteria.statuses else false())
        if criteria.priorities:
            conditions.append(TicketModel.priority.in_(criteria.priorities))
        if criteria.reporter_id is not None:
            conditions.append(TicketModel.reporter_id == criteria.reporter_id)
        if criteria.assigned_analyst_id is not None:
            conditions.append(TicketModel.assigned_analyst_id == criteria.assigned_analyst_id)
        if criteria.search:
            text_match = TicketModel.title.ilike(f"%{_escape_like(criteria.search)}%", escape="\\")
            code = _CODE.match(criteria.search)
            conditions.append(or_(text_match, TicketModel.ticket_number == int(code.group(1))) if code else text_match)
        return conditions
