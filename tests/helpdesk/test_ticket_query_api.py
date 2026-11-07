"""Pruebas de integración de los endpoints de consulta de tickets (T17, TS08). Requieren TEST_DATABASE_URL."""
import base64
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app.helpdesk.domain.enums import ImpactLevel, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import VisualEvidence
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from tests.conftest import FAKE_HASH

S = TicketStatus
BASE_TIME = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


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
        "other_analyst": _user(db_session, workspace.id, RoleName.ANALYST_L1, "Otra Analista"),
        "specialist": _user(db_session, workspace.id, RoleName.SPECIALIST_L2, "Especialista Demo"),
        "leader": _user(db_session, workspace.id, RoleName.IT_LEADER, "Líder Demo"),
        "other_collaborator": _user(db_session, workspace.id, RoleName.COLLABORATOR, "Otro Colaborador"),
    }
    return {
        "workspace": workspace,
        "users": users,
        "headers": {k: auth_headers(db_session, u) for k, u in users.items()},
    }


@pytest.fixture()
def make_ticket(db_session, people):
    repo = SqlAlchemyTicketRepository(db_session)
    counter = iter(range(1000))

    def _make(
        title="Incidente",
        *,
        status=S.OPEN,
        priority=TicketPriority.MEDIUM,
        reporter="collaborator",
        assigned=None,
        minutes=None,
        evidences=0,
    ) -> Ticket:
        ticket = Ticket.register(
            workspace_id=people["workspace"].id,
            reporter_id=people["users"][reporter].id,
            title=title,
            description="Descripción del incidente",
            impact_level=ImpactLevel.MEDIUM,
            evidences=[VisualEvidence(file_name=f"captura{i}.png", mime_type="image/png", content=_png()) for i in range(evidences)],
        )
        ticket.status = status
        ticket.priority = priority
        ticket.assigned_analyst_id = people["users"][assigned].id if assigned else None
        ticket.created_at = BASE_TIME + timedelta(minutes=next(counter) if minutes is None else minutes)
        return repo.save(ticket)

    return _make


# --- GET /tickets/queue ---------------------------------------------------------------------------------------

