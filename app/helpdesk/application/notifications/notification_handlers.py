"""Manejadores de eventos de dominio para generar notificaciones in-app y por correo (US19, T91)."""
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.helpdesk.application.ports import EmailMessage, IEmailSender
from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.events import EscalatedTicketResolved, MessagePosted, TicketStatusChanged
from app.helpdesk.domain.notification import Notification, render_email_body, render_email_subject
from app.helpdesk.infrastructure.email import get_email_sender
from app.helpdesk.infrastructure.iam_user_directory import IamUserDirectory
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.helpdesk.infrastructure.persistence.notification_repository import SqlAlchemyNotificationRepository


def _format_ticket_code(ticket_number: int | None) -> str:
    return f"TK-{ticket_number:04d}" if ticket_number is not None else ""


class NotificationEventHandler:
    """Suscriptor de TicketStatusChanged, MessagePosted y EscalatedTicketResolved.

    Cada evento abre su propia sesión (mismo patrón que AuditEventHandler), guarda la notificación
    in-app si el canal está activo, hace commit y luego despacha el correo si notify_email está activo.
    Resuelve el IEmailSender dinámicamente en cada evento para facilitar la inyección en pruebas.
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
        email_sender_factory: Callable[[], IEmailSender] = get_email_sender,
        portal_base_url_provider: Callable[[], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._email_sender_factory = email_sender_factory
        self._portal_base_url_provider = portal_base_url_provider or (lambda: get_settings().portal_base_url)

    def on_ticket_status_changed(self, event: TicketStatusChanged) -> Notification | None:
        # Omitir acciones del propio colaborador (aceptar autoservicio, confirmar o reabrir)
        if event.changed_by == event.reporter_id:
            return None
        # Omitir ESCALATED_L2 -> RESOLVED: lo cubre EscalatedTicketResolved sin duplicar
        if event.previous_status == TicketStatus.ESCALATED_L2 and event.new_status == TicketStatus.RESOLVED:
            return None
        # Omitir ASSIGNED_L1 -> PENDING_ASSIGNMENT: liberación o reasignación interna (T73)
        if event.previous_status == TicketStatus.ASSIGNED_L1 and event.new_status == TicketStatus.PENDING_ASSIGNMENT:
            return None

        return self._deliver(
            recipient_id=event.reporter_id,
            workspace_id=event.workspace_id,
            build=lambda session: Notification.for_status_changed(
                workspace_id=event.workspace_id,
                recipient_id=event.reporter_id,
                ticket_id=event.ticket_id,
                ticket_code=self._read_ticket_code(session, event.ticket_id),
                previous_status=event.previous_status,
                new_status=event.new_status,
            ),
        )

    def on_message_posted(self, event: MessagePosted) -> Notification | None:
        if event.is_internal_note:
            return None

        if not event.author_is_reporter:
            recipient_id: uuid.UUID | None = event.reporter_id
        elif event.ticket_status == TicketStatus.ESCALATED_L2:
            # T82 agrega assigned_specialist_id al evento; hasta entonces es None (US19 §2.2)
            recipient_id = getattr(event, "assigned_specialist_id", None)
        else:
            recipient_id = event.assigned_analyst_id

        if recipient_id is None or recipient_id == event.author_id:
            return None

        return self._deliver(
            recipient_id=recipient_id,
            workspace_id=event.workspace_id,
            build=lambda session: Notification.for_message_posted(
                workspace_id=event.workspace_id,
                recipient_id=recipient_id,
                ticket_id=event.ticket_id,
                ticket_code=event.ticket_code or self._read_ticket_code(session, event.ticket_id),
                message_id=event.message_id,
                author_is_reporter=event.author_is_reporter,
            ),
        )

    def on_escalated_ticket_resolved(self, event: EscalatedTicketResolved) -> Notification | None:
        if event.resolved_by == event.reporter_id:
            return None

        return self._deliver(
            recipient_id=event.reporter_id,
            workspace_id=event.workspace_id,
            build=lambda session: Notification.for_escalated_resolved(
                workspace_id=event.workspace_id,
                recipient_id=event.reporter_id,
                ticket_id=event.ticket_id,
                ticket_code=self._read_ticket_code(session, event.ticket_id),
                escalated_group=event.escalated_group,
            ),
        )

    def _deliver(
        self,
        *,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
        build: Callable[[Session], Notification],
    ) -> Notification | None:
        notification: Notification | None = None
        email_to_send: EmailMessage | None = None

        with self._session_factory() as session:
            profile = IamUserDirectory(session).notification_profile(recipient_id)
            if profile is None or not profile.is_active or profile.workspace_id != workspace_id:
                return None
            if not profile.notify_inapp and not profile.notify_email:
                return None

            notification = build(session)
            if profile.notify_inapp:
                SqlAlchemyNotificationRepository(session).save(notification)
                session.commit()

            if profile.notify_email:
                email_to_send = EmailMessage(
                    to=profile.email,
                    subject=render_email_subject(notification),
                    text_body=render_email_body(notification, self._portal_base_url_provider()),
                )

        if email_to_send is not None:
            self._email_sender_factory().send(email_to_send)

        return notification

    @staticmethod
    def _read_ticket_code(session: Session, ticket_id: uuid.UUID) -> str:
        number = session.scalar(select(TicketModel.ticket_number).where(TicketModel.id == ticket_id))
        return _format_ticket_code(number)
