"""Pruebas de integración de GET y POST /api/v1/tickets/{id}/messages (US26, T85). Requieren TEST_DATABASE_URL."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import MessagePosted
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.models import TicketCommentModel
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.shared.infrastructure.event_bus import event_bus
from tests.conftest import FAKE_HASH

S = TicketStatus
SECRET_TEXT = "Mi usuario de red es jperez.lima y la clave Secreta123"


def _user(db_session, workspace_id, role: RoleName, name: str) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(), workspace_id=workspace_id, full_name=name,
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=role, department="TI",
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
        "leader": _user(db_session, workspace.id, RoleName.IT_LEADER, "Líder Demo"),
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

    def _make(status=S.ASSIGNED_L1) -> Ticket:
        ticket = Ticket.register(
            workspace_id=people["workspace"].id,
            reporter_id=people["users"]["collaborator"].id,
            title="VPN caída",
            description="No conecta",
            impact_level=ImpactLevel.MEDIUM,
        )
        ticket.status = status
        ticket.assigned_analyst_id = people["users"]["analyst"].id
        return repo.save(ticket)

    return _make


def _url(ticket_id) -> str:
    return f"/api/v1/tickets/{ticket_id}/messages"


def _post(client, people, ticket, who, content="Hola", **extra):
    return client.post(_url(ticket.id), json={"content": content, **extra}, headers=people["headers"][who])


def _seed(db_session, ticket, author, content, *, internal=False, minutes=0):
    db_session.add(
        TicketCommentModel(
            ticket_id=ticket.id,
            author_id=author.id,
            content=content,
            is_internal_note=internal,
            created_at=datetime(2026, 11, 20, 13, 0, tzinfo=UTC) + timedelta(minutes=minutes),
        )
    )
    db_session.flush()


# --- POST ---------------------------------------------------------------------------------------------------

def test_collaborator_posts_message_on_own_ticket(api_client, people, make_ticket):
    ticket = make_ticket()
    response = _post(api_client, people, ticket, "collaborator", "  Solo falla con la VPN.  ")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content"] == "Solo falla con la VPN."
    assert body["from_reporter"] is True and body["is_internal_note"] is False and body["is_ai_generated"] is False
    assert body["author_name"] == "Colaborador Demo" and body["ticket_id"] == str(ticket.id)

    for who in ("collaborator", "analyst"):
        listing = api_client.get(_url(ticket.id), headers=people["headers"][who]).json()
        assert [m["id"] for m in listing["items"]] == [body["id"]]


def test_analyst_posts_message_and_collaborator_sees_it(api_client, people, make_ticket):
    ticket = make_ticket()
    response = _post(api_client, people, ticket, "analyst", "¿Ocurre fuera de la VPN?")

    assert response.status_code == 201, response.text
    assert response.json()["from_reporter"] is False
    items = api_client.get(_url(ticket.id), headers=people["headers"]["collaborator"]).json()["items"]
    assert [m["content"] for m in items] == ["¿Ocurre fuera de la VPN?"]


def test_any_support_member_can_write_even_if_not_assigned(api_client, people, make_ticket):
    ticket = make_ticket()
    assert _post(api_client, people, ticket, "specialist").status_code == 201


def test_message_is_stored_as_written_without_pii_masking(api_client, db_session, people, make_ticket):
    ticket = make_ticket()
    assert _post(api_client, people, ticket, "collaborator", SECRET_TEXT).status_code == 201
    stored = db_session.query(TicketCommentModel).filter_by(ticket_id=ticket.id).one()
    assert stored.content == SECRET_TEXT


def test_internal_note_is_hidden_from_collaborator_and_not_counted(api_client, people, make_ticket):
    ticket = make_ticket()
    _post(api_client, people, ticket, "collaborator", "Visible 1")
    note = _post(api_client, people, ticket, "analyst", "Nota para el equipo", is_internal_note=True)
    _post(api_client, people, ticket, "analyst", "Visible 2")
    assert note.status_code == 201 and note.json()["is_internal_note"] is True

    collab = api_client.get(_url(ticket.id), headers=people["headers"]["collaborator"]).json()
    assert [m["content"] for m in collab["items"]] == ["Visible 1", "Visible 2"]
    assert collab["total"] == 2
    paged = api_client.get(_url(ticket.id) + "?size=1&page=2", headers=people["headers"]["collaborator"]).json()
    assert paged["total"] == 2 and paged["total_pages"] == 2 and paged["items"][0]["content"] == "Visible 2"

    analyst = api_client.get(_url(ticket.id), headers=people["headers"]["analyst"]).json()
    assert analyst["total"] == 3 and analyst["items"][1]["is_internal_note"] is True

    detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()
    assert "Nota para el equipo" not in [c["content"] for c in detail["comments"]]


def test_collaborator_cannot_post_internal_note(api_client, db_session, people, make_ticket):
    ticket = make_ticket()
    response = _post(api_client, people, ticket, "collaborator", is_internal_note=True)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:tracehelp:problems:internal-note-not-allowed"
    assert db_session.query(TicketCommentModel).filter_by(ticket_id=ticket.id).count() == 0


def test_other_collaborator_gets_403_on_get_and_post(api_client, people, make_ticket):
    ticket = make_ticket()
    for response in (
        api_client.get(_url(ticket.id), headers=people["headers"]["other"]),
        _post(api_client, people, ticket, "other"),
    ):
        assert response.status_code == 403
        assert response.json()["type"] == "urn:tracehelp:problems:ticket-access-denied"


def test_it_leader_has_no_access_to_foreign_ticket_messages(api_client, people, make_ticket):
    ticket = make_ticket()
    assert api_client.get(_url(ticket.id), headers=people["headers"]["leader"]).status_code == 403
    assert _post(api_client, people, ticket, "leader").status_code == 403


def test_unknown_ticket_returns_404(api_client, people):
    missing = uuid.uuid4()
    assert api_client.get(_url(missing), headers=people["headers"]["analyst"]).status_code == 404
    response = api_client.post(_url(missing), json={"content": "Hola"}, headers=people["headers"]["analyst"])
    assert response.status_code == 404
    assert response.json()["type"] == "urn:tracehelp:problems:ticket-not-found"


@pytest.mark.parametrize("status", [S.RESOLVED, S.CLOSED])
@pytest.mark.parametrize("who", ["collaborator", "analyst"])
def test_resolved_or_closed_ticket_rejects_messages_with_409(api_client, db_session, people, make_ticket, status, who):
    ticket = make_ticket(status)
    response = _post(api_client, people, ticket, who)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:tracehelp:problems:ticket-closed"
    assert db_session.query(TicketCommentModel).filter_by(ticket_id=ticket.id).count() == 0


def test_analyst_cannot_post_internal_note_in_resolved_ticket(api_client, db_session, people, make_ticket):
    ticket = make_ticket(S.RESOLVED)
    response = _post(api_client, people, ticket, "analyst", "Nota tardía", is_internal_note=True)

    assert response.status_code == 409
    assert response.json()["type"] == "urn:tracehelp:problems:ticket-closed"
    assert db_session.query(TicketCommentModel).filter_by(ticket_id=ticket.id).count() == 0


@pytest.mark.parametrize("status", [S.RESOLVED, S.CLOSED])
def test_resolved_or_closed_ticket_can_still_be_read(api_client, people, make_ticket, status):
    ticket = make_ticket(status)
    assert api_client.get(_url(ticket.id), headers=people["headers"]["collaborator"]).status_code == 200


def test_reopening_resolved_ticket_allows_posting_messages_again(api_client, people, make_ticket):
    ticket = make_ticket(S.RESOLVED)
    blocked = _post(api_client, people, ticket, "collaborator", "Sigue fallando")
    assert blocked.status_code == 409
    assert blocked.json()["type"] == "urn:tracehelp:problems:ticket-closed"

    reopen = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "REOPENED", "reason": "El problema persiste"},
        headers=people["headers"]["collaborator"],
    )
    assert reopen.status_code == 200, reopen.text

    allowed = _post(api_client, people, ticket, "collaborator", "Adjunto nuevos detalles")
    assert allowed.status_code == 201, allowed.text
    detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()
    assert detail["status"] == "REOPENED"


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_empty_or_blank_message_returns_422(api_client, people, make_ticket, content):
    response = _post(api_client, people, make_ticket(), "collaborator", content)
    assert response.status_code == 422
    assert response.json()["type"] == "urn:tracehelp:problems:validation-error"
    assert response.json()["errors"][0]["field"] == "content"


def test_message_longer_than_2000_returns_422_and_2000_is_accepted(api_client, people, make_ticket):
    ticket = make_ticket()
    too_long = _post(api_client, people, ticket, "collaborator", "a" * 2001)
    assert too_long.status_code == 422
    error = too_long.json()["errors"][0]
    assert error["type"] == "string_too_long" and error["message"] == "no puede superar los 2000 caracteres"
    assert _post(api_client, people, ticket, "collaborator", "a" * 2000).status_code == 201


def test_unknown_field_and_non_boolean_flag_return_422(api_client, people, make_ticket):
    ticket = make_ticket()
    headers = people["headers"]["collaborator"]
    assert api_client.post(_url(ticket.id), json={"content": "x", "extra": 1}, headers=headers).status_code == 422
    assert api_client.post(_url(ticket.id), json={"content": "x", "is_internal_note": "quizá"}, headers=headers).status_code == 422


def test_requires_authentication(api_client, make_ticket):
    ticket = make_ticket()
    assert api_client.get(_url(ticket.id)).status_code == 401
    assert api_client.post(_url(ticket.id), json={"content": "x"}).status_code == 401


# --- GET ----------------------------------------------------------------------------------------------------

def test_messages_are_chronological_and_paginated(api_client, db_session, people, make_ticket):
    ticket = make_ticket()
    collaborator, analyst = people["users"]["collaborator"], people["users"]["analyst"]
    # Se insertan fuera de orden para comprobar que el orden sale de created_at
    _seed(db_session, ticket, analyst, "tercero", minutes=3)
    _seed(db_session, ticket, collaborator, "primero", minutes=1)
    _seed(db_session, ticket, analyst, "segundo", minutes=2)
    headers = people["headers"]["analyst"]

    body = api_client.get(_url(ticket.id), headers=headers).json()
    assert [m["content"] for m in body["items"]] == ["primero", "segundo", "tercero"]
    assert body["size"] == 50 and body["total"] == 3 and body["total_pages"] == 1
    assert [m["from_reporter"] for m in body["items"]] == [True, False, False]
    assert body["items"][0]["author_name"] == "Colaborador Demo"

    page2 = api_client.get(_url(ticket.id) + "?size=2&page=2", headers=headers).json()
    assert [m["content"] for m in page2["items"]] == ["tercero"] and page2["total_pages"] == 2


def test_empty_thread_returns_empty_page(api_client, people, make_ticket):
    body = api_client.get(_url(make_ticket().id), headers=people["headers"]["collaborator"]).json()
    assert body["items"] == [] and body["total"] == 0 and body["total_pages"] == 0


@pytest.mark.parametrize("query", ["page=0", "size=0", "size=101", "page=2"])
def test_invalid_pagination_returns_400(api_client, people, make_ticket, query):
    ticket = make_ticket()
    _post(api_client, people, ticket, "collaborator")
    response = api_client.get(f"{_url(ticket.id)}?{query}", headers=people["headers"]["collaborator"])
    assert response.status_code == 400
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-page-request"


def test_ticket_detail_keeps_returning_comments(api_client, people, make_ticket):
    ticket = make_ticket()
    _post(api_client, people, ticket, "analyst", "Visible")
    detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()
    assert [c["content"] for c in detail["comments"]] == ["Visible"]


# --- Evento y auditoría -------------------------------------------------------------------------------------

def test_message_posted_event_is_published_once_without_text(api_client, people, make_ticket):
    ticket = make_ticket()
    received = []
    event_bus.subscribe(MessagePosted, received.append)
    try:
        response = _post(api_client, people, ticket, "analyst", SECRET_TEXT, is_internal_note=True)
    finally:
        event_bus.unsubscribe(MessagePosted, received.append)

    assert response.status_code == 201
    assert len(received) == 1
    event = received[0]
    assert event.message_id == uuid.UUID(response.json()["id"])
    assert event.is_internal_note is True and event.author_is_reporter is False
    assert event.author_id == people["users"]["analyst"].id and event.reporter_id == people["users"]["collaborator"].id
    assert event.assigned_analyst_id == people["users"]["analyst"].id
    assert event.ticket_code == ticket.code and event.ticket_status == "ASSIGNED_L1"
    assert event.content_length == len(SECRET_TEXT)
    assert not hasattr(event, "content") and SECRET_TEXT not in repr(event.__dict__)


def test_audit_log_records_message_without_leaking_text(api_client, people, make_ticket):
    ticket = make_ticket()
    assert _post(api_client, people, ticket, "collaborator", SECRET_TEXT).status_code == 201

    audit = api_client.get(
        f"/api/v1/audit-log?ticket_id={ticket.id}&event_type=MessagePosted", headers=people["headers"]["leader"]
    )
    assert audit.status_code == 200, audit.text
    items = audit.json()["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["entity_type"] == "ticket_message"
    assert entry["actor_id"] == str(people["users"]["collaborator"].id)
    assert entry["detail"] == {
        "is_internal_note": False,
        "author_is_reporter": True,
        "ticket_status": "ASSIGNED_L1",
        "content_length": len(SECRET_TEXT),
    }
    assert "jperez" not in audit.text and "Secreta123" not in audit.text
