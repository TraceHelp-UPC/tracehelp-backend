"""Pruebas de integración de GET /tickets/{id}/diagnosis y POST /triage/diagnoses/{id}/review (T39).

Requieren TEST_DATABASE_URL.
"""
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.conftest import FAKE_HASH
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate

ALL_ACTIONS = ["APPROVE", "EDIT_AND_APPROVE", "REJECT", "MANUAL_RESPONSE"]


@pytest.fixture()
def api(api_client, db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users

    def user(role, name):
        model = UserModel(
            id=uuid.uuid4(), workspace_id=workspace.id, full_name=name, email=f"{uuid.uuid4().hex[:8]}@demo.pe",
            password_hash=FAKE_HASH, role=role, department="TI",
        )
        db_session.add(model)
        db_session.flush()
        return model

    users = {
        "collaborator": collaborator,
        "analyst": analyst,
        "specialist": user(RoleName.SPECIALIST_L2, "Especialista Demo"),
        "leader": user(RoleName.IT_LEADER, "Líder Demo"),
        "other_collaborator": user(RoleName.COLLABORATOR, "Otro Colaborador"),
    }
    headers = {k: auth_headers(db_session, u) for k, u in users.items()}

    def setup(*, score=0.78, outcome=DiagnosisStatus.ANSWERED, ticket_status=TicketStatus.ASSIGNED_L1, with_diagnosis=True):
        ticket = Ticket.register(
            workspace_id=workspace.id, reporter_id=collaborator.id, title="VPN error 809",
            description="No conecta la VPN desde casa", impact_level=ImpactLevel.MEDIUM,
        )
        ticket.status = ticket_status
        ticket.assigned_analyst_id = analyst.id if ticket_status is not TicketStatus.PENDING_ASSIGNMENT else None
        SqlAlchemyTicketRepository(db_session).save(ticket)
        diagnosis = None
        if with_diagnosis:
            diagnosis = _diagnosis(evaluate(score), status=outcome)
            diagnosis.ticket_id, diagnosis.workspace_id = ticket.id, workspace.id
            diagnosis.pull_events()
            SqlAlchemyTriageDiagnosisRepository(db_session).save(diagnosis)
        db_session.commit()
        return ticket, diagnosis

    def get(ticket, who):
        return api_client.get(f"/api/v1/tickets/{ticket.id}/diagnosis", headers=headers[who])

    def review(diagnosis_id, who, **body):
        return api_client.post(f"/api/v1/triage/diagnoses/{diagnosis_id}/review", json=body, headers=headers[who])

    return {"setup": setup, "get": get, "review": review, "users": users, "db": db_session}


# --- GET /tickets/{id}/diagnosis -----------------------------------------------------------------------------

def test_support_staff_see_the_full_diagnosis(api):
    ticket, diagnosis = api["setup"]()
    response = api["get"](ticket, "analyst")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["diagnosis_id"], body["ticket_code"], body["ticket_status"]) == (str(diagnosis.id), ticket.code, "ASSIGNED_L1")
    assert body["review_status"] == "PENDING_REVIEW" and body["allowed_actions"] == ALL_ACTIONS
    assert body["confidence_level"] == "GROUNDED" and body["confidence_score"] == 0.78
    assert body["ai_answer"]["sources"][0] == {
        "reference": "F1", "citation": "guia-vpn.md, sección «Error 809», párr. 1",
        "document_title": "guia-vpn", "similarity": 0.78,
    }
    assert body["ocr"] == {"legible": True, "error_codes": ["Error 809"], "text": "VPN Error 809"}
    assert body["review"] is None and body["final_answer"] is None


def test_leader_sees_the_diagnosis_only_if_they_reported_it(api):
    ticket, _ = api["setup"]()
    assert api["get"](ticket, "leader").status_code == 403


def test_reporter_cannot_see_a_diagnosis_under_review(api):
    ticket, _ = api["setup"]()
    response = api["get"](ticket, "collaborator")
    assert response.status_code == 403 and "equipo de soporte" in response.json()["detail"]


def test_reporter_sees_a_self_service_proposal_without_internal_details(api):
    ticket, _ = api["setup"](score=0.91, ticket_status=TicketStatus.SELF_SERVICE_PROPOSED)
    body = api["get"](ticket, "collaborator").json()
    assert body["review_status"] == "SELF_SERVICE_PROPOSED" and body["allowed_actions"] == []
    assert body["ai_answer"]["steps"] and body["ai_answer"]["sources"][0]["similarity"] is None
    assert body["confidence_score"] is None and body["ocr"] is None and body["outcome"] is None


def test_other_collaborators_get_403(api):
    ticket, _ = api["setup"]()
    assert api["get"](ticket, "other_collaborator").status_code == 403


def test_ticket_still_in_triage_returns_404(api):
    ticket, _ = api["setup"](with_diagnosis=False)
    response = api["get"](ticket, "analyst")
    assert response.status_code == 404 and "triaje" in response.json()["detail"]


