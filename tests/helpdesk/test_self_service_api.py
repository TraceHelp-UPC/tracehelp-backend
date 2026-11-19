"""Pruebas de integración de US12 / T76: autoservicio en GET /tickets/{id}, accept/reject y cierre D10.

Requieren TEST_DATABASE_URL.
"""
import contextlib
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.helpdesk.infrastructure.triage_routing import TriageRoutingHandler
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.automatic_triage_service import AutomaticTriageService
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.domain.triage_diagnosis import ReviewStatus
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.conftest import FAKE_HASH
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker
from tests.smart_triage.test_triage_analysis_service import FakeOcr
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate

S = TicketStatus

INTERNAL_KEYS = {
    "similarity",
    "similarity_threshold",
    "self_service_threshold",
    "model",
    "ocr",
    "outcome_reason",
    "suggested_category",
    "suggested_priority",
    "review_status",
    "chunk_id",
    "document_id",
}


def _user(db_session, workspace_id, role: RoleName, name: str) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name=name,
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=role,
        department="TI",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def env(api_client, db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()

    users = {
        "collaborator": collaborator,
        "analyst": analyst,
        "specialist": _user(db_session, workspace.id, RoleName.SPECIALIST_L2, "Especialista Demo"),
        "leader": _user(db_session, workspace.id, RoleName.IT_LEADER, "Líder Demo"),
        "other_collaborator": _user(db_session, workspace.id, RoleName.COLLABORATOR, "Otro Colaborador"),
        "foreign_user": _user(db_session, other_ws.id, RoleName.COLLABORATOR, "Ajeno Workspace"),
    }
    headers = {k: auth_headers(db_session, u) for k, u in users.items()}

    def setup(
        *,
        ticket_status: TicketStatus = S.SELF_SERVICE_PROPOSED,
        score: float = 0.89,
        outcome: DiagnosisStatus = DiagnosisStatus.ANSWERED,
        with_diagnosis: bool = True,
        review_status_override: ReviewStatus | None = None,
        summary_override: str | None = None,
        clear_steps: bool = False,
        clear_sources: bool = False,
    ):
        ticket = Ticket.register(
            workspace_id=workspace.id,
            reporter_id=collaborator.id,
            title="VPN error 809 al conectar desde casa",
            description="Al intentar conectar la VPN corporativa aparece error 809.",
            impact_level=ImpactLevel.MEDIUM,
        )
        ticket.pull_events()
        ticket.status = ticket_status
        if ticket_status in (S.PENDING_ASSIGNMENT, S.ASSIGNED_L1):
            ticket.current_tier = SupportTier.TIER_L1
        if ticket_status is S.ASSIGNED_L1:
            ticket.assigned_analyst_id = analyst.id
        SqlAlchemyTicketRepository(db_session).save(ticket)

        diagnosis = None
        if with_diagnosis:
            diagnosis = _diagnosis(evaluate(score), status=outcome)
            diagnosis.ticket_id = ticket.id
            diagnosis.workspace_id = workspace.id
            if review_status_override is not None:
                diagnosis.review_status = review_status_override
            if summary_override is not None:
                diagnosis.summary = summary_override
            if clear_steps:
                diagnosis.steps = ()
            if clear_sources:
                diagnosis.sources = ()
            diagnosis.pull_events()
            SqlAlchemyTriageDiagnosisRepository(db_session).save(diagnosis)
        db_session.commit()
        return ticket, diagnosis

    return {
        "client": api_client,
        "db": db_session,
        "workspace": workspace,
        "users": users,
        "headers": headers,
        "setup": setup,
    }


# --- Exposición de self_service_recommendation en GET /api/v1/tickets/{id} -----------------------------------


def test_get_ticket_detail_exposes_safe_self_service_recommendation_without_internal_fields(env):
    ticket, _ = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, score=0.89)

    response = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"])
    assert response.status_code == 200, response.text
    body = response.json()
    rec = body["self_service_recommendation"]
    assert rec is not None
    assert rec["summary"] == "Puertos bloqueados [F1]."
    assert rec["steps"] == ["Reinicia el router [F1]."]
    assert rec["match_percentage"] == 89
    assert rec["confidence_label"] == "Alta coincidencia"
    assert rec["sources"] == [
        {
            "reference": "F1",
            "document_title": "guia-vpn",
            "citation": "guia-vpn.md, sección «Error 809», párr. 1",
        }
    ]
    assert set(rec.keys()) == {"summary", "steps", "match_percentage", "confidence_label", "sources"}
    assert set(rec["sources"][0].keys()) == {"reference", "document_title", "citation"}
    assert INTERNAL_KEYS.isdisjoint(rec.keys())
    assert INTERNAL_KEYS.isdisjoint(rec["sources"][0].keys())


