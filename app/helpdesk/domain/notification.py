"""Entidad Notification, tipos y plantillas fijas del submódulo de notificaciones (US19, T91)."""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.helpdesk.domain.enums import TicketStatus


def _now() -> datetime:
    return datetime.now(UTC)


class NotificationType(StrEnum):
    TICKET_STATUS_CHANGED = "TICKET_STATUS_CHANGED"
    MESSAGE_POSTED = "MESSAGE_POSTED"
    ESCALATED_TICKET_RESOLVED = "ESCALATED_TICKET_RESOLVED"


# Etiquetas visibles de estado (mismas del badge del portal, US19 §2.2)
STATUS_LABELS: dict[str, str] = {
    TicketStatus.OPEN: "Registrado",
    TicketStatus.PENDING_ASSIGNMENT: "En espera de un analista",
    TicketStatus.SELF_SERVICE_PROPOSED: "Solución propuesta",
    TicketStatus.ASSIGNED_L1: "En atención",
    TicketStatus.ESCALATED_L2: "Derivado a un especialista",
    TicketStatus.RESOLVED: "Resuelto",
    TicketStatus.REOPENED: "Reabierto",
    TicketStatus.CLOSED: "Cerrado",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(str(status), str(status))


@dataclass
class Notification:
    """Notificación in-app sobre el avance o conversación de un ticket.

    El contenido se arma solo con plantillas fijas: nunca incluye el texto del mensaje, la descripción ni la solución (D22).
    """

    workspace_id: uuid.UUID
    recipient_id: uuid.UUID
    ticket_id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def ticket_code(self) -> str:
        return str(self.data.get("ticket_code") or "")

    def mark_as_read(self, now: datetime | None = None) -> None:
        """Marca la notificación como leída de forma idempotente, conservando el read_at original."""
        if self.read_at is None:
            self.read_at = now or _now()

    # ------------------------------------------------------------------ fábricas con plantillas fijas
    @classmethod
    def for_status_changed(
        cls,
        *,
        workspace_id: uuid.UUID,
        recipient_id: uuid.UUID,
        ticket_id: uuid.UUID,
        ticket_code: str,
        previous_status: str,
        new_status: str,
    ) -> "Notification":
        prev_label = status_label(previous_status)
        new_label = status_label(new_status)
        title = f"{ticket_code}: tu ticket está {new_label}"
        if new_status == TicketStatus.RESOLVED:
            body = f"Tu ticket {ticket_code} cambió de «{prev_label}» a «{new_label}». Revisa la solución y confírmala."
        else:
            body = f"Tu ticket {ticket_code} cambió de «{prev_label}» a «{new_label}»."
        return cls(
            workspace_id=workspace_id,
            recipient_id=recipient_id,
            ticket_id=ticket_id,
            type=NotificationType.TICKET_STATUS_CHANGED,
            title=title[:150],
            body=body[:500],
            data={
                "ticket_code": ticket_code,
                "previous_status": str(previous_status),
                "new_status": str(new_status),
            },
        )

    @classmethod
    def for_message_posted(
        cls,
        *,
        workspace_id: uuid.UUID,
        recipient_id: uuid.UUID,
        ticket_id: uuid.UUID,
        ticket_code: str,
        message_id: uuid.UUID,
        author_is_reporter: bool,
    ) -> "Notification":
        if not author_is_reporter:
            title = f"Tienes una nueva respuesta en {ticket_code}"
            body = f"El equipo de soporte publicó una nueva respuesta en tu ticket {ticket_code}."
        else:
            title = f"Nuevo mensaje del colaborador en {ticket_code}"
            body = f"El colaborador agregó un nuevo mensaje en el ticket {ticket_code}."
        return cls(
            workspace_id=workspace_id,
            recipient_id=recipient_id,
            ticket_id=ticket_id,
            type=NotificationType.MESSAGE_POSTED,
            title=title[:150],
            body=body[:500],
            data={
                "ticket_code": ticket_code,
                "message_id": str(message_id),
            },
        )

    @classmethod
    def for_escalated_resolved(
        cls,
        *,
        workspace_id: uuid.UUID,
        recipient_id: uuid.UUID,
        ticket_id: uuid.UUID,
        ticket_code: str,
        escalated_group: str | None = None,
    ) -> "Notification":
        resolved_label = status_label(TicketStatus.RESOLVED)
        title = f"{ticket_code}: tu ticket está {resolved_label}"
        body = f"Un especialista de soporte marcó tu ticket {ticket_code} como «{resolved_label}». Revisa la solución y confírmala."
        return cls(
            workspace_id=workspace_id,
            recipient_id=recipient_id,
            ticket_id=ticket_id,
            type=NotificationType.ESCALATED_TICKET_RESOLVED,
            title=title[:150],
            body=body[:500],
            data={
                "ticket_code": ticket_code,
                "escalated_group": escalated_group,
            },
        )


def render_email_subject(notification: Notification) -> str:
    return f"[TraceHelp] {notification.title}"


def render_email_body(notification: Notification, portal_base_url: str = "") -> str:
    lines = [notification.body]
    base = (portal_base_url or "").strip().rstrip("/")
    if base:
        lines.extend(["", f"Consulta tu ticket en: {base}"])
    lines.extend(["", "No respondas a este correo."])
    return "\n".join(lines)
