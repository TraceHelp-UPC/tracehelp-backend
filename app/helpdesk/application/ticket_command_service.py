"""Casos de uso de escritura del contexto Helpdesk."""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.helpdesk.application import status_change_policy
from app.helpdesk.application.ports import (
    IAnalystAvailabilityReader,
    IImageProcessor,
    ITriageContextReader,
    TriageContextSnapshot,
)
from app.helpdesk.application.ticket_queries import IUserDirectory
from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import ImpactLevel, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.exceptions import (
    InternalNoteNotAllowedError,
    InvalidTicketDataError,
    InvalidTicketStateTransitionError,
    InvalidVisualEvidenceError,
    TicketAccessDeniedError,
    TicketNotFoundError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket, TicketComment
from app.helpdesk.domain.value_objects import MAX_EVIDENCE_BYTES, VisualEvidence
from app.iam.domain.permissions import Permission
from app.shared.domain.specialist_group import SpecialistGroup
from app.shared.infrastructure.event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_OCR_LENGTH = 1000
_NO_TRIAGE_SUMMARY = "Sin diagnóstico automático registrado al momento del escalamiento."


@dataclass(frozen=True)
class UploadedFile:
    file_name: str
    content: bytes


@dataclass(frozen=True)
class RegisterTicketCommand:
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    title: str
    description: str
    impact_level: ImpactLevel
    affected_module: str | None = None
    screenshots: list[UploadedFile] = field(default_factory=list)


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    ticket_id: uuid.UUID
    actor: Actor
    target_status: TicketStatus
    reason: str | None = None


@dataclass(frozen=True)
class CorrectTicketClassificationCommand:
    ticket_id: uuid.UUID
    actor: Actor
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AssignTicketCommand:
    ticket_id: uuid.UUID
    actor: Actor
    analyst_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PostMessageCommand:
    ticket_id: uuid.UUID
    actor: Actor
    content: str
    is_internal_note: bool = False


@dataclass(frozen=True)
class PostedMessage:
    """Resultado de publicar un mensaje: el comentario creado y lo que la API necesita para responder."""

    ticket_id: uuid.UUID
    comment: TicketComment
    from_reporter: bool
    author_name: str | None


@dataclass(frozen=True)
class EscalateTicketCommand:
    ticket_id: uuid.UUID
    actor: Actor
    specialist_group: SpecialistGroup
    reason: str


@dataclass(frozen=True)
class ReturnToL1Command:
    ticket_id: uuid.UUID
    actor: Actor
    requested_info: str


def _format_escalation_snapshot(
    *,
    ticket: Ticket,
    specialist_group: SpecialistGroup,
    reason: str,
    triage: TriageContextSnapshot | None,
) -> str:
    """Construye la plantilla determinística de la nota interna de escalamiento (US17, D30 §2.3)."""
    category_label = ticket.category.value if ticket.category else "Sin categoría"
    module_label = ticket.affected_module or "No especificado"

    if triage is None:
        triage_line = f"Triaje IA: {_NO_TRIAGE_SUMMARY}"
        ocr_line = "Sin evidencia OCR"
        sources_block = "- Sin fuentes consultadas"
    else:
        summary = (triage.summary or "").strip() or _NO_TRIAGE_SUMMARY
        outcome = triage.outcome or "N/A"
        confidence = triage.confidence_level or "N/A"
        score = f"{triage.best_score:.2f}" if triage.best_score is not None else "N/A"
        triage_line = f"Triaje IA: {summary} (resultado={outcome}, confianza={confidence}, score={score})"

        if triage.ocr_legible is False:
            ocr_line = "Captura adjunta no legible"
        else:
            ocr_parts: list[str] = []
            if triage.ocr_error_codes:
                ocr_parts.append(f"Códigos: {', '.join(triage.ocr_error_codes)}")
            ocr_text = (triage.ocr_masked_text or "").strip()
            if ocr_text:
                if len(ocr_text) > MAX_SNAPSHOT_OCR_LENGTH:
                    ocr_text = ocr_text[:MAX_SNAPSHOT_OCR_LENGTH] + "…"
                ocr_parts.append(ocr_text)
            ocr_line = " | ".join(ocr_parts) if ocr_parts else "Sin evidencia OCR"

        if triage.sources:
            sources_block = "\n".join(
                f"- [{src.reference}] {src.citation} ({src.document_title})" for src in triage.sources
            )
        else:
            sources_block = "- Sin fuentes consultadas"

    return (
        f"[ESCALAMIENTO A L2 · {specialist_group.value}]\n"
        f"Motivo del escalamiento: {reason.strip()}\n"
        f"Clasificación: Categoría={category_label} | Prioridad={ticket.priority.value} "
        f"| Impacto={ticket.impact_level.value} | Módulo={module_label}\n"
        f"{triage_line}\n"
        f"OCR (anonimizado): {ocr_line}\n"
        f"Fuentes consultadas:\n"
        f"{sources_block}"
    )


def _format_return_to_l1_note(*, ticket: Ticket, requested_info: str) -> str:
    """Construye la plantilla determinística de la nota interna al devolver a L1 (US17, D30 §2.3)."""
    group_label = ticket.escalated_group.value if ticket.escalated_group else "L2"
    return (
        f"[DEVOLUCIÓN DE L2 A L1 · {group_label}]\n"
        f"Información adicional solicitada: {requested_info.strip()}"
    )


class TicketCommandService:
    def __init__(
        self,
        session: Session,
        tickets: ITicketRepository,
        images: IImageProcessor,
        events: InMemoryEventBus,
        analysts: IAnalystAvailabilityReader | None = None,
        users: IUserDirectory | None = None,
        triage_context: ITriageContextReader | None = None,
    ) -> None:
        self._session = session
        self._tickets = tickets
        self._images = images
        self._events = events
        self._analysts = analysts
        self._users = users
        self._triage_context = triage_context

    def register(self, command: RegisterTicketCommand) -> Ticket:
        """Registra un incidente con texto y capturas opcionales (US10, TS04) y publica TicketRegistered."""
        evidences = []
        for upload in command.screenshots:
            if len(upload.content) > MAX_EVIDENCE_BYTES:
                raise InvalidVisualEvidenceError(
                    f"La imagen '{upload.file_name}' supera el tamaño máximo permitido de 10 MB."
                )
            image = self._images.process(upload.content, upload.file_name)
            evidences.append(VisualEvidence(file_name=image.file_name, mime_type=image.mime_type, content=image.content))

        ticket = Ticket.register(
            workspace_id=command.workspace_id,
            reporter_id=command.reporter_id,
            title=command.title,
            description=command.description,
            impact_level=command.impact_level,
            affected_module=command.affected_module,
            evidences=evidences,
        )
        self._tickets.save(ticket)
        self._session.commit()
        # Se publica después del commit para no notificar cambios que podrían revertirse
        self._events.publish_all(ticket.pull_events())
        return ticket

    def change_status(self, command: ChangeTicketStatusCommand) -> Ticket:
        """Cambia el estado de un ticket (TS04).

        Orden de validación: el ticket existe y es visible (404), el cambio existe en la máquina de estados (422)
        y el actor puede hacerlo (403). Publica TicketStatusChanged después del commit.
        """
        actor = command.actor
        ticket = self._tickets.find_by_id(command.ticket_id)
        # Un ticket de otro workspace, o uno ajeno para un colaborador, se trata como inexistente
        if (
            ticket is None
            or ticket.workspace_id != actor.workspace_id
            or (not actor.is_support_staff and ticket.reporter_id != actor.id)
        ):
            raise TicketNotFoundError("El ticket no existe.")

        state_machine.ensure_transition(ticket.status, command.target_status)
        status_change_policy.authorize(actor, ticket, command.target_status)

        # Al tomar un ticket sin responsable, queda asignado a quien lo toma
        assignee_id = None
        if command.target_status is TicketStatus.ASSIGNED_L1 and ticket.assigned_analyst_id is None:
            assignee_id = actor.id

        ticket.change_status(
            command.target_status, changed_by=actor.id, reason=command.reason, assignee_id=assignee_id
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def post_message(self, command: PostMessageCommand) -> PostedMessage:
        """Publica un mensaje o nota interna en la conversación del ticket (US26, T85).

        Orden de validación: el ticket existe en el workspace (404), el actor lo ve (403), la nota interna está
        permitida (403), el ticket no está RESOLVED ni CLOSED (409, D30) y la longitud del texto (defensa del dominio).
        Guarda el texto tal cual; no se envía nada a Gemini. Si un consumidor futuro envía mensajes al LLM,
        debe pasarlos por get_pii_masker().mask(...) y entregar SanitizedText. Publica MessagePosted (sin el
        texto) después del commit.
        """
        actor = command.actor
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        is_reporter = ticket.reporter_id == actor.id
        if not actor.is_support_staff and not is_reporter:
            raise TicketAccessDeniedError("No tienes acceso a este ticket: solo lo ven quien lo reportó y el equipo de soporte.")
        if command.is_internal_note and not actor.is_support_staff:
            raise InternalNoteNotAllowedError("Solo el equipo de soporte puede registrar notas internas.")

        comment = ticket.post_message(
            author_id=actor.id,
            content=command.content,
            is_internal_note=command.is_internal_note,
            author_is_reporter=is_reporter,
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        names = self._users.display_names({actor.id}) if self._users is not None else {}
        return PostedMessage(
            ticket_id=ticket.id, comment=comment, from_reporter=is_reporter, author_name=names.get(actor.id)
        )

    def assign_ticket(self, command: AssignTicketCommand) -> Ticket:
        """Asigna un ticket a un analista disponible o al propio analista que lo toma (US24, T47)."""
        actor = command.actor
        if not (actor.can(Permission.TICKETS_MANAGE) or actor.can(Permission.IAM_ADMIN)):
            raise TicketStatusChangeForbiddenError("No tienes permiso para asignar tickets.")
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")

        target_analyst_id = command.analyst_id or actor.id
        if self._analysts is not None:
            candidate = self._analysts.get_candidate(target_analyst_id)
            if candidate is None or candidate.workspace_id != actor.workspace_id or not candidate.is_active:
                raise InvalidTicketDataError("El analista indicado no existe en este workspace.")
            if not candidate.is_support_staff:
                raise InvalidTicketDataError("Solo se pueden asignar tickets a analistas o especialistas de soporte.")
            if not candidate.is_available:
                raise InvalidTicketStateTransitionError(
                    f"El analista {candidate.full_name} se encuentra UNAVAILABLE y no puede recibir tickets."
                )

        reason = command.reason or "Asignado a soporte Nivel 1"
        if ticket.status is TicketStatus.ASSIGNED_L1:
            ticket.assigned_analyst_id = target_analyst_id
        else:
            ticket.change_status(
                TicketStatus.ASSIGNED_L1,
                changed_by=actor.id,
                reason=reason,
                assignee_id=target_analyst_id,
            )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def route_after_triage(
        self,
        ticket_id: uuid.UUID,
        target: TicketStatus,
        reason: str,
        *,
        suggested_category: TicketCategory | None = None,
        suggested_priority: TicketPriority | None = None,
    ) -> Ticket | None:
        """Mueve el ticket según el resultado del triaje automático (T28) y aplica la clasificación sugerida (T41).

        Si el ticket ya no está en OPEN (por ejemplo, un analista lo tomó a mano), se respeta ese cambio y no se mueve.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None:
            logger.warning("El triaje terminó para un ticket inexistente: %s", ticket_id)
            return None
        if ticket.status is not TicketStatus.OPEN:
            logger.info("El ticket %s ya está en %s; el triaje no lo mueve", ticket.code, ticket.status.value)
            return None
        ticket.apply_triage_classification(
            suggested_category=suggested_category,
            suggested_priority=suggested_priority,
        )
        ticket.change_status(target, changed_by=None, reason=reason)
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def correct_classification(self, command: CorrectTicketClassificationCommand) -> Ticket:
        """Establece o corrige la clasificación del ticket por el analista (US27, T42)."""
        actor = command.actor
        if not actor.can(Permission.TICKETS_MANAGE):
            raise TicketStatusChangeForbiddenError("Solo el equipo de soporte puede clasificar tickets.")
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        ticket.correct_classification(
            corrected_by=actor.id,
            category=command.category,
            priority=command.priority,
            reason=command.reason,
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def stage_resolution(
        self, ticket_id: uuid.UUID, actor: Actor, *, response_text: str, ai_generated: bool
    ) -> list:
        """Deja el ticket en RESOLVED con la respuesta para el colaborador como comentario visible (US15, T35).

        No hace commit: lo hace quien llama, junto con la revisión del diagnóstico, en una sola transacción.
        Aplica las mismas reglas que PATCH /status: el ticket debe ser del workspace del analista, estar asignado
        (ASSIGNED_L1) o escalado (ESCALATED_L2), y el rol debe poder resolverlo. Devuelve los eventos por publicar.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        if ticket.status is TicketStatus.PENDING_ASSIGNMENT:
            raise InvalidTicketStateTransitionError(
                f"Toma el ticket {ticket.code} (Atender) antes de responderlo."
            )
        state_machine.ensure_transition(ticket.status, TicketStatus.RESOLVED)
        status_change_policy.authorize(actor, ticket, TicketStatus.RESOLVED)

        ticket.add_comment(author_id=actor.id, content=response_text, is_ai_generated=ai_generated)
        reason = "Respuesta de la IA validada por el analista." if ai_generated else "Respuesta manual del analista."
        ticket.change_status(TicketStatus.RESOLVED, changed_by=actor.id, reason=reason)
        self._tickets.save(ticket)
        return ticket.pull_events()

    def escalate(self, command: EscalateTicketCommand) -> Ticket:
        """Escala un ticket ASSIGNED_L1 a un grupo especialista L2 con snapshot de contexto (US17, T79).

        Orden de validación (D30 §4.1):
        1. Ticket existe y pertenece al workspace del actor (404).
        2. Transición válida hacia ESCALATED_L2 (422).
        3. Permiso del actor para escalar (403).
        """
        actor = command.actor
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")

        state_machine.ensure_transition(ticket.status, TicketStatus.ESCALATED_L2)
        status_change_policy.authorize(actor, ticket, TicketStatus.ESCALATED_L2)

        triage = self._triage_context.for_ticket(ticket.id) if self._triage_context is not None else None
        snapshot = _format_escalation_snapshot(
            ticket=ticket,
            specialist_group=command.specialist_group,
            reason=command.reason,
            triage=triage,
        )
        ticket.escalate(
            escalated_by=actor.id,
            specialist_group=command.specialist_group,
            reason=command.reason,
            context_snapshot=snapshot,
            has_triage_snapshot=triage is not None,
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def return_to_l1(self, command: ReturnToL1Command) -> Ticket:
        """Devuelve un ticket ESCALATED_L2 al analista L1 original solicitando información (US17, T79).

        Orden de validación (D30 §4.2):
        1. Ticket existe y pertenece al workspace del actor (404).
        2. El ticket está en ESCALATED_L2 y admite transición a ASSIGNED_L1 (422).
        3. Guarda `ensure_can_work_escalated` (permiso + grupo; punto de extensión para reclamo en T82).
        4. El ticket conserva un assigned_analyst_id original (400 si falta por datos legados).
        """
        actor = command.actor
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")

        state_machine.ensure_transition(ticket.status, TicketStatus.ASSIGNED_L1)
        if ticket.status is not TicketStatus.ESCALATED_L2:
            raise InvalidTicketStateTransitionError(
                f"Solo se pueden devolver a Nivel 1 los tickets en estado ESCALATED_L2 (estado actual: {ticket.status.value})."
            )

        actor_group = self._users.specialist_group(actor.id) if self._users is not None else None
        status_change_policy.ensure_can_work_escalated(actor, ticket, actor_group)

        internal_note = _format_return_to_l1_note(ticket=ticket, requested_info=command.requested_info)
        ticket.return_to_l1(
            returned_by=actor.id,
            requested_info=command.requested_info,
            internal_note=internal_note,
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket
