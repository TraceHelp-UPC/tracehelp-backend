"""Pruebas unitarias del submódulo de notificaciones, adaptadores de correo y preferencias IAM (US19, T91)."""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.helpdesk.application.ports import EmailMessage
from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.events import EscalatedTicketResolved
from app.helpdesk.domain.notification import (
    STATUS_LABELS,
    Notification,
    NotificationType,
    render_email_body,
    render_email_subject,
)
from app.helpdesk.infrastructure.email import (
    BackgroundEmailSender,
    LogEmailSender,
    SmtpEmailSender,
    build_email_sender,
    get_email_sender,
    mask_email,
    reset_email_sender,
    set_email_sender,
)
from app.iam.domain.enums import RoleName
from app.iam.domain.events import UserProfileUpdated
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash

FAKE_HASH = PasswordHash("$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm")


# --- Dominio: Notification & plantillas ---------------------------------------------------------------------

def test_status_labels_cover_all_ticket_statuses():
    for st in TicketStatus:
        assert st in STATUS_LABELS
        assert STATUS_LABELS[st]


def test_notification_for_status_changed_resolved_and_other():
    wid, uid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    resolved = Notification.for_status_changed(
        workspace_id=wid,
        recipient_id=uid,
        ticket_id=tid,
        ticket_code="TK-0042",
        previous_status=TicketStatus.ASSIGNED_L1,
        new_status=TicketStatus.RESOLVED,
    )
    assert resolved.type is NotificationType.TICKET_STATUS_CHANGED
    assert resolved.ticket_code == "TK-0042"
    assert resolved.title == "TK-0042: tu ticket está Resuelto"
    assert resolved.body == "Tu ticket TK-0042 cambió de «En atención» a «Resuelto». Revisa la solución y confírmala."
    assert resolved.data == {
        "ticket_code": "TK-0042",
        "previous_status": "ASSIGNED_L1",
        "new_status": "RESOLVED",
    }
    assert resolved.is_read is False

    in_progress = Notification.for_status_changed(
        workspace_id=wid,
        recipient_id=uid,
        ticket_id=tid,
        ticket_code="TK-0042",
        previous_status=TicketStatus.PENDING_ASSIGNMENT,
        new_status=TicketStatus.ASSIGNED_L1,
    )
    assert in_progress.title == "TK-0042: tu ticket está En atención"
    assert "Revisa la solución" not in in_progress.body


def test_notification_for_message_posted_templates():
    wid, uid, tid, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    from_support = Notification.for_message_posted(
        workspace_id=wid,
        recipient_id=uid,
        ticket_id=tid,
        ticket_code="TK-0042",
        message_id=mid,
        author_is_reporter=False,
    )
    assert from_support.type is NotificationType.MESSAGE_POSTED
    assert from_support.title == "Tienes una nueva respuesta en TK-0042"
    assert from_support.data == {"ticket_code": "TK-0042", "message_id": str(mid)}

    from_reporter = Notification.for_message_posted(
        workspace_id=wid,
        recipient_id=uid,
        ticket_id=tid,
        ticket_code="TK-0042",
        message_id=mid,
        author_is_reporter=True,
    )
    assert from_reporter.title == "Nuevo mensaje del colaborador en TK-0042"


def test_notification_for_escalated_resolved_and_event_signature():
    wid, uid, tid, spec_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event = EscalatedTicketResolved(
        ticket_id=tid,
        workspace_id=wid,
        reporter_id=uid,
        resolved_by=spec_id,
        escalated_group="INFRAESTRUCTURA",
    )
    assert event.escalated_group == "INFRAESTRUCTURA"
    notif = Notification.for_escalated_resolved(
        workspace_id=wid,
        recipient_id=uid,
        ticket_id=tid,
        ticket_code="TK-0099",
        escalated_group=event.escalated_group,
    )
    assert notif.type is NotificationType.ESCALATED_TICKET_RESOLVED
    assert notif.ticket_code == "TK-0099"
    assert notif.data == {"ticket_code": "TK-0099", "escalated_group": "INFRAESTRUCTURA"}
    assert "Resuelto" in notif.title


def test_notification_mark_as_read_is_idempotent():
    t1 = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    t2 = t1 + timedelta(minutes=10)
    notif = Notification.for_status_changed(
        workspace_id=uuid.uuid4(),
        recipient_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        ticket_code="TK-0001",
        previous_status=TicketStatus.OPEN,
        new_status=TicketStatus.PENDING_ASSIGNMENT,
    )
    notif.mark_as_read(now=t1)
    assert notif.is_read is True and notif.read_at == t1
    notif.mark_as_read(now=t2)
    assert notif.read_at == t1


def test_render_email_subject_and_body_with_and_without_portal_url():
    notif = Notification.for_status_changed(
        workspace_id=uuid.uuid4(),
        recipient_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        ticket_code="TK-0042",
        previous_status=TicketStatus.ASSIGNED_L1,
        new_status=TicketStatus.RESOLVED,
    )
    assert render_email_subject(notif) == "[TraceHelp] TK-0042: tu ticket está Resuelto"

    body_no_url = render_email_body(notif, "")
    assert notif.body in body_no_url
    assert "No respondas a este correo." in body_no_url
    assert "http" not in body_no_url

    body_with_url = render_email_body(notif, "https://portal.tracehelp.pe/")
    assert "https://portal.tracehelp.pe" in body_with_url
    assert "No respondas a este correo." in body_with_url


