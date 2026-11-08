"""Pruebas unitarias y de integración de la clasificación en triaje y corrección manual (US27, T41, T42)."""
from app.helpdesk.domain.enums import TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.smart_triage.domain.diagnosis import DiagnosisDraft, SuggestedCategory, SuggestedPriority
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.smart_triage.test_automatic_triage import kb, triage  # noqa: F401
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator


def test_triage_applies_suggested_category_and_priority_to_ticket(triage):  # noqa: F811
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    draft = DiagnosisDraft(
        answerable=True,
        summary="Puertos bloqueados [F1].",
        steps=("Abre UDP 500 y 4500 [F1].",),
        cited_fragments=(1,),
        suggested_category=SuggestedCategory.NETWORK_VPN,
        suggested_priority=SuggestedPriority.HIGH,
    )
    service, _ = triage["build"](generator=FakeGenerator(draft))
    diagnosis = service.triage(ticket.id)

    assert diagnosis.suggested_category is SuggestedCategory.NETWORK_VPN
    assert diagnosis.suggested_priority is SuggestedPriority.HIGH

    triage["db"].expire_all()
    stored_ticket = SqlAlchemyTicketRepository(triage["db"]).find_by_id(ticket.id)
    assert stored_ticket.status is TicketStatus.PENDING_ASSIGNMENT
    assert stored_ticket.category is TicketCategory.NETWORK_VPN
    assert stored_ticket.priority is TicketPriority.HIGH

    stored_diag = SqlAlchemyTriageDiagnosisRepository(triage["db"]).find_by_ticket_id(ticket.id)
    assert stored_diag.suggested_category is SuggestedCategory.NETWORK_VPN
    assert stored_diag.suggested_priority is SuggestedPriority.HIGH


def test_analyst_corrects_classification_and_audits_change(api_client, db_session, workspace_and_users, auth_headers):
    from app.helpdesk.domain.enums import ImpactLevel
    from app.helpdesk.domain.ticket import Ticket
    from app.iam.domain.enums import RoleName
    from app.iam.infrastructure.persistence.models import UserModel
    from tests.conftest import FAKE_HASH
    import uuid

    workspace, collaborator, analyst = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Líder Demo",
        email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    db_session.add(leader)
    db_session.flush()

    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="Falla de red",
        description="No carga el portal interno",
        impact_level=ImpactLevel.LOW,
    )
    ticket.apply_triage_classification(
        suggested_category=TicketCategory.NETWORK_VPN,
        suggested_priority=TicketPriority.MEDIUM,
    )
    SqlAlchemyTicketRepository(db_session).save(ticket)
    db_session.flush()

    analyst_headers = auth_headers(db_session, analyst)
    collab_headers = auth_headers(db_session, collaborator)
    leader_headers = auth_headers(db_session, leader)

    # Colaborador no puede clasificar (403)
    assert (
        api_client.patch(
            f"/api/v1/tickets/{ticket.id}/classification",
            json={"category": "Software", "priority": "HIGH"},
            headers=collab_headers,
        ).status_code
        == 403
    )

    # Categoría fuera del catálogo cerrado devuelve 400
    assert (
        api_client.patch(
            f"/api/v1/tickets/{ticket.id}/classification",
            json={"category": "Inexistente"},
            headers=analyst_headers,
        ).status_code
        == 400
    )

    # Corrección válida por el analista
    response = api_client.patch(
        f"/api/v1/tickets/{ticket.id}/classification",
        json={"category": "Software", "priority": "CRITICAL", "reason": "Es caída del servidor de aplicaciones"},
        headers=analyst_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "Software" and body["priority"] == "CRITICAL"

    # Queda registrado en la bitácora de auditoría
    audit = api_client.get(
        f"/api/v1/audit-log?event_type=TicketClassificationCorrected&ticket_id={ticket.id}",
        headers=leader_headers,
    ).json()
    assert audit["total"] == 1
    detail = audit["items"][0]["detail"]
    assert detail["previous_category"] == "Red/VPN" and detail["new_category"] == "Software"
    assert detail["previous_priority"] == "MEDIUM" and detail["new_priority"] == "CRITICAL"
