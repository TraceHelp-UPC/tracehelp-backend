"""Agregado Ticket y sus entidades internas TicketComment y TicketStatusChange."""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.events import TicketRegistered, TicketStatusChanged
from app.helpdesk.domain.exceptions import InvalidTicketDataError
from app.helpdesk.domain.value_objects import VisualEvidence
from app.shared.domain.aggregate_root import AggregateRoot

MAX_TITLE_LENGTH = 200
MAX_EVIDENCES = 5
MAX_REASON_LENGTH = 500

# Prioridad inicial según el impacto declarado; el triaje (US27) puede ajustarla después
PRIORITY_BY_IMPACT = {
    ImpactLevel.LOW: TicketPriority.LOW,
    ImpactLevel.MEDIUM: TicketPriority.MEDIUM,
    ImpactLevel.HIGH: TicketPriority.HIGH,
}


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TicketComment:
    """Mensaje, respuesta validada o nota interna dentro del ticket."""

    author_id: uuid.UUID
    content: str
    is_ai_generated: bool = False
    is_internal_note: bool = False
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise InvalidTicketDataError("El comentario no puede estar vacío.")


@dataclass(frozen=True)
class TicketStatusChange:
    """Registro inmutable de una transición de estado del ticket (US14, T45)."""

    previous_status: TicketStatus
    new_status: TicketStatus
    changed_by: uuid.UUID | None = None
    reason: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    changed_at: datetime = field(default_factory=_now)

    @property
    def from_status(self) -> TicketStatus:
        return self.previous_status

    @property
    def to_status(self) -> TicketStatus:
        return self.new_status


class Ticket(AggregateRoot):
    """Agregado raíz del ciclo de vida del incidente."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        reporter_id: uuid.UUID,
        title: str,
        description: str,
        affected_module: str | None,
        impact_level: ImpactLevel,
        status: TicketStatus,
        priority: TicketPriority,
        current_tier: SupportTier,
        number: int | None = None,
        assigned_analyst_id: uuid.UUID | None = None,
        evidences: list[VisualEvidence] | None = None,
        comments: list[TicketComment] | None = None,
        status_history: list[TicketStatusChange] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        resolved_at: datetime | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.workspace_id = workspace_id
        self.reporter_id = reporter_id
        self.title = title
        self.description = description
        self.affected_module = affected_module
        self.impact_level = impact_level
        self.status = status
        self.priority = priority
        self.current_tier = current_tier
        self.number = number
        self.assigned_analyst_id = assigned_analyst_id
        self.evidences = list(evidences or [])
        self.comments = list(comments or [])
        self.status_history = list(status_history or [])
        self.created_at = created_at or _now()
        self.updated_at = updated_at or self.created_at
        self.resolved_at = resolved_at
        self.closed_at = closed_at

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def register(
        cls,
        *,
        workspace_id: uuid.UUID,
        reporter_id: uuid.UUID,
        title: str,
        description: str,
        impact_level: ImpactLevel,
        affected_module: str | None = None,
        evidences: list[VisualEvidence] | None = None,
    ) -> "Ticket":
        """Registra un nuevo incidente (US10) y emite TicketRegistered."""
        title = (title or "").strip()
        description = (description or "").strip()
        if not title:
            raise InvalidTicketDataError("El título del incidente es obligatorio.")
        if len(title) > MAX_TITLE_LENGTH:
            raise InvalidTicketDataError(f"El título no puede superar los {MAX_TITLE_LENGTH} caracteres.")
        if not description:
            raise InvalidTicketDataError("La descripción del incidente es obligatoria.")
        evidences = list(evidences or [])
        if len(evidences) > MAX_EVIDENCES:
            raise InvalidTicketDataError(f"Se permiten como máximo {MAX_EVIDENCES} capturas por ticket.")

        ticket = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            reporter_id=reporter_id,
            title=title,
            description=description,
            affected_module=(affected_module or "").strip() or None,
            impact_level=impact_level,
            status=TicketStatus.OPEN,
            priority=PRIORITY_BY_IMPACT[impact_level],
            current_tier=SupportTier.SELF_SERVICE,
            evidences=evidences,
        )
        ticket.record_event(
            TicketRegistered(
                ticket_id=ticket.id,
                workspace_id=workspace_id,
                reporter_id=reporter_id,
                has_evidence=bool(evidences),
            )
        )
        return ticket

    # ------------------------------------------------------------------ comportamiento
    @property
    def code(self) -> str | None:
        """Código público del ticket, por ejemplo TK-0001. Se asigna al guardarlo."""
        return f"TK-{self.number:04d}" if self.number is not None else None

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidences)

    def add_comment(
        self,
        *,
        author_id: uuid.UUID,
        content: str,
        is_internal_note: bool = False,
        is_ai_generated: bool = False,
    ) -> TicketComment:
        comment = TicketComment(
            author_id=author_id,
            content=content.strip(),
            is_internal_note=is_internal_note,
            is_ai_generated=is_ai_generated,
        )
        self.comments.append(comment)
        self.updated_at = _now()
        return comment

    def change_status(
        self,
        target: TicketStatus,
        *,
        changed_by: uuid.UUID | None = None,
        reason: str | None = None,
        assignee_id: uuid.UUID | None = None,
    ) -> None:
        """Cambia el estado respetando la máquina de estados (TS04) y emite TicketStatusChanged.

        changed_by es None cuando el cambio lo hace el sistema (por ejemplo, el triaje automático).
        assignee_id solo se usa al pasar a ASSIGNED_L1; si no se indica, se conserva el analista ya asignado.
        """
        state_machine.ensure_transition(self.status, target)
        reason = (reason or "").strip() or None
        if reason and len(reason) > MAX_REASON_LENGTH:
            raise InvalidTicketDataError(f"El motivo no puede superar los {MAX_REASON_LENGTH} caracteres.")

        if target is TicketStatus.ASSIGNED_L1:
            if assignee_id is not None:
                self.assigned_analyst_id = assignee_id
            elif self.assigned_analyst_id is None:
                raise InvalidTicketDataError("Para pasar el ticket a ASSIGNED_L1 se necesita un analista asignado.")
        elif target is TicketStatus.PENDING_ASSIGNMENT:
            self.assigned_analyst_id = None  # vuelve a la cola sin responsable

        now = _now()
        if target is TicketStatus.RESOLVED:
            self.resolved_at = now
        elif target is TicketStatus.CLOSED:
            self.closed_at = now
        elif target is TicketStatus.REOPENED:
            self.resolved_at = None

        previous = self.status
        self.status = target
        self.current_tier = state_machine.TIER_BY_STATUS.get(target, self.current_tier)
        self.updated_at = now
        self.status_history.append(
            TicketStatusChange(
                previous_status=previous,
                new_status=target,
                changed_by=changed_by,
                reason=reason,
                changed_at=now,
            )
        )
        self.record_event(
            TicketStatusChanged(
                ticket_id=self.id,
                workspace_id=self.workspace_id,
                reporter_id=self.reporter_id,
                previous_status=previous.value,
                new_status=target.value,
                changed_by=changed_by,
                reason=reason,
            )
        )