@pytest.mark.parametrize(
    "status",
    [S.OPEN, S.PENDING_ASSIGNMENT, S.ASSIGNED_L1, S.ESCALATED_L2, S.RESOLVED, S.CLOSED, S.REOPENED],
)
def test_get_ticket_detail_hides_recommendation_outside_self_service_proposed(env, status):
    ticket, _ = env["setup"](ticket_status=status, score=0.92)
    body = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"]).json()
    assert body["self_service_recommendation"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"score": 0.76, "review_status_override": ReviewStatus.PENDING_REVIEW},
        {"outcome": DiagnosisStatus.INSUFFICIENT_EVIDENCE},
        {"with_diagnosis": False},
        {"summary_override": "   "},
        {"clear_steps": True},
        {"clear_sources": True},
    ],
)
def test_get_ticket_detail_returns_null_when_diagnosis_not_eligible_for_self_service(env, kwargs):
    ticket, _ = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, **kwargs)
    body = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"]).json()
    assert body["self_service_recommendation"] is None


# --- Triaje completo: tres caminos (autoservicio / baja confianza / sin evidencia) ----------------------------


@pytest.mark.parametrize(
    ("score", "expected_status", "expect_recommendation"),
    [
        (0.89, S.SELF_SERVICE_PROPOSED, True),
        (0.75, S.PENDING_ASSIGNMENT, False),
        (0.45, S.PENDING_ASSIGNMENT, False),
    ],
)
def test_triage_three_paths_route_and_expose_self_service_correctly(
    env, score, expected_status, expect_recommendation
):
    db = env["db"]
    ticket, _ = env["setup"](ticket_status=S.OPEN, with_diagnosis=False)
    bus = InMemoryEventBus()
    bus.subscribe(
        TriageCompleted,
        TriageRoutingHandler(session_factory=lambda: contextlib.nullcontext(db), events=bus),
    )

    retrieval = EvidenceRetrievalService(
        retriever=FakeRetriever(score),
        masker=masker,
        events=bus,
        thresholds=GroundingThresholds(similarity=0.68, self_service=0.80),
    )
    service = AutomaticTriageService(
        session=db,
        tickets=HelpdeskTicketReader(db),
        diagnoses=SqlAlchemyTriageDiagnosisRepository(db),
        analysis=TriageAnalysisService(
            ocr=FakeOcr(),
            retrieval=retrieval,
            generation=DiagnosisGenerationService(generator=FakeGenerator(), masker=masker),
        ),
        masker=masker,
        events=bus,
    )
    service.triage(ticket.id)

    detail = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"])
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == expected_status.value
    if expect_recommendation:
        assert body["current_tier"] == "SELF_SERVICE"
        assert body["self_service_recommendation"] is not None
        assert body["self_service_recommendation"]["match_percentage"] == 89
        assert body["self_service_recommendation"]["sources"]
    else:
        assert body["current_tier"] == "TIER_L1"
        assert body["self_service_recommendation"] is None
        # Colaborador tampoco puede leer el diagnóstico interno en baja confianza / sin evidencia
        diag_res = env["client"].get(f"/api/v1/tickets/{ticket.id}/diagnosis", headers=env["headers"]["collaborator"])
        assert diag_res.status_code == 403


# --- POST /api/v1/tickets/{id}/self-service/accept -----------------------------------------------------------


