"""Agregado Ticket y su entidad interna TicketComment."""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.events import (
    TicketClassificationOverridden,
    TicketRegistered,
    TicketStatusChanged,
)
from app.helpdesk.domain.exceptions import InvalidTicketDataError
from app.helpdesk.domain.value_objects import VisualEvidence
from app.shared.domain.aggregate_root import AggregateRoot
from app.smart_triage.domain.classification import DEFAULT_CATEGORY, VALID_CATEGORIES, TriageClassification

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
        category: str = DEFAULT_CATEGORY,
        suggested_category: str | None = None,
        suggested_priority: TicketPriority | None = None,
        number: int | None = None,
        assigned_analyst_id: uuid.UUID | None = None,
        evidences: list[VisualEvidence] | None = None,
        comments: list[TicketComment] | None = None,
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
        self.category = category
        self.suggested_category = suggested_category or category
        self.suggested_priority = suggested_priority or priority
        self.number = number
        self.assigned_analyst_id = assigned_analyst_id
        self.evidences = list(evidences or [])
        self.comments = list(comments or [])
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
        """Registra un nuevo incidente (US10, US27) y emite TicketRegistered."""
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

        cleaned_module = (affected_module or "").strip() or None
        classification = TriageClassification.infer_from_incident(
            title=title,
            description=description,
            impact_level=impact_level,
            affected_module=cleaned_module,
        )

        ticket = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            reporter_id=reporter_id,
            title=title,
            description=description,
            affected_module=cleaned_module,
            impact_level=impact_level,
            status=TicketStatus.OPEN,
            priority=classification.priority,
            current_tier=SupportTier.SELF_SERVICE,
            category=classification.category,
            suggested_category=classification.category,
            suggested_priority=classification.priority,
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

    def apply_triage_classification(self, classification: TriageClassification) -> None:
        """Aplica la clasificación estructurada devuelta por el triaje automático (US27, T41)."""
        self.category = classification.category
        self.priority = classification.priority
        self.suggested_category = classification.category
        self.suggested_priority = classification.priority
        self.updated_at = _now()

    def override_classification(
        self,
        *,
        category: str,
        priority: TicketPriority,
        analyst_id: uuid.UUID,
    ) -> None:
        """Permite al analista corregir categoría y prioridad conservando la clasificación sugerida (US27, T42)."""
        cleaned = (category or "").strip()
        if not cleaned or cleaned not in VALID_CATEGORIES:
            raise InvalidTicketDataError(
                f"La categoría '{cleaned}' no pertenece al catálogo permitido: {', '.join(sorted(VALID_CATEGORIES))}."
            )
        if not isinstance(priority, TicketPriority):
            try:
                priority = TicketPriority(str(priority).upper())
            except ValueError as exc:
                raise InvalidTicketDataError(f"Prioridad inválida: {priority}.") from exc

        if self.suggested_category is None:
            self.suggested_category = self.category
        if self.suggested_priority is None:
            self.suggested_priority = self.priority

        self.category = cleaned
        self.priority = priority
        self.updated_at = _now()
        self.record_event(
            TicketClassificationOverridden(
                ticket_id=self.id,
                workspace_id=self.workspace_id,
                analyst_id=analyst_id,
                suggested_category=self.suggested_category,
                suggested_priority=self.suggested_priority.value,
                new_category=self.category,
                new_priority=self.priority.value,
            )
        )