def test_my_queue_lists_only_my_active_tickets_by_priority(api_client, people, make_ticket):
    low = make_ticket("Impresora", status=S.ASSIGNED_L1, priority=TicketPriority.LOW, assigned="analyst")
    critical = make_ticket("ERP caído", status=S.ASSIGNED_L1, priority=TicketPriority.CRITICAL, assigned="analyst")
    high_old = make_ticket("VPN antigua", status=S.ESCALATED_L2, priority=TicketPriority.HIGH, assigned="analyst", minutes=-60)
    high_new = make_ticket("VPN nueva", status=S.REOPENED, priority=TicketPriority.HIGH, assigned="analyst")
    make_ticket("De otra analista", status=S.ASSIGNED_L1, assigned="other_analyst")
    make_ticket("Ya resuelto", status=S.RESOLVED, assigned="analyst")

    response = api_client.get("/api/v1/tickets/queue", headers=people["headers"]["analyst"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert [t["id"] for t in body["items"]] == [str(x.id) for x in (critical, high_old, high_new, low)]
    assert body["total"] == 4 and body["total_pages"] == 1


def test_unassigned_tab_shows_tickets_waiting_for_an_analyst(api_client, people, make_ticket):
    waiting = make_ticket("Sin responsable", status=S.PENDING_ASSIGNMENT)
    make_ticket("Asignado", status=S.ASSIGNED_L1, assigned="other_analyst")
    make_ticket("Recién creado", status=S.OPEN)

    body = api_client.get("/api/v1/tickets/queue?scope=unassigned", headers=people["headers"]["analyst"]).json()

    assert [t["id"] for t in body["items"]] == [str(waiting.id)]
    item = body["items"][0]
    assert item["code"] == waiting.code
    assert item["reporter_name"] == "Colaborador Demo" and item["assigned_analyst_name"] is None


def test_escalated_tab_is_the_specialist_queue(api_client, people, make_ticket):
    escalated = make_ticket("Escalado", status=S.ESCALATED_L2, assigned="analyst")
    make_ticket("En L1", status=S.ASSIGNED_L1, assigned="analyst")

    body = api_client.get("/api/v1/tickets/queue?scope=escalated", headers=people["headers"]["specialist"]).json()

    assert [t["id"] for t in body["items"]] == [str(escalated.id)]
    assert body["items"][0]["assigned_analyst_name"] == "Analista Demo"


def test_all_tab_excludes_resolved_and_closed(api_client, people, make_ticket):
    for status in S:
        make_ticket(status.value, status=status, assigned="analyst")
    body = api_client.get("/api/v1/tickets/queue?scope=all", headers=people["headers"]["analyst"]).json()
    assert {t["status"] for t in body["items"]} == {s.value for s in S} - {"RESOLVED", "CLOSED"}


def test_queue_filters_by_status_priority_and_search(api_client, people, make_ticket):
    target = make_ticket("Error 809 en la VPN", status=S.PENDING_ASSIGNMENT, priority=TicketPriority.HIGH)
    make_ticket("Error 809 en la VPN", status=S.PENDING_ASSIGNMENT, priority=TicketPriority.LOW)
    make_ticket("Impresora", status=S.PENDING_ASSIGNMENT, priority=TicketPriority.HIGH)
    headers = people["headers"]["analyst"]

    by_text = api_client.get("/api/v1/tickets/queue?scope=all&search=vpn&priority=HIGH", headers=headers).json()
    by_code = api_client.get(f"/api/v1/tickets/queue?scope=all&search={target.code}", headers=headers).json()
    other_tab = api_client.get("/api/v1/tickets/queue?scope=mine&status=PENDING_ASSIGNMENT", headers=headers).json()

    assert [t["id"] for t in by_text["items"]] == [str(target.id)]
    assert [t["id"] for t in by_code["items"]] == [str(target.id)]
    assert other_tab["items"] == [] and other_tab["total"] == 0


def test_search_treats_like_wildcards_as_text(api_client, people, make_ticket):
    make_ticket("Disco al 100%", status=S.PENDING_ASSIGNMENT)
    make_ticket("Disco lleno", status=S.PENDING_ASSIGNMENT)
    body = api_client.get("/api/v1/tickets/queue?scope=all&search=100%25", headers=people["headers"]["analyst"]).json()
    assert [t["title"] for t in body["items"]] == ["Disco al 100%"]


@pytest.mark.parametrize("who", ["collaborator", "leader"])
def test_queue_requires_tickets_manage(api_client, people, who):
    assert api_client.get("/api/v1/tickets/queue", headers=people["headers"][who]).status_code == 403


def test_queue_does_not_show_other_workspaces(api_client, db_session, people, make_ticket, auth_headers):
    make_ticket("Nuestro", status=S.PENDING_ASSIGNMENT)
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other)
    db_session.flush()
    outsider = _user(db_session, other.id, RoleName.ANALYST_L1, "Analista Externo")
    body = api_client.get("/api/v1/tickets/queue?scope=all", headers=auth_headers(db_session, outsider)).json()
    assert body["total"] == 0


# --- Paginación ---------------------------------------------------------------------------------------------

def test_pagination_returns_the_requested_page(api_client, people, make_ticket):
    for i in range(5):
        make_ticket(f"Ticket {i}", status=S.PENDING_ASSIGNMENT)
    body = api_client.get(
        "/api/v1/tickets/queue?scope=unassigned&page=2&size=2", headers=people["headers"]["analyst"]
    ).json()
    assert [t["title"] for t in body["items"]] == ["Ticket 2", "Ticket 3"]
    assert (body["page"], body["size"], body["total"], body["total_pages"]) == (2, 2, 5, 3)


@pytest.mark.parametrize("query", ["page=4&size=2", "page=0", "size=0", "size=101"])
def test_out_of_range_pagination_returns_400(api_client, people, make_ticket, query):
    for i in range(5):
        make_ticket(f"Ticket {i}", status=S.PENDING_ASSIGNMENT)
    response = api_client.get(f"/api/v1/tickets/queue?scope=unassigned&{query}", headers=people["headers"]["analyst"])
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"]


def test_empty_result_first_page_is_ok(api_client, people):
    body = api_client.get("/api/v1/tickets/my-history", headers=people["headers"]["collaborator"]).json()
    assert body == {"items": [], "page": 1, "size": 20, "total": 0, "total_pages": 0}


# --- GET /tickets/my-history ----------------------------------------------------------------------------------

def test_history_lists_only_my_tickets_newest_first(api_client, people, make_ticket):
    old = make_ticket("Primero", status=S.CLOSED, evidences=2)
    new = make_ticket("Segundo", status=S.OPEN)
    make_ticket("De otro", reporter="other_collaborator")

    body = api_client.get("/api/v1/tickets/my-history", headers=people["headers"]["collaborator"]).json()

    assert [t["id"] for t in body["items"]] == [str(new.id), str(old.id)]
    assert body["items"][1]["evidence_count"] == 2


def test_history_filters_by_status_and_search(api_client, people, make_ticket):
    make_ticket("VPN", status=S.CLOSED)
    target = make_ticket("VPN", status=S.OPEN)
    make_ticket("Correo", status=S.OPEN)
    body = api_client.get(
        "/api/v1/tickets/my-history?status=OPEN&search=vpn", headers=people["headers"]["collaborator"]
    ).json()
    assert [t["id"] for t in body["items"]] == [str(target.id)]


def test_history_requires_authentication(api_client):
    assert api_client.get("/api/v1/tickets/my-history").status_code == 401


# --- GET /tickets/{id} ----------------------------------------------------------------------------------------

def test_reporter_sees_the_detail_without_internal_notes(api_client, db_session, people, make_ticket):
    ticket = make_ticket("ERP", status=S.ASSIGNED_L1, assigned="analyst", evidences=1)
    ticket.add_comment(author_id=people["users"]["analyst"].id, content="Revisando permisos")
    ticket.add_comment(author_id=people["users"]["analyst"].id, content="Nota interna", is_internal_note=True)
    SqlAlchemyTicketRepository(db_session).save(ticket)

    body = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()

    assert body["code"] == ticket.code and body["description"] == "Descripción del incidente"
    assert body["reporter_name"] == "Colaborador Demo" and body["assigned_analyst_name"] == "Analista Demo"
    assert len(body["evidences"]) == 1
    assert [c["content"] for c in body["comments"]] == ["Revisando permisos"]
    assert body["comments"][0]["author_name"] == "Analista Demo"


def test_support_staff_also_see_internal_notes(api_client, db_session, people, make_ticket):
    ticket = make_ticket("ERP", status=S.ASSIGNED_L1, assigned="analyst")
    ticket.add_comment(author_id=people["users"]["analyst"].id, content="Nota interna", is_internal_note=True)
    SqlAlchemyTicketRepository(db_session).save(ticket)

    for who in ("analyst", "specialist"):
        body = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"][who]).json()
        assert [c["content"] for c in body["comments"]] == ["Nota interna"]


@pytest.mark.parametrize("who", ["other_collaborator", "leader"])
def test_ticket_of_another_collaborator_returns_403(api_client, people, make_ticket, who):
    ticket = make_ticket("Privado")
    response = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"][who])
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_ticket_returns_404(api_client, people):
    assert api_client.get(f"/api/v1/tickets/{uuid.uuid4()}", headers=people["headers"]["analyst"]).status_code == 404


def test_ticket_from_another_workspace_returns_404(api_client, db_session, people, make_ticket, auth_headers):
    ticket = make_ticket("Nuestro")
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other)
    db_session.flush()
    outsider = _user(db_session, other.id, RoleName.ANALYST_L1, "Analista Externo")
    response = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=auth_headers(db_session, outsider))
    assert response.status_code == 404