def test_accept_self_service_resolves_ticket_records_history_and_audit_and_keeps_diagnosis_locked(env):
    ticket, diagnosis = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, score=0.90)

    response = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/accept",
        headers=env["headers"]["collaborator"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["current_tier"] == "SELF_SERVICE"
    assert body["resolved_at"] is not None

    # Detalle ya no expone self_service_recommendation
    detail = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"]).json()
    assert detail["self_service_recommendation"] is None

    # Historial permite derivar la tasa de deflexión (D10)
    history = env["client"].get(f"/api/v1/tickets/{ticket.id}/history", headers=env["headers"]["collaborator"]).json()
    assert any(
        h["previous_status"] == "SELF_SERVICE_PROPOSED" and h["new_status"] == "RESOLVED" for h in history["items"]
    )

    # El diagnóstico sigue en SELF_SERVICE_PROPOSED (el analista no puede revisarlo en HITL)
    stored = SqlAlchemyTriageDiagnosisRepository(env["db"]).find_by_id(diagnosis.id)
    assert stored is not None and stored.review_status is ReviewStatus.SELF_SERVICE_PROPOSED
    review = env["client"].post(
        f"/api/v1/triage/diagnoses/{diagnosis.id}/review",
        json={"decision": "APPROVE"},
        headers=env["headers"]["analyst"],
    )
    assert review.status_code == 409

    # Auditoría registra SelfServiceAccepted
    audit = env["client"].get(
        f"/api/v1/audit/logs?ticket_id={ticket.id}&event_type=SelfServiceAccepted",
        headers=env["headers"]["leader"],
    )
    assert audit.status_code == 200, audit.text
    items = audit.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_id"] == str(env["users"]["collaborator"].id)
    assert items[0]["entity_type"] == "ticket"
    assert items[0]["entity_id"] == str(ticket.id)
    assert items[0]["detail"] == {"outcome": "RESOLVED_BY_SELF_SERVICE"}


# --- POST /api/v1/tickets/{id}/self-service/reject + cierre hueco D10 ----------------------------------------


def test_reject_self_service_reopens_diagnosis_for_l1_hitl_review_and_masks_pii_in_audit(env):
    ticket, diagnosis = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, score=0.91)
    reason = "Seguí los pasos desde 10.0.0.15 para carlos@empresa.pe pero persiste el error 809."

    response = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/reject",
        json={"reason": reason},
        headers=env["headers"]["collaborator"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PENDING_ASSIGNMENT"
    assert body["current_tier"] == "TIER_L1"
    assert body["assigned_analyst_id"] is None

    # D10: el diagnóstico pasó a PENDING_REVIEW automáticamente (aun con triage_worker_enabled=False)
    stored = SqlAlchemyTriageDiagnosisRepository(env["db"]).find_by_id(diagnosis.id)
    assert stored is not None and stored.review_status is ReviewStatus.PENDING_REVIEW

    # El detalle del ticket ya no expone self_service_recommendation
    detail = env["client"].get(f"/api/v1/tickets/{ticket.id}", headers=env["headers"]["collaborator"]).json()
    assert detail["self_service_recommendation"] is None

    # Analista L1 toma el ticket y aprueba el diagnóstico en HITL (200, ya no 409!)
    assign = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={},
        headers=env["headers"]["analyst"],
    )
    assert assign.status_code == 200, assign.text

    diag_view = env["client"].get(f"/api/v1/tickets/{ticket.id}/diagnosis", headers=env["headers"]["analyst"])
    assert diag_view.status_code == 200
    assert diag_view.json()["review_status"] == "PENDING_REVIEW"
    assert "APPROVE" in diag_view.json()["allowed_actions"]

    review = env["client"].post(
        f"/api/v1/triage/diagnoses/{diagnosis.id}/review",
        json={"decision": "APPROVE"},
        headers=env["headers"]["analyst"],
    )
    assert review.status_code == 200, review.text
    assert review.json()["ticket_resolved"] is True
    assert review.json()["diagnosis"]["review_status"] == "APPROVED"

    # Auditoría registra SelfServiceRejected con PII anonimizado
    audit = env["client"].get(
        f"/api/v1/audit/logs?ticket_id={ticket.id}&event_type=SelfServiceRejected",
        headers=env["headers"]["leader"],
    )
    assert audit.status_code == 200, audit.text
    items = audit.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_id"] == str(env["users"]["collaborator"].id)
    assert items[0]["entity_type"] == "ticket"
    assert items[0]["detail"]["outcome"] == "DERIVED_TO_ANALYST"
    assert "carlos@empresa.pe" not in (items[0]["detail"]["reason"] or "")
    assert "10.0.0.15" not in (items[0]["detail"]["reason"] or "")


