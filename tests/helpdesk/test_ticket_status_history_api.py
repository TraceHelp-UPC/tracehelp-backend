"""Pruebas de integración del historial de cambios de estado del ticket (US14, T45)."""
import uuid

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from tests.conftest import FAKE_HASH


def test_status_history_records_transitions_in_chronological_order(
    api_client, db_session, workspace_and_users, auth_headers
):
    workspace, collaborator, analyst = workspace_and_users
    specialist = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Especialista Demo",
        email=f"esp-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.SPECIALIST_L2,
        department="TI",
    )
    other_collab = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Otro Colaborador",
        email=f"otro-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR,
        department="Ventas",
    )
    db_session.add_all([specialist, other_collab])
    db_session.flush()

    repo = SqlAlchemyTicketRepository(db_session)
    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="No conecta VPN",
        description="Error 809 al autenticar",
        impact_level=ImpactLevel.MEDIUM,
    )
    # Transición de sistema (triaje automático)
    ticket.change_status(TicketStatus.PENDING_ASSIGNMENT, changed_by=None, reason="Requiere validación de analista")
    repo.save(ticket)
    db_session.flush()

    analyst_headers = auth_headers(db_session, analyst)
    specialist_headers = auth_headers(db_session, specialist)
    collab_headers = auth_headers(db_session, collaborator)
    other_headers = auth_headers(db_session, other_collab)

    assert (
        api_client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "ASSIGNED_L1", "reason": "Tomo el ticket"},
            headers=analyst_headers,
        ).status_code
        == 200
    )
    assert (
        api_client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "ESCALATED_L2", "reason": "Escalo a redes L2"},
            headers=analyst_headers,
        ).status_code
        == 200
    )
    assert (
        api_client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "RESOLVED", "reason": "Regla de firewall aplicada"},
            headers=specialist_headers,
        ).status_code
        == 200
    )

    response = api_client.get(f"/api/v1/tickets/{ticket.id}/history", headers=collab_headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["previous_status"], i["new_status"], i["changed_by_name"]) for i in items] == [
        ("OPEN", "PENDING_ASSIGNMENT", "Sistema"),
        ("PENDING_ASSIGNMENT", "ASSIGNED_L1", "Analista Demo"),
        ("ASSIGNED_L1", "ESCALATED_L2", "Analista Demo"),
        ("ESCALATED_L2", "RESOLVED", "Especialista Demo"),
    ]

    # Otro colaborador recibe 403
    assert api_client.get(f"/api/v1/tickets/{ticket.id}/history", headers=other_headers).status_code == 403
    # Ticket inexistente devuelve 404
    assert api_client.get(f"/api/v1/tickets/{uuid.uuid4()}/history", headers=analyst_headers).status_code == 404
