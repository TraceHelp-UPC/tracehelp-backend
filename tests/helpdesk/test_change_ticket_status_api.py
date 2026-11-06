"""Pruebas de integración de PATCH /api/v1/tickets/{id}/status (T15, TS04). Requieren TEST_DATABASE_URL."""
import uuid

import pytest

from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.events import TicketStatusChanged
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.shared.infrastructure.event_bus import event_bus
from tests.conftest import FAKE_HASH

FORM = {"title": "No puedo ingresar al ERP", "description": "Error 0x80070005", "impact_level": "MEDIUM"}


def _url(ticket_id) -> str:
    return f"/api/v1/tickets/{ticket_id}/status"


def _user(db_session, workspace_id, role: RoleName) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(), workspace_id=workspace_id, full_name=f"{role.value} Demo",
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=role, department="TI",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def actors(db_session, workspace_and_users, auth_headers):
    """Encabezados de autorización por rol y un ticket recién registrado por el colaborador."""
    workspace, collaborator, analyst = workspace_and_users
    specialist = _user(db_session, workspace.id, RoleName.SPECIALIST_L2)
    leader = _user(db_session, workspace.id, RoleName.IT_LEADER)
    other_collaborator = _user(db_session, workspace.id, RoleName.COLLABORATOR)
    users = {
        "collaborator": collaborator, "analyst": analyst, "specialist": specialist,
        "leader": leader, "other_collaborator": other_collaborator,
    }
    return {name: (user, auth_headers(db_session, user)) for name, user in users.items()}


@pytest.fixture()
def ticket_id(api_client, actors):
    response = api_client.post("/api/v1/tickets", data=FORM, headers=actors["collaborator"][1])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _patch(api_client, actors, ticket_id, who, status, reason=None):
    body = {"status": status} | ({"reason": reason} if reason else {})
    return api_client.patch(_url(ticket_id), json=body, headers=actors[who][1])


def test_full_happy_path_until_closed(api_client, actors, ticket_id):
    steps = [
        ("analyst", "PENDING_ASSIGNMENT"),
        ("analyst", "ASSIGNED_L1"),
        ("analyst", "ESCALATED_L2"),
        ("specialist", "RESOLVED"),
        ("collaborator", "CLOSED"),
    ]
    for who, status in steps:
        response = _patch(api_client, actors, ticket_id, who, status)
        assert response.status_code == 200, f"{who} -> {status}: {response.text}"
        assert response.json()["status"] == status

    body = response.json()
    assert body["resolved_at"] is not None and body["closed_at"] is not None
    assert body["current_tier"] == "TIER_L2"
    history = body["status_history"]
    assert len(history) == 5
    assert [(h["previous_status"], h["new_status"]) for h in history] == [
        ("OPEN", "PENDING_ASSIGNMENT"),
        ("PENDING_ASSIGNMENT", "ASSIGNED_L1"),
        ("ASSIGNED_L1", "ESCALATED_L2"),
        ("ESCALATED_L2", "RESOLVED"),
        ("RESOLVED", "CLOSED"),
    ]


def test_taking_a_ticket_assigns_it_to_the_analyst(api_client, actors, ticket_id, db_session):
    _patch(api_client, actors, ticket_id, "analyst", "PENDING_ASSIGNMENT")
    response = _patch(api_client, actors, ticket_id, "analyst", "ASSIGNED_L1", reason="Lo tomo yo")

    assert response.status_code == 200
    assert response.json()["assigned_analyst_id"] == str(actors["analyst"][0].id)
    model = db_session.get(TicketModel, uuid.UUID(ticket_id))
    assert model.status is TicketStatus.ASSIGNED_L1


def test_reporter_can_reopen_a_resolved_ticket(api_client, actors, ticket_id):
    for status in ("PENDING_ASSIGNMENT", "ASSIGNED_L1", "RESOLVED"):
        _patch(api_client, actors, ticket_id, "analyst", status)
    response = _patch(api_client, actors, ticket_id, "collaborator", "REOPENED", reason="Volvió a fallar")
    assert response.status_code == 200
    assert response.json()["status"] == "REOPENED" and response.json()["resolved_at"] is None