def test_unknown_ticket_returns_404(api):
    response = api["get"](type("T", (), {"id": uuid.uuid4()}), "analyst")
    assert response.status_code == 404


def test_without_ai_answer_only_manual_response_is_offered(api):
    ticket, _ = api["setup"](outcome=DiagnosisStatus.INSUFFICIENT_EVIDENCE)
    body = api["get"](ticket, "analyst").json()
    assert body["allowed_actions"] == ["MANUAL_RESPONSE"] and body["ai_answer"] is None


def test_specialists_also_get_the_review_actions(api):
    ticket, _ = api["setup"]()
    assert api["get"](ticket, "specialist").json()["allowed_actions"] == ALL_ACTIONS


# --- POST /triage/diagnoses/{id}/review --------------------------------------------------------------------

def test_approve_resolves_the_ticket(api):
    ticket, diagnosis = api["setup"]()
    response = api["review"](diagnosis.id, "analyst", decision="APPROVE")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticket_resolved"] is True
    d = body["diagnosis"]
    assert (d["review_status"], d["ticket_status"], d["allowed_actions"]) == ("APPROVED", "RESOLVED", [])
    assert d["final_answer"] == {"summary": "Puertos bloqueados [F1].", "steps": ["Reinicia el router [F1]."]}
    assert d["review"]["reviewer_name"] == "Analista Demo"


def test_edit_and_approve(api):
    ticket, diagnosis = api["setup"]()
    body = api["review"](
        diagnosis.id, "analyst", decision="EDIT_AND_APPROVE", summary="El router bloquea la VPN.", steps=["Reinicia el router."]
    ).json()
    assert body["diagnosis"]["review_status"] == "EDITED_AND_APPROVED"
    assert body["diagnosis"]["final_answer"]["summary"] == "El router bloquea la VPN."
    assert body["diagnosis"]["ai_answer"]["summary"] == "Puertos bloqueados [F1]."


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "EDIT_AND_APPROVE", "summary": "Resumen"},
        {"decision": "REJECT"},
        {"decision": "MANUAL_RESPONSE", "response": "corto"},
    ],
)
def test_missing_decision_data_returns_400(api, payload):
    _, diagnosis = api["setup"]()
    response = api["review"](diagnosis.id, "analyst", **payload)
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


def test_reject_keeps_the_ticket_open_and_allows_a_manual_response(api):
    ticket, diagnosis = api["setup"]()
    body = api["review"](diagnosis.id, "analyst", decision="REJECT", reason="El manual es de otra versión").json()
    assert body["ticket_resolved"] is False
    assert body["diagnosis"]["ticket_status"] == "ASSIGNED_L1"
    assert body["diagnosis"]["review"]["rejection_reason"] == "El manual es de otra versión"
    assert body["diagnosis"]["allowed_actions"] == ["MANUAL_RESPONSE"]

    body = api["review"](diagnosis.id, "analyst", decision="MANUAL_RESPONSE", response="Reinstalé tu perfil VPN; prueba de nuevo.").json()
    assert body["ticket_resolved"] is True and body["diagnosis"]["manual_response"].startswith("Reinstalé")


@pytest.mark.parametrize("who", ["collaborator", "leader"])
def test_roles_without_hitl_permission_get_403(api, who):
    _, diagnosis = api["setup"]()
    assert api["review"](diagnosis.id, who, decision="APPROVE").status_code == 403


def test_reviewing_twice_returns_409(api):
    _, diagnosis = api["setup"]()
    api["review"](diagnosis.id, "analyst", decision="APPROVE")
    response = api["review"](diagnosis.id, "specialist", decision="APPROVE")
    assert response.status_code == 409 and "ya fue revisado" in response.json()["detail"]


def test_self_service_proposals_return_409(api):
    _, diagnosis = api["setup"](score=0.91, ticket_status=TicketStatus.SELF_SERVICE_PROPOSED)
    assert api["review"](diagnosis.id, "analyst", decision="APPROVE").status_code == 409


def test_ticket_not_taken_returns_422_and_changes_nothing(api):
    ticket, diagnosis = api["setup"](ticket_status=TicketStatus.PENDING_ASSIGNMENT)
    response = api["review"](diagnosis.id, "analyst", decision="APPROVE")
    assert response.status_code == 422 and "Atender" in response.json()["detail"]
    assert api["get"](ticket, "analyst").json()["review_status"] == "PENDING_REVIEW"


def test_analyst_cannot_resolve_an_escalated_ticket(api):
    _, diagnosis = api["setup"](ticket_status=TicketStatus.ESCALATED_L2)
    assert api["review"](diagnosis.id, "analyst", decision="APPROVE").status_code == 403
    assert api["review"](diagnosis.id, "specialist", decision="APPROVE").status_code == 200


def test_unknown_diagnosis_returns_404(api):
    assert api["review"](uuid.uuid4(), "analyst", decision="APPROVE").status_code == 404


def test_unknown_decision_returns_422(api):
    _, diagnosis = api["setup"]()
    assert api["review"](diagnosis.id, "analyst", decision="ARCHIVAR").status_code == 422
