"""Pruebas de integración de disponibilidad del analista y asignación de tickets (US24, T47)."""
import uuid

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from tests.conftest import FAKE_HASH


def test_analyst_availability_and_ticket_assignment(api_client, db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    other_analyst = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Otra Analista",
        email=f"otra-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.ANALYST_L1,
        department="TI",
    )
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Líder Demo",
        email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    db_session.add_all([other_analyst, leader])
    db_session.flush()

    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="Falla Outlook",
        description="No sincroniza bandeja de entrada",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.status = TicketStatus.PENDING_ASSIGNMENT
    SqlAlchemyTicketRepository(db_session).save(ticket)
    db_session.flush()

    analyst_headers = auth_headers(db_session, analyst)
    other_headers = auth_headers(db_session, other_analyst)
    collab_headers = auth_headers(db_session, collaborator)
    leader_headers = auth_headers(db_session, leader)

    # Colaborador no puede cambiar disponibilidad (403)
    assert (
        api_client.patch(
            "/api/v1/analysts/me/availability",
            json={"availability_status": "UNAVAILABLE"},
            headers=collab_headers,
        ).status_code
        == 403
    )

    # Otra analista se marca como UNAVAILABLE
    resp = api_client.patch(
        "/api/v1/analysts/me/availability",
        json={"availability_status": "UNAVAILABLE"},
        headers=other_headers,
    )
    assert resp.status_code == 200 and resp.json()["availability_status"] == "UNAVAILABLE"

    # GET /analysts muestra estados de disponibilidad
    staff = api_client.get("/api/v1/analysts", headers=leader_headers).json()
    by_id = {u["id"]: u["availability_status"] for u in staff}
    assert by_id[str(analyst.id)] == "AVAILABLE"
    assert by_id[str(other_analyst.id)] == "UNAVAILABLE"

    # Intentar asignar el ticket a un analista UNAVAILABLE devuelve 422
    unavailable_assign = api_client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"analyst_id": str(other_analyst.id)},
        headers=leader_headers,
    )
    assert unavailable_assign.status_code == 422
    assert "UNAVAILABLE" in unavailable_assign.json()["detail"]

    # Asignar el ticket al analista AVAILABLE funciona y lo pasa a ASSIGNED_L1
    ok_assign = api_client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"analyst_id": str(analyst.id), "reason": "Asignado por líder"},
        headers=leader_headers,
    )
    assert ok_assign.status_code == 200, ok_assign.text
    body = ok_assign.json()
    assert body["status"] == "ASSIGNED_L1"
    assert body["assigned_analyst_id"] == str(analyst.id)

    # Colaborador no puede asignar tickets (403)
    assert api_client.post(f"/api/v1/tickets/{ticket.id}/assign", headers=collab_headers).status_code == 403
