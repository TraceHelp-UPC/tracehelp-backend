"""Pruebas de integración de notificaciones y preferencias (US19, T91). Requieren TEST_DATABASE_URL."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import EscalatedTicketResolved, MessagePosted, TicketStatusChanged
from app.helpdesk.domain.notification import NotificationType
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.models import NotificationModel
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName, UserStatus
from app.iam.infrastructure.persistence.models import UserModel
from app.shared.infrastructure.event_bus import event_bus
from tests.conftest import FAKE_HASH

S = TicketStatus
SECRET_MESSAGE = "Clave secreta XYZ-98765 que nunca debe salir en la notificación ni en el correo"


def _user(db_session, workspace_id, role: RoleName, name: str, *, status=UserStatus.ACTIVE) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name=name,
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=role,
        department="TI",
        status=status,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def people(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    users = {
        "collaborator": collaborator,
        "analyst": analyst,
        "specialist": _user(db_session, workspace.id, RoleName.SPECIALIST_L2, "Especialista Demo"),
        "other": _user(db_session, workspace.id, RoleName.COLLABORATOR, "Otro Colaborador"),
    }
    return {
        "workspace": workspace,
        "users": users,
        "headers": {k: auth_headers(db_session, u) for k, u in users.items()},
    }


@pytest.fixture()
def make_ticket(db_session, people):
    repo = SqlAlchemyTicketRepository(db_session)

    def _make(status=S.ASSIGNED_L1, *, assigned_analyst=True) -> Ticket:
        ticket = Ticket.register(
            workspace_id=people["workspace"].id,
            reporter_id=people["users"]["collaborator"].id,
            title="VPN caída",
            description="No conecta al ERP",
            impact_level=ImpactLevel.MEDIUM,
        )
        ticket.status = status
        ticket.assigned_analyst_id = people["users"]["analyst"].id if assigned_analyst else None
        return repo.save(ticket)

    return _make


# --- Generación de notificaciones por eventos ---------------------------------------------------------------

def test_status_change_by_analyst_notifies_collaborator_inapp_and_email(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    resp = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "RESOLVED", "reason": "Se reinició el servicio VPN"},
        headers=people["headers"]["analyst"],
    )
    assert resp.status_code == 200, resp.text

    listing = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"])
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["unread_count"] == 1
    item = body["items"][0]
    assert item["type"] == NotificationType.TICKET_STATUS_CHANGED
    assert item["ticket_id"] == str(ticket.id)
    assert item["ticket_code"] == ticket.code
    assert item["read"] is False and item["read_at"] is None
    assert item["data"] == {
        "ticket_code": ticket.code,
        "previous_status": "ASSIGNED_L1",
        "new_status": "RESOLVED",
    }
    assert "Se reinició el servicio VPN" not in item["body"]

    assert len(fake_email_sender.sent) == 1
    sent = fake_email_sender.sent[0]
    assert sent.to == people["users"]["collaborator"].email
    assert f"[TraceHelp] {ticket.code}" in sent.subject
    assert "Resuelto" in sent.subject
    assert "No respondas a este correo." in sent.text_body


def test_own_status_change_by_collaborator_does_not_notify(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.RESOLVED)
    resp = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "CLOSED"},
        headers=people["headers"]["collaborator"],
    )
    assert resp.status_code == 200

    body = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert body["total"] == 0 and body["unread_count"] == 0
    assert fake_email_sender.sent == []


def test_internal_release_assigned_l1_to_pending_does_not_notify(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    resp = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "PENDING_ASSIGNMENT"},
        headers=people["headers"]["analyst"],
    )
    assert resp.status_code == 200

    body = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert body["total"] == 0
    assert fake_email_sender.sent == []


def test_escalated_l2_resolution_creates_single_notification_without_duplicate(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ESCALATED_L2)
    # Simula T82: el agregado emite ambos eventos en ESCALATED_L2 -> RESOLVED
    event_bus.publish(
        TicketStatusChanged(
            ticket_id=ticket.id,
            workspace_id=people["workspace"].id,
            reporter_id=people["users"]["collaborator"].id,
            previous_status=S.ESCALATED_L2,
            new_status=S.RESOLVED,
            changed_by=people["users"]["specialist"].id,
        )
    )
    event_bus.publish(
        EscalatedTicketResolved(
            ticket_id=ticket.id,
            workspace_id=people["workspace"].id,
            reporter_id=people["users"]["collaborator"].id,
            resolved_by=people["users"]["specialist"].id,
            escalated_group="INFRAESTRUCTURA",
        )
    )

    body = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert body["total"] == 1 and body["unread_count"] == 1
    item = body["items"][0]
    assert item["type"] == NotificationType.ESCALATED_TICKET_RESOLVED
    assert item["ticket_code"] == ticket.code
    assert item["data"] == {"ticket_code": ticket.code, "escalated_group": "INFRAESTRUCTURA"}
    assert len(fake_email_sender.sent) == 1


def test_message_posted_by_analyst_notifies_collaborator_without_message_text(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    resp = api_client.post(
        f"/api/v1/tickets/{ticket.id}/messages",
        json={"content": SECRET_MESSAGE},
        headers=people["headers"]["analyst"],
    )
    assert resp.status_code == 201

    collab_notifs = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert collab_notifs["total"] == 1
    item = collab_notifs["items"][0]
    assert item["type"] == NotificationType.MESSAGE_POSTED
    assert item["title"] == f"Tienes una nueva respuesta en {ticket.code}"
    assert SECRET_MESSAGE not in item["title"] and SECRET_MESSAGE not in item["body"]

    analyst_notifs = api_client.get("/api/v1/notifications", headers=people["headers"]["analyst"]).json()
    assert analyst_notifs["total"] == 0

    assert len(fake_email_sender.sent) == 1
    assert fake_email_sender.sent[0].to == people["users"]["collaborator"].email
    assert SECRET_MESSAGE not in fake_email_sender.sent[0].text_body


def test_internal_note_creates_no_notification_and_no_email(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    resp = api_client.post(
        f"/api/v1/tickets/{ticket.id}/messages",
        json={"content": "Nota interna solo para TI", "is_internal_note": True},
        headers=people["headers"]["analyst"],
    )
    assert resp.status_code == 201
    assert api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()["total"] == 0
    assert api_client.get("/api/v1/notifications", headers=people["headers"]["analyst"]).json()["total"] == 0
    assert fake_email_sender.sent == []


def test_message_posted_by_collaborator_notifies_only_assigned_analyst(api_client, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1, assigned_analyst=True)
    resp = api_client.post(
        f"/api/v1/tickets/{ticket.id}/messages",
        json={"content": "Ya probé reiniciar el equipo"},
        headers=people["headers"]["collaborator"],
    )
    assert resp.status_code == 201

    analyst_notifs = api_client.get("/api/v1/notifications", headers=people["headers"]["analyst"]).json()
    assert analyst_notifs["total"] == 1
    assert analyst_notifs["items"][0]["type"] == NotificationType.MESSAGE_POSTED

    collab_notifs = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert collab_notifs["total"] == 0
    assert len(fake_email_sender.sent) == 1
    assert fake_email_sender.sent[0].to == people["users"]["analyst"].email


def test_message_posted_by_collaborator_on_unassigned_or_unclaimed_escalated_notifies_nobody(
    api_client, fake_email_sender, people, make_ticket
):
    unassigned = make_ticket(S.PENDING_ASSIGNMENT, assigned_analyst=False)
    assert (
        api_client.post(
            f"/api/v1/tickets/{unassigned.id}/messages",
            json={"content": "Sigo esperando"},
            headers=people["headers"]["collaborator"],
        ).status_code
        == 201
    )
    escalated = make_ticket(S.ESCALATED_L2, assigned_analyst=True)
    assert (
        api_client.post(
            f"/api/v1/tickets/{escalated.id}/messages",
            json={"content": "Más detalles para L2"},
            headers=people["headers"]["collaborator"],
        ).status_code
        == 201
    )
    assert api_client.get("/api/v1/notifications", headers=people["headers"]["analyst"]).json()["total"] == 0
    assert api_client.get("/api/v1/notifications", headers=people["headers"]["specialist"]).json()["total"] == 0
    assert fake_email_sender.sent == []


def test_message_posted_on_escalated_with_assigned_specialist_id_notifies_specialist(
    api_client, fake_email_sender, people, make_ticket
):
    @dataclass(frozen=True, kw_only=True)
    class MessagePostedWithSpecialist(MessagePosted):
        assigned_specialist_id: uuid.UUID | None = None

    ticket = make_ticket(S.ESCALATED_L2, assigned_analyst=True)
    event_bus.publish(
        MessagePostedWithSpecialist(
            ticket_id=ticket.id,
            workspace_id=people["workspace"].id,
            message_id=uuid.uuid4(),
            ticket_code=ticket.code or "TK-0001",
            author_id=people["users"]["collaborator"].id,
            reporter_id=people["users"]["collaborator"].id,
            assigned_analyst_id=people["users"]["analyst"].id,
            assigned_specialist_id=people["users"]["specialist"].id,
            author_is_reporter=True,
            is_internal_note=False,
            ticket_status=S.ESCALATED_L2,
            content_length=15,
        )
    )
    spec_notifs = api_client.get("/api/v1/notifications", headers=people["headers"]["specialist"]).json()
    assert spec_notifs["total"] == 1
    assert len(fake_email_sender.sent) == 1
    assert fake_email_sender.sent[0].to == people["users"]["specialist"].email


# --- Preferencias de canales y destinatarios inactivos ------------------------------------------------------

def test_channel_preferences_are_respected_independently(api_client, fake_email_sender, people, make_ticket):
    collab_headers = people["headers"]["collaborator"]
    analyst_headers = people["headers"]["analyst"]

    # 1) notify_email=False, notify_inapp=True -> fila in-app y 0 correos
    pref = api_client.patch(
        "/api/v1/users/me/notification-preferences", json={"notify_email": False}, headers=collab_headers
    )
    assert pref.status_code == 200 and pref.json() == {"notify_inapp": True, "notify_email": False}

    t1 = make_ticket(S.ASSIGNED_L1)
    assert api_client.patch(f"/api/v1/tickets/{t1.id}/status", json={"status": "RESOLVED"}, headers=analyst_headers).status_code == 200
    assert api_client.get("/api/v1/notifications", headers=collab_headers).json()["total"] == 1
    assert fake_email_sender.sent == []

    # 2) notify_inapp=False, notify_email=True -> 0 filas nuevas y 1 correo
    pref = api_client.patch(
        "/api/v1/users/me/notification-preferences",
        json={"notify_inapp": False, "notify_email": True},
        headers=collab_headers,
    )
    assert pref.status_code == 200 and pref.json() == {"notify_inapp": False, "notify_email": True}

    t2 = make_ticket(S.ASSIGNED_L1)
    assert api_client.patch(f"/api/v1/tickets/{t2.id}/status", json={"status": "RESOLVED"}, headers=analyst_headers).status_code == 200
    assert api_client.get("/api/v1/notifications", headers=collab_headers).json()["total"] == 1  # sigue siendo solo t1
    assert len(fake_email_sender.sent) == 1

    # 3) ambos desactivados -> ni fila ni correo
    assert (
        api_client.patch(
            "/api/v1/users/me/notification-preferences",
            json={"notify_inapp": False, "notify_email": False},
            headers=collab_headers,
        ).status_code
        == 200
    )
    t3 = make_ticket(S.ASSIGNED_L1)
    assert api_client.patch(f"/api/v1/tickets/{t3.id}/status", json={"status": "RESOLVED"}, headers=analyst_headers).status_code == 200
    assert api_client.get("/api/v1/notifications", headers=collab_headers).json()["total"] == 1
    assert len(fake_email_sender.sent) == 1


def test_inactive_recipient_receives_no_notification_or_email(api_client, db_session, fake_email_sender, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    people["users"]["collaborator"].status = UserStatus.INACTIVE
    db_session.flush()

    resp = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "RESOLVED"},
        headers=people["headers"]["analyst"],
    )
    assert resp.status_code == 200
    rows = db_session.scalars(select(NotificationModel).where(NotificationModel.recipient_id == people["users"]["collaborator"].id)).all()
    assert rows == []
    assert fake_email_sender.sent == []


# --- Endpoints GET /notifications y PATCH /notifications/{id}/read ------------------------------------------

def test_notifications_pagination_filter_and_mark_read_idempotent(api_client, db_session, people, make_ticket):
    ticket = make_ticket(S.ASSIGNED_L1)
    collab = people["users"]["collaborator"]
    other = people["users"]["other"]
    base = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    n1 = NotificationModel(
        id=uuid.uuid4(),
        workspace_id=people["workspace"].id,
        recipient_id=collab.id,
        ticket_id=ticket.id,
        type=NotificationType.TICKET_STATUS_CHANGED.value,
        title="Notif 1",
        body="Body 1",
        data={"ticket_code": ticket.code},
        created_at=base,
    )
    n2 = NotificationModel(
        id=uuid.uuid4(),
        workspace_id=people["workspace"].id,
        recipient_id=collab.id,
        ticket_id=ticket.id,
        type=NotificationType.MESSAGE_POSTED.value,
        title="Notif 2",
        body="Body 2",
        data={"ticket_code": ticket.code},
        created_at=base + timedelta(minutes=1),
    )
    n3 = NotificationModel(
        id=uuid.uuid4(),
        workspace_id=people["workspace"].id,
        recipient_id=collab.id,
        ticket_id=ticket.id,
        type=NotificationType.TICKET_STATUS_CHANGED.value,
        title="Notif 3",
        body="Body 3",
        data={"ticket_code": ticket.code},
        read_at=base + timedelta(minutes=5),
        created_at=base + timedelta(minutes=2),
    )
    other_notif = NotificationModel(
        id=uuid.uuid4(),
        workspace_id=people["workspace"].id,
        recipient_id=other.id,
        ticket_id=ticket.id,
        type=NotificationType.MESSAGE_POSTED.value,
        title="Notif otro",
        body="Body otro",
        data={"ticket_code": ticket.code},
        created_at=base + timedelta(minutes=3),
    )
    db_session.add_all([n1, n2, n3, other_notif])
    db_session.flush()

    # Orden DESC + paginación + unread_count global
    page1 = api_client.get("/api/v1/notifications?size=2&page=1", headers=people["headers"]["collaborator"]).json()
    assert [i["title"] for i in page1["items"]] == ["Notif 3", "Notif 2"]
    assert page1["total"] == 3 and page1["total_pages"] == 2 and page1["unread_count"] == 2

    # Filtro unread_only=true
    unread = api_client.get("/api/v1/notifications?unread_only=true", headers=people["headers"]["collaborator"]).json()
    assert [i["title"] for i in unread["items"]] == ["Notif 2", "Notif 1"]
    assert unread["total"] == 2 and unread["unread_count"] == 2

    # Marcar como leída e idempotencia
    r1 = api_client.patch(f"/api/v1/notifications/{n2.id}/read", headers=people["headers"]["collaborator"])
    assert r1.status_code == 200
    assert r1.json()["read"] is True and r1.json()["read_at"] is not None
    first_read_at = r1.json()["read_at"]

    r2 = api_client.patch(f"/api/v1/notifications/{n2.id}/read", headers=people["headers"]["collaborator"])
    assert r2.status_code == 200 and r2.json()["read_at"] == first_read_at

    after = api_client.get("/api/v1/notifications", headers=people["headers"]["collaborator"]).json()
    assert after["unread_count"] == 1

    # Notificación de otro usuario -> 404 notification-not-found
    r_other = api_client.patch(f"/api/v1/notifications/{other_notif.id}/read", headers=people["headers"]["collaborator"])
    assert r_other.status_code == 404
    assert r_other.json()["type"] == "urn:tracehelp:problems:notification-not-found"

    # UUID inexistente -> 404
    r_missing = api_client.patch(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=people["headers"]["collaborator"])
    assert r_missing.status_code == 404
    assert r_missing.json()["type"] == "urn:tracehelp:problems:notification-not-found"

    # No-UUID -> 422
    r_bad_uuid = api_client.patch("/api/v1/notifications/no-es-uuid/read", headers=people["headers"]["collaborator"])
    assert r_bad_uuid.status_code == 422
    assert r_bad_uuid.json()["type"] == "urn:tracehelp:problems:validation-error"

    # Página fuera de rango -> 400 invalid-page-request
    r_bad_page = api_client.get("/api/v1/notifications?page=99", headers=people["headers"]["collaborator"])
    assert r_bad_page.status_code == 400
    assert r_bad_page.json()["type"] == "urn:tracehelp:problems:invalid-page-request"

    # Sin token -> 401
    assert api_client.get("/api/v1/notifications").status_code == 401
    assert api_client.patch(f"/api/v1/notifications/{n1.id}/read").status_code == 401


# --- Endpoints GET y PATCH /users/me/notification-preferences -----------------------------------------------

def test_notification_preferences_endpoints_validation_audit_and_inactive(api_client, db_session, people):
    headers = people["headers"]["collaborator"]

    # GET por defecto -> true / true
    r_get = api_client.get("/api/v1/users/me/notification-preferences", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json() == {"notify_inapp": True, "notify_email": True}

    # PATCH válido audita UserProfileUpdated con formato {"from", "to"}
    r_patch = api_client.patch("/api/v1/users/me/notification-preferences", json={"notify_email": False}, headers=headers)
    assert r_patch.status_code == 200
    assert r_patch.json() == {"notify_inapp": True, "notify_email": False}

    audit_rows = db_session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.event_type == "UserProfileUpdated",
            AuditLogModel.entity_id == people["users"]["collaborator"].id,
        )
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].detail == {"changes": {"notify_email": {"from": "true", "to": "false"}}}

    # PATCH idempotente sin cambios no crea nuevo evento en auditoría
    r_same = api_client.patch("/api/v1/users/me/notification-preferences", json={"notify_email": False}, headers=headers)
    assert r_same.status_code == 200
    audit_rows_after = db_session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.event_type == "UserProfileUpdated",
            AuditLogModel.entity_id == people["users"]["collaborator"].id,
        )
    ).all()
    assert len(audit_rows_after) == 1

    # Validaciones 422
    for payload in ({}, {"notify_email": "false"}, {"notify_email": 1}, {"notify_email": None}, {"extra": True}):
        r_err = api_client.patch("/api/v1/users/me/notification-preferences", json=payload, headers=headers)
        assert r_err.status_code == 422, f"Esperaba 422 para {payload}, obtuve {r_err.status_code}: {r_err.text}"
        assert r_err.json()["type"] == "urn:tracehelp:problems:validation-error"

    # Sin token -> 401
    assert api_client.get("/api/v1/users/me/notification-preferences").status_code == 401
    assert api_client.patch("/api/v1/users/me/notification-preferences", json={"notify_email": True}).status_code == 401

    # Usuario inactivo con token vigente -> 401
    people["users"]["collaborator"].status = UserStatus.INACTIVE
    db_session.flush()
    assert api_client.get("/api/v1/users/me/notification-preferences", headers=headers).status_code == 401
    assert api_client.patch("/api/v1/users/me/notification-preferences", json={"notify_email": True}, headers=headers).status_code == 401


def test_notifications_endpoints_documented_in_openapi(api_client):
    schema = api_client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/notifications" in paths
    assert "get" in paths["/api/v1/notifications"]
    assert "/api/v1/notifications/{notification_id}/read" in paths
    assert "patch" in paths["/api/v1/notifications/{notification_id}/read"]
    assert "/api/v1/users/me/notification-preferences" in paths
    assert "get" in paths["/api/v1/users/me/notification-preferences"]
    assert "patch" in paths["/api/v1/users/me/notification-preferences"]
    # Sin tags duplicados
    notif_tags = paths["/api/v1/notifications"]["get"]["tags"]
    assert len(notif_tags) == len(set(notif_tags))