# --- GET /tickets/{id}/evidences/{evidence_id} ----------------------------------------------------------------

def test_evidence_is_returned_as_data_url(api_client, people, make_ticket):
    ticket = make_ticket("Con captura", evidences=1)
    evidence = ticket.evidences[0]
    body = api_client.get(
        f"/api/v1/tickets/{ticket.id}/evidences/{evidence.id}", headers=people["headers"]["collaborator"]
    ).json()
    prefix = "data:image/png;base64,"
    assert body["data_url"].startswith(prefix)
    assert base64.b64decode(body["data_url"][len(prefix):]) == evidence.content
    assert body["size_bytes"] == evidence.size_bytes


def test_evidence_follows_the_detail_access_rules(api_client, people, make_ticket):
    ticket = make_ticket("Con captura", evidences=1)
    url = f"/api/v1/tickets/{ticket.id}/evidences/{ticket.evidences[0].id}"
    assert api_client.get(url, headers=people["headers"]["other_collaborator"]).status_code == 403
    assert api_client.get(url, headers=people["headers"]["analyst"]).status_code == 200
    unknown = f"/api/v1/tickets/{ticket.id}/evidences/{uuid.uuid4()}"
    assert api_client.get(unknown, headers=people["headers"]["collaborator"]).status_code == 404