# --- Adaptadores de correo (D14) ----------------------------------------------------------------------------

def test_mask_email_hides_local_part():
    assert mask_email("carlos.mendoza@empresa.com") == "c***@empresa.com"
    assert mask_email("a@b.pe") == "a***@b.pe"
    assert mask_email("invalido") == "***"


def test_log_email_sender_masks_recipient_and_omits_body(caplog):
    sender = LogEmailSender()
    msg = EmailMessage(
        to="carlos.mendoza@empresa.com",
        subject="[TraceHelp] TK-0042: tu ticket está Resuelto",
        text_body="CUERPO_PRIVADO_QUE_NO_DEBE_APARECER_EN_LOGS",
    )
    with caplog.at_level(logging.INFO):
        sender.send(msg)
    assert "c***@empresa.com" in caplog.text
    assert "[TraceHelp] TK-0042: tu ticket está Resuelto" in caplog.text
    assert "carlos.mendoza@empresa.com" not in caplog.text
    assert "CUERPO_PRIVADO_QUE_NO_DEBE_APARECER_EN_LOGS" not in caplog.text


def test_smtp_email_sender_uses_tls_and_login():
    mock_server = MagicMock()
    mock_smtp_cm = MagicMock()
    mock_smtp_cm.__enter__.return_value = mock_server

    with patch("smtplib.SMTP", return_value=mock_smtp_cm) as smtp_cls:
        sender = SmtpEmailSender(
            host="smtp.example.com",
            port=587,
            from_address="TraceHelp <no-reply@example.com>",
            username="smtp-user",
            password="smtp-test-value",
            use_tls=True,
        )
        sender.send(EmailMessage(to="user@example.com", subject="Asunto", text_body="Cuerpo"))

    smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10.0)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("smtp-user", "smtp-test-value")
    mock_server.send_message.assert_called_once()
    sent_mime = mock_server.send_message.call_args[0][0]
    assert sent_mime["To"] == "user@example.com"
    assert sent_mime["Subject"] == "Asunto"


def test_background_email_sender_swallows_errors_and_logs_only_exception_class(caplog):
    class FailingSender:
        def send(self, message: EmailMessage) -> None:
            raise ConnectionRefusedError("secreto-smtp-que-no-debe-loguearse")

    bg = BackgroundEmailSender(FailingSender())
    try:
        with caplog.at_level(logging.WARNING):
            future = bg.submit(EmailMessage(to="a@b.pe", subject="S", text_body="B"))
            future.result(timeout=5)
        assert "ConnectionRefusedError" in caplog.text
        assert "secreto-smtp-que-no-debe-loguearse" not in caplog.text
    finally:
        bg.shutdown(wait=True)


def test_build_email_sender_factory_and_dynamic_override(caplog):
    assert isinstance(build_email_sender(Settings(email_backend="log")), LogEmailSender)
    assert isinstance(build_email_sender(Settings(email_backend="desconocido")), LogEmailSender)

    with caplog.at_level(logging.WARNING):
        fallback = build_email_sender(Settings(email_backend="smtp", smtp_host=""))
    assert isinstance(fallback, LogEmailSender)
    assert "SMTP_HOST" in caplog.text

    smtp_wrapped = build_email_sender(Settings(email_backend="smtp", smtp_host="smtp.example.com"))
    assert isinstance(smtp_wrapped, BackgroundEmailSender)
    smtp_wrapped.shutdown(wait=True)

    reset_email_sender()
    sentinel = LogEmailSender()
    set_email_sender(sentinel)
    assert get_email_sender() is sentinel
    reset_email_sender()
    assert get_email_sender() is not sentinel


# --- Dominio IAM: preferencias de notificación --------------------------------------------------------------

def test_user_update_notification_preferences_emits_profile_updated_only_on_change():
    user = User.register(
        workspace_id=uuid.uuid4(),
        full_name="Colaborador",
        email=EmailAddress("colab@demo.pe"),
        password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR,
        department="Ventas",
    )
    user.pull_events()  # limpiar UserRegistered

    # Sin cambios: no emite evento
    user.update_notification_preferences(notify_inapp=True, notify_email=True, changed_by=user.id)
    assert user.pull_events() == []

    # Cambio de email solamente
    user.update_notification_preferences(notify_email=False, changed_by=user.id)
    assert user.notify_email is False and user.notify_inapp is True
    events = user.pull_events()
    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, UserProfileUpdated)
    assert evt.user_id == user.id and evt.changed_by == user.id
    assert evt.changes == {"notify_email": {"from": "true", "to": "false"}}

    # Cambio de ambos
    user.update_notification_preferences(notify_inapp=False, notify_email=True, changed_by=user.id)
    evt2 = user.pull_events()[0]
    assert evt2.changes == {
        "notify_inapp": {"from": "true", "to": "false"},
        "notify_email": {"from": "false", "to": "true"},
    }