@pytest.mark.parametrize("payload", [None, {}, {"reason": None}, {"reason": "   "}])
def test_reject_self_service_accepts_missing_empty_or_blank_reason(env, payload):
    ticket, diagnosis = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, score=0.88)
    kwargs = {"json": payload} if payload is not None else {}

    response = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/reject",
        headers=env["headers"]["collaborator"],
        **kwargs,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PENDING_ASSIGNMENT"
    stored = SqlAlchemyTriageDiagnosisRepository(env["db"]).find_by_id(diagnosis.id)
    assert stored is not None and stored.review_status is ReviewStatus.PENDING_REVIEW


def test_patch_status_from_self_service_to_pending_assignment_also_reopens_diagnosis(env):
    ticket, diagnosis = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED, score=0.90)

    response = env["client"].patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "PENDING_ASSIGNMENT", "reason": "Prefiero hablar con un analista"},
        headers=env["headers"]["collaborator"],
    )
    assert response.status_code == 200, response.text
    stored = SqlAlchemyTriageDiagnosisRepository(env["db"]).find_by_id(diagnosis.id)
    assert stored is not None and stored.review_status is ReviewStatus.PENDING_REVIEW


# --- Control de acceso, aislamiento y validaciones -----------------------------------------------------------


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_self_service_endpoints_require_authentication(env, action):
    ticket, _ = env["setup"]()
    response = env["client"].post(f"/api/v1/tickets/{ticket.id}/self-service/{action}")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("action", ["accept", "reject"])
@pytest.mark.parametrize("who", ["analyst", "specialist", "leader", "other_collaborator"])
def test_only_reporter_can_accept_or_reject_self_service(env, action, who):
    # Incluso si el ticket NO está en SELF_SERVICE_PROPOSED, el orden de validación devuelve 403 antes de 422
    ticket, _ = env["setup"](ticket_status=S.PENDING_ASSIGNMENT)
    response = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/{action}",
        headers=env["headers"][who],
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:tracehelp:problems:ticket-status-change-forbidden"


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_unknown_or_foreign_workspace_ticket_returns_404(env, action):
    ticket, _ = env["setup"]()
    missing = env["client"].post(
        f"/api/v1/tickets/{uuid.uuid4()}/self-service/{action}",
        headers=env["headers"]["collaborator"],
    )
    assert missing.status_code == 404
    assert missing.json()["type"] == "urn:tracehelp:problems:ticket-not-found"

    foreign = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/{action}",
        headers=env["headers"]["foreign_user"],
    )
    assert foreign.status_code == 404
    assert foreign.json()["type"] == "urn:tracehelp:problems:ticket-not-found"


@pytest.mark.parametrize("action", ["accept", "reject"])
@pytest.mark.parametrize("status", [S.OPEN, S.PENDING_ASSIGNMENT, S.ASSIGNED_L1, S.RESOLVED, S.CLOSED])
def test_reporter_gets_422_outside_self_service_proposed(env, action, status):
    ticket, _ = env["setup"](ticket_status=status)
    response = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/{action}",
        headers=env["headers"]["collaborator"],
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-ticket-state-transition"


def test_reject_validates_reason_length_and_forbids_unknown_fields(env):
    ticket, _ = env["setup"](ticket_status=S.SELF_SERVICE_PROPOSED)
    headers = env["headers"]["collaborator"]

    too_long = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/reject",
        json={"reason": "a" * 501},
        headers=headers,
    )
    assert too_long.status_code == 422
    assert too_long.json()["type"] == "urn:tracehelp:problems:validation-error"
    assert too_long.json()["errors"][0]["field"] == "reason"

    unknown = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/reject",
        json={"reason": "ok", "extra": True},
        headers=headers,
    )
    assert unknown.status_code == 422
    assert unknown.json()["type"] == "urn:tracehelp:problems:validation-error"

    exact_limit = env["client"].post(
        f"/api/v1/tickets/{ticket.id}/self-service/reject",
        json={"reason": "a" * 500},
        headers=headers,
    )
    assert exact_limit.status_code == 200


def test_openapi_documents_self_service_endpoints_and_recommendation_field(env):
    spec = env["client"].get("/openapi.json").json()
    paths = spec["paths"]
    for suffix in ("accept", "reject"):
        op = paths[f"/api/v1/tickets/{{ticket_id}}/self-service/{suffix}"]["post"]
        assert {"200", "401", "403", "404", "422"} <= set(op["responses"])
    detail_schema = spec["components"]["schemas"]["TicketDetailResponse"]["properties"]
    assert "self_service_recommendation" in detail_schema