def test_invalid_transition_returns_422(api_client, actors, ticket_id):
    response = _patch(api_client, actors, ticket_id, "analyst", "CLOSED")
    assert response.status_code == 422
    assert "OPEN" in response.json()["detail"]


def test_self_service_proposal_is_only_made_by_the_system(api_client, actors, ticket_id):
    response = _patch(api_client, actors, ticket_id, "analyst", "SELF_SERVICE_PROPOSED")
    assert response.status_code == 403


def test_collaborator_cannot_assign_tickets(api_client, actors, ticket_id):
    _patch(api_client, actors, ticket_id, "analyst", "PENDING_ASSIGNMENT")
    assert _patch(api_client, actors, ticket_id, "collaborator", "ASSIGNED_L1").status_code == 403


def test_specialist_cannot_escalate(api_client, actors, ticket_id):
    _patch(api_client, actors, ticket_id, "analyst", "PENDING_ASSIGNMENT")
    _patch(api_client, actors, ticket_id, "analyst", "ASSIGNED_L1")
    assert _patch(api_client, actors, ticket_id, "specialist", "ESCALATED_L2").status_code == 403


def test_analyst_cannot_resolve_an_escalated_ticket(api_client, actors, ticket_id):
    for status in ("PENDING_ASSIGNMENT", "ASSIGNED_L1", "ESCALATED_L2"):
        _patch(api_client, actors, ticket_id, "analyst", status)
    assert _patch(api_client, actors, ticket_id, "analyst", "RESOLVED").status_code == 403


def test_only_the_reporter_can_close(api_client, actors, ticket_id):
    for status in ("PENDING_ASSIGNMENT", "ASSIGNED_L1", "RESOLVED"):
        _patch(api_client, actors, ticket_id, "analyst", status)
    assert _patch(api_client, actors, ticket_id, "analyst", "CLOSED").status_code == 403


def test_other_collaborators_do_not_see_the_ticket(api_client, actors, ticket_id):
    assert _patch(api_client, actors, ticket_id, "other_collaborator", "PENDING_ASSIGNMENT").status_code == 404


def test_tickets_from_another_workspace_are_not_found(api_client, db_session, auth_headers, ticket_id):
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(workspace)
    db_session.flush()
    outsider = _user(db_session, workspace.id, RoleName.ANALYST_L1)
    response = api_client.patch(
        _url(ticket_id), json={"status": "PENDING_ASSIGNMENT"}, headers=auth_headers(db_session, outsider)
    )
    assert response.status_code == 404


def test_unknown_ticket_returns_404(api_client, actors):
    assert _patch(api_client, actors, uuid.uuid4(), "analyst", "PENDING_ASSIGNMENT").status_code == 404


def test_unknown_status_value_returns_422(api_client, actors, ticket_id):
    assert _patch(api_client, actors, ticket_id, "analyst", "EN_PROCESO").status_code == 422


def test_requires_authentication(api_client, ticket_id):
    assert api_client.patch(_url(ticket_id), json={"status": "PENDING_ASSIGNMENT"}).status_code == 401


def test_publishes_ticket_status_changed(api_client, actors, ticket_id):
    received = []
    event_bus.subscribe(TicketStatusChanged, received.append)
    try:
        response = _patch(api_client, actors, ticket_id, "analyst", "PENDING_ASSIGNMENT", reason="Triaje manual")
    finally:
        event_bus.unsubscribe(TicketStatusChanged, received.append)
    assert response.status_code == 200
    assert len(received) == 1
    event = received[0]
    assert (event.previous_status, event.new_status, event.reason) == ("OPEN", "PENDING_ASSIGNMENT", "Triaje manual")
    assert event.changed_by == actors["analyst"][0].id
